"""Main power processing logic for Sun Allocator."""

import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_ON,
    SERVICE_TURN_OFF,
    STATE_UNKNOWN,
    STATE_UNAVAILABLE,
    STATE_ON,
)
from homeassistant.components.light import ATTR_BRIGHTNESS

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
    CONF_MIN_EXPECTED_W,
    CONF_MAX_EXPECTED_W,
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
    DEFAULT_MIN_START_W,
    DEFAULT_HYSTERESIS_W,
    SIGNAL_POWER_DISTRIBUTION_UPDATED,
    CONF_DEVICE_ENTITY,
    CONF_DEFAULT_MIN_START_W,
    CONF_HYSTERESIS_W,
    CONF_DEBOUNCE_TIME,
    DEFAULT_DEBOUNCE_TIME,
    RELAY_MODE_OFF,
    RELAY_MODE_ON,
    RELAY_MODE_PROPORTIONAL,
    CONF_ESPHOME_MODE_SELECT_ENTITY,
    CONF_AUTO_CONTROL_ENABLED,
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
    entry_data["device_status"] = {}
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
        log_warning(
            f"Device '{device_name}' skipped: Unsupported or missing entity_id: {relay_entity}"
        )
        return "Unsupported or missing entity_id"

    # 2. Check for entity availability
    relay_state_obj = hass.states.get(relay_entity)
    if relay_state_obj is None or relay_state_obj.state in (
        STATE_UNKNOWN,
        STATE_UNAVAILABLE,
    ):
        log_debug(
            f"Device '{device_name}' skipped: Entity {relay_entity} not found or unavailable."
        )
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
    device, remaining_power, device_on_state, device_debounce_state, cfg, now
):
    """Calculate the desired state (on/off) for a device based on power, hysteresis, and debounce."""
    device_id = device.get(CONF_DEVICE_ID)
    device_name = device.get(CONF_DEVICE_NAME)

    min_expected_w = float(device.get(CONF_MIN_EXPECTED_W, 0) or 0)
    default_min_start_w = float(cfg.get(CONF_DEFAULT_MIN_START_W, DEFAULT_MIN_START_W))
    hysteresis_w = float(cfg.get(CONF_HYSTERESIS_W, DEFAULT_HYSTERESIS_W))

    # Hysteresis and threshold calculation
    effective_min_power = min_expected_w if min_expected_w > 0 else default_min_start_w
    on_threshold = effective_min_power
    off_threshold = max(0.0, effective_min_power - hysteresis_w)

    prev_on = bool(device_on_state.get(device_id, False))
    is_active_candidate = remaining_power >= (
        off_threshold if prev_on else on_threshold
    )

    log_debug(
        f"Device {device_name}: remaining_power={remaining_power}, on_threshold={on_threshold}, off_threshold={off_threshold}, prev_on={prev_on}, is_active_candidate={is_active_candidate}"
    )

    # Debouncer logic
    debounce_time_s = device.get(CONF_DEBOUNCE_TIME, DEFAULT_DEBOUNCE_TIME)
    debounce_info = device_debounce_state.get(
        device_id, {"candidate_state": None, "state_change_time": None}
    )

    is_active = prev_on  # Assume current state until debounce confirms change
    log_debug(f"Device {device_name}: initial is_active={is_active}")

    if debounce_time_s == 0:
        is_active = is_active_candidate
    else:
        if is_active_candidate != debounce_info["candidate_state"]:
            debounce_info["candidate_state"] = is_active_candidate
            debounce_info["state_change_time"] = now
            device_debounce_state[device_id] = debounce_info
        elif (
            debounce_info["state_change_time"]
            and (now - debounce_info["state_change_time"]).total_seconds()
            >= debounce_time_s
        ):
            is_active = is_active_candidate

    log_debug(f"Device {device_name}: final is_active={is_active}")
    return is_active, is_active_candidate


def _initialize_status_entry(device):
    """Initialize the status dictionary for a device."""
    min_expected_w = float(device.get(CONF_MIN_EXPECTED_W, 0) or 0)
    max_expected_w = float(device.get(CONF_MAX_EXPECTED_W, 0) or 0)
    if max_expected_w <= 0 and min_expected_w > 0:
        max_expected_w = min_expected_w * 1.1

    return {
        "name": device.get(CONF_DEVICE_NAME),
        "priority": int(device.get(CONF_DEVICE_PRIORITY, 50)),
        "entity_id": device.get(CONF_DEVICE_ENTITY),
        "mode_entity_id": device.get(CONF_ESPHOME_MODE_SELECT_ENTITY),
        "mode": None,
        "percent_target": 0.0,
        "percent_actual": 0.0,
        "allocated_w": 0.0,
        "min_expected_w": min_expected_w,
        "max_expected_w": max_expected_w,
    }


async def _control_standard_device(
    hass, device, is_active, prev_on, remaining_power, cfg, status_entry
):
    """Control logic for a standard (on/off) device."""
    power_used = 0.0
    relay_entity = device.get(CONF_DEVICE_ENTITY)
    device_name = device.get(CONF_DEVICE_NAME)
    service_domain = relay_entity.split(".")[0]
    hvac_mode = device.get("hvac_mode")
    default_min_start_w = float(cfg.get(CONF_DEFAULT_MIN_START_W, DEFAULT_MIN_START_W))

    if is_active:
        if not prev_on:
            log_debug(f"Turning on standard device {device_name}")
            service_data = {ATTR_ENTITY_ID: relay_entity}
            service_name = SERVICE_TURN_ON
            if service_domain == DOMAIN_LIGHT:
                service_data[ATTR_BRIGHTNESS] = MAX_BRIGHTNESS
            elif service_domain == DOMAIN_CLIMATE:
                service_name = "set_hvac_mode"
                service_data["hvac_mode"] = hvac_mode or "heat"
            log_debug(
                f"Calling service {service_domain}.{service_name} with data {service_data}"
            )
            await hass.services.async_call(
                service_domain, service_name, service_data, blocking=True
            )

        cap = (
            status_entry["max_expected_w"]
            if status_entry["max_expected_w"] > 0
            else (default_min_start_w * 3)
        )
        power_used = min(remaining_power, cap)
        status_entry.update(
            {
                "allocated_w": float(power_used),
                "percent_target": 100.0,
                "percent_actual": 100.0,
            }
        )
    else:
        if prev_on:
            log_debug(
                f"Turning off standard device {device_name} (remaining power {remaining_power}W below threshold)"
            )
            service_name = SERVICE_TURN_OFF
            service_data = {ATTR_ENTITY_ID: relay_entity}
            if service_domain == DOMAIN_CLIMATE:
                service_name = "set_hvac_mode"
                service_data["hvac_mode"] = "off"
            log_debug(
                f"Calling service {service_domain}.{service_name} with data {service_data}"
            )
            await hass.services.async_call(
                service_domain, service_name, service_data, blocking=True
            )
        status_entry.update(
            {"percent_target": 0.0, "percent_actual": 0.0, "allocated_w": 0.0}
        )

    return power_used, status_entry


async def _control_custom_device(
    hass, device, is_active, prev_on, remaining_power, cfg, status_entry, ramp_targets
):
    """Control logic for a custom (ESPHome) device."""
    power_used = 0.0
    device_name = device.get(CONF_DEVICE_NAME)
    relay_entity = device.get(CONF_DEVICE_ENTITY)
    service_domain = relay_entity.split(".")[0]
    mode_select_entity = device.get(CONF_ESPHOME_MODE_SELECT_ENTITY)
    device_max_percent_default = 90.0

    if not mode_select_entity:
        log_warning(f"Custom device {device_name} has no mode select entity, skipping.")
        return power_used, status_entry

    mode_state = hass.states.get(mode_select_entity)
    if not mode_state or mode_state.state == RELAY_MODE_OFF:
        log_debug(f"Device {device_name} is in Off mode, skipping")
        status_entry["mode"] = RELAY_MODE_OFF
        return power_used, status_entry

    status_entry["mode"] = mode_state.state

    if mode_state.state == RELAY_MODE_PROPORTIONAL:
        if is_active:
            max_w = status_entry["max_expected_w"]
            target_percent = 0.0
            if max_w <= 0:
                log_warning(
                    f"Device {device_name} in Proportional has no max_expected_w; forcing 0%/OFF"
                )
            else:
                power_percent = min(
                    MAX_PERCENTAGE, max(5, (remaining_power / max_w) * 100)
                )
                target_percent = min(power_percent, device_max_percent_default)

            log_debug(
                f"Proportional target for {device_name}: {target_percent}% (remaining power: {remaining_power}W)"
            )
            status_entry["percent_target"] = float(target_percent)

            if service_domain == DOMAIN_LIGHT:
                ramp_targets[relay_entity] = target_percent
            elif not prev_on:
                log_debug(
                    f"Calling service {service_domain}.{SERVICE_TURN_ON} with data {{ATTR_ENTITY_ID: {relay_entity}}}"
                )
                await hass.services.async_call(
                    service_domain,
                    SERVICE_TURN_ON,
                    {ATTR_ENTITY_ID: relay_entity},
                    blocking=True,
                )

            power_used = min(remaining_power, max_w * (target_percent / MAX_PERCENTAGE))
            status_entry["allocated_w"] = float(power_used)
        else:
            log_debug(
                f"Proportional below threshold for {device_name} -> target 0 / OFF"
            )
            if service_domain == DOMAIN_LIGHT:
                ramp_targets[relay_entity] = 0.0
            elif prev_on:
                log_debug(
                    f"Calling service {service_domain}.{SERVICE_TURN_OFF} with data {{ATTR_ENTITY_ID: {relay_entity}}}"
                )
                await hass.services.async_call(
                    service_domain,
                    SERVICE_TURN_OFF,
                    {ATTR_ENTITY_ID: relay_entity},
                    blocking=True,
                )

    elif mode_state.state == RELAY_MODE_ON:
        # This logic is identical to a standard device
        power_used, status_entry = await _control_standard_device(
            hass, device, is_active, prev_on, remaining_power, cfg, status_entry
        )

    return power_used, status_entry


def _finalize_run(entry_data, excess_power, remaining_power):
    """Update global state and prepare for dispatcher signal."""
    entry_data[CONF_POWER_DISTRIBUTION] = {
        "total_power": excess_power,
        "remaining_power": remaining_power,
        "allocated_power": excess_power - remaining_power,
        "allocation": entry_data.get(CONF_POWER_ALLOCATION, {}).copy(),
    }
    # device_status, device_filter_reasons, device_on_state, device_debounce_state are updated by reference


async def process_excess_power(
    hass: HomeAssistant, config_entry: ConfigType, excess_power: float
):
    """Process excess power value and control devices accordingly."""
    # Add caching
    if (
        hasattr(process_excess_power, "_last_values")
        and process_excess_power._last_values.get("excess_power") == excess_power
    ):
        return

    process_excess_power._last_values = {"excess_power": excess_power}

    log_debug(f"--- process_excess_power START, excess_power={excess_power} ---")
    now = dt_util.now()
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    cfg = config_entry.data
    log_debug(f"entry_data keys: {list(entry_data.keys())}")

    # Ensure state dictionaries exist and get a reference to them
    device_on_state = entry_data.setdefault("device_on_state", {})
    device_debounce_state = entry_data.setdefault("device_debounce_state", {})

    # 1. Initialize states for the run
    auto_control_devices = _initialize_run(entry_data, cfg.get(CONF_DEVICES, []))
    log_debug(f"auto_control_devices: {auto_control_devices}")

    remaining_power = excess_power

    # 2. Main processing loop
    for device in auto_control_devices:
        device_id = device.get(CONF_DEVICE_ID)
        log_debug(f"Looping for device: {device_id}")

        # 2a. Filter out invalid or out-of-schedule devices
        filter_reason = await _filter_device(hass, device, now)
        log_debug(f"Filter reason for {device_id}: {filter_reason}")
        if filter_reason:
            if device_id:
                entry_data["device_filter_reasons"][device_id] = filter_reason
            continue

        # 2b. Initialize status entry for this device
        status_entry = _initialize_status_entry(device)
        log_debug(f"Initialized status_entry for {device_id}: {status_entry}")

        # 2c. Calculate desired state (on/off) based on power and debounce
        is_active, is_active_candidate = _calculate_device_state(
            device, remaining_power, device_on_state, device_debounce_state, cfg, now
        )
        log_debug(
            f"Calculated state for {device_id}: is_active={is_active}, is_active_candidate={is_active_candidate}"
        )
        status_entry["is_active_candidate"] = is_active_candidate

        # 2d. Execute control logic based on device type
        power_used = 0.0
        prev_on = bool(device_on_state.get(device_id, False))
        log_debug(f"Control logic for {device_id}: prev_on={prev_on}")

        if device.get(CONF_DEVICE_TYPE) == DEVICE_TYPE_STANDARD:
            power_used, status_entry = await _control_standard_device(
                hass, device, is_active, prev_on, remaining_power, cfg, status_entry
            )
        elif device.get(CONF_DEVICE_TYPE) == DEVICE_TYPE_CUSTOM:
            power_used, status_entry = await _control_custom_device(
                hass,
                device,
                is_active,
                prev_on,
                remaining_power,
                cfg,
                status_entry,
                entry_data["ramp_targets"],
            )

        remaining_power -= power_used
        log_debug(
            f"Power used by {device_id}: {power_used}, remaining_power: {remaining_power}"
        )

        # 2e. Finalize status for the device
        if device_id:
            log_debug(f"Adding to device_status for {device_id}")
            entry_data["device_status"][device_id] = status_entry
            entry_data[CONF_POWER_ALLOCATION][device_id] = power_used
            device_on_state[device_id] = is_active

    # 3. Finalize global state and notify
    _finalize_run(entry_data, excess_power, remaining_power)
    async_dispatcher_send(
        hass, f"{SIGNAL_POWER_DISTRIBUTION_UPDATED}_{config_entry.entry_id}"
    )
    log_debug("--- process_excess_power END ---")
