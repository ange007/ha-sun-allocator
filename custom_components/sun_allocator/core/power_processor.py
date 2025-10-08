"""Main power processing logic for Sun Allocator."""

import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_ON,
    SERVICE_TURN_OFF,
    STATE_UNKNOWN,
    STATE_UNAVAILABLE,
    STATE_ON,
)

# Local imports from the same 'core' directory
from .logger import log_debug, log_warning
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
    # Reset power allocation for all devices
    power_allocation = entry_data.get(CONF_POWER_ALLOCATION, {})
    for dev_id in power_allocation:
        power_allocation[dev_id] = 0

    # Initialize dictionaries for the current run
    entry_data.setdefault("device_status", {})
    entry_data["device_filter_reasons"] = {}
    entry_data["ramp_targets"] = {}

    # Get and sort devices with auto-control enabled
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
        parts = relay_entity.split("|")
        relay_entity = parts[0]

    service_domain = (
        relay_entity.split(".")[0] if relay_entity and "." in relay_entity else None
    )

    # 1. Check for supported entity
    if not relay_entity or service_domain not in SUPPORTED_DOMAINS:
        log_warning(f"Device '{device_name}' skipped: Unsupported or missing entity_id: {relay_entity}")
        return "Unsupported or missing entity_id"

    # 2. Check for entity availability
    relay_state_obj = hass.states.get(relay_entity)
    if relay_state_obj is None or relay_state_obj.state in (
        STATE_UNKNOWN,
        STATE_UNAVAILABLE,
    ):
        log_debug(f"Device '{device_name}' skipped: Entity {relay_entity} not found or unavailable.")
        return "Entity unavailable or not found"

    # 3. Check schedule
    if not is_device_in_schedule(device, now):
        log_debug(f"Device '{device_name}' skipped: Outside of schedule.")

        # Ensure device is turned off if it's outside of its schedule
        if relay_state_obj.state == STATE_ON:
            await hass.services.async_call(
                service_domain,
                SERVICE_TURN_OFF,
                {ATTR_ENTITY_ID: relay_entity},
                blocking=True,
            )

        return "Outside of schedule"

    return None  # No filter reason means the device is valid


def _calculate_device_state(
    device, excess_power, device_on_state, device_debounce_state, cfg, now
):
    """Calculate the desired state (on/off) for a device based on power, hysteresis, and debounce.
    
    Args:
        device: Device configuration dictionary
        excess_power: Total available excess power before any device allocations
        device_on_state: Dictionary of current device states
        device_debounce_state: Dictionary of device debounce states
        cfg: Configuration dictionary
        now: Current datetime
    """
    device_id = device.get(CONF_DEVICE_ID)
    device_name = device.get(CONF_DEVICE_NAME)

    log_debug(f"[STATE_DEBUG] Device {device_name}: Starting state calculation")
    log_debug(f"[STATE_DEBUG] Current device_on_state: {device_on_state.get(device_id)}")
    log_debug(f"[STATE_DEBUG] Current debounce_state: {device_debounce_state.get(device_id)}")

    min_expected_w = float(device.get(CONF_DEVICE_MIN_EXPECTED_W, 0) or 0)
    hysteresis_w = float(cfg.get(CONF_HYSTERESIS_W, DEFAULT_HYSTERESIS_W))

    # Hysteresis and threshold calculation
    effective_min_power = min_expected_w
    on_threshold = effective_min_power
    off_threshold = max(0.0, effective_min_power - hysteresis_w)

    prev_on = bool(device_on_state.get(device_id, False))
    is_active_candidate = excess_power >= (
        off_threshold if prev_on else on_threshold
    )

    log_debug(f"Device {device_name}: excess_power={excess_power}, on_threshold={on_threshold}, off_threshold={off_threshold}, prev_on={prev_on}, is_active_candidate={is_active_candidate}")

    # Debouncer logic
    debounce_time_s = device.get(CONF_DEVICE_DEBOUNCE_TIME, DEFAULT_DEBOUNCE_TIME)
    # Initialize or get debounce info
    if device_id not in device_debounce_state:
        log_debug(f"Device {device_name}: Initializing new debounce state")
        device_debounce_state[device_id] = {"candidate_state": None, "state_change_time": None}

    debounce_info = device_debounce_state[device_id]
    log_debug(f"Device {device_name}: Current debounce info: {debounce_info}")
    log_debug(f"Device {device_name}: debounce check starting with prev_on={prev_on}")

    if debounce_time_s == 0:
        is_active = is_active_candidate  # No debounce
        log_debug(f"Device {device_name}: No debounce needed, setting state to {is_active}")
        # Immediate state update when no debounce
        device_on_state[device_id] = is_active
    else:
        is_active = prev_on  # Default to previous state
        log_debug(f"Device {device_name}: Checking debounce with candidate state={is_active_candidate}")
        
        # If state matches candidate, update completion time
        if is_active_candidate == prev_on:
            debounce_info["state_change_time"] = None  # Mark as completed
            # Maintain state since it matches what we want
            device_on_state[device_id] = prev_on
        # State has changed from current state
        elif is_active_candidate != prev_on:
            if debounce_info["state_change_time"] is None:
                # Start debounce timer for new state change
                log_debug(f"Device {device_name}: Starting debounce timer for state change {prev_on} -> {is_active_candidate}")
                log_debug(f"Device {device_name}: Current on_state={device_on_state.get(device_id)}, setting candidate_state={is_active_candidate}")
                debounce_info["candidate_state"] = is_active_candidate
                debounce_info["state_change_time"] = now
                device_debounce_state[device_id] = debounce_info
            else:
                # Check if debounce period has completed and candidate matches our current target
                debounce_elapsed = (now - debounce_info["state_change_time"]).total_seconds()
                log_debug(f"Device {device_name}: Checking debounce elapsed={debounce_elapsed}s vs required={debounce_time_s}s, candidate={debounce_info['candidate_state']} vs target={is_active_candidate}")

                if debounce_elapsed >= debounce_time_s:
                    # Debounce period complete
                    if debounce_info["candidate_state"] == is_active_candidate:
                        # Candidate matches current target, apply it
                        is_active = is_active_candidate
                        # Let _control_standard_device handle updating device_on_state
                        log_debug(f"Device {device_name}: State transition complete: {prev_on} -> {is_active}")
                        
                        # Keep the current candidate but clear timer to mark completion
                        debounce_info["state_change_time"] = None
                        device_debounce_state[device_id] = debounce_info
                    else:
                        # Candidate doesn't match current target, start new debounce
                        log_debug(f"Device {device_name}: Starting new debounce - candidate no longer matches target")
                        debounce_info["candidate_state"] = is_active_candidate
                        debounce_info["state_change_time"] = now
                        device_debounce_state[device_id] = debounce_info
                else:
                    log_debug(f"Device {device_name}: Still in debounce period ({debounce_elapsed}s < {debounce_time_s}s)")
        else:
            # Keep tracking the candidate state even when it matches current
            # But reset the timer if we have one from a previous incomplete transition
            if debounce_info["state_change_time"] is not None:
                debounce_info["state_change_time"] = None  # Clear the timer, keep the candidate
                device_debounce_state[device_id] = debounce_info
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

    if is_active:
        # First update internal state tracking
        if device_id:
            device_on_state[device_id] = True
        
        # Then call HA service
        log_debug(f"Turning on standard device {device_name} because state is active (prev_on={prev_on})")
        service_data = {ATTR_ENTITY_ID: relay_entity}
        service_name = SERVICE_TURN_ON
        if service_domain == DOMAIN_LIGHT:
            service_data[ATTR_BRIGHTNESS] = MAX_BRIGHTNESS
        elif service_domain == DOMAIN_CLIMATE:
            service_name = "set_hvac_mode"
            service_data["hvac_mode"] = hvac_mode or "heat"
        
        log_debug(f"Calling service {service_domain}.{service_name} with data {service_data}")
        await hass.services.async_call(
            service_domain, service_name, service_data, blocking=True
        )

        power_used = status_entry["min_expected_w"]
        status_entry.update(
            {
                "allocated_w": float(power_used),
                "percent_target": 100.0,
                "percent_actual": 100.0,
            }
        )
    else:
        # First update internal state
        if device_id:
            device_on_state[device_id] = False
            
        # Then turn off if needed
        if prev_on:
            log_debug(f"Turning off standard device {device_name} (remaining power {remaining_power}W below threshold, prev_on={prev_on})")
            service_name = SERVICE_TURN_OFF
            service_data = {ATTR_ENTITY_ID: relay_entity}
            if service_domain == DOMAIN_CLIMATE:
                service_name = "set_hvac_mode"
                service_data["hvac_mode"] = "off"

            log_debug(f"Calling service {service_domain}.{service_name} with data {service_data}")
            await hass.services.async_call(
                service_domain, service_name, service_data, blocking=True
            )

        status_entry.update(
            {"percent_target": 0.0, "percent_actual": 0.0, "allocated_w": 0.0}
        )

    return power_used, status_entry


async def _control_custom_device(
    hass, device, is_active, prev_on, power_to_allocate, cfg, status_entry, ramp_targets
):
    """Control logic for a custom (ESPHome) device."""
    power_used = 0.0
    device_name = device.get(CONF_DEVICE_NAME)
    relay_entity = device.get(CONF_DEVICE_ENTITY)
    service_domain = relay_entity.split(".")[0]

    if status_entry.get("mode") == RELAY_MODE_PROPORTIONAL:
        if is_active:
            max_w = status_entry["max_expected_w"]
            target_percent = 0.0
            if max_w <= 0:
                log_warning(f"Device {device_name} in Proportional has no max_expected_w; forcing 0%/OFF")
            else:
                power_percent = min(
                    MAX_PERCENTAGE, max(5, (power_to_allocate / max_w) * 100)
                )
                target_percent = power_percent

            log_debug(f"Proportional target for {device_name}: {target_percent}% (power to allocate: {power_to_allocate}W)")
            status_entry["percent_target"] = float(target_percent)

            if service_domain == DOMAIN_LIGHT:
                ramp_targets[relay_entity] = target_percent
            elif not prev_on:
                log_debug(f"Calling service {service_domain}.{SERVICE_TURN_ON} with data {{ATTR_ENTITY_ID: {relay_entity}}}")
                await hass.services.async_call(
                    service_domain,
                    SERVICE_TURN_ON,
                    {ATTR_ENTITY_ID: relay_entity},
                    blocking=True,
                )

            power_used = min(power_to_allocate, max_w * (target_percent / MAX_PERCENTAGE))
            status_entry["allocated_w"] = float(power_used)
        else:
            log_debug(f"Proportional below threshold for {device_name} -> target 0 / OFF")
            if service_domain == DOMAIN_LIGHT:
                ramp_targets[relay_entity] = 0.0
            elif prev_on:
                log_debug(f"Calling service {service_domain}.{SERVICE_TURN_OFF} with data {{ATTR_ENTITY_ID: {relay_entity}}}")
                await hass.services.async_call(
                    service_domain,
                    SERVICE_TURN_OFF,
                    {ATTR_ENTITY_ID: relay_entity},
                    blocking=True,
                )

    elif status_entry.get("mode") == RELAY_MODE_ON:
        # This logic is identical to a standard device
        power_used, status_entry = await _control_standard_device(
            hass, device, is_active, prev_on, power_to_allocate, cfg, status_entry, {}
        )

    return power_used, status_entry


def _finalize_device_status(entry_data):
    """Finalize device status by converting datetime objects to strings."""
    for device_id, status in entry_data.get("device_status", {}).items():
        if "last_on_time" in status and status["last_on_time"] and not isinstance(status["last_on_time"], str):
            status["last_on_time"] = status["last_on_time"].isoformat()
        if "last_off_time" in status and status["last_off_time"] and not isinstance(status["last_off_time"], str):
            status["last_off_time"] = status["last_off_time"].isoformat()


def _finalize_run(entry_data, excess_power, remaining_power):
    """Update global state and prepare for dispatcher signal."""
    # Trim the remainder to less than epsilon
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
    # device_status, device_filter_reasons, device_on_state, device_debounce_state are updated by reference


async def process_excess_power(
    hass: HomeAssistant, config_entry: ConfigType, excess_power: float
):
    """Process excess power value and control devices accordingly."""

    log_debug(f"--- process_excess_power START, excess_power={excess_power} ---")
    now = dt_util.now()
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    cfg = config_entry.data
    log_debug(f"entry_data keys: {list(entry_data.keys())}")

    # Ensure state dictionaries exist and get a reference to them
    device_on_state = entry_data.setdefault("device_on_state", {})
    device_debounce_state = entry_data.setdefault("device_debounce_state", {})
    device_on_time_state = entry_data.setdefault("device_on_time_state", {})  # Track last on/off times

    # 1. Initialize states for the run
    auto_control_devices = _initialize_run(entry_data, cfg.get(CONF_DEVICES, []))
    log_debug(f"auto_control_devices: {auto_control_devices}")

    # Initialize/update device_status for all devices at the beginning
    for device in auto_control_devices:
        device_id = device.get(CONF_DEVICE_ID)
        entry_data["device_status"][device_id] = _initialize_status_entry(hass, device)

    remaining_power = excess_power
    proportional_allocations = {}
    strategy = cfg.get(CONF_DEVICE_ALLOCATION_STRATEGY, STRATEGY_FILL_ONE_BY_ONE)

    if strategy == STRATEGY_DISTRIBUTE_EVENLY:
        # Pre-calculate power for proportional devices
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
            power_for_distribution = remaining_power
            for device in proportional_devices:
                device_id = device.get(CONF_DEVICE_ID)
                status_entry = entry_data["device_status"].get(device_id)
                device_share = status_entry["max_expected_w"] / total_proportional_max_w
                proportional_allocations[device_id] = power_for_distribution * device_share

    # 2. Main processing loop
    for device in auto_control_devices:
        device_id = device.get(CONF_DEVICE_ID)
        log_debug(f"Looping for device: {device_id}")

        status_entry = entry_data["device_status"].get(device_id)
        if not status_entry:
            log_warning(f"Could not find status_entry for device {device_id}, skipping.")
            continue

        # 2a. Filter out invalid or out-of-schedule devices
        filter_reason = await _filter_device(hass, device, now)
        log_debug(f"Filter reason for {device_id}: {filter_reason}")
        
        if filter_reason:
            if device_id:
                entry_data["device_filter_reasons"][device_id] = filter_reason
                status_entry["refusal_reasons"] = [filter_reason]
            continue

        log_debug(f"Initialized status_entry for {device_id}: {status_entry}")

        # Log the status_entry before the min_on_time logic
        log_debug(f"[PRE-MIN-ON-TIME] status_entry for {device_id}: {status_entry}")

        # 2c. Calculate desired state (on/off) based on power, debounce, and min_on_time
        is_active, is_active_candidate = _calculate_device_state(
            device, remaining_power, device_on_state, device_debounce_state, cfg, now
        )

        log_debug( f"Calculated state for {device_id}: is_active={is_active}, is_active_candidate={is_active_candidate}")
        status_entry["is_active_candidate"] = is_active_candidate

        # --- Minimum On-Time Logic ---
        min_on_time = status_entry.get(CONF_DEVICE_MIN_ON_TIME, 0)
        prev_on = bool(device_on_state.get(device_id, False))

        # Always set last_on_time if device is ON and missing last_on_time
        if is_active and not device_on_time_state.get(device_id, {}).get("last_on_time"):
            log_debug(f"[min_on_time] Device {device_id} is ON and last_on_time is missing, setting last_on_time to {now}")
            device_on_time_state.setdefault(device_id, {})["last_on_time"] = now
            status_entry["last_on_time"] = now

        last_on_time = device_on_time_state.get(device_id, {}).get("last_on_time")
        log_debug(f"[min_on_time] DEBUG: now={now}, last_on_time={last_on_time}, prev_on={prev_on}, is_active={is_active}")

        # If device was ON and is now being turned OFF, check min_on_time
        if prev_on and not is_active:
            log_debug(f"[min_on_time] prev_on=True, is_active=False, min_on_time={min_on_time}, last_on_time={last_on_time}, now={now}")
            if min_on_time > 0 and last_on_time:
                elapsed = (now - last_on_time).total_seconds()
                log_debug(f"[min_on_time] ELAPSED DEBUG: now={now}, last_on_time={last_on_time}, elapsed={elapsed:.2f}s, required={min_on_time}s, device_state={hass.states.get(device.get('entity_id') or device.get('device_entity')).state if device.get('entity_id') or device.get('device_entity') else 'N/A'}")
                if elapsed < min_on_time:
                    # Still within min_on_time, refuse to turn off
                    is_active = True
                    status_entry["refusal_reasons"].append(f"Minimum on-time not yet elapsed: {elapsed:.1f}s < {min_on_time}s")
                    log_debug(f"[min_on_time] Refusing to turn off device {device_id}, keeping ON due to min_on_time")

                    # Actively keep device ON in HA if needed
                    relay_entity = device.get("entity_id") or device.get("device_entity")
                    if relay_entity:
                        service_domain = relay_entity.split(".")[0]
                        await hass.services.async_call(
                            service_domain,
                            SERVICE_TURN_ON,
                            {ATTR_ENTITY_ID: relay_entity},
                            blocking=True,
                        )
                else:
                    # Min on time elapsed, allow turn off
                    log_debug(f"[min_on_time] Allowing turn off, setting last_off_time for {device_id} to {now}")
                    device_on_time_state.setdefault(device_id, {})["last_off_time"] = now
                    status_entry["last_off_time"] = now
            else:
                # No min_on_time restriction or missing last_on_time, allow turn off
                log_debug(f"[min_on_time] No min_on_time restriction or last_on_time missing, turning off {device_id}")
                device_on_time_state.setdefault(device_id, {})["last_off_time"] = now
                status_entry["last_off_time"] = now

        # Log the status_entry after the min_on_time logic
        log_debug(f"[POST-MIN-ON-TIME] status_entry for {device_id}: {status_entry}")

        # 2d. Execute control logic based on device type
        power_used = 0.0
        log_debug(f"Control logic for {device_id}: prev_on={prev_on}")

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
            )

        remaining_power -= power_used
        log_debug(f"Power used by {device_id}: {power_used}, remaining_power: {remaining_power}")

        # 2e. Finalize status for the device
        if device_id:
            entry_data[CONF_POWER_ALLOCATION][device_id] = power_used
            # Don't update device_on_state here - it's already handled in _calculate_device_state

    # 3. Finalize global state and notify
    _finalize_run(entry_data, excess_power, remaining_power)
    async_dispatcher_send(hass, f"{SIGNAL_POWER_DISTRIBUTION_UPDATED}_{config_entry.entry_id}")
