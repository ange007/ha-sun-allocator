"""Service handlers for Sun Allocator."""
from homeassistant.const import (
    ATTR_ENTITY_ID
)

from .utils.logger import log_error
from .entity_control import set_power_for_entity, set_mode_for_entity

from .const import (
    CONF_DEVICE_ID, 
    CONF_ESPHOME_MODE_SELECT_ENTITY, 
    CONF_ESPHOME_RELAY_ENTITY, 
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_TYPE,
    DEVICE_TYPE_CUSTOM, 
    CONF_DEVICE_NAME,
    CONF_DEVICES,
)
    

async def handle_set_relay_mode(hass, config_entry, call):
    mode = call.data["mode"]
    entity_id = call.data.get(ATTR_ENTITY_ID)
    device_id = call.data.get(CONF_DEVICE_ID)
    devices = config_entry.data.get(CONF_DEVICES, [])
    if entity_id:
        await set_mode_for_entity(hass, entity_id, mode)
    elif device_id:
        device = next((d for d in devices if d.get(CONF_DEVICE_ID) == device_id), None)
        if device:
            entity_id = device.get(CONF_ESPHOME_MODE_SELECT_ENTITY)
            if entity_id:
                await set_mode_for_entity(hass, entity_id, mode)
            else:
                log_error(f"Device {device.get(CONF_DEVICE_NAME)} has no mode select entity configured")
        else:
            log_error(f"Device with ID {device_id} not found")
    else:
        for device in devices:
            entity_id = device.get(CONF_ESPHOME_MODE_SELECT_ENTITY)
            if entity_id:
                await set_mode_for_entity(hass, entity_id, mode)

async def handle_set_relay_power(hass, config_entry, call):
    power_percent = call.data["power"]
    entity_id = call.data.get(ATTR_ENTITY_ID)
    device_id = call.data.get(CONF_DEVICE_ID)
    devices = config_entry.data.get(CONF_DEVICES, [])

    if entity_id:
        await set_power_for_entity(hass, entity_id, power_percent)
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
                log_error(f"Device {device.get(CONF_DEVICE_NAME)} has no entity configured")
        else:
            log_error(f"Device with ID {device_id} not found")
    else:
        for device in devices:
            device_type = device.get(CONF_DEVICE_TYPE, DEVICE_TYPE_CUSTOM)
            if device_type == DEVICE_TYPE_CUSTOM:
                entity_id = device.get(CONF_ESPHOME_RELAY_ENTITY)
            else:
                entity_id = device.get(CONF_DEVICE_ENTITY)
            if entity_id:
                await set_power_for_entity(hass, entity_id, power_percent)
