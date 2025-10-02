"""Service handlers for Sun Allocator."""

from homeassistant.const import ATTR_ENTITY_ID

from .logger import log_error
from .entity_control import set_power_for_entity, set_mode_for_entity

from ..const import (
    DOMAIN,
    CONF_DEVICE_ID,
    CONF_ESPHOME_MODE_SELECT_ENTITY,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_NAME,
    CONF_DEVICES,
)


def _find_config_entry_for_device(hass, device_id):
    """Find the config entry that contains the specified device_id."""
    domain_data = hass.data.get(DOMAIN, {})
    for entry_id, entry_data in domain_data.items():
        if entry_id.startswith("_"):  # Skip internal keys like _entry_count
            continue
        config = entry_data.get("config", {})
        devices = config.get(CONF_DEVICES, [])
        for device in devices:
            if device.get(CONF_DEVICE_ID) == device_id:
                # Return the config entry data
                return config
    return None


async def handle_set_relay_mode(hass, call):
    """Handle the set_relay_mode service call."""
    mode = call.data["mode"]
    entity_id = call.data.get(ATTR_ENTITY_ID)
    device_id = call.data.get(CONF_DEVICE_ID)

    if entity_id:
        await set_mode_for_entity(hass, entity_id, mode)
    elif device_id:
        config = _find_config_entry_for_device(hass, device_id)
        if not config:
            log_error(f"Config entry not found for device ID {device_id}")
            return

        devices = config.get(CONF_DEVICES, [])
        device = next((d for d in devices if d.get(CONF_DEVICE_ID) == device_id), None)
        if device:
            entity_id = device.get(CONF_ESPHOME_MODE_SELECT_ENTITY)
            if entity_id:
                await set_mode_for_entity(hass, entity_id, mode)
            else:
                log_error(
                    f"Device {device.get(CONF_DEVICE_NAME)} has no mode select entity configured"
                )
        else:
            log_error(f"Device with ID {device_id} not found")
    else:
        # Apply to all devices across all config entries
        domain_data = hass.data.get(DOMAIN, {})
        for entry_id, entry_data in domain_data.items():
            if entry_id.startswith("_"):  # Skip internal keys
                continue
            config = entry_data.get("config", {})
            devices = config.get(CONF_DEVICES, [])
            for device in devices:
                entity_id = device.get(CONF_ESPHOME_MODE_SELECT_ENTITY)
                if entity_id:
                    await set_mode_for_entity(hass, entity_id, mode)


async def handle_set_relay_power(hass, call):
    """Handle the set_relay_power service call."""
    power_percent = call.data["power"]
    entity_id = call.data.get(ATTR_ENTITY_ID)
    device_id = call.data.get(CONF_DEVICE_ID)

    if entity_id:
        await set_power_for_entity(hass, entity_id, power_percent)
    elif device_id:
        config = _find_config_entry_for_device(hass, device_id)
        if not config:
            log_error(f"Config entry not found for device ID {device_id}")
            return

        devices = config.get(CONF_DEVICES, [])
        device = next((d for d in devices if d.get(CONF_DEVICE_ID) == device_id), None)
        if device:
            entity_id = device.get(CONF_DEVICE_ENTITY)
            if entity_id:
                await set_power_for_entity(hass, entity_id, power_percent)
            else:
                log_error(
                    f"Device {device.get(CONF_DEVICE_NAME)} has no entity configured"
                )
        else:
            log_error(f"Device with ID {device_id} not found")
    else:
        # Apply to all devices across all config entries
        domain_data = hass.data.get(DOMAIN, {})
        for entry_id, entry_data in domain_data.items():
            if entry_id.startswith("_"):  # Skip internal keys
                continue
            config = entry_data.get("config", {})
            devices = config.get(CONF_DEVICES, [])
            for device in devices:
                entity_id = device.get(CONF_DEVICE_ENTITY)
                if entity_id:
                    await set_power_for_entity(hass, entity_id, power_percent)
