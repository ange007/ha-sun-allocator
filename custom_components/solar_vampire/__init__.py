import logging
import voluptuous as vol
from datetime import time, datetime
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_ON,
    SERVICE_TURN_OFF,
    SERVICE_SELECT_OPTION,
)
from homeassistant.components.light import ATTR_BRIGHTNESS
import homeassistant.util.dt as dt_util

from .const import (
    DOMAIN,
    SERVICE_SET_RELAY_MODE,
    SERVICE_SET_RELAY_POWER,
    RELAY_MODE_OFF,
    RELAY_MODE_ON,
    RELAY_MODE_PROPORTIONAL,
    CONF_ESPHOME_RELAY_ENTITY,
    CONF_ESPHOME_MODE_SELECT_ENTITY,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_MIN_EXCESS_POWER,
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
    DAY_TUESDAY,
    DAY_WEDNESDAY,
    DAY_THURSDAY,
    DAY_FRIDAY,
    DAY_SATURDAY,
    DAY_SUNDAY,
    CONF_POWER_ALLOCATION,
    CONF_POWER_DISTRIBUTION,
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
    """Set up SolarVampire from a config entry."""
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
        _LOGGER.debug(f"Setting relay mode to {mode} for entity {entity_id}")
        await hass.services.async_call(
            "select", SERVICE_SELECT_OPTION,
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
                entity_id = device.get(CONF_ESPHOME_RELAY_ENTITY)
                if entity_id:
                    await set_power_for_entity(hass, entity_id, power_percent)
                else:
                    _LOGGER.error(f"Device {device.get(CONF_DEVICE_NAME)} has no relay entity configured")
            else:
                _LOGGER.error(f"Device with ID {device_id} not found")
        # If neither is provided, set power for all devices
        else:
            for device in devices:
                entity_id = device.get(CONF_ESPHOME_RELAY_ENTITY)
                if entity_id:
                    await set_power_for_entity(hass, entity_id, power_percent)
    
    async def set_power_for_entity(hass, entity_id, power_percent):
        """Set power for a specific entity."""
        # Get the domain from the entity_id
        domain = entity_id.split('.')[0]
        
        # Convert percentage (0-100) to brightness (0-255) for light entities
        brightness = int((power_percent / 100) * 255)
        
        if power_percent <= 0:
            # Turn off the entity
            _LOGGER.debug(f"Turning off entity {entity_id}")
            
            # Use the appropriate service based on the domain
            if domain == "light":
                await hass.services.async_call(
                    "light", SERVICE_TURN_OFF,
                    {ATTR_ENTITY_ID: entity_id},
                    blocking=True
                )
            elif domain in ["switch", "input_boolean", "automation", "script"]:
                await hass.services.async_call(
                    domain, SERVICE_TURN_OFF,
                    {ATTR_ENTITY_ID: entity_id},
                    blocking=True
                )
            else:
                _LOGGER.warning(f"Unsupported entity domain: {domain}. Cannot turn off {entity_id}")
        else:
            # Turn on the entity
            _LOGGER.debug(f"Turning on entity {entity_id} with power {power_percent}%")
            
            # Use the appropriate service based on the domain
            if domain == "light":
                # For lights, we can set brightness
                _LOGGER.debug(f"Setting light brightness to {brightness}")
                await hass.services.async_call(
                    "light", SERVICE_TURN_ON,
                    {ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS: brightness},
                    blocking=True
                )
            elif domain in ["switch", "input_boolean", "automation", "script"]:
                # For other entities, we can only turn them on (no brightness/power control)
                await hass.services.async_call(
                    domain, SERVICE_TURN_ON,
                    {ATTR_ENTITY_ID: entity_id},
                    blocking=True
                )
            else:
                _LOGGER.warning(f"Unsupported entity domain: {domain}. Cannot turn on {entity_id}")
    
    # Register the services
    hass.services.async_register(
        DOMAIN, SERVICE_SET_RELAY_MODE, handle_set_relay_mode, schema=SET_RELAY_MODE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_RELAY_POWER, handle_set_relay_power, schema=SET_RELAY_POWER_SCHEMA
    )
    
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
    
    # Check if current day is in schedule
    current_day = now.strftime("%A").lower()
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
    
    # Get devices from config
    devices = config_entry.data.get(CONF_DEVICES, [])
    
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
    
    @callback
    async def handle_state_change(entity_id, old_state, new_state):
        """Handle changes to the excess power sensor."""
        if not new_state or new_state.state in ("unknown", "unavailable"):
            return
        
        try:
            excess_power = float(new_state.state)
            _LOGGER.debug(f"Excess power: {excess_power}W")
            
            # Get current time for schedule checking
            now = dt_util.now()
            
            # Reset power allocation
            for device_id in power_allocation:
                power_allocation[device_id] = 0
            
            # Distribute excess power among devices based on priority
            remaining_power = excess_power
            
            for device in auto_control_devices:
                device_id = device.get(CONF_DEVICE_ID)
                device_type = device.get(CONF_DEVICE_TYPE, DEVICE_TYPE_CUSTOM)
                relay_entity = device.get(CONF_ESPHOME_RELAY_ENTITY)
                mode_select_entity = device.get(CONF_ESPHOME_MODE_SELECT_ENTITY)
                min_excess_power = device.get(CONF_MIN_EXCESS_POWER, 50)
                device_name = device.get(CONF_DEVICE_NAME, "Unknown")
                
                # Skip devices without relay entity
                if not relay_entity:
                    _LOGGER.debug(f"Device {device_name} has no relay entity, skipping")
                    continue
                
                # Check if device is within scheduled time
                if not is_device_in_schedule(device, now):
                    _LOGGER.debug(f"Device {device_name} is outside scheduled time, skipping")
                    # Turn off the device if it's outside scheduled time
                    await hass.services.async_call(
                        "light", SERVICE_TURN_OFF,
                        {ATTR_ENTITY_ID: relay_entity},
                        blocking=False
                    )
                    continue
                
                # Handle different device types
                if device_type == DEVICE_TYPE_STANDARD:
                    # Standard device: only on/off control based on threshold
                    if remaining_power >= min_excess_power:
                        # Turn on the device
                        _LOGGER.debug(f"Turning on standard device {device_name}")
                        await hass.services.async_call(
                            "light", SERVICE_TURN_ON,
                            {ATTR_ENTITY_ID: relay_entity, ATTR_BRIGHTNESS: 255},
                            blocking=False
                        )
                        
                        # Estimate power used (simplified)
                        power_used = min(remaining_power, min_excess_power * 3)
                        remaining_power -= power_used
                        
                        # Track power allocation
                        if device_id:
                            power_allocation[device_id] = power_used
                    else:
                        # Turn off the device
                        _LOGGER.debug(f"Turning off standard device {device_name} (remaining power {remaining_power}W below threshold {min_excess_power}W)")
                        await hass.services.async_call(
                            "light", SERVICE_TURN_OFF,
                            {ATTR_ENTITY_ID: relay_entity},
                            blocking=False
                        )
                elif device_type == DEVICE_TYPE_CUSTOM:
                    # Custom device: check mode and control accordingly
                    if not mode_select_entity:
                        _LOGGER.warning(f"Custom device {device_name} has no mode select entity")
                        continue
                    
                    # Get current mode
                    mode_state = hass.states.get(mode_select_entity)
                    if not mode_state or mode_state.state == RELAY_MODE_OFF:
                        # Don't do anything if mode is Off
                        _LOGGER.debug(f"Device {device_name} is in Off mode, skipping")
                        continue
                    
                    if mode_state.state == RELAY_MODE_PROPORTIONAL:
                        # In proportional mode, set power based on excess
                        if remaining_power >= min_excess_power:
                            # Calculate power percentage (0-100%)
                            # Scale it so min_excess_power = 5% and 3*min_excess_power = 100%
                            power_percent = min(100, max(5, (remaining_power - min_excess_power) / (2 * min_excess_power) * 95 + 5))
                            
                            # Set relay power
                            _LOGGER.debug(f"Setting device {device_name} power to {power_percent}% (remaining power: {remaining_power}W)")
                            await hass.services.async_call(
                                "light", SERVICE_TURN_ON,
                                {ATTR_ENTITY_ID: relay_entity, ATTR_BRIGHTNESS: int((power_percent / 100) * 255)},
                                blocking=False
                            )
                            
                            # Calculate power used by this device (approximate)
                            # This is a simplification - in reality, the power used would depend on the actual load
                            power_used = min(remaining_power, min_excess_power * 3 * (power_percent / 100))
                            remaining_power -= power_used
                            
                            # Track power allocation
                            if device_id:
                                power_allocation[device_id] = power_used
                        else:
                            # Turn off relay if excess power is below threshold
                            _LOGGER.debug(f"Turning off device {device_name} (remaining power {remaining_power}W below threshold {min_excess_power}W)")
                            await hass.services.async_call(
                                "light", SERVICE_TURN_OFF,
                                {ATTR_ENTITY_ID: relay_entity},
                                blocking=False
                            )
                    elif mode_state.state == RELAY_MODE_ON:
                        # In On mode, always set to full power
                        _LOGGER.debug(f"Device {device_name} is in On mode, setting to full power")
                        await hass.services.async_call(
                            "light", SERVICE_TURN_ON,
                            {ATTR_ENTITY_ID: relay_entity, ATTR_BRIGHTNESS: 255},
                            blocking=False
                        )
                        
                        # Estimate power used (simplified)
                        power_used = min(remaining_power, min_excess_power * 3)
                        remaining_power -= power_used
                        
                        # Track power allocation
                        if device_id:
                            power_allocation[device_id] = power_used
            
            # Update power distribution data
            entry_data[CONF_POWER_DISTRIBUTION] = {
                "total_power": excess_power,
                "remaining_power": remaining_power,
                "allocated_power": excess_power - remaining_power,
                "allocation": power_allocation.copy()
            }
            
        except (ValueError, TypeError) as e:
            _LOGGER.error(f"Error processing excess power value: {e}")
    
    # Subscribe to state changes of the excess power sensor
    excess_sensor_id = f"sensor.solarvampire_excess_1"
    entry_data["unsub_auto_control"] = hass.states.async_track_state_change(
        excess_sensor_id, handle_state_change
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
    
    # Remove config entry from data
    hass.data[DOMAIN].pop(config_entry.entry_id)
    
    # Unregister services
    hass.services.async_remove(DOMAIN, SERVICE_SET_RELAY_MODE)
    hass.services.async_remove(DOMAIN, SERVICE_SET_RELAY_POWER)
    
    return True
