import logging
import voluptuous as vol
from datetime import time, datetime, timedelta
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_ON,
    SERVICE_TURN_OFF,
    SERVICE_SELECT_OPTION,
    STATE_UNKNOWN,
    STATE_UNAVAILABLE,
)
from homeassistant.components.light import ATTR_BRIGHTNESS
import homeassistant.util.dt as dt_util

from .utils.sensor_utils import clean_entity_id_and_mode

from .const import (
    DOMAIN,
    SERVICE_SET_RELAY_MODE,
    SERVICE_SET_RELAY_POWER,
    RELAY_MODE_OFF,
    RELAY_MODE_ON,
    RELAY_MODE_PROPORTIONAL,
    CONF_ESPHOME_RELAY_ENTITY,
    CONF_ESPHOME_MODE_SELECT_ENTITY,
    CONF_DEVICE_ENTITY,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_PRIORITY,
    CONF_DEVICE_TYPE,
    DEVICE_TYPE_NONE,
    DEVICE_TYPE_STANDARD,
    DEVICE_TYPE_CUSTOM,
    CONF_SCHEDULE_ENABLED,
    CONF_START_TIME,
    CONF_END_TIME,
    CONF_DAYS_OF_WEEK,
    DAYS_OF_WEEK,
    DAY_MONDAY,
    CONF_MIN_EXPECTED_W,
    CONF_MAX_EXPECTED_W,
    DAY_TUESDAY,
    DAY_WEDNESDAY,
    DAY_THURSDAY,
    DAY_FRIDAY,
    DAY_SATURDAY,
    DAY_SUNDAY,
    CONF_POWER_ALLOCATION,
    CONF_POWER_DISTRIBUTION,
    STATE_ON,
    STATE_OFF,
    DOMAIN_LIGHT,
    DOMAIN_SWITCH,
    DOMAIN_SELECT,
    DOMAIN_INPUT_BOOLEAN,
    DOMAIN_AUTOMATION,
    DOMAIN_SCRIPT,
    DOMAIN_CLIMATE,
    MAX_BRIGHTNESS,
    MAX_PERCENTAGE,
    DEFAULT_MIN_START_W,
    DEFAULT_HYSTERESIS_W,
    SENSOR_ID_PREFIX,
    SENSOR_EXCESS_SUFFIX,
    SIGNAL_POWER_DISTRIBUTION_UPDATED,
    CONF_RAMP_UP_STEP,
    CONF_RAMP_DOWN_STEP,
    CONF_RAMP_DEADBAND,
    CONF_DEFAULT_MIN_START_W,
    CONF_HYSTERESIS_W,
)

_LOGGER = logging.getLogger(__name__)

# Service schema for set_relay_mode
SET_RELAY_MODE_SCHEMA = vol.Schema({
    vol.Optional(ATTR_ENTITY_ID): cv.entity_id,
    vol.Optional(CONF_DEVICE_ID): cv.string,
    vol.Required("mode"): vol.In([RELAY_MODE_OFF, RELAY_MODE_ON, RELAY_MODE_PROPORTIONAL]),
})

# Service schema for set_relay_power
SET_RELAY_POWER_SCHEMA = vol.Schema({
    vol.Optional(ATTR_ENTITY_ID): cv.entity_id,
    vol.Optional(CONF_DEVICE_ID): cv.string,
    vol.Required("power"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
})

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigType):
    """Set up SunAllocator from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # Store config entry data
    entry_data = {
        "config": config_entry.data,
        "unsub_update_listener": None,
        "unsub_auto_control": None,
    }
    hass.data[DOMAIN][config_entry.entry_id] = entry_data
    
    # Set up sensors
    await hass.config_entries.async_forward_entry_setups(config_entry, ["sensor"])
    
    # Register services
    async def handle_set_relay_mode(call: ServiceCall):
        """Handle the set_relay_mode service."""
        mode = call.data["mode"]
        entity_id = call.data.get(ATTR_ENTITY_ID)
        device_id = call.data.get(CONF_DEVICE_ID)
        
        # Get devices from config
        devices = config_entry.data.get(CONF_DEVICES, [])
        
        # If entity_id is provided, use it directly
        if entity_id:
            await set_mode_for_entity(hass, entity_id, mode)
        # If device_id is provided, find the corresponding device
        elif device_id:
            device = next((d for d in devices if d.get(CONF_DEVICE_ID) == device_id), None)
            if device:
                entity_id = device.get(CONF_ESPHOME_MODE_SELECT_ENTITY)
                if entity_id:
                    await set_mode_for_entity(hass, entity_id, mode)
                else:
                    _LOGGER.error(f"Device {device.get(CONF_DEVICE_NAME)} has no mode select entity configured")
            else:
                _LOGGER.error(f"Device with ID {device_id} not found")
        # If neither is provided, set mode for all devices
        else:
            for device in devices:
                entity_id = device.get(CONF_ESPHOME_MODE_SELECT_ENTITY)
                if entity_id:
                    await set_mode_for_entity(hass, entity_id, mode)

    async def set_mode_for_entity(hass, entity_id, mode):
        """Set mode for a specific entity."""
        # Guard: ensure entity exists and is available
        state = hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            _LOGGER.debug(
                f"Entity {entity_id} not found or unavailable, skipping set_relay_mode({mode})"
            )
            return

        _LOGGER.debug(f"Setting relay mode to {mode} for entity {entity_id}")
        await hass.services.async_call(
            DOMAIN_SELECT, SERVICE_SELECT_OPTION,
            {ATTR_ENTITY_ID: entity_id, "option": mode},
            blocking=True
        )
    
    async def handle_set_relay_power(call: ServiceCall):
        """Handle the set_relay_power service."""
        power_percent = call.data["power"]
        entity_id = call.data.get(ATTR_ENTITY_ID)
        device_id = call.data.get(CONF_DEVICE_ID)
        
        # Get devices from config
        devices = config_entry.data.get(CONF_DEVICES, [])
        
        # If entity_id is provided, use it directly
        if entity_id:
            await set_power_for_entity(hass, entity_id, power_percent)
        # If device_id is provided, find the corresponding device
        elif device_id:
            device = next((d for d in devices if d.get(CONF_DEVICE_ID) == device_id), None)
            if device:
                device_type = device.get(CONF_DEVICE_TYPE, DEVICE_TYPE_CUSTOM)
                if device_type == DEVICE_TYPE_CUSTOM:
                    entity_id = device.get(CONF_ESPHOME_RELAY_ENTITY)
                else:
                    entity_id = device.get(CONF_DEVICE_ENTITY)
                if entity_id:
                    await set_power_for_entity(hass, entity_id, power_percent)
                else:
                    _LOGGER.error(f"Device {device.get(CONF_DEVICE_NAME)} has no entity configured")
            else:
                _LOGGER.error(f"Device with ID {device_id} not found")
        # If neither is provided, set power for all devices
        else:
            for device in devices:
                device_type = device.get(CONF_DEVICE_TYPE, DEVICE_TYPE_CUSTOM)
                if device_type == DEVICE_TYPE_CUSTOM:
                    entity_id = device.get(CONF_ESPHOME_RELAY_ENTITY)
                else:
                    entity_id = device.get(CONF_DEVICE_ENTITY)
                if entity_id:
                    await set_power_for_entity(hass, entity_id, power_percent)
    
    async def set_power_for_entity(hass, entity_id, power_percent):
        """Set power for a specific entity."""
        # Guard: ensure entity exists and is available
        state = hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            _LOGGER.debug(
                f"Entity {entity_id} not found or unavailable, skipping set_relay_power({power_percent}%)"
            )
            return

        # Climate entity: entity_id|mode (heat/cool)
        hvac_mode = None
        if '|' in entity_id:
            entity_id, hvac_mode = entity_id.split('|', 1)
            entity_id = entity_id.strip()
            hvac_mode = hvac_mode.strip()

        # Get the domain from the entity_id
        domain = entity_id.split('.')[0]
        brightness = int((power_percent / MAX_PERCENTAGE) * MAX_BRIGHTNESS)

        if power_percent <= 0:
            _LOGGER.debug(f"Turning off entity {entity_id}")
            if domain == DOMAIN_LIGHT:
                await hass.services.async_call(
                    DOMAIN_LIGHT, SERVICE_TURN_OFF,
                    {ATTR_ENTITY_ID: entity_id},
                    blocking=True
                )
            elif domain in [DOMAIN_SWITCH, DOMAIN_INPUT_BOOLEAN, DOMAIN_AUTOMATION, DOMAIN_SCRIPT]:
                await hass.services.async_call(
                    domain, SERVICE_TURN_OFF,
                    {ATTR_ENTITY_ID: entity_id},
                    blocking=True
                )
            elif domain == DOMAIN_CLIMATE:
                await hass.services.async_call(
                    DOMAIN_CLIMATE, "set_hvac_mode",
                    {ATTR_ENTITY_ID: entity_id, "hvac_mode": "off"},
                    blocking=True
                )
            else:
                _LOGGER.warning(f"Unsupported entity domain: {domain}. Cannot turn off {entity_id}")
        else:
            _LOGGER.debug(f"Turning on entity {entity_id} with power {power_percent}%")
            if domain == DOMAIN_LIGHT:
                await hass.services.async_call(
                    DOMAIN_LIGHT, SERVICE_TURN_ON,
                    {ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS: brightness},
                    blocking=True
                )
            elif domain in [DOMAIN_SWITCH, DOMAIN_INPUT_BOOLEAN, DOMAIN_AUTOMATION, DOMAIN_SCRIPT]:
                await hass.services.async_call(
                    domain, SERVICE_TURN_ON,
                    {ATTR_ENTITY_ID: entity_id},
                    blocking=True
                )
            elif domain == DOMAIN_CLIMATE:
                await hass.services.async_call(
                    DOMAIN_CLIMATE, "set_hvac_mode",
                    {ATTR_ENTITY_ID: entity_id, "hvac_mode": hvac_mode or "heat"},
                    blocking=True
                )
            else:
                _LOGGER.warning(f"Unsupported entity domain: {domain}. Cannot turn on {entity_id}")
    
    # Register the services once (global) and track entry count
    root = hass.data[DOMAIN]
    root.setdefault("_entry_count", 0)
    root.setdefault("_services_registered", False)
    if not root["_services_registered"]:
        hass.services.async_register(
            DOMAIN, SERVICE_SET_RELAY_MODE, handle_set_relay_mode, schema=SET_RELAY_MODE_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_SET_RELAY_POWER, handle_set_relay_power, schema=SET_RELAY_POWER_SCHEMA
        )
        root["_services_registered"] = True
    # Increment active entry count
    root["_entry_count"] = int(root.get("_entry_count", 0)) + 1
    
    # Track and resync desired modes for ESPHome select entities to avoid boot Off override
    VALID_MODES = {RELAY_MODE_OFF, RELAY_MODE_ON, RELAY_MODE_PROPORTIONAL}
    desired_modes = {}
    select_entity_ids = []
    devices = config_entry.data.get(CONF_DEVICES, [])
    for d in devices:
        entity = d.get(CONF_ESPHOME_MODE_SELECT_ENTITY)
        if entity:
            select_entity_ids.append(entity)
            state = hass.states.get(entity)
            if state and state.state in VALID_MODES:
                desired_modes[entity] = state.state
    entry_data["desired_modes"] = desired_modes

    # Fallback: load persisted last_mode from config entry if HA state not yet restored
    for d in devices:
        entity = d.get(CONF_ESPHOME_MODE_SELECT_ENTITY)
        if entity and entity not in desired_modes:
            persisted = d.get("last_mode")
            if persisted in VALID_MODES:
                desired_modes[entity] = persisted

    async def _persist_last_mode(entity_id: str, mode: str):
        # Persist last_mode to config entry data for the matching device
        if mode not in VALID_MODES:
            return
        data = dict(config_entry.data)
        devs = list(data.get(CONF_DEVICES, []))
        changed = False
        for i, d in enumerate(devs):
            if d.get(CONF_ESPHOME_MODE_SELECT_ENTITY) == entity_id:
                if d.get("last_mode") != mode:
                    nd = dict(d)
                    nd["last_mode"] = mode
                    devs[i] = nd
                    changed = True
                break
        if changed:
            data[CONF_DEVICES] = devs
            hass.config_entries.async_update_entry(config_entry, data=data)

    if select_entity_ids:
        async def _mode_select_state_listener(event):
            entity_id = event.data.get("entity_id")
            if entity_id not in select_entity_ids:
                return
            new_state = event.data.get("new_state")
            old_state = event.data.get("old_state")
            if not new_state:
                return
            # Update desired mode when user/integration changes it to a valid option
            if new_state.state in VALID_MODES:
                desired_modes[entity_id] = new_state.state
                await _persist_last_mode(entity_id, new_state.state)
            # When entity becomes available, reassert desired mode once
            was_unavailable = (old_state is None) or (old_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE))
            now_available = new_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
            if was_unavailable and now_available:
                desired = desired_modes.get(entity_id)
                if desired and new_state.state != desired:
                    _LOGGER.debug(
                        "Re-applying desired mode %s to %s after availability", desired, entity_id
                    )
                    await set_mode_for_entity(hass, entity_id, desired)

        # Subscribe to state changes for all tracked select entities
        entry_data["unsub_mode_listener"] = async_track_state_change_event(
            hass, select_entity_ids, _mode_select_state_listener
        )

        # Initial re-assert of desired mode if entity already available
        for _entity_id in select_entity_ids:
            _state = hass.states.get(_entity_id)
            _desired = desired_modes.get(_entity_id)
            if _desired and _state and _state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE) and _state.state != _desired:
                _LOGGER.debug("Initial re-applying desired mode %s to %s", _desired, _entity_id)
                await set_mode_for_entity(hass, _entity_id, _desired)
    
    # Set up auto-control
    await setup_auto_control(hass, config_entry)
    
    # Listen for config entry updates
    entry_data["unsub_update_listener"] = config_entry.add_update_listener(update_listener)
    
    return True

def is_device_in_schedule(device, now=None):
    """Check if the device is within its scheduled time."""
    # If scheduling is not enabled, device is always active
    if not device.get(CONF_SCHEDULE_ENABLED, False):
        return True
    
    # Get current time and day if not provided
    if now is None:
        now = dt_util.now()
    
    # Get schedule settings
    start_time = device.get(CONF_START_TIME)
    end_time = device.get(CONF_END_TIME)
    days_of_week = device.get(CONF_DAYS_OF_WEEK, DAYS_OF_WEEK)
    
    # If no schedule settings, device is always active
    if not start_time or not end_time or not days_of_week:
        return True
    
    # Check if current day is in schedule (locale-independent)
    DAY_INDEX_TO_NAME = DAYS_OF_WEEK  # ["monday", ..., "sunday"]
    current_day = DAY_INDEX_TO_NAME[now.weekday()]
    if current_day not in days_of_week:
        return False
    
    # Convert datetime to time for comparison
    current_time = now.time()
    
    # Handle overnight schedules (end_time < start_time)
    if end_time < start_time:
        # Active from start_time to midnight or from midnight to end_time
        return current_time >= start_time or current_time <= end_time
    else:
        # Active from start_time to end_time
        return start_time <= current_time <= end_time

async def setup_auto_control(hass: HomeAssistant, config_entry: ConfigType):
    """Set up automatic control of the relay based on excess power."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    
    # Cancel any existing auto-control
    if entry_data.get("unsub_auto_control"):
        entry_data["unsub_auto_control"]()
        entry_data["unsub_auto_control"] = None

    # Cancel existing watchdog timer if any (to avoid duplicates on re-setup)
    if entry_data.get("unsub_watchdog_timer"):
        entry_data["unsub_watchdog_timer"]()
        entry_data["unsub_watchdog_timer"] = None

    # Cancel existing ramp timer if any (to avoid duplicates on re-setup)
    if entry_data.get("unsub_ramp_timer"):
        entry_data["unsub_ramp_timer"]()
        entry_data["unsub_ramp_timer"] = None
    
    # Get devices from config
    import re
    devices = config_entry.data.get(CONF_DEVICES, [])
    # Normalize entity_id and hvac_mode at registration/configuration time
    for device in devices:
        device_type = device.get(CONF_DEVICE_TYPE, DEVICE_TYPE_CUSTOM)
        if device_type == DEVICE_TYPE_CUSTOM:
            relay_entity = device.get(CONF_ESPHOME_RELAY_ENTITY)
            clean_id, hvac_mode = clean_entity_id_and_mode(relay_entity)
            device["_clean_entity_id"] = clean_id
            if hvac_mode:
                device["_hvac_mode"] = hvac_mode
        else:
            relay_entity_raw = device.get(CONF_DEVICE_ENTITY)
            clean_id, hvac_mode = clean_entity_id_and_mode(relay_entity_raw)
            device["_clean_entity_id"] = clean_id
            if hvac_mode:
                device["_hvac_mode"] = hvac_mode
    # Filter devices with auto-control enabled
    auto_control_devices = [d for d in devices if d.get(CONF_AUTO_CONTROL_ENABLED, False)]
    if not auto_control_devices:
        _LOGGER.debug("No devices with auto-control enabled")
        return
    # Sort devices by priority (higher priority first)
    auto_control_devices.sort(key=lambda d: d.get(CONF_DEVICE_PRIORITY, 50), reverse=True)
    _LOGGER.debug(f"Setting up auto-control for {len(auto_control_devices)} devices")
    # Initialize power allocation tracking
    power_allocation = {}
    for device in auto_control_devices:
        device_id = device.get(CONF_DEVICE_ID)
        if device_id:
            power_allocation[device_id] = 0
    # Store power allocation in hass data for access by sensors
    entry_data[CONF_POWER_ALLOCATION] = power_allocation
    
    # Watchdog: detect stale excess sensor updates and enforce OFF fail-safe
    WATCHDOG_STALE_AFTER = timedelta(minutes=3)
    WATCHDOG_PERIOD = timedelta(seconds=60)

    # Initialize freshness tracking
    entry_data["watchdog_last_seen"] = dt_util.utcnow()
    entry_data["watchdog_alerted"] = False

    async def _enforce_all_off(reason: str):
        devices_cfg = config_entry.data.get(CONF_DEVICES, [])
        for d in devices_cfg:
            entity_id = d.get(CONF_ESPHOME_RELAY_ENTITY)
            if not entity_id:
                continue
            domain = entity_id.split(".")[0]
            try:
                await hass.services.async_call(
                    domain if domain in [DOMAIN_LIGHT, DOMAIN_SWITCH, DOMAIN_INPUT_BOOLEAN, DOMAIN_AUTOMATION, DOMAIN_SCRIPT] else DOMAIN_LIGHT,
                    SERVICE_TURN_OFF,
                    {ATTR_ENTITY_ID: entity_id},
                    blocking=False,
                )
            except Exception as e:
                _LOGGER.warning("Watchdog OFF failed for %s: %s", entity_id, e)
        _LOGGER.error("SunAllocator watchdog: fail-safe OFF enforced (%s)", reason)

    async def _watchdog_check(now):
        last_seen = entry_data.get("watchdog_last_seen")
        alerted = entry_data.get("watchdog_alerted", False)
        if not last_seen:
            return
        stale_for = dt_util.utcnow() - last_seen
        if stale_for > WATCHDOG_STALE_AFTER:
            if not alerted:
                entry_data["watchdog_alerted"] = True
                await _enforce_all_off(f"excess sensor stale for {int(stale_for.total_seconds())}s")
        else:
            if alerted:
                entry_data["watchdog_alerted"] = False
                _LOGGER.info("SunAllocator watchdog: data fresh again; normal operation resumed")

    # Start periodic watchdog timer
    entry_data["unsub_watchdog_timer"] = async_track_time_interval(hass, _watchdog_check, WATCHDOG_PERIOD)

    # RAMPER: smooth proportional power changes
    # Parameters
    RAMP_INTERVAL = timedelta(seconds=5)
    cfg = config_entry.data
    RAMP_UP_STEP = float(cfg.get(CONF_RAMP_UP_STEP, 10.0))     # percent per tick when increasing
    RAMP_DOWN_STEP = float(cfg.get(CONF_RAMP_DOWN_STEP, 20.0)) # percent per tick when decreasing
    RAMP_DEADBAND = float(cfg.get(CONF_RAMP_DEADBAND, 1.0))    # percent; below this, treat as reached
    DEVICE_MAX_PERCENT_DEFAULT = 90.0

    # Variant A thresholds (configurable)
    DEFAULT_MIN_START_W_LOCAL = float(cfg.get(CONF_DEFAULT_MIN_START_W, DEFAULT_MIN_START_W))
    HYSTERESIS_W_LOCAL = float(cfg.get(CONF_HYSTERESIS_W, DEFAULT_HYSTERESIS_W))

    # Initialize ramp state containers
    if entry_data.get("ramp_targets") is None:
        entry_data["ramp_targets"] = {}
    if entry_data.get("ramp_currents") is None:
        entry_data["ramp_currents"] = {}

    # Initialize device status and entity mapping for percent tracking
    if entry_data.get("device_status") is None:
        entry_data["device_status"] = {}
    # Build mapping from cleaned relay entity to device_id for quick lookup
    entity_to_device_id = {}
    for d in auto_control_devices:
        did = d.get(CONF_DEVICE_ID)
        eid = d.get("_clean_entity_id")
        if eid and did:
            entity_to_device_id[eid] = did
    entry_data["entity_to_device_id"] = entity_to_device_id

    # Device domains as a configurable parameter for easy extension
    SUPPORTED_DOMAINS = set(cfg.get("supported_domains", [
        DOMAIN_LIGHT, DOMAIN_SWITCH, DOMAIN_INPUT_BOOLEAN, 
        DOMAIN_AUTOMATION, DOMAIN_SCRIPT, DOMAIN_CLIMATE
    ]))

    # Initialize per-device on/off state for hysteresis control (Variant A)
    if entry_data.get("device_on_state") is None:
        entry_data["device_on_state"] = {}

    async def _ramp_tick(now):
        targets = entry_data.get("ramp_targets", {})
        currents = entry_data.get("ramp_currents", {})
        # Iterate over current targets
        for entity_id, target in list(targets.items()):
            try:
                t = float(target)
            except (TypeError, ValueError):
                t = 0.0
            if t < 0.0:
                t = 0.0
            if t > 100.0:
                t = 100.0

            cur = currents.get(entity_id)
            if cur is None:
                # Try to derive current percent from HA state (brightness)
                s = hass.states.get(entity_id)
                cur = 0.0
                if s and entity_id.startswith(f"{DOMAIN_LIGHT}."):
                    try:
                        br = int(s.attributes.get("brightness", 0))
                        cur = (br / MAX_BRIGHTNESS) * MAX_PERCENTAGE
                    except Exception:
                        cur = 0.0
                currents[entity_id] = cur

            delta = t - cur
            if abs(delta) < RAMP_DEADBAND:
                currents[entity_id] = t
                continue

            if delta > 0:
                new_percent = min(t, cur + RAMP_UP_STEP)
            else:
                new_percent = max(t, cur - RAMP_DOWN_STEP)

            currents[entity_id] = new_percent
            # Apply
            # Use cleaned entity_id for ramping
            await set_power_for_entity(hass, entity_id, new_percent)

            # Update device_status percent_actual if mapped
            try:
                entity_to_device_id = entry_data.get("entity_to_device_id", {})
                dev_id = entity_to_device_id.get(entity_id)
                if dev_id:
                    ds = entry_data.get("device_status", {})
                    if dev_id in ds:
                        ds[dev_id]["percent_actual"] = float(currents.get(entity_id, new_percent))
                        entry_data["device_status"] = ds
            except Exception:
                pass

    # Start periodic ramp timer
    entry_data["unsub_ramp_timer"] = async_track_time_interval(hass, _ramp_tick, RAMP_INTERVAL)

    async def process_excess_power(excess_power: float):
        """Process excess power value and control devices accordingly."""
        _LOGGER.debug(f"Excess power: {excess_power}W")
        now = dt_util.now()
        for device_id in power_allocation:
            power_allocation[device_id] = 0
        remaining_power = excess_power
        ramp_targets = {}
        entry_data["ramp_targets"] = ramp_targets
        device_status = entry_data.get("device_status", {})
        device_on_state = entry_data.get("device_on_state", {})
        for device in auto_control_devices:
            device_id = device.get(CONF_DEVICE_ID)
            device_type = device.get(CONF_DEVICE_TYPE, DEVICE_TYPE_CUSTOM)
            relay_entity = device.get("_clean_entity_id")
            mode_select_entity = device.get(CONF_ESPHOME_MODE_SELECT_ENTITY) if device_type == DEVICE_TYPE_CUSTOM else None
            hvac_mode = device.get("_hvac_mode") if device_type == DEVICE_TYPE_STANDARD else None
            device_name = device.get(CONF_DEVICE_NAME, "Unknown")
            device_priority = int(device.get(CONF_DEVICE_PRIORITY, 50))
            max_expected_w = float(device.get(CONF_MAX_EXPECTED_W, 0) or 0)
            min_expected_w = float(device.get(CONF_MIN_EXPECTED_W, 0) or 0)
            effective_min_power = max(min_expected_w, DEFAULT_MIN_START_W_LOCAL)
            on_threshold = effective_min_power + (HYSTERESIS_W_LOCAL / 2.0)
            off_threshold = max(0.0, effective_min_power - (HYSTERESIS_W_LOCAL / 2.0))
            prev_on = bool(entry_data.get("device_on_state", {}).get(device_id, False))
            is_active = remaining_power >= (off_threshold if prev_on else on_threshold)
            status_entry = {
                "name": device_name,
                "priority": device_priority,
                "entity_id": relay_entity,
                "mode_entity_id": mode_select_entity,
                "mode": None,
                "percent_target": 0.0,
                "percent_actual": 0.0,
                "allocated_w": 0.0,
                "min_expected_w": float(min_expected_w),
                "max_expected_w": float(max_expected_w),
            }
            service_domain = None
            if relay_entity and isinstance(relay_entity, str) and "." in relay_entity:
                service_domain = relay_entity.split(".")[0]
            if not relay_entity or service_domain not in SUPPORTED_DOMAINS:
                _LOGGER.warning(f"Unsupported or missing relay entity domain for {device_name}: {relay_entity}")
                continue
            relay_state_obj = hass.states.get(relay_entity)
            if relay_state_obj is None or relay_state_obj.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                _LOGGER.debug(f"Relay entity {relay_entity} not found or not available yet for device {device_name}, skipping this cycle")
                continue
            if not is_device_in_schedule(device, now):
                _LOGGER.debug(f"Device {device_name} is outside scheduled time, skipping")
                await hass.services.async_call(
                    service_domain, SERVICE_TURN_OFF,
                    {ATTR_ENTITY_ID: relay_entity},
                    blocking=False
                )
                continue
            if device_type == DEVICE_TYPE_STANDARD:
                if is_active:
                    _LOGGER.debug(f"Turning on standard device {device_name}")
                    if service_domain == DOMAIN_LIGHT:
                        await hass.services.async_call(
                            DOMAIN_LIGHT, SERVICE_TURN_ON,
                            {ATTR_ENTITY_ID: relay_entity, ATTR_BRIGHTNESS: MAX_BRIGHTNESS},
                            blocking=False
                        )
                    elif service_domain == DOMAIN_CLIMATE:
                        mode = hvac_mode or "heat"
                        await hass.services.async_call(
                            DOMAIN_CLIMATE, "set_hvac_mode",
                            {ATTR_ENTITY_ID: relay_entity, "hvac_mode": mode},
                            blocking=False
                        )
                    else:
                        await hass.services.async_call(
                            service_domain, SERVICE_TURN_ON,
                            {ATTR_ENTITY_ID: relay_entity},
                            blocking=False
                        )
                    cap = max_expected_w if max_expected_w > 0 else (DEFAULT_MIN_START_W_LOCAL * 3)
                    power_used = min(remaining_power, cap)
                    remaining_power -= power_used
                    if device_id:
                        power_allocation[device_id] = power_used
                        status_entry["allocated_w"] = float(power_used)
                        status_entry["percent_target"] = 100.0
                        status_entry["percent_actual"] = 100.0
                else:
                    _LOGGER.debug(f"Turning off standard device {device_name} (remaining power {remaining_power}W below effective threshold {effective_min_power}W)")
                    if service_domain == DOMAIN_CLIMATE:
                        await hass.services.async_call(
                            DOMAIN_CLIMATE, "set_hvac_mode",
                            {ATTR_ENTITY_ID: relay_entity, "hvac_mode": "off"},
                            blocking=False
                        )
                    else:
                        await hass.services.async_call(
                            service_domain, SERVICE_TURN_OFF,
                            {ATTR_ENTITY_ID: relay_entity},
                            blocking=False
                        )
                    status_entry["percent_target"] = 0.0
                    status_entry["percent_actual"] = 0.0
                    status_entry["allocated_w"] = 0.0
            elif device_type == DEVICE_TYPE_CUSTOM:
                if not mode_select_entity:
                    _LOGGER.warning(f"Custom device {device_name} has no mode select entity")
                    if device_id:
                        device_status[device_id] = status_entry
                    continue
                mode_state = hass.states.get(mode_select_entity)
                if not mode_state or mode_state.state == RELAY_MODE_OFF:
                    _LOGGER.debug(f"Device {device_name} is in Off mode, skipping")
                    status_entry["mode"] = RELAY_MODE_OFF
                    status_entry["percent_target"] = 0.0
                    status_entry["percent_actual"] = 0.0
                    status_entry["allocated_w"] = 0.0
                    if device_id:
                        device_status[device_id] = status_entry
                    continue
                status_entry["mode"] = mode_state.state
                if mode_state.state == RELAY_MODE_PROPORTIONAL:
                    if is_active:
                        if max_expected_w <= 0:
                            _LOGGER.warning(f"Device {device_name} in Proportional has no max_expected_w; forcing 0%/OFF")
                            status_entry["percent_target"] = 0.0
                            if service_domain == DOMAIN_LIGHT:
                                ramp_targets[relay_entity] = 0.0
                            else:
                                await hass.services.async_call(
                                    service_domain, SERVICE_TURN_OFF,
                                    {ATTR_ENTITY_ID: relay_entity},
                                    blocking=False
                                )
                                status_entry["percent_actual"] = 0.0
                        else:
                            power_percent = min(MAX_PERCENTAGE, max(5, (remaining_power / max_expected_w) * 100))
                            target_percent = min(power_percent, DEVICE_MAX_PERCENT_DEFAULT)
                            _LOGGER.debug(f"Proportional target for {device_name}: {target_percent}% (remaining power: {remaining_power}W)")
                            status_entry["percent_target"] = float(target_percent)
                            if service_domain == DOMAIN_LIGHT:
                                ramp_targets[relay_entity] = target_percent
                            else:
                                await hass.services.async_call(
                                    service_domain, SERVICE_TURN_ON,
                                    {ATTR_ENTITY_ID: relay_entity},
                                    blocking=False
                                )
                                status_entry["percent_actual"] = float(target_percent)
                            cap_total = max_expected_w
                            power_used = min(remaining_power, cap_total * (target_percent / MAX_PERCENTAGE))
                            remaining_power -= power_used
                            if device_id:
                                power_allocation[device_id] = power_used
                                status_entry["allocated_w"] = float(power_used)
                    else:
                        _LOGGER.debug(f"Proportional below threshold for {device_name} → target 0 / OFF")
                        status_entry["percent_target"] = 0.0
                        if service_domain == DOMAIN_LIGHT:
                            ramp_targets[relay_entity] = 0.0
                        else:
                            await hass.services.async_call(
                                service_domain, SERVICE_TURN_OFF,
                                {ATTR_ENTITY_ID: relay_entity},
                                blocking=False
                            )
                            status_entry["percent_actual"] = 0.0
                elif mode_state.state == RELAY_MODE_ON:
                    if remaining_power >= effective_min_power:
                        _LOGGER.debug(f"Device {device_name} is in On mode with enough excess, setting to full power")
                        if service_domain == DOMAIN_LIGHT:
                            await hass.services.async_call(
                                DOMAIN_LIGHT, SERVICE_TURN_ON,
                                {ATTR_ENTITY_ID: relay_entity, ATTR_BRIGHTNESS: MAX_BRIGHTNESS},
                                blocking=False
                            )
                        else:
                            await hass.services.async_call(
                                service_domain, SERVICE_TURN_ON,
                                {ATTR_ENTITY_ID: relay_entity},
                                blocking=False
                            )
                        cap = max_expected_w if max_expected_w > 0 else (DEFAULT_MIN_START_W_LOCAL * 3)
                        power_used = min(remaining_power, cap)
                        remaining_power -= power_used
                        if device_id:
                            power_allocation[device_id] = power_used
                            status_entry["allocated_w"] = float(power_used)
                            status_entry["percent_target"] = 100.0
                            status_entry["percent_actual"] = 100.0
                    else:
                        _LOGGER.debug(f"Device {device_name} is in On mode but remaining power {remaining_power}W is below threshold {effective_min_power}W; turning off")
                        await hass.services.async_call(
                            service_domain, SERVICE_TURN_OFF,
                            {ATTR_ENTITY_ID: relay_entity},
                            blocking=False
                        )
            if device_id:
                device_status[device_id] = status_entry
                device_on_state[device_id] = is_active
        entry_data[CONF_POWER_DISTRIBUTION] = {
            "total_power": excess_power,
            "remaining_power": remaining_power,
            "allocated_power": excess_power - remaining_power,
            "allocation": power_allocation.copy()
        }
        entry_data["device_status"] = device_status
        entry_data["device_on_state"] = device_on_state
        async_dispatcher_send(hass, f"{SIGNAL_POWER_DISTRIBUTION_UPDATED}_{config_entry.entry_id}")
    
    @callback
    async def handle_state_change(event):
        """Handle changes to the excess power sensor (event-based)."""
        new_state = event.data.get("new_state") if hasattr(event, "data") else None
        if not new_state or new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        
        # Watchdog touch: mark data as fresh
        entry_data["watchdog_last_seen"] = dt_util.utcnow()
        entry_data["watchdog_alerted"] = False
        
        try:
            excess_power = float(new_state.state)
            await process_excess_power(excess_power)
        except (ValueError, TypeError) as e:
            _LOGGER.error(f"Error processing excess power value: {e}")
    
    # Subscribe to state changes of the excess power sensor (per entry_id) with fallback for legacy entity_id
    excess_sensor_id = f"sensor.{SENSOR_ID_PREFIX}_{SENSOR_EXCESS_SUFFIX}_{config_entry.entry_id}"
    legacy_excess_sensor_id = f"sensor.{SENSOR_ID_PREFIX}_{SENSOR_EXCESS_SUFFIX}_1"
    entry_data["unsub_auto_control"] = async_track_state_change_event(
        hass, [excess_sensor_id, legacy_excess_sensor_id], handle_state_change
    )

    # Perform an initial pass based on the current state of the excess sensor (prefer entry_id-based, fallback to legacy)
    initial_state = hass.states.get(excess_sensor_id) or hass.states.get(legacy_excess_sensor_id)
    if initial_state and initial_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        try:
            excess_power = float(initial_state.state)
            # Watchdog touch on initial read to avoid false stale trigger
            entry_data["watchdog_last_seen"] = dt_util.utcnow()
            entry_data["watchdog_alerted"] = False
            await process_excess_power(excess_power)
            _LOGGER.info(
                "Performed initial auto-control pass based on current excess from %s: %sW",
                initial_state.entity_id,
                excess_power,
            )
        except (ValueError, TypeError):
            _LOGGER.debug(
                "Excess sensor state is not numeric yet for initial pass: %s",
                initial_state.state,
            )
    else:
        _LOGGER.debug(
            "Neither %s nor %s are ready (unknown/unavailable) for initial pass", 
            excess_sensor_id,
            legacy_excess_sensor_id,
        )
    
    _LOGGER.info(f"Auto-control set up for {len(auto_control_devices)} devices")

async def update_listener(hass: HomeAssistant, config_entry: ConfigType):
    """Handle options update."""
    # Restart auto-control with new settings
    await setup_auto_control(hass, config_entry)

async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigType):
    """Unload a config entry."""
    # Unload sensors
    await hass.config_entries.async_forward_entry_unload(config_entry, "sensor")
    
    # Unsubscribe from update listener and auto-control
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    if entry_data.get("unsub_update_listener"):
        entry_data["unsub_update_listener"]()
    
    if entry_data.get("unsub_auto_control"):
        entry_data["unsub_auto_control"]()

    if entry_data.get("unsub_mode_listener"):
        entry_data["unsub_mode_listener"]()

    if entry_data.get("unsub_watchdog_timer"):
        entry_data["unsub_watchdog_timer"]()

    if entry_data.get("unsub_ramp_timer"):
        entry_data["unsub_ramp_timer"]()
    
    # Remove config entry from data and manage global services
    root = hass.data.get(DOMAIN, {})
    root.pop(config_entry.entry_id, None)

    # Decrement active entry count and remove services only if last entry unloaded
    try:
        root["_entry_count"] = max(0, int(root.get("_entry_count", 1)) - 1)
    except Exception:
        root["_entry_count"] = 0

    if root.get("_entry_count", 0) == 0 and root.get("_services_registered"):
        hass.services.async_remove(DOMAIN, SERVICE_SET_RELAY_MODE)
        hass.services.async_remove(DOMAIN, SERVICE_SET_RELAY_POWER)
        root["_services_registered"] = False
    
    return True
