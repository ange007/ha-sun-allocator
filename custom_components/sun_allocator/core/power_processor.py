"""Main power processing logic for Sun Allocator."""

import datetime as dt_stdlib
import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.template import Template
from homeassistant.const import (
    STATE_UNKNOWN,
    STATE_UNAVAILABLE,
)

# Local imports from the same 'core' directory
from .logger import log_debug, log_warning
from .schedule import is_device_in_schedule
from .settings import COUNTER_DEBOUNCE_FRACTION
from .device_restore import persist_grace_state, persist_manual_overrides, persist_on_time_state
from .timed_run import is_expired as is_timed_run_expired
from .probe import running_controllable_floor_w, battery_net_charge_w
from .constants_internal import SUPPORTED_DOMAINS
from .entity_control import (
    is_entity_on,
    turn_on_entity,
    turn_off_entity,
    set_power_for_entity,
    set_mode_for_entity,
    parse_relay_entity,
)

# Imports from the parent directory 'sun_allocator'
from ..const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_PRIORITY,
    CONF_DEVICE_MIN_ON_TIME,
    CONF_DEVICE_MIN_EXPECTED_W,
    CONF_DEVICE_MAX_EXPECTED_W,
    CONF_POWER_ALLOCATION,
    CONF_POWER_DISTRIBUTION,
    MAX_PERCENTAGE,
    DEFAULT_HYSTERESIS_W,
    SIGNAL_POWER_DISTRIBUTION_UPDATED,
    CONF_DEVICE_ENTITY,
    CONF_HYSTERESIS_W,
    CONF_DEVICE_DEBOUNCE_TIME,
    DEFAULT_DEBOUNCE_TIME,
    RELAY_MODE_ON,
    RELAY_MODE_OFF,
    RELAY_MODE_PROPORTIONAL,
    CONF_ESPHOME_MODE_SELECT_ENTITY,
    CONF_DEVICE_CONTROL_MODE,
    CONTROL_MODE_PROPORTIONAL,
    DOMAIN_CLIMATE,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_DEVICE_ALLOCATION_STRATEGY,
    STRATEGY_FILL_ONE_BY_ONE,
    STRATEGY_DISTRIBUTE_EVENLY,
    KEY_STARTUP_GRACE_PERIOD,
    DEFAULT_STARTUP_GRACE_PERIOD,
    CONF_BATTERY_SOC_SENSOR,
    CONF_BATTERY_PROTECTION_SOC,
    CONF_BATTERY_POWER,
    CONF_BATTERY_POWER_REVERSED,
    CONF_BATTERY_DISCHARGE_TOLERANCE_W,
    DEFAULT_BATTERY_DISCHARGE_TOLERANCE_W,
    CONF_DEVICE_STOP_BATTERY_SOC,
    DEFAULT_DEVICE_STOP_BATTERY_SOC,
    CONF_DEVICE_ACTUAL_POWER_SENSOR,
    CONF_DEVICE_ACTUAL_POWER_THRESHOLD_W,
    DEFAULT_ACTUAL_POWER_THRESHOLD_W,
    CONF_DEVICE_CHECK_USABLE_TEMPLATE,
    CONF_DEVICE_MAX_ON_TIME_PER_DAY,
    CONF_DEVICE_ALLOW_PROBE,
    DEFAULT_DEVICE_ALLOW_PROBE,
)
from ..sensor.utils import get_sensor_state_safely

def _initialize_run(entry_data, devices_config):
    """Initialize states for the processing run."""
    power_allocation = entry_data.get(CONF_POWER_ALLOCATION, {})
    for dev_id in power_allocation:
        power_allocation[dev_id] = 0

    entry_data.setdefault("device_status", {})
    entry_data["device_filter_reasons"] = {}

    # Drop leftover per-device state for devices no longer configured, so removed
    # devices don't leak entries (and stale state can't resurface if an id is reused).
    valid_ids = {d.get(CONF_DEVICE_ID) for d in devices_config}
    for _key in (
        "device_debounce_state", "device_on_time_state", "battery_soc_gate_state",
        "battery_stop_gate_state", "manual_overrides", "command_retries",
        "last_controlled_at",
    ):
        _d = entry_data.get(_key)
        if isinstance(_d, dict):
            for _stale in [k for k in _d if k not in valid_ids]:
                _d.pop(_stale, None)

    auto_control_devices = [
        d for d in devices_config if d.get(CONF_AUTO_CONTROL_ENABLED, False)
    ]
    auto_control_devices.sort(
        key=lambda d: int(d.get(CONF_DEVICE_PRIORITY, 50)), reverse=True
    )

    return auto_control_devices


def _read_battery_soc(hass, cfg) -> float | None:
    """Return current battery SOC % from the configured sensor, or None if unavailable.

    Genuine sensor death is surfaced by HA as ``unavailable``/``unknown`` (this
    inverter does so on comms loss) and handled below. A *stale* timestamp is NOT
    treated as unavailable: SOC sensors report only on value change, so a battery
    resting at a flat value (e.g. 100% all afternoon) legitimately freezes every
    timestamp for hours. Discarding that as "stale" would fail-safe-block every
    SOC-gated start exactly when the battery is fullest — so trust the last known
    numeric value instead.
    """
    soc_sensor = cfg.get(CONF_BATTERY_SOC_SENSOR)
    if not soc_sensor:
        return None
    state = hass.states.get(soc_sensor)
    if not state or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    try:
        return float(state.state)
    except (ValueError, TypeError):
        return None


# Battery-SOC gates live in their own module; re-exported for import back-compat.
from .battery_gates import (  # noqa: E402
    _apply_battery_soc_gate,
    decide_battery_soc_stop,
    _effective_stop_soc,
    _apply_battery_stop_floor,
)
# On-time accounting lives in its own module; re-exported for import back-compat
# (_accumulate_daily_on_time has no direct caller here but is part of the public
# surface — manual_switch / tests reference it via power_processor).
from .device_timing import (  # noqa: E402, F401
    _accumulate_daily_on_time,
    _close_on_time_session,
    _daily_on_time_sec,
)


def _apply_max_on_time_gate(
    device, device_id, is_active, prev_on, device_on_time_state, now, status_entry
) -> bool:
    """Block (and turn off) a device that has hit its daily on-time budget.

    ``max_on_time_per_day`` is in minutes; 0 disables the limit. Unlike the SOC
    gate this also forces a RUNNING device off once the budget is exhausted, mirroring
    schedule filtering. The accumulator resets at midnight.
    """
    max_minutes = float(device.get(CONF_DEVICE_MAX_ON_TIME_PER_DAY, 0) or 0)
    if max_minutes <= 0:
        return is_active
    on_sec = _daily_on_time_sec(device_on_time_state, device_id, now, currently_on=prev_on)
    if on_sec >= max_minutes * 60.0:
        status_entry["refusal_reasons"].append(
            f"Daily on-time limit reached: {on_sec / 60.0:.0f}min >= {max_minutes:.0f}min"
        )
        log_debug(
            f"[max_on_time] Blocking {device.get(CONF_DEVICE_NAME)}: "
            f"{on_sec / 60.0:.0f}min >= {max_minutes:.0f}min today"
        )
        if prev_on:
            # We force a running device off here, bypassing _apply_min_on_time's
            # turn-off branch — so close the session now, otherwise it would go
            # uncounted and the device could immediately restart.
            _close_on_time_session(device_on_time_state, device_id, now)
        return False
    return is_active


async def _filter_device(hass, device, now):
    """Filter out devices that are unavailable, unsupported, or outside of their schedule."""
    device_name = device.get(CONF_DEVICE_NAME)
    relay_entity, _ = parse_relay_entity(device.get(CONF_DEVICE_ENTITY))

    service_domain = (
        relay_entity.split(".")[0] if relay_entity and "." in relay_entity else None
    )

    if not relay_entity or service_domain not in SUPPORTED_DOMAINS:
        log_warning(f"Device '{device_name}' skipped: Unsupported or missing entity_id: {relay_entity}")
        return "Unsupported or missing entity_id"

    relay_state_obj = hass.states.get(relay_entity)
    if relay_state_obj is None or relay_state_obj.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        log_debug(f"Device '{device_name}' skipped: Entity {relay_entity} not found or unavailable.")
        return "Entity unavailable or not found"

    if not is_device_in_schedule(device, now, hass):
        log_debug(f"Device '{device_name}' skipped: Outside of schedule.")
        if is_entity_on(service_domain, relay_state_obj):
            await turn_off_entity(hass, relay_entity, device_name)
        return "Outside of schedule"

    usable_template = device.get(CONF_DEVICE_CHECK_USABLE_TEMPLATE)
    if usable_template:
        try:
            usable = Template(usable_template, hass).async_render(parse_result=True)
        except TemplateError as exc:
            # Broken template → fail-open (don't block a device over a typo), but warn.
            log_warning(
                f"Device '{device_name}': check_usable template error, treating as "
                f"usable: {exc}"
            )
            usable = True
        if not usable:
            log_debug(f"Device '{device_name}' skipped: check_usable template is falsy.")
            if is_entity_on(service_domain, relay_state_obj):
                await turn_off_entity(hass, relay_entity, device_name)
            return "Not usable (template)"

    return None


def _calculate_device_state(
    device, excess_power, device_on_state, device_debounce_state, cfg, now
):
    """Calculate the desired state (on/off) for a device based on power, hysteresis, and debounce."""
    device_id = device.get(CONF_DEVICE_ID)
    device_name = device.get(CONF_DEVICE_NAME)

    min_expected_w = float(device.get(CONF_DEVICE_MIN_EXPECTED_W, 0) or 0)
    hysteresis_w = float(cfg.get(CONF_HYSTERESIS_W, DEFAULT_HYSTERESIS_W))

    on_threshold = min_expected_w
    off_threshold = max(0.0, min_expected_w - hysteresis_w)

    prev_on = bool(device_on_state.get(device_id, False))
    is_active_candidate = excess_power >= (off_threshold if prev_on else on_threshold)

    log_debug(f"Device {device_name}: excess_power={excess_power}, on_threshold={on_threshold}, off_threshold={off_threshold}, prev_on={prev_on}, is_active_candidate={is_active_candidate}")

    debounce_time_s = device.get(CONF_DEVICE_DEBOUNCE_TIME, DEFAULT_DEBOUNCE_TIME)

    if device_id not in device_debounce_state:
        log_debug(f"Device {device_name}: Initializing new debounce state")
        device_debounce_state[device_id] = {"candidate_state": None, "state_change_time": None, "counter_debounce_start": None}

    debounce_info = device_debounce_state[device_id]
    log_debug(f"Device {device_name}: Current debounce info: {debounce_info}")

    if debounce_time_s == 0:
        is_active = is_active_candidate
        device_on_state[device_id] = is_active
        log_debug(f"Device {device_name}: No debounce needed, setting state to {is_active}")
    else:
        is_active = prev_on

        if debounce_info["state_change_time"] is None:
            # No debounce active
            if is_active_candidate != prev_on:
                log_debug(f"Device {device_name}: Starting debounce timer {prev_on} -> {is_active_candidate}")
                debounce_info["candidate_state"] = is_active_candidate
                debounce_info["state_change_time"] = now
                debounce_info["counter_debounce_start"] = None
                device_debounce_state[device_id] = debounce_info
            device_on_state[device_id] = prev_on
        else:
            # Debounce is active
            debounce_elapsed = (now - debounce_info["state_change_time"]).total_seconds()

            if is_active_candidate == prev_on:
                # Signal reverted to original state — use counter-debounce to avoid
                # cancelling on brief power fluctuations (e.g., kettle cycling)
                if debounce_info.get("counter_debounce_start") is None:
                    log_debug(f"Device {device_name}: Signal reversed, starting counter-debounce")
                    debounce_info["counter_debounce_start"] = now
                else:
                    counter_elapsed = (now - debounce_info["counter_debounce_start"]).total_seconds()
                    log_debug(f"Device {device_name}: Counter-debounce elapsed={counter_elapsed:.1f}s / {debounce_time_s * COUNTER_DEBOUNCE_FRACTION:.1f}s")
                    if counter_elapsed >= debounce_time_s * COUNTER_DEBOUNCE_FRACTION:
                        log_debug(f"Device {device_name}: Cancelling debounce — sustained reversal for {counter_elapsed:.1f}s")
                        debounce_info["state_change_time"] = None
                        debounce_info["counter_debounce_start"] = None
                        device_debounce_state[device_id] = debounce_info
                device_on_state[device_id] = prev_on
            else:
                # Candidate still pointing toward debounce target — reset counter-debounce
                debounce_info["counter_debounce_start"] = None
                log_debug(f"Device {device_name}: debounce elapsed={debounce_elapsed:.1f}s / {debounce_time_s}s, candidate={debounce_info['candidate_state']} vs target={is_active_candidate}")

                if debounce_elapsed >= debounce_time_s:
                    is_active = is_active_candidate
                    device_on_state[device_id] = is_active
                    debounce_info["state_change_time"] = None
                    debounce_info["counter_debounce_start"] = None
                    device_debounce_state[device_id] = debounce_info
                    log_debug(f"Device {device_name}: Debounce complete: {prev_on} -> {is_active}")
                else:
                    log_debug(f"Device {device_name}: Still debouncing ({debounce_elapsed:.1f}s < {debounce_time_s}s)")
                    device_on_state[device_id] = prev_on

    log_debug(f"Device {device_name}: final decision: active={is_active}, candidate={is_active_candidate}")
    return is_active, is_active_candidate


def _is_proportional(device) -> bool:
    """True when the device is driven proportionally (dimmer or ESPHome Proportional)."""
    return device.get(CONF_DEVICE_CONTROL_MODE) == CONTROL_MODE_PROPORTIONAL


def _initialize_status_entry(hass, device):
    """Initialize the status dictionary for a device."""
    min_expected_w = float(device.get(CONF_DEVICE_MIN_EXPECTED_W, 0) or 0)
    max_expected_w = float(device.get(CONF_DEVICE_MAX_EXPECTED_W, 0) or 0)
    if max_expected_w <= min_expected_w:
        max_expected_w = min_expected_w * 1.1

    # Proportional devices (native dimmer or ESPHome) flow through the proportional
    # allocator; on/off devices have no relay "mode". The live ESPHome select state
    # is not read here — SunAllocator drives the select itself per control_mode.
    mode = RELAY_MODE_PROPORTIONAL if _is_proportional(device) else None

    return {
        "name": device.get(CONF_DEVICE_NAME),
        "priority": int(device.get(CONF_DEVICE_PRIORITY, 50)),
        "entity_id": device.get(CONF_DEVICE_ENTITY),
        "mode_entity_id": device.get(CONF_ESPHOME_MODE_SELECT_ENTITY),
        "mode": mode,
        "percent_target": 0.0,
        "percent_actual": 0.0,
        "allocated_w": 0.0,
        CONF_DEVICE_MIN_EXPECTED_W: min_expected_w,
        CONF_DEVICE_MAX_EXPECTED_W: max_expected_w,
        CONF_DEVICE_MIN_ON_TIME: float(device.get(CONF_DEVICE_MIN_ON_TIME, 0) or 0),
        "allow_probe": bool(device.get(CONF_DEVICE_ALLOW_PROBE, DEFAULT_DEVICE_ALLOW_PROBE)),
        "refusal_reasons": [],
    }


def _startup_reserve_active(device_on_time_state, device_id, now) -> bool:
    """True while a just-turned-on device is still inside its startup-grace window.

    During this window a low actual-power reading is not yet trustworthy (the load
    hasn't ramped up), so we hold the declared budget instead of freeing it.
    """
    if now is None:
        return False
    startup_until = device_on_time_state.get(device_id, {}).get("startup_until")
    return startup_until is not None and now < startup_until


def _resolve_standard_power_used(
    hass, device, status_entry, device_on_time_state, device_id, now, device_sensor_cache,
) -> float:
    """Determine accounting power for an ON standard device.

    Without an actual-power sensor: use ``min_expected_w`` (the original behaviour).
    With one:
      - reading >= threshold  → trust it (measured consumption)
      - reading < threshold during startup grace → reserve ``min_expected_w``
        (load not ramped yet; avoid handing its budget to the next device)
      - reading < threshold after grace → genuinely idle: free the budget (0 W)
        and flag ``is_idle`` so the status sensor can report it.
    """
    min_expected_w = float(status_entry["min_expected_w"])
    actual_sensor = device.get(CONF_DEVICE_ACTUAL_POWER_SENSOR)
    if not actual_sensor:
        status_entry.pop("is_idle", None)
        return min_expected_w

    threshold = float(
        device.get(CONF_DEVICE_ACTUAL_POWER_THRESHOLD_W) or DEFAULT_ACTUAL_POWER_THRESHOLD_W
    )
    if device_sensor_cache and actual_sensor in device_sensor_cache:
        actual_w, ok = device_sensor_cache[actual_sensor]
    else:
        actual_w, ok = get_sensor_state_safely(hass, actual_sensor, "Actual Power")

    if not ok:
        # Sensor unavailable — fall back to the declared estimate, no idle claim.
        status_entry.pop("is_idle", None)
        return min_expected_w

    if actual_w >= threshold:
        status_entry["is_idle"] = False
        return actual_w

    if _startup_reserve_active(device_on_time_state, device_id, now):
        status_entry["is_idle"] = False
        status_entry["reserved_w"] = min_expected_w
        return min_expected_w

    # Confirmed drawing below threshold after startup — genuinely idle.
    status_entry["is_idle"] = True
    return 0.0


async def _control_standard_device(
    hass, device, is_active, prev_on, remaining_power, cfg, status_entry, device_on_state,
    device_sensor_cache=None, device_on_time_state=None, now=None, entry_data=None,
):
    """Control logic for a standard (on/off) device (also used for climate).

    Owns the ON-command retry policy: the first command on a fresh ON decision goes
    out immediately; while the relay stays OFF (unresponsive) we re-send at most once
    per ``COMMAND_RETRY_INTERVAL_SECONDS`` and never permanently give up. After
    ``UNREACHABLE_AFTER_RETRIES`` unanswered re-sends the device is surfaced as
    ``unreachable`` (suppressed for climate, whose OFF is usually a satisfied thermostat).
    """
    power_used = 0.0
    relay_entity, hvac_mode = parse_relay_entity(device.get(CONF_DEVICE_ENTITY))
    device_id = device.get(CONF_DEVICE_ID)
    device_name = device.get(CONF_DEVICE_NAME)
    service_domain = relay_entity.split(".")[0] if relay_entity else ""
    is_climate = service_domain == DOMAIN_CLIMATE

    actual_state = hass.states.get(relay_entity)
    is_actually_on = is_entity_on(service_domain, actual_state) if actual_state else False

    retries = entry_data.setdefault("command_retries", {}) if entry_data is not None else None

    # is_enabled = relay commanded ON this cycle. Tracked separately from allocated
    # power so the status sensor can distinguish a powered-but-idle device (relay on,
    # measured draw ~0) from one that simply wasn't allocated any power.
    status_entry["is_enabled"] = bool(is_active)

    if is_active:
        if device_id:
            device_on_state[device_id] = True

        if not prev_on:
            # Fresh ON decision → command immediately and (re)start the retry clock so
            # the first re-send waits a full interval.
            log_debug(f"Turning on standard device {device_name} (prev_on={prev_on}, actual={actual_state.state if actual_state else 'N/A'})")
            await turn_on_entity(hass, relay_entity, hvac_mode, device_name)
            if retries is not None and device_id:
                retries[device_id] = {
                    "expected": True, "last_command_at": now, "count": 0, "notified": False,
                }
        elif not is_actually_on and retries is not None and device_id:
            # Commanded before but the relay is still OFF (unresponsive). Re-send at most
            # once per COMMAND_RETRY_INTERVAL_SECONDS; never permanently give up.
            r = retries.get(device_id)
            if r is None or r.get("expected") is not True:
                r = {"expected": True, "last_command_at": None, "count": 0, "notified": False}
            last = r.get("last_command_at")
            due = (
                last is None
                or now is None
                or (now - last).total_seconds() >= COMMAND_RETRY_INTERVAL_SECONDS
            )
            if due:
                log_debug(f"[retry] Re-sending ON for {device_name} (attempt {r['count'] + 1})")
                await turn_on_entity(hass, relay_entity, hvac_mode, device_name)
                r["last_command_at"] = now
                r["count"] += 1
                if not is_climate and r["count"] >= UNREACHABLE_AFTER_RETRIES and not r["notified"]:
                    r["notified"] = True
                    _send_retry_notification(hass, device_name or device_id, device_id, True, r["count"])
            retries[device_id] = r
            status_entry["retry_count"] = r["count"]
            status_entry["retry_expected_on"] = True
            if not is_climate and r["count"] >= UNREACHABLE_AFTER_RETRIES:
                status_entry["unreachable"] = True
        elif is_actually_on and retries is not None and device_id and device_id in retries:
            # Relay confirmed ON → clear retry bookkeeping + any pending notification.
            retries.pop(device_id, None)
            _dismiss_retry_notification(hass, device_id)

        power_used = _resolve_standard_power_used(
            hass, device, status_entry, device_on_time_state or {}, device_id, now,
            device_sensor_cache,
        )
        status_entry.update({"allocated_w": float(power_used), "percent_target": 100.0, "percent_actual": 100.0})
    else:
        if device_id:
            device_on_state[device_id] = False
        if prev_on or is_actually_on:
            log_debug(f"Turning off standard device {device_name} (remaining={remaining_power}W)")
            await turn_off_entity(hass, relay_entity, device_name)
        # No longer expecting ON → drop any pending ON-retry bookkeeping.
        if retries is not None and device_id and device_id in retries:
            retries.pop(device_id, None)
            _dismiss_retry_notification(hass, device_id)

        status_entry.pop("is_idle", None)
        status_entry.update({"percent_target": 0.0, "percent_actual": 0.0, "allocated_w": 0.0})

    return power_used, status_entry


async def _control_custom_device(
    hass, device, is_active, prev_on, power_to_allocate, cfg, status_entry, device_on_state
):
    """Proportional control for an ESPHome relay (mode select + light brightness).

    SunAllocator drives the paired mode-select entity itself: ``Proportional``
    while active (then sets brightness on the light), ``Off`` when inactive.
    """
    power_used = 0.0
    device_name = device.get(CONF_DEVICE_NAME)
    device_id = device.get(CONF_DEVICE_ID)
    relay_entity, _ = parse_relay_entity(device.get(CONF_DEVICE_ENTITY))
    mode_select = device.get(CONF_ESPHOME_MODE_SELECT_ENTITY)

    if not relay_entity or "." not in relay_entity:
        log_warning(f"Device {device_name} has no valid entity_id, skipping control")
        return 0.0, status_entry

    if is_active:
        max_w = status_entry["max_expected_w"]
        target_percent = 0.0
        if max_w <= 0:
            log_warning(f"Device {device_name} in Proportional has no max_expected_w; forcing 0%/OFF")
        else:
            target_percent = min(MAX_PERCENTAGE, max(5, (power_to_allocate / max_w) * 100))
        log_debug(f"Proportional target for {device_name}: {target_percent}% ({power_to_allocate}W)")
        status_entry["percent_target"] = float(target_percent)
        if mode_select:
            await set_mode_for_entity(hass, mode_select, RELAY_MODE_PROPORTIONAL)
        await set_power_for_entity(hass, relay_entity, target_percent)
        power_used = min(power_to_allocate, max_w * (target_percent / MAX_PERCENTAGE))
        status_entry["allocated_w"] = float(power_used)
        if device_id:
            device_on_state[device_id] = True
    else:
        log_debug(f"Proportional below threshold for {device_name} -> target 0 / OFF")
        if mode_select:
            await set_mode_for_entity(hass, mode_select, RELAY_MODE_OFF)
        elif prev_on:
            await turn_off_entity(hass, relay_entity, device_name)
        if device_id:
            device_on_state[device_id] = False
        status_entry.update({"percent_target": 0.0, "percent_actual": 0.0, "allocated_w": 0.0})

    return power_used, status_entry


async def _control_esphome_onoff(
    hass, device, is_active, prev_on, remaining_power, cfg, status_entry, device_on_state,
    device_sensor_cache=None, device_on_time_state=None, now=None,
):
    """On/off control for an ESPHome relay via its mode select (``On`` / ``Off``)."""
    power_used = 0.0
    device_name = device.get(CONF_DEVICE_NAME)
    device_id = device.get(CONF_DEVICE_ID)
    mode_select = device.get(CONF_ESPHOME_MODE_SELECT_ENTITY)

    status_entry["is_enabled"] = bool(is_active)

    if is_active:
        if device_id:
            device_on_state[device_id] = True
        if not prev_on:
            log_debug(f"ESPHome on/off {device_name}: select -> On")
            await set_mode_for_entity(hass, mode_select, RELAY_MODE_ON)
        power_used = _resolve_standard_power_used(
            hass, device, status_entry, device_on_time_state or {}, device_id, now,
            device_sensor_cache,
        )
        status_entry.update({"allocated_w": float(power_used), "percent_target": 100.0, "percent_actual": 100.0})
    else:
        if device_id:
            device_on_state[device_id] = False
        if prev_on:
            log_debug(f"ESPHome on/off {device_name}: select -> Off")
            await set_mode_for_entity(hass, mode_select, RELAY_MODE_OFF)
        status_entry.pop("is_idle", None)
        status_entry.update({"percent_target": 0.0, "percent_actual": 0.0, "allocated_w": 0.0})

    return power_used, status_entry


async def _control_native_dimmer_device(
    hass, device, is_active, prev_on, power_to_allocate, cfg, status_entry, device_on_state
):
    """Proportional control for a native HA dimmable light (brightness via light.turn_on)."""
    power_used = 0.0
    device_name = device.get(CONF_DEVICE_NAME)
    device_id = device.get(CONF_DEVICE_ID)
    relay_entity, _ = parse_relay_entity(device.get(CONF_DEVICE_ENTITY))

    if not relay_entity or "." not in relay_entity:
        log_warning(f"Native dimmer {device_name} has no valid entity_id, skipping")
        return 0.0, status_entry

    if is_active:
        max_w = float(status_entry.get(CONF_DEVICE_MAX_EXPECTED_W, 0) or 0)
        if max_w <= 0:
            log_warning(f"Native dimmer {device_name} has no max_expected_w; skipping")
            return 0.0, status_entry
        target_percent = min(MAX_PERCENTAGE, max(5.0, (power_to_allocate / max_w) * 100))
        log_debug(
            f"Native dimmer {device_name}: {target_percent:.1f}% "
            f"({power_to_allocate:.0f}W / {max_w:.0f}W max)"
        )
        status_entry["percent_target"] = float(target_percent)
        await set_power_for_entity(hass, relay_entity, target_percent)
        power_used = min(power_to_allocate, max_w * (target_percent / MAX_PERCENTAGE))
        status_entry["allocated_w"] = float(power_used)
        if device_id:
            device_on_state[device_id] = True
    else:
        if prev_on:
            await turn_off_entity(hass, relay_entity, device_name)
        if device_id:
            device_on_state[device_id] = False
        status_entry.update({"percent_target": 0.0, "percent_actual": 0.0, "allocated_w": 0.0})

    return power_used, status_entry


def _finalize_device_status(entry_data):
    """Finalize device status by converting datetime objects to strings."""
    for device_id, status in entry_data.get("device_status", {}).items():
        if "last_on_time" in status and status["last_on_time"] and not isinstance(status["last_on_time"], str):
            status["last_on_time"] = status["last_on_time"].isoformat()
        if "last_off_time" in status and status["last_off_time"] and not isinstance(status["last_off_time"], str):
            status["last_off_time"] = status["last_off_time"].isoformat()
        if "startup_until" in status and status["startup_until"] and not isinstance(status["startup_until"], str):
            status["startup_until"] = status["startup_until"].isoformat()


# --- Retry tunables ------------------------------------------------------------------
# When we command a device ON but the relay stays OFF (unresponsive / offline), the
# first command goes out immediately; subsequent re-sends are throttled to at most one
# per this interval. We never permanently give up — we keep retrying slowly so the
# device recovers on its own once it comes back (e.g. cloud/Tuya reconnects).
COMMAND_RETRY_INTERVAL_SECONDS = 120
# After this many throttled re-sends still go unanswered, surface the device as
# "unreachable" (suppressed for climate, whose reported OFF is usually a satisfied
# thermostat rather than a comms failure).
UNREACHABLE_AFTER_RETRIES = 2
# A mismatch is only "user-initiated" if the entity's last real change is THIS recent
# relative to now. Without a freshness bound, a long-dormant device (e.g. overnight with
# zero excess, so the control loop barely runs) can have BOTH last_controlled_at and the
# entity's last_changed frozen for hours; their mere relative order (one a few seconds
# "newer" than the other, both ancient) would otherwise still read as "the user just
# toggled it" the instant the loop wakes up — confirmed live: last_controlled=22:54:44,
# actual_last_changed=22:54:59 (a same-value flicker seconds later), both from the
# previous evening, misfired the next morning at 10:32 when excess finally rose again.
EXTERNAL_CHANGE_FRESHNESS_SECONDS = 120


def _send_retry_notification(hass, device_name: str, device_id: str, expected_on: bool, count: int) -> None:
    hass.async_create_task(
        hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "Sun Allocator",
                "message": (
                    f"Device '{device_name}' did not respond to "
                    f"{'turn ON' if expected_on else 'turn OFF'} command "
                    f"after {count} attempts."
                ),
                "notification_id": f"sun_allocator_retry_{device_id}",
            },
        )
    )


def _dismiss_retry_notification(hass, device_id: str) -> None:
    hass.async_create_task(
        hass.services.async_call(
            "persistent_notification",
            "dismiss",
            {"notification_id": f"sun_allocator_retry_{device_id}"},
        )
    )


def _detect_external_change(
    hass, device, device_id, entry_data, status_entry, device_on_state, now,
):
    """Reconcile the desired state with the actual entity state.

    Only distinguishes a *user* toggle (→ sticky manual override) from an
    *unresponsive* device; it never sends commands and never "gives up". The
    throttled re-send + ``unreachable`` escalation live next to the actual
    service call in the per-capability control coroutine. Always returns
    ``None``; mutates ``manual_overrides`` / ``command_retries`` as side effects.
    """
    manual_overrides = entry_data.setdefault("manual_overrides", {})
    command_retries = entry_data.setdefault("command_retries", {})

    relay_entity, _ = parse_relay_entity(device.get(CONF_DEVICE_ENTITY))
    actual_state = hass.states.get(relay_entity) if relay_entity else None
    expected_on = device_on_state.get(device_id)

    if (
        not actual_state
        or actual_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE)
        or expected_on is None
        or not relay_entity
    ):
        return None

    service_domain = relay_entity.split(".")[0]
    actual_on = is_entity_on(service_domain, actual_state)

    if actual_on == expected_on:
        # Aligned: clear any pending retry bookkeeping.
        if device_id in command_retries:
            command_retries.pop(device_id, None)
            _dismiss_retry_notification(hass, device_id)
        return None

    # last_controlled_at is purely in-memory (never persisted) — a HA restart wipes it
    # while device_on_state/manual_overrides/grace deadlines resync or restore from
    # storage. A missing timestamp defaulting to "user-initiated" would misattribute a
    # slow-to-confirm command (or a mismatch surviving a restart) as a deliberate user
    # toggle, sticking a phantom manual override — so treat "never recorded controlling
    # this device" as unresponsive/unknown, not as evidence of a user action.
    last_controlled = entry_data.get("last_controlled_at", {}).get(device_id)
    is_recent = (now - actual_state.last_changed).total_seconds() <= EXTERNAL_CHANGE_FRESHNESS_SECONDS
    user_initiated = (
        last_controlled is not None and actual_state.last_changed >= last_controlled and is_recent
    )

    if user_initiated:
        # User flipped the entity → start/refresh a sticky manual-control entry. Always
        # update the recorded state (and re-stamp the day) so an on→off / off→on flip is
        # reflected; the entry persists until the auto-control switch is re-toggled, the
        # day rolls over, or (for ON) battery protection trips — see decide_manual_state.
        prev = manual_overrides.get(device_id)
        if prev is None or prev.get("state") != actual_on:
            log_debug(
                f"[manual] User state change for {device_id}: "
                f"expected={expected_on}, actual={actual_on}"
            )
        manual_overrides[device_id] = {"since": now, "state": actual_on}
        device_on_state[device_id] = actual_on
        if device_id in command_retries:
            command_retries.pop(device_id, None)
            _dismiss_retry_notification(hass, device_id)
        return None

    # Unresponsive (we commanded a state, the entity hasn't matched, and the user
    # didn't touch it). Don't count / give up here — the control coroutine owns the
    # throttled re-send and the unreachable escalation, keeping the retry cadence next
    # to the actual service call.
    return None


def decide_manual_state(override) -> str:
    """Pure classification of a device's manual-control state this cycle.

    ``override`` is the ``entry_data["manual_overrides"]`` entry (``{"state", "since"}``)
    or ``None``. The daily rollover / clearing is handled by the caller; battery-protection
    force-off is handled separately by ``decide_battery_soc_stop`` (applied to a ``manual_on``
    device by the caller), so this function only classifies the entry:

    * ``"auto"``       — no override → auto-control runs normally.
    * ``"manual_off"`` — user forced the device OFF (sticky; auto won't re-enable).
    * ``"manual_on"``  — user forced ON, keep it (and account its draw).
    """
    if not override:
        return "auto"
    if not override.get("state"):
        return "manual_off"
    return "manual_on"


def _finalize_run(entry_data, excess_power, remaining_power):
    """Update global state and prepare for dispatcher signal."""
    epsilon = 1e-9
    allocation = entry_data.get(CONF_POWER_ALLOCATION, {}).copy()
    for k, v in allocation.items():
        if abs(v) < epsilon:
            allocation[k] = 0.0

    _finalize_device_status(entry_data)

    entry_data[CONF_POWER_DISTRIBUTION] = {
        "total_power": round(excess_power, 1),
        "remaining_power": round(remaining_power, 1),
        "allocated_power": round(excess_power - remaining_power, 1),
        "allocation": {k: round(v, 1) for k, v in allocation.items()},
    }


def _sync_initial_device_states(
    hass, devices, device_on_state, entry_data, device_on_time_state=None, now=None,
) -> None:
    """First-run-after-startup sync of ``device_on_state`` from actual HA entity states.

    Without this, every device defaults to ``False`` (off) on a fresh
    integration load and the hysteresis thresholds for ``prev_on=True`` would
    never trigger correctly. Runs at most once per integration setup.

    A device found already ON across the restart gets a fresh on-time session seeded
    from ``now`` (continuing on top of the persisted daily total — see
    ``load_on_time_state``) rather than losing the in-progress session entirely.
    """
    if entry_data.get("_device_on_state_initialized"):
        return
    for _dev in devices:
        _dev_id = _dev.get(CONF_DEVICE_ID)
        _relay, _ = parse_relay_entity(_dev.get(CONF_DEVICE_ENTITY))
        if not _relay or "." not in _relay:
            continue
        _state = hass.states.get(_relay)
        if _state is None or _state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            continue
        _domain = _relay.split(".")[0]
        _is_on = is_entity_on(_domain, _state)
        device_on_state[_dev_id] = _is_on
        if (
            _is_on and _dev_id and device_on_time_state is not None and now is not None
            and device_on_time_state.get(_dev_id, {}).get("last_on_time") is None
        ):
            device_on_time_state.setdefault(_dev_id, {})["last_on_time"] = now
        log_debug(f"[init] Synced device_on_state[{_dev_id}] = {_is_on} from actual state")
    entry_data["_device_on_state_initialized"] = True


def _compute_proportional_allocations(
    devices, device_status, remaining_power, device_on_state, device_debounce_state, cfg, now
) -> dict:
    """Pre-allocate excess across active proportional ESPHome devices for STRATEGY_DISTRIBUTE_EVENLY.

    Each active proportional device gets a share of ``remaining_power``
    weighted by its ``max_expected_w``. Inactive devices and non-proportional
    custom devices are excluded from the pool.
    """
    proportional_devices = []
    total_max_w = 0.0
    for device in devices:
        device_id = device.get(CONF_DEVICE_ID)
        status_entry = device_status.get(device_id)
        if (
            status_entry
            and status_entry.get("mode") == RELAY_MODE_PROPORTIONAL
        ):
            is_active, _ = _calculate_device_state(
                device, remaining_power, device_on_state, device_debounce_state, cfg, now
            )
            if is_active:
                proportional_devices.append((device_id, status_entry["max_expected_w"]))
                total_max_w += status_entry["max_expected_w"]

    if total_max_w <= 0:
        return {}
    return {
        device_id: remaining_power * (max_w / total_max_w)
        for device_id, max_w in proportional_devices
    }


def _record_grace_deadline(hass, config_entry, device_on_time_state, device_id, now, startup_grace):
    """Set + persist the startup-grace deadline for a device that just turned on."""
    startup_until = now + dt_stdlib.timedelta(seconds=startup_grace)
    device_on_time_state.setdefault(device_id, {})["startup_until"] = startup_until
    log_debug(
        f"[grace] Startup grace period set for {device_id}: {startup_grace}s until {startup_until}"
    )
    hass.async_create_task(persist_grace_state(hass, config_entry, device_id, startup_until))


def _clear_grace_deadline(hass, config_entry, device_on_time_state, device_id):
    device_on_time_state.get(device_id, {}).pop("startup_until", None)
    hass.async_create_task(persist_grace_state(hass, config_entry, device_id, None))


def _apply_min_on_time(
    hass, config_entry, device, device_id, device_on_time_state, status_entry,
    is_active, prev_on_before_calc, now, min_on_time,
):
    """Enforce min-on-time and close the on-time session on an off-transition.

    NOTE: the session/grace START is recorded at the END of ``_control_one_device``
    (only after every gate has confirmed the start survives), NOT here — recording it
    here would write ``last_on_time`` and a per-cycle-refreshed grace deadline for a
    device that the SOC/max gates then veto (phantom state + Store flash churn).
    """
    if not (prev_on_before_calc and not is_active):
        return is_active

    last_on_time = device_on_time_state.get(device_id, {}).get("last_on_time")
    if min_on_time > 0 and last_on_time:
        elapsed = (now - last_on_time).total_seconds()
        if elapsed < min_on_time:
            status_entry["refusal_reasons"].append(
                f"Minimum on-time not yet elapsed: {elapsed:.1f}s < {min_on_time}s"
            )
            log_debug(f"[min_on_time] Keeping {device_id} ON (min_on_time not elapsed)")
            return True

    # Off-transition: close the session and clear the (persisted) grace deadline.
    _close_on_time_session(device_on_time_state, device_id, now)
    device_on_time_state.setdefault(device_id, {}).pop("startup_until", None)
    hass.async_create_task(persist_grace_state(hass, config_entry, device_id, None))
    status_entry["last_off_time"] = now
    return is_active


def _apply_startup_grace(
    hass, config_entry, device, device_id, device_on_time_state, status_entry,
    is_active, prev_on_before_calc, now,
):
    """Honor an active startup-grace deadline by keeping the device ON. Returns ``is_active``."""
    startup_grace = float(device.get(KEY_STARTUP_GRACE_PERIOD, DEFAULT_STARTUP_GRACE_PERIOD))
    if startup_grace <= 0 or is_active or not prev_on_before_calc:
        return is_active

    startup_until = device_on_time_state.get(device_id, {}).get("startup_until")
    if not startup_until:
        return is_active

    # Stored as string when reloaded from persistent storage.
    if isinstance(startup_until, str):
        startup_until = dt_stdlib.datetime.fromisoformat(startup_until)
    if now < startup_until:
        remaining_grace = (startup_until - now).total_seconds()
        elapsed_grace = startup_grace - remaining_grace
        log_debug(
            f"[grace] Keeping {device_id} ON during startup grace "
            f"({elapsed_grace:.1f}s elapsed, {remaining_grace:.1f}s remaining)"
        )
        status_entry["refusal_reasons"].append(
            f"Startup grace period: {remaining_grace:.0f}s remaining"
        )
        return True
    _clear_grace_deadline(hass, config_entry, device_on_time_state, device_id)
    log_debug(f"[grace] Startup grace period expired for {device_id}")
    return is_active


async def _dispatch_device_control(
    hass, device, is_active, prev_on, status_entry, cfg, device_on_state,
    strategy, proportional_allocations, remaining_power, device_sensor_cache=None,
    device_on_time_state=None, now=None, entry_data=None,
):
    """Forward to the per-capability control coroutine and return ``(power_used, status_entry)``."""
    device_id = device.get(CONF_DEVICE_ID)
    mode_select = device.get(CONF_ESPHOME_MODE_SELECT_ENTITY)

    if _is_proportional(device):
        # Proportional: native dimmer (brightness) or ESPHome relay (select + brightness).
        if strategy == STRATEGY_DISTRIBUTE_EVENLY:
            power_to_allocate = proportional_allocations.get(device_id, 0.0)
        else:
            power_to_allocate = proportional_allocations.get(device_id, remaining_power)
        if mode_select:
            return await _control_custom_device(
                hass, device, is_active, prev_on, power_to_allocate, cfg, status_entry, device_on_state,
            )
        return await _control_native_dimmer_device(
            hass, device, is_active, prev_on, power_to_allocate, cfg, status_entry, device_on_state,
        )

    if mode_select:
        # ESPHome relay driven on/off via its mode select (On / Off).
        return await _control_esphome_onoff(
            hass, device, is_active, prev_on, remaining_power, cfg, status_entry,
            device_on_state, device_sensor_cache=device_sensor_cache,
            device_on_time_state=device_on_time_state, now=now,
        )

    # Standard on/off device
    return await _control_standard_device(
        hass, device, is_active, prev_on, remaining_power, cfg, status_entry,
        device_on_state, device_sensor_cache=device_sensor_cache,
        device_on_time_state=device_on_time_state, now=now, entry_data=entry_data,
    )


async def _control_one_device(
    hass, config_entry, device, *,
    cfg, entry_data, now, strategy, proportional_allocations, remaining_power, battery_soc,
    battery_soc_configured=False, device_sensor_cache=None,
    discharging=False, protection_soc=0.0,
):
    """Run the full per-device control pipeline for one cycle.

    Returns the power consumed by this device (or ``0.0`` if the device was
    skipped/filtered/aborted). Mutates shared state dicts inside ``entry_data``.
    """
    device_id = device.get(CONF_DEVICE_ID)
    log_debug(f"Looping for device: {device_id}")

    status_entry = entry_data["device_status"].get(device_id)
    if not status_entry:
        log_warning(f"Could not find status_entry for device {device_id}, skipping.")
        return 0.0

    device_on_state = entry_data["device_on_state"]
    device_debounce_state = entry_data["device_debounce_state"]
    device_on_time_state = entry_data["device_on_time_state"]

    # Reconcile expected vs actual FIRST — before any schedule/usable filter. The
    # filter turns the relay off when out of schedule / not usable; if it ran first it
    # would erase a user's manual toggle before _detect_external_change could record it,
    # so a manual ON could never override the schedule. This only detects a user toggle
    # vs an unresponsive device; the throttled re-send lives in the control coroutine.
    _detect_external_change(
        hass, device, device_id, entry_data, status_entry, device_on_state, now
    )

    # Manual control: a user toggle is sticky (no time-out) for the rest of the local
    # day, or until the auto-control switch is re-toggled / battery protection trips.
    # A manual choice overrides the schedule and check_usable filters (handled below,
    # only for the auto path); only battery protection (SOC) forces a manual ON off.
    manual_overrides = entry_data.setdefault("manual_overrides", {})
    override = manual_overrides.get(device_id)
    if (
        override
        and override.get("since") is not None
        and now.date() != override["since"].date()
    ):
        # Daily rollover → the manual choice expired; resume auto-control.
        log_debug(f"[manual] Daily rollover cleared manual state for {device_id}")
        del manual_overrides[device_id]
        override = None

    # Timed-run expiry → release the override entirely; auto-control decides from here
    # on (matches the manual-switch OFF release semantics — a timed run is a temporary
    # override, not a standing manual_on once its window is over). device_on_state stays
    # True (still physically on), so the auto gates below see an accurate prev_on and
    # decide fresh whether to keep the device running.
    if is_timed_run_expired(override, now):
        log_debug(f"[manual] Timed run expired for {device_id} → released to auto")
        del manual_overrides[device_id]
        override = None

    decision = decide_manual_state(override)
    if decision == "manual_off":
        # Close out any in-progress on-time session — this path returns before the auto
        # gates (_apply_min_on_time) ever see the on→off transition, so nobody else will.
        _close_on_time_session(device_on_time_state, device_id, now)
        device_on_state[device_id] = False
        status_entry["manual_override"] = True
        status_entry["refusal_reasons"].append("Manual control (off)")
        if device_id:
            entry_data[CONF_POWER_ALLOCATION][device_id] = 0.0
        return 0.0
    stop_gate = entry_data.setdefault("battery_stop_gate_state", {})
    if decision == "manual_on":
        # Battery protection can still force a manual ON off (discharge-side stop floor or
        # the absolute protection floor) — the only exception to a sticky manual choice.
        # A timed run with ignore_battery bypasses this entirely (full SOC override).
        if not override.get("ignore_battery") and decide_battery_soc_stop(
            battery_soc=battery_soc,
            soc_configured=battery_soc_configured,
            discharging=discharging,
            stop_soc=device.get(CONF_DEVICE_STOP_BATTERY_SOC, DEFAULT_DEVICE_STOP_BATTERY_SOC),
            protection_soc=protection_soc,
            was_blocked=bool(stop_gate.get(device_id)),
        ):
            stop_gate[device_id] = True
            floor = _effective_stop_soc(device, protection_soc)
            log_debug(
                f"[manual] Battery protection: forcing OFF {device_id} "
                f"(SOC {battery_soc} < {floor})"
            )
            relay_entity, _ = parse_relay_entity(device.get(CONF_DEVICE_ENTITY))
            if relay_entity:
                await turn_off_entity(hass, relay_entity, device.get(CONF_DEVICE_NAME, ""))
            manual_overrides.pop(device_id, None)
            _close_on_time_session(device_on_time_state, device_id, now)
            device_on_state[device_id] = False
            status_entry["refusal_reasons"].append(
                f"Battery protection (SOC {float(battery_soc):.0f}% < {floor:.0f}%)"
            )
            entry_data.setdefault("last_controlled_at", {})[device_id] = now
            if device_id:
                entry_data[CONF_POWER_ALLOCATION][device_id] = 0.0
            return 0.0
        stop_gate.pop(device_id, None)
        device_on_state[device_id] = True
        status_entry["manual_active"] = True
        status_entry["manual_override"] = True
        status_entry["percent_actual"] = 100.0
        # Start (or continue) today's on-time session — this path bypasses the auto
        # gates (_apply_min_on_time normally does this), so the runtime sensor would
        # otherwise never see last_on_time for a manually/timer-driven device.
        if device_on_time_state.get(device_id, {}).get("last_on_time") is None:
            device_on_time_state.setdefault(device_id, {})["last_on_time"] = now
        # Timed run → distinct status so the card shows "Manual (timer)" not plain manual;
        # the remaining minutes are surfaced by the dedicated timer sensor / number field.
        if override.get("until") is not None:
            status_entry["manual_timer"] = True
        # Account the user-forced draw against the budget (do NOT re-command the relay —
        # the user owns it); other auto devices then see the real remaining surplus.
        power_used = _resolve_standard_power_used(
            hass, device, status_entry, device_on_time_state, device_id, now, device_sensor_cache
        )
        if device_id:
            entry_data[CONF_POWER_ALLOCATION][device_id] = power_used
        return power_used

    # Auto-control path only: apply the schedule / usability filter now. A manual
    # override returned above and therefore bypasses this (manual beats schedule +
    # check_usable; only battery protection forces a manual ON off).
    filter_reason = await _filter_device(hass, device, now)
    log_debug(f"Filter reason for {device_id}: {filter_reason}")
    if filter_reason:
        if device_id:
            entry_data["device_filter_reasons"][device_id] = filter_reason
            status_entry["refusal_reasons"].append(filter_reason)
            entry_data.setdefault("command_retries", {}).pop(device_id, None)
            # The filter just turned the relay off — close any running on-time session
            # (this path returns before the auto gates that would otherwise close it),
            # and record that OFF as OUR command so a later user toggle is detected as
            # user-initiated (not a spurious manual OFF / "unresponsive device" fight).
            _close_on_time_session(device_on_time_state, device_id, now)
            device_on_state[device_id] = False
            entry_data.setdefault("last_controlled_at", {})[device_id] = now
        return 0.0

    # Save prev_on BEFORE _calculate_device_state — that mutates device_on_state.
    prev_on_before_calc = bool(device_on_state.get(device_id, False))

    is_active, is_active_candidate = _calculate_device_state(
        device, remaining_power, device_on_state, device_debounce_state, cfg, now
    )
    log_debug(
        f"Calculated state for {device_id}: "
        f"is_active={is_active}, is_active_candidate={is_active_candidate}"
    )
    status_entry["is_active_candidate"] = is_active_candidate
    prev_on = prev_on_before_calc

    min_on_time = status_entry.get(CONF_DEVICE_MIN_ON_TIME, 0)
    is_active = _apply_min_on_time(
        hass, config_entry, device, device_id, device_on_time_state, status_entry,
        is_active, prev_on_before_calc, now, min_on_time,
    )
    is_active = _apply_startup_grace(
        hass, config_entry, device, device_id, device_on_time_state, status_entry,
        is_active, prev_on_before_calc, now,
    )
    gate_state = entry_data.setdefault("battery_soc_gate_state", {})
    is_active = _apply_battery_soc_gate(
        device, device_id, is_active, prev_on_before_calc, battery_soc,
        battery_soc_configured, gate_state, status_entry
    )
    # Discharge-side battery protection — CAN turn off a running device (unlike the
    # start gate above). Shares the manual path's sticky gate-state for hysteresis.
    is_active = _apply_battery_stop_floor(
        device, device_id, is_active, battery_soc, battery_soc_configured,
        discharging, protection_soc, stop_gate, status_entry,
    )
    is_active = _apply_max_on_time_gate(
        device, device_id, is_active, prev_on_before_calc, device_on_time_state, now, status_entry
    )

    # On-time session bookkeeping — AFTER every gate (so a start any gate vetoed records
    # no phantom session/grace: R1.2) but BEFORE dispatch (so _resolve_standard_power_used
    # sees startup_until this same cycle for the startup-reserve). The close also covers a
    # running device shed by the discharge stop-floor (R1.1); the per-gate closes above are
    # idempotent with it.
    if prev_on_before_calc and not is_active:
        _close_on_time_session(device_on_time_state, device_id, now)
    elif is_active and not prev_on_before_calc:
        device_on_time_state.setdefault(device_id, {})["last_on_time"] = now
        status_entry["last_on_time"] = now
        startup_grace = float(device.get(KEY_STARTUP_GRACE_PERIOD, DEFAULT_STARTUP_GRACE_PERIOD))
        if startup_grace > 0:
            _record_grace_deadline(hass, config_entry, device_on_time_state, device_id, now, startup_grace)

    log_debug(f"Control logic for {device_id}: prev_on={prev_on}, prev_on_before_calc={prev_on_before_calc}")
    power_used, _ = await _dispatch_device_control(
        hass, device, is_active, prev_on, status_entry, cfg, device_on_state,
        strategy, proportional_allocations, remaining_power,
        device_sensor_cache=device_sensor_cache,
        device_on_time_state=device_on_time_state, now=now, entry_data=entry_data,
    )

    # Stamp our command time whenever we drive the device ON (every active cycle), not
    # only on a transition. Otherwise, if we command ON but the entity stays OFF (a
    # not-yet-committed/failing turn-on, or a template-light propagation lag), the stale
    # last_controlled_at makes _detect_external_change misread the persistent OFF as a
    # USER manual-OFF and record a phantom sticky override. Stamping each active cycle
    # routes "commanded ON but still OFF" to the retry (unresponsive) path instead.
    if device_id and (is_active or is_active != prev_on_before_calc):
        entry_data.setdefault("last_controlled_at", {})[device_id] = now
    if device_id:
        entry_data[CONF_POWER_ALLOCATION][device_id] = power_used
    return power_used


async def process_excess_power(
    hass: HomeAssistant, config_entry: ConfigType, excess_power: float
) -> None:
    """Process excess power value and control devices accordingly."""
    log_debug(f"--- process_excess_power START, excess_power={excess_power} ---")
    now = dt_util.now()
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    cfg = config_entry.data
    log_debug(f"entry_data keys: {list(entry_data.keys())}")

    device_on_state = entry_data.setdefault("device_on_state", {})
    entry_data.setdefault("device_debounce_state", {})
    device_on_time_state = entry_data.setdefault("device_on_time_state", {})

    auto_control_devices = _initialize_run(entry_data, cfg.get(CONF_DEVICES, []))
    _sync_initial_device_states(
        hass, auto_control_devices, device_on_state, entry_data, device_on_time_state, now,
    )
    log_debug(f"auto_control_devices: {auto_control_devices}")

    for device in auto_control_devices:
        device_id = device.get(CONF_DEVICE_ID)
        entry_data["device_status"][device_id] = _initialize_status_entry(hass, device)

    # Pre-read all per-device sensors once per cycle to avoid redundant state
    # lookups when multiple devices share the same entity (e.g. a shared power
    # meter), and to give every device a consistent snapshot of the same instant.
    device_sensor_cache: dict[str, tuple[float, bool]] = {}
    for _dev in auto_control_devices:
        _sensor = _dev.get(CONF_DEVICE_ACTUAL_POWER_SENSOR)
        if _sensor and _sensor not in device_sensor_cache:
            device_sensor_cache[_sensor] = get_sensor_state_safely(hass, _sensor, "Actual Power")

    # Probe budget (mppt_probe). ABSOLUTE model: probe_headroom_w is the discovered
    # sustainable controllable-load budget, NOT an increment on the (volatile)
    # cautious excess. We split it into two pools:
    #   real_pool  = cautious excess — genuinely available, usable by ALL devices.
    #   extra_pool = probe-discovered surplus beyond the cautious excess — usable
    #                ONLY by devices that allow probing.
    # The total (real + extra) equals max(excess, headroom). Using max (not sum)
    # keeps the budget stable when a probe-driven load turns on and de-curtails the
    # panels: the cautious excess then drops to ~0, but the headroom holds the
    # budget at the load level so the device is not immediately dropped (which is
    # what excess+headroom did → cycling). Both pools are 0/negative-safe.
    probe_headroom_w = float(entry_data.get("probe_headroom_w", 0.0) or 0.0)
    # Race-free floor: a manual→auto transition (or an external switch-on) allocates
    # in THIS cycle, before the next probe tick recomputes probe_headroom_w. While the
    # probe is active and the battery is healthy (flag set by the probe tick), keep the
    # budget at the already-running probe load so an adopted device is not dropped for a
    # cycle then rediscovered. Gated on battery health so a fresh discharge still drops
    # it (the probe backs the stored headroom off within a tick).
    if entry_data.get("probe_battery_healthy"):
        probe_headroom_w = max(
            probe_headroom_w,
            running_controllable_floor_w(
                entry_data.get("device_status", {}),
                entry_data.get("device_on_state", {}),
            ),
        )
    real_pool = max(0.0, excess_power)
    extra_pool = max(0.0, probe_headroom_w - real_pool)
    starting_budget = real_pool + extra_pool  # == max(excess, headroom); finalize total
    strategy = cfg.get(CONF_DEVICE_ALLOCATION_STRATEGY, STRATEGY_FILL_ONE_BY_ONE)
    battery_soc = _read_battery_soc(hass, cfg)
    battery_soc_configured = bool(cfg.get(CONF_BATTERY_SOC_SENSOR))
    protection_soc = float(cfg.get(CONF_BATTERY_PROTECTION_SOC, 0) or 0)
    # Battery net charge → discharge flag for the discharge-side stop floor. Reuse the
    # excess discharge tolerance so minor jitter is not read as a real discharge.
    net_charge = 0.0
    bp_entity = cfg.get(CONF_BATTERY_POWER)
    if bp_entity:
        _bp_val, _bp_ok = get_sensor_state_safely(hass, bp_entity, "Battery Power")
        if _bp_ok:
            net_charge = battery_net_charge_w(_bp_val, cfg.get(CONF_BATTERY_POWER_REVERSED, False))
    discharge_tol = float(
        cfg.get(CONF_BATTERY_DISCHARGE_TOLERANCE_W, DEFAULT_BATTERY_DISCHARGE_TOLERANCE_W)
    )
    battery_discharging = net_charge < -discharge_tol
    proportional_allocations: dict = {}
    if strategy == STRATEGY_DISTRIBUTE_EVENLY:
        proportional_allocations = _compute_proportional_allocations(
            auto_control_devices,
            entry_data["device_status"],
            starting_budget,
            dict(entry_data["device_on_state"]),
            {k: dict(v) for k, v in entry_data["device_debounce_state"].items()},
            cfg, now,
        )

    # Process user-forced (manual-ON) devices first so their accounted draw reduces the
    # pool before auto devices allocate (stable sort preserves priority within groups).
    overrides = entry_data.get("manual_overrides", {})
    ordered_devices = sorted(
        auto_control_devices,
        key=lambda d: 0 if (overrides.get(d.get(CONF_DEVICE_ID)) or {}).get("state") else 1,
    )

    for device in ordered_devices:
        status_entry = entry_data["device_status"].get(device.get(CONF_DEVICE_ID))
        allow_probe = status_entry.get("allow_probe", True) if status_entry else True
        # Opt-out devices may draw only from the real (cautious) pool, never from
        # speculative probe headroom.
        device_budget = real_pool + (extra_pool if allow_probe else 0.0)
        power_used = await _control_one_device(
            hass, config_entry, device,
            cfg=cfg, entry_data=entry_data, now=now, strategy=strategy,
            proportional_allocations=proportional_allocations,
            remaining_power=device_budget,
            battery_soc=battery_soc,
            battery_soc_configured=battery_soc_configured,
            device_sensor_cache=device_sensor_cache,
            discharging=battery_discharging,
            protection_soc=protection_soc,
        )
        # Consume the real pool first, then (for probe-allowed devices) the extra.
        from_real = min(power_used, real_pool)
        real_pool -= from_real
        if allow_probe:
            extra_pool = max(0.0, extra_pool - (power_used - from_real))
        log_debug(
            f"Power used by {device.get(CONF_DEVICE_ID)}: {power_used}, "
            f"real_pool: {real_pool}, extra_pool: {extra_pool}"
        )

    _finalize_run(entry_data, starting_budget, real_pool + extra_pool)

    # Persist the sticky manual overrides (only when they changed) so they survive a HA
    # restart. Cheap: a serialized snapshot gate avoids a write every cycle.
    overrides = entry_data.get("manual_overrides", {})
    snapshot = {
        did: (
            ov.get("since").isoformat() if isinstance(ov.get("since"), dt_stdlib.datetime) else None,
            bool(ov.get("state")),
            ov.get("until").isoformat() if isinstance(ov.get("until"), dt_stdlib.datetime) else None,
            bool(ov.get("ignore_battery")),
        )
        for did, ov in overrides.items()
    }
    if snapshot != entry_data.get("_manual_persisted"):
        entry_data["_manual_persisted"] = snapshot
        hass.async_create_task(persist_manual_overrides(hass, config_entry, overrides))

    # Persist today's accumulated on-time per device (only when it changed) so a HA
    # restart mid-day doesn't reset the runtime sensor / max_on_time_per_day gate to 0.
    on_time_snapshot = {
        did: (
            st.get("on_time_day").isoformat() if hasattr(st.get("on_time_day"), "isoformat") else None,
            round(float(st.get("on_time_accum_sec", 0.0) or 0.0), 1),
        )
        for did, st in device_on_time_state.items()
        if st.get("on_time_day") is not None
    }
    if on_time_snapshot != entry_data.get("_on_time_persisted"):
        entry_data["_on_time_persisted"] = on_time_snapshot
        hass.async_create_task(persist_on_time_state(hass, config_entry, device_on_time_state))

    async_dispatcher_send(hass, f"{SIGNAL_POWER_DISTRIBUTION_UPDATED}_{config_entry.entry_id}")
