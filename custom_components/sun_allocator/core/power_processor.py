"""Main power processing logic for Sun Allocator."""

import datetime as dt_stdlib
import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.const import (
    STATE_UNKNOWN,
    STATE_UNAVAILABLE,
)

# Local imports from the same 'core' directory
from .logger import log_debug, log_warning
from .schedule import is_device_in_schedule
from .settings import COUNTER_DEBOUNCE_FRACTION
from .device_restore import persist_grace_state
from .constants_internal import SUPPORTED_DOMAINS
from .entity_control import (
    is_entity_on,
    turn_on_entity,
    turn_off_entity,
    set_power_for_entity,
    parse_relay_entity,
)

# Imports from the parent directory 'sun_allocator'
from ..const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_PRIORITY,
    CONF_DEVICE_TYPE,
    DEVICE_TYPE_STANDARD,
    DEVICE_TYPE_CUSTOM,
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
    RELAY_MODE_PROPORTIONAL,
    CONF_ESPHOME_MODE_SELECT_ENTITY,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_DEVICE_ALLOCATION_STRATEGY,
    STRATEGY_FILL_ONE_BY_ONE,
    STRATEGY_DISTRIBUTE_EVENLY,
    KEY_STARTUP_GRACE_PERIOD,
    DEFAULT_STARTUP_GRACE_PERIOD,
)

def _initialize_run(entry_data, devices_config):
    """Initialize states for the processing run."""
    power_allocation = entry_data.get(CONF_POWER_ALLOCATION, {})
    for dev_id in power_allocation:
        power_allocation[dev_id] = 0

    entry_data.setdefault("device_status", {})
    entry_data["device_filter_reasons"] = {}

    auto_control_devices = [
        d for d in devices_config if d.get(CONF_AUTO_CONTROL_ENABLED, False)
    ]
    auto_control_devices.sort(
        key=lambda d: int(d.get(CONF_DEVICE_PRIORITY, 50)), reverse=True
    )

    return auto_control_devices


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

    return None


def _calculate_device_state(
    device, excess_power, device_on_state, device_debounce_state, cfg, now
):
    """Calculate the desired state (on/off) for a device based on power, hysteresis, and debounce."""
    device_id = device.get(CONF_DEVICE_ID)
    device_name = device.get(CONF_DEVICE_NAME)

    log_debug(f"[STATE_DEBUG] Device {device_name}: Starting state calculation")
    log_debug(f"[STATE_DEBUG] Current device_on_state: {device_on_state.get(device_id)}")
    log_debug(f"[STATE_DEBUG] Current debounce_state: {device_debounce_state.get(device_id)}")

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


def _initialize_status_entry(hass, device):
    """Initialize the status dictionary for a device."""
    min_expected_w = float(device.get(CONF_DEVICE_MIN_EXPECTED_W, 0) or 0)
    max_expected_w = float(device.get(CONF_DEVICE_MAX_EXPECTED_W, 0) or 0)
    if max_expected_w <= min_expected_w:
        max_expected_w = min_expected_w * 1.1

    mode = None
    if device.get(CONF_DEVICE_TYPE) == DEVICE_TYPE_CUSTOM:
        mode_select_entity = device.get(CONF_ESPHOME_MODE_SELECT_ENTITY)
        if mode_select_entity:
            mode_state = hass.states.get(mode_select_entity)
            if mode_state:
                mode = mode_state.state

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
        "refusal_reasons": [],
    }


async def _control_standard_device(
    hass, device, is_active, prev_on, remaining_power, cfg, status_entry, device_on_state
):
    """Control logic for a standard (on/off) device."""
    power_used = 0.0
    relay_entity, hvac_mode = parse_relay_entity(device.get(CONF_DEVICE_ENTITY))
    device_id = device.get(CONF_DEVICE_ID)
    device_name = device.get(CONF_DEVICE_NAME)
    service_domain = relay_entity.split(".")[0] if relay_entity else ""

    actual_state = hass.states.get(relay_entity)
    is_actually_on = is_entity_on(service_domain, actual_state) if actual_state else False

    if is_active:
        if device_id:
            device_on_state[device_id] = True

        if not prev_on or not is_actually_on:
            log_debug(f"Turning on standard device {device_name} (prev_on={prev_on}, actual={actual_state.state if actual_state else 'N/A'})")
            await turn_on_entity(hass, relay_entity, hvac_mode, device_name)

        power_used = status_entry["min_expected_w"]
        status_entry.update({"allocated_w": float(power_used), "percent_target": 100.0, "percent_actual": 100.0})
    else:
        if device_id:
            device_on_state[device_id] = False
        if prev_on or is_actually_on:
            log_debug(f"Turning off standard device {device_name} (remaining={remaining_power}W)")
            await turn_off_entity(hass, relay_entity, device_name)

        status_entry.update({"percent_target": 0.0, "percent_actual": 0.0, "allocated_w": 0.0})

    return power_used, status_entry


async def _control_custom_device(
    hass, device, is_active, prev_on, power_to_allocate, cfg, status_entry, device_on_state
):
    """Control logic for a custom (ESPHome) device."""
    power_used = 0.0
    device_name = device.get(CONF_DEVICE_NAME)
    relay_entity, _ = parse_relay_entity(device.get(CONF_DEVICE_ENTITY))

    if not relay_entity or "." not in relay_entity:
        log_warning(f"Device {device_name} has no valid entity_id, skipping control")
        return 0.0, status_entry

    if status_entry.get("mode") == RELAY_MODE_PROPORTIONAL:
        if is_active:
            max_w = status_entry["max_expected_w"]
            target_percent = 0.0
            if max_w <= 0:
                log_warning(f"Device {device_name} in Proportional has no max_expected_w; forcing 0%/OFF")
            else:
                target_percent = min(MAX_PERCENTAGE, max(5, (power_to_allocate / max_w) * 100))
            log_debug(f"Proportional target for {device_name}: {target_percent}% ({power_to_allocate}W)")
            status_entry["percent_target"] = float(target_percent)
            await set_power_for_entity(hass, relay_entity, target_percent)
            power_used = min(power_to_allocate, max_w * (target_percent / MAX_PERCENTAGE))
            status_entry["allocated_w"] = float(power_used)
        else:
            log_debug(f"Proportional below threshold for {device_name} -> target 0 / OFF")
            if prev_on:
                await turn_off_entity(hass, relay_entity, device_name)

    elif status_entry.get("mode") == RELAY_MODE_ON:
        power_used, status_entry = await _control_standard_device(
            hass, device, is_active, prev_on, power_to_allocate, cfg, status_entry, device_on_state
        )

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


# --- Manual override / retry tunables -----------------------------------------------
# Time window during which a user-initiated state change suppresses auto-control.
MANUAL_OVERRIDE_TTL_SECONDS = 300
# Throttle between retry attempts when an entity ignored our last command.
RETRY_INTERVAL_SECONDS = 30
# After this many failed ON attempts we give up (and notify the user once).
RETRY_MAX_ATTEMPTS = 3


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

    Returns ``"give_up"`` when an unresponsive device should be skipped this
    cycle, otherwise ``None``. Mutates ``manual_overrides``, ``command_retries``
    and ``device_retry_failed`` in ``entry_data`` as side effects.
    """
    manual_overrides = entry_data.setdefault("manual_overrides", {})
    command_retries = entry_data.setdefault("command_retries", {})
    retry_failed = entry_data.setdefault("device_retry_failed", {})

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
        was_failed = retry_failed.pop(device_id, False)
        if device_id in command_retries or was_failed:
            command_retries.pop(device_id, None)
            _dismiss_retry_notification(hass, device_id)
        return None

    last_controlled = entry_data.get("last_controlled_at", {}).get(device_id)
    user_initiated = (
        last_controlled is None or actual_state.last_changed >= last_controlled
    )

    if user_initiated:
        # User flipped the entity → trigger a manual override window.
        if device_id not in manual_overrides:
            log_debug(
                f"[manual_override] External state change for {device_id}: "
                f"expected={expected_on}, actual={actual_on}"
            )
            manual_overrides[device_id] = {"since": now, "state": actual_on}
            device_on_state[device_id] = actual_on
        command_retries.pop(device_id, None)
        retry_failed.pop(device_id, None)
        return None

    # Unresponsive device — throttle retries.
    retry = command_retries.get(device_id)
    if retry is None or retry.get("expected") != expected_on:
        retry = {"count": 0, "expected": expected_on, "last_retry_at": None, "notified": False}

    last_retry = retry.get("last_retry_at")
    retry_due = last_retry is None or (now - last_retry).total_seconds() >= RETRY_INTERVAL_SECONDS

    if retry_due:
        retry["count"] += 1
        retry["last_retry_at"] = now
        log_debug(
            f"[retry] Device {device_id} unresponsive, retry {retry['count']} "
            f"(expected={'ON' if expected_on else 'OFF'})"
        )

        if retry["count"] >= RETRY_MAX_ATTEMPTS and not retry["notified"]:
            retry["notified"] = True
            _send_retry_notification(
                hass, device.get(CONF_DEVICE_NAME, device_id), device_id, expected_on, retry["count"],
            )

        # ON: give up after RETRY_MAX_ATTEMPTS; OFF: keep retrying.
        if expected_on and retry["count"] >= RETRY_MAX_ATTEMPTS:
            log_warning(
                f"[retry] Giving up ON for {device_id} after {retry['count']} retries"
            )
            retry_failed[device_id] = True
            device_on_state[device_id] = actual_on
            command_retries.pop(device_id, None)
            return "give_up"

    status_entry["retry_count"] = retry["count"]
    status_entry["retry_expected_on"] = expected_on
    command_retries[device_id] = retry
    return None


def _apply_manual_override(entry_data, device_id, status_entry, device_on_state, now) -> bool:
    """Return True when an active manual override should skip control this cycle."""
    manual_overrides = entry_data.get("manual_overrides", {})
    if device_id not in manual_overrides:
        return False
    override = manual_overrides[device_id]
    elapsed = (now - override["since"]).total_seconds()
    if elapsed > MANUAL_OVERRIDE_TTL_SECONDS:
        log_debug(f"[manual_override] Override expired for {device_id} after {elapsed:.0f}s")
        del manual_overrides[device_id]
        return False
    status_entry["manual_override"] = True
    status_entry["refusal_reasons"].append(
        f"Manual override ({int(MANUAL_OVERRIDE_TTL_SECONDS - elapsed)}s remaining)"
    )
    device_on_state[device_id] = override["state"]
    log_debug(
        f"[manual_override] Skipping auto-control for {device_id}, "
        f"override active for {elapsed:.0f}s"
    )
    return True


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


def _sync_initial_device_states(hass, devices, device_on_state, entry_data) -> None:
    """First-run-after-startup sync of ``device_on_state`` from actual HA entity states.

    Without this, every device defaults to ``False`` (off) on a fresh
    integration load and the hysteresis thresholds for ``prev_on=True`` would
    never trigger correctly. Runs at most once per integration setup.
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
            device.get(CONF_DEVICE_TYPE) == DEVICE_TYPE_CUSTOM
            and status_entry
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
    """Enforce min-on-time and record off-time bookkeeping. Returns possibly-updated ``is_active``."""
    if is_active and not prev_on_before_calc:
        log_debug(f"[min_on_time] Device {device_id} just turned ON, recording last_on_time={now}")
        device_on_time_state.setdefault(device_id, {})["last_on_time"] = now
        status_entry["last_on_time"] = now
        startup_grace = float(device.get(KEY_STARTUP_GRACE_PERIOD, DEFAULT_STARTUP_GRACE_PERIOD))
        if startup_grace > 0:
            _record_grace_deadline(hass, config_entry, device_on_time_state, device_id, now, startup_grace)

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

    device_on_time_state.setdefault(device_id, {})["last_off_time"] = now
    device_on_time_state[device_id].pop("last_on_time", None)
    device_on_time_state[device_id].pop("startup_until", None)
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
    strategy, proportional_allocations, remaining_power,
):
    """Forward to the per-type control coroutine and return ``(power_used, status_entry)``."""
    device_id = device.get(CONF_DEVICE_ID)
    device_type = device.get(CONF_DEVICE_TYPE)

    if device_type == DEVICE_TYPE_STANDARD:
        return await _control_standard_device(
            hass, device, is_active, prev_on, remaining_power, cfg, status_entry, device_on_state,
        )

    if device_type == DEVICE_TYPE_CUSTOM:
        # Under DISTRIBUTE_EVENLY a device not pre-allocated as proportional must
        # NOT consume the entire remaining budget. Under FILL_ONE_BY_ONE the next
        # device greedily takes whatever is still left.
        if strategy == STRATEGY_DISTRIBUTE_EVENLY:
            power_to_allocate = proportional_allocations.get(device_id, 0.0)
        else:
            power_to_allocate = proportional_allocations.get(device_id, remaining_power)
        return await _control_custom_device(
            hass, device, is_active, prev_on, power_to_allocate, cfg, status_entry, device_on_state,
        )

    return 0.0, status_entry


async def _control_one_device(
    hass, config_entry, device, *,
    cfg, entry_data, now, strategy, proportional_allocations, remaining_power,
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

    filter_reason = await _filter_device(hass, device, now)
    log_debug(f"Filter reason for {device_id}: {filter_reason}")

    if entry_data.get("device_retry_failed", {}).get(device_id):
        status_entry["retry_failed"] = True

    if filter_reason:
        if device_id:
            entry_data["device_filter_reasons"][device_id] = filter_reason
            status_entry["refusal_reasons"] = [filter_reason]
            entry_data.setdefault("command_retries", {}).pop(device_id, None)
            entry_data.setdefault("device_retry_failed", {}).pop(device_id, None)
        return 0.0

    # Reconcile expected vs actual; "give_up" = unresponsive ON beyond max retries.
    if _detect_external_change(
        hass, device, device_id, entry_data, status_entry, device_on_state, now
    ) == "give_up":
        return 0.0

    if _apply_manual_override(entry_data, device_id, status_entry, device_on_state, now):
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

    log_debug(f"Control logic for {device_id}: prev_on={prev_on}, prev_on_before_calc={prev_on_before_calc}")
    power_used, _ = await _dispatch_device_control(
        hass, device, is_active, prev_on, status_entry, cfg, device_on_state,
        strategy, proportional_allocations, remaining_power,
    )

    if device_id and is_active != prev_on_before_calc:
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
    entry_data.setdefault("device_on_time_state", {})

    auto_control_devices = _initialize_run(entry_data, cfg.get(CONF_DEVICES, []))
    _sync_initial_device_states(hass, auto_control_devices, device_on_state, entry_data)
    log_debug(f"auto_control_devices: {auto_control_devices}")

    for device in auto_control_devices:
        device_id = device.get(CONF_DEVICE_ID)
        entry_data["device_status"][device_id] = _initialize_status_entry(hass, device)

    remaining_power = excess_power
    strategy = cfg.get(CONF_DEVICE_ALLOCATION_STRATEGY, STRATEGY_FILL_ONE_BY_ONE)
    proportional_allocations: dict = {}
    if strategy == STRATEGY_DISTRIBUTE_EVENLY:
        proportional_allocations = _compute_proportional_allocations(
            auto_control_devices,
            entry_data["device_status"],
            remaining_power,
            dict(entry_data["device_on_state"]),
            {k: dict(v) for k, v in entry_data["device_debounce_state"].items()},
            cfg, now,
        )

    for device in auto_control_devices:
        power_used = await _control_one_device(
            hass, config_entry, device,
            cfg=cfg, entry_data=entry_data, now=now, strategy=strategy,
            proportional_allocations=proportional_allocations,
            remaining_power=remaining_power,
        )
        remaining_power -= power_used
        log_debug(
            f"Power used by {device.get(CONF_DEVICE_ID)}: {power_used}, "
            f"remaining_power: {remaining_power}"
        )

    _finalize_run(entry_data, excess_power, remaining_power)
    async_dispatcher_send(hass, f"{SIGNAL_POWER_DISTRIBUTION_UPDATED}_{config_entry.entry_id}")
