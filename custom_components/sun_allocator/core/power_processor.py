"""Main power processing logic for Sun Allocator."""

import datetime as dt_stdlib
import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.exceptions import HomeAssistantError
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_ON,
    SERVICE_TURN_OFF,
    STATE_UNKNOWN,
    STATE_UNAVAILABLE,
    STATE_ON,
)

# Local imports from the same 'core' directory
from .logger import log_debug, log_warning, log_error
from .schedule import is_device_in_schedule

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
    DOMAIN_LIGHT,
    DOMAIN_SWITCH,
    DOMAIN_INPUT_BOOLEAN,
    DOMAIN_AUTOMATION,
    DOMAIN_SCRIPT,
    DOMAIN_CLIMATE,
    MAX_BRIGHTNESS,
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

# Supported domains for auto-control
SUPPORTED_DOMAINS = {
    DOMAIN_LIGHT,
    DOMAIN_SWITCH,
    DOMAIN_INPUT_BOOLEAN,
    DOMAIN_AUTOMATION,
    DOMAIN_SCRIPT,
    DOMAIN_CLIMATE,
}


def _initialize_run(entry_data, devices_config):
    """Initialize states for the processing run."""
    power_allocation = entry_data.get(CONF_POWER_ALLOCATION, {})
    for dev_id in power_allocation:
        power_allocation[dev_id] = 0

    entry_data.setdefault("device_status", {})
    entry_data["device_filter_reasons"] = {}
    entry_data["ramp_targets"] = {}

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
    relay_entity = device.get(CONF_DEVICE_ENTITY)

    if relay_entity and "|" in relay_entity:
        relay_entity = relay_entity.split("|")[0]

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

    if not is_device_in_schedule(device, now):
        log_debug(f"Device '{device_name}' skipped: Outside of schedule.")
        is_device_on = (
            relay_state_obj.state != "off"
            if service_domain == DOMAIN_CLIMATE
            else relay_state_obj.state == STATE_ON
        )
        if is_device_on:
            try:
                if service_domain == DOMAIN_CLIMATE:
                    await hass.services.async_call(
                        service_domain, "set_hvac_mode",
                        {ATTR_ENTITY_ID: relay_entity, "hvac_mode": "off"},
                        blocking=True,
                    )
                else:
                    await hass.services.async_call(
                        service_domain, SERVICE_TURN_OFF,
                        {ATTR_ENTITY_ID: relay_entity}, blocking=True,
                    )
            except HomeAssistantError as exc:
                log_error(f"Failed to turn off {relay_entity} (outside schedule): {exc}")
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
                    log_debug(f"Device {device_name}: Counter-debounce elapsed={counter_elapsed:.1f}s / {debounce_time_s * 0.5:.1f}s")
                    if counter_elapsed >= debounce_time_s * 0.5:
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
    relay_entity = device.get(CONF_DEVICE_ENTITY)
    device_id = device.get(CONF_DEVICE_ID)
    device_name = device.get(CONF_DEVICE_NAME)
    service_domain = relay_entity.split(".")[0]
    hvac_mode = device.get("hvac_mode")

    actual_state = hass.states.get(relay_entity)
    if actual_state is None:
        is_actually_on = False
    elif service_domain == DOMAIN_CLIMATE:
        is_actually_on = actual_state.state != "off"
    else:
        is_actually_on = actual_state.state == STATE_ON

    if is_active:
        if device_id:
            device_on_state[device_id] = True

        if not prev_on or not is_actually_on:
            log_debug(f"Turning on standard device {device_name} (prev_on={prev_on}, actual={actual_state.state if actual_state else 'N/A'})")
            service_data = {ATTR_ENTITY_ID: relay_entity}
            service_name = SERVICE_TURN_ON
            if service_domain == DOMAIN_LIGHT:
                service_data[ATTR_BRIGHTNESS] = MAX_BRIGHTNESS
            elif service_domain == DOMAIN_CLIMATE:
                service_name = "set_hvac_mode"
                service_data["hvac_mode"] = hvac_mode or "heat"
            try:
                await hass.services.async_call(service_domain, service_name, service_data, blocking=True)
            except HomeAssistantError as exc:
                log_error(f"Failed to turn on {device_name} ({relay_entity}): {exc}")

        power_used = status_entry["min_expected_w"]
        status_entry.update({"allocated_w": float(power_used), "percent_target": 100.0, "percent_actual": 100.0})
    else:
        if device_id:
            device_on_state[device_id] = False
        if prev_on or is_actually_on:
            log_debug(f"Turning off standard device {device_name} (remaining={remaining_power}W)")
            service_name = SERVICE_TURN_OFF
            service_data = {ATTR_ENTITY_ID: relay_entity}
            if service_domain == DOMAIN_CLIMATE:
                service_name = "set_hvac_mode"
                service_data["hvac_mode"] = "off"
            try:
                await hass.services.async_call(service_domain, service_name, service_data, blocking=True)
            except HomeAssistantError as exc:
                log_error(f"Failed to turn off {device_name} ({relay_entity}): {exc}")

        status_entry.update({"percent_target": 0.0, "percent_actual": 0.0, "allocated_w": 0.0})

    return power_used, status_entry


async def _control_custom_device(
    hass, device, is_active, prev_on, power_to_allocate, cfg, status_entry, ramp_targets, device_on_state
):
    """Control logic for a custom (ESPHome) device."""
    power_used = 0.0
    device_name = device.get(CONF_DEVICE_NAME)
    relay_entity = device.get(CONF_DEVICE_ENTITY)

    if not relay_entity or "." not in relay_entity:
        log_warning(f"Device {device_name} has no valid entity_id, skipping control")
        return 0.0, status_entry

    service_domain = relay_entity.split(".")[0]

    if status_entry.get("mode") == RELAY_MODE_PROPORTIONAL:
        if is_active:
            max_w = status_entry["max_expected_w"]
            target_percent = 0.0
            if max_w <= 0:
                log_warning(f"Device {device_name} in Proportional has no max_expected_w; forcing 0%/OFF")
            else:
                power_percent = min(MAX_PERCENTAGE, max(5, (power_to_allocate / max_w) * 100))
                target_percent = power_percent
            log_debug(f"Proportional target for {device_name}: {target_percent}% ({power_to_allocate}W)")
            status_entry["percent_target"] = float(target_percent)
            if service_domain == DOMAIN_LIGHT:
                ramp_targets[relay_entity] = target_percent
            elif not prev_on:
                try:
                    await hass.services.async_call(
                        service_domain, SERVICE_TURN_ON, {ATTR_ENTITY_ID: relay_entity}, blocking=True,
                    )
                except HomeAssistantError as exc:
                    log_error(f"Failed to turn on {device_name} ({relay_entity}): {exc}")
            power_used = min(power_to_allocate, max_w * (target_percent / MAX_PERCENTAGE))
            status_entry["allocated_w"] = float(power_used)
        else:
            log_debug(f"Proportional below threshold for {device_name} -> target 0 / OFF")
            if service_domain == DOMAIN_LIGHT:
                ramp_targets[relay_entity] = 0.0
            elif prev_on:
                try:
                    await hass.services.async_call(
                        service_domain, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: relay_entity}, blocking=True,
                    )
                except HomeAssistantError as exc:
                    log_error(f"Failed to turn off {device_name} ({relay_entity}): {exc}")

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


def _finalize_run(entry_data, excess_power, remaining_power):
    """Update global state and prepare for dispatcher signal."""
    epsilon = 1e-9
    allocation = entry_data.get(CONF_POWER_ALLOCATION, {}).copy()
    for k, v in allocation.items():
        if abs(v) < epsilon:
            allocation[k] = 0.0

    _finalize_device_status(entry_data)

    entry_data[CONF_POWER_DISTRIBUTION] = {
        "total_power": excess_power,
        "remaining_power": remaining_power,
        "allocated_power": excess_power - remaining_power,
        "allocation": allocation,
    }


async def process_excess_power(
    hass: HomeAssistant, config_entry: ConfigType, excess_power: float
):
    """Process excess power value and control devices accordingly."""
    log_debug(f"--- process_excess_power START, excess_power={excess_power} ---")
    now = dt_util.now()
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    cfg = config_entry.data
    log_debug(f"entry_data keys: {list(entry_data.keys())}")

    device_on_state = entry_data.setdefault("device_on_state", {})
    device_debounce_state = entry_data.setdefault("device_debounce_state", {})
    device_on_time_state = entry_data.setdefault("device_on_time_state", {})

    auto_control_devices = _initialize_run(entry_data, cfg.get(CONF_DEVICES, []))

    # On first run after startup, sync device_on_state with actual HA entity states.
    # Without this, all devices default to False (off), causing wrong hysteresis thresholds.
    if not entry_data.get("_device_on_state_initialized"):
        for _dev in auto_control_devices:
            _dev_id = _dev.get(CONF_DEVICE_ID)
            _relay = _dev.get(CONF_DEVICE_ENTITY)
            if _relay and "." in _relay:
                if "|" in _relay:
                    _relay = _relay.split("|")[0]
                _state = hass.states.get(_relay)
                if _state and _state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                    _domain = _relay.split(".")[0]
                    _is_on = _state.state != "off" if _domain == DOMAIN_CLIMATE else _state.state == STATE_ON
                    device_on_state[_dev_id] = _is_on
                    log_debug(f"[init] Synced device_on_state[{_dev_id}] = {_is_on} from actual state")
        entry_data["_device_on_state_initialized"] = True
    log_debug(f"auto_control_devices: {auto_control_devices}")

    for device in auto_control_devices:
        device_id = device.get(CONF_DEVICE_ID)
        entry_data["device_status"][device_id] = _initialize_status_entry(hass, device)

    remaining_power = excess_power
    proportional_allocations = {}
    strategy = cfg.get(CONF_DEVICE_ALLOCATION_STRATEGY, STRATEGY_FILL_ONE_BY_ONE)

    if strategy == STRATEGY_DISTRIBUTE_EVENLY:
        proportional_devices = []
        total_proportional_max_w = 0
        for device in auto_control_devices:
            device_id = device.get(CONF_DEVICE_ID)
            status_entry = entry_data["device_status"].get(device_id)
            if device.get(CONF_DEVICE_TYPE) == DEVICE_TYPE_CUSTOM and status_entry and status_entry.get("mode") == RELAY_MODE_PROPORTIONAL:
                is_active, _ = _calculate_device_state(device, remaining_power, device_on_state, device_debounce_state, cfg, now)
                if is_active:
                    proportional_devices.append(device)
                    total_proportional_max_w += status_entry["max_expected_w"]

        if total_proportional_max_w > 0:
            for device in proportional_devices:
                device_id = device.get(CONF_DEVICE_ID)
                status_entry = entry_data["device_status"].get(device_id)
                device_share = status_entry["max_expected_w"] / total_proportional_max_w
                proportional_allocations[device_id] = remaining_power * device_share

    for device in auto_control_devices:
        device_id = device.get(CONF_DEVICE_ID)
        log_debug(f"Looping for device: {device_id}")

        status_entry = entry_data["device_status"].get(device_id)
        if not status_entry:
            log_warning(f"Could not find status_entry for device {device_id}, skipping.")
            continue

        filter_reason = await _filter_device(hass, device, now)
        log_debug(f"Filter reason for {device_id}: {filter_reason}")

        if filter_reason:
            if device_id:
                entry_data["device_filter_reasons"][device_id] = filter_reason
                status_entry["refusal_reasons"] = [filter_reason]
            continue

        # --- Manual Override Detection ---
        # Detect when actual HA entity state diverges from what auto-control set.
        # Only trigger if entity state changed AFTER our last command (avoids false overrides on slow devices).
        manual_overrides = entry_data.setdefault("manual_overrides", {})
        _relay_entity = device.get(CONF_DEVICE_ENTITY)
        if _relay_entity and "|" in _relay_entity:
            _relay_entity = _relay_entity.split("|")[0]
        _actual_state = hass.states.get(_relay_entity) if _relay_entity else None
        _expected_on = device_on_state.get(device_id)

        if _actual_state and _actual_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE) and _expected_on is not None:
            _service_domain = _relay_entity.split(".")[0] if _relay_entity else ""
            _actual_on = _actual_state.state != "off" if _service_domain == DOMAIN_CLIMATE else _actual_state.state == STATE_ON
            _last_controlled = entry_data.get("last_controlled_at", {}).get(device_id)
            # Only treat as manual override if the entity state changed AFTER our last command.
            # If last_changed is before our command, the device hasn't responded yet — not an override.
            _state_changed_after_command = (
                _last_controlled is None
                or _actual_state.last_changed >= _last_controlled
            )
            if _actual_on != _expected_on and _state_changed_after_command:
                if device_id not in manual_overrides:
                    log_debug(f"[manual_override] Detected external state change for {device_id}: expected={_expected_on}, actual={_actual_on}")
                    manual_overrides[device_id] = {"since": now, "state": _actual_on}
                    device_on_state[device_id] = _actual_on

        if device_id in manual_overrides:
            _override = manual_overrides[device_id]
            _override_elapsed = (now - _override["since"]).total_seconds()
            if _override_elapsed > 300:
                log_debug(f"[manual_override] Override expired for {device_id} after {_override_elapsed:.0f}s")
                del manual_overrides[device_id]
            else:
                status_entry["manual_override"] = True
                status_entry["refusal_reasons"].append(f"Manual override ({int(300 - _override_elapsed)}s remaining)")
                device_on_state[device_id] = _override["state"]
                log_debug(f"[manual_override] Skipping auto-control for {device_id}, override active for {_override_elapsed:.0f}s")
                continue

        # Save prev_on BEFORE _calculate_device_state, since that function updates device_on_state
        prev_on_before_calc = bool(device_on_state.get(device_id, False))

        is_active, is_active_candidate = _calculate_device_state(
            device, remaining_power, device_on_state, device_debounce_state, cfg, now
        )

        log_debug(f"Calculated state for {device_id}: is_active={is_active}, is_active_candidate={is_active_candidate}")
        status_entry["is_active_candidate"] = is_active_candidate

        # Use prev_on_before_calc — the state BEFORE _calculate_device_state modified device_on_state
        prev_on = prev_on_before_calc

        # --- Minimum On-Time Logic ---
        min_on_time = status_entry.get(CONF_DEVICE_MIN_ON_TIME, 0)

        # OFF->ON transition: use prev_on_before_calc, NOT prev_on after state calculation
        if is_active and not prev_on_before_calc:
            log_debug(f"[min_on_time] Device {device_id} just turned ON, recording last_on_time={now}")
            device_on_time_state.setdefault(device_id, {})["last_on_time"] = now
            status_entry["last_on_time"] = now

            # Record startup grace period deadline
            startup_grace = float(device.get(KEY_STARTUP_GRACE_PERIOD, DEFAULT_STARTUP_GRACE_PERIOD))
            if startup_grace > 0:
                startup_until = now + dt_stdlib.timedelta(seconds=startup_grace)
                device_on_time_state[device_id]["startup_until"] = startup_until
                log_debug(f"[grace] Startup grace period set for {device_id}: {startup_grace}s until {startup_until}")

        last_on_time = device_on_time_state.get(device_id, {}).get("last_on_time")
        log_debug(f"[min_on_time] now={now}, last_on_time={last_on_time}, prev_on_before_calc={prev_on_before_calc}, is_active={is_active}")

        # min_on_time check: device was ON and we now want to turn it off
        if prev_on_before_calc and not is_active:
            log_debug(f"[min_on_time] Checking min_on_time for {device_id}")
            if min_on_time > 0 and last_on_time:
                elapsed = (now - last_on_time).total_seconds()
                log_debug(f"[min_on_time] elapsed={elapsed:.2f}s, required={min_on_time}s")
                if elapsed < min_on_time:
                    is_active = True
                    status_entry["refusal_reasons"].append(f"Minimum on-time not yet elapsed: {elapsed:.1f}s < {min_on_time}s")
                    log_debug(f"[min_on_time] Keeping {device_id} ON (min_on_time not elapsed)")
                else:
                    log_debug(f"[min_on_time] Allowing turn off for {device_id}")
                    device_on_time_state.setdefault(device_id, {})["last_off_time"] = now
                    device_on_time_state[device_id].pop("last_on_time", None)
                    device_on_time_state[device_id].pop("startup_until", None)
                    status_entry["last_off_time"] = now
            else:
                log_debug(f"[min_on_time] No restriction for {device_id}, allowing turn off")
                device_on_time_state.setdefault(device_id, {})["last_off_time"] = now
                device_on_time_state[device_id].pop("last_on_time", None)
                device_on_time_state[device_id].pop("startup_until", None)
                status_entry["last_off_time"] = now

        # --- Startup Grace Period Logic ---
        startup_grace = float(device.get(KEY_STARTUP_GRACE_PERIOD, DEFAULT_STARTUP_GRACE_PERIOD))
        if startup_grace > 0 and not is_active and prev_on_before_calc:
            startup_until = device_on_time_state.get(device_id, {}).get("startup_until")
            if startup_until:
                # Convert from string if needed (value was persisted before HA restart)
                if isinstance(startup_until, str):
                    startup_until = dt_stdlib.datetime.fromisoformat(startup_until)
                if now < startup_until:
                    is_active = True
                    remaining_grace = (startup_until - now).total_seconds()
                    elapsed_grace = startup_grace - remaining_grace
                    log_debug(f"[grace] Keeping {device_id} ON during startup grace ({elapsed_grace:.1f}s elapsed, {remaining_grace:.1f}s remaining)")
                    status_entry["refusal_reasons"].append(f"Startup grace period: {remaining_grace:.0f}s remaining")
                else:
                    device_on_time_state.get(device_id, {}).pop("startup_until", None)
                    log_debug(f"[grace] Startup grace period expired for {device_id}")

        log_debug(f"[POST-MIN-ON-TIME] status_entry for {device_id}: {status_entry}")

        power_used = 0.0
        log_debug(f"Control logic for {device_id}: prev_on={prev_on}, prev_on_before_calc={prev_on_before_calc}")

        if device.get(CONF_DEVICE_TYPE) == DEVICE_TYPE_STANDARD:
            power_used, status_entry = await _control_standard_device(
                hass, device, is_active, prev_on, remaining_power, cfg, status_entry, device_on_state
            )
        elif device.get(CONF_DEVICE_TYPE) == DEVICE_TYPE_CUSTOM:
            power_to_allocate = proportional_allocations.get(device_id, remaining_power)
            power_used, status_entry = await _control_custom_device(
                hass,
                device,
                is_active,
                prev_on,
                power_to_allocate,
                cfg,
                status_entry,
                entry_data["ramp_targets"],
                device_on_state,
            )

        remaining_power -= power_used
        log_debug(f"Power used by {device_id}: {power_used}, remaining_power: {remaining_power}")

        # Track when we last controlled this device (used by manual override detection)
        if device_id and is_active != prev_on_before_calc:
            entry_data.setdefault("last_controlled_at", {})[device_id] = now

        if device_id:
            entry_data[CONF_POWER_ALLOCATION][device_id] = power_used

    _finalize_run(entry_data, excess_power, remaining_power)
    async_dispatcher_send(hass, f"{SIGNAL_POWER_DISTRIBUTION_UPDATED}_{config_entry.entry_id}")
