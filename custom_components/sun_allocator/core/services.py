"""Service handlers for Sun Allocator."""

from __future__ import annotations

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall

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


def rebuild_device_index(hass: HomeAssistant) -> None:
    """Rebuild the device_id -> entry_id index. Call after entry setup or update."""
    domain_data = hass.data.get(DOMAIN, {})
    index: dict[str, str] = {}
    for entry_id, entry_data in domain_data.items():
        if not isinstance(entry_data, dict) or entry_id.startswith("_"):
            continue
        config = entry_data.get("config", {})
        for device in config.get(CONF_DEVICES, []) or []:
            dev_id = device.get(CONF_DEVICE_ID)
            if dev_id:
                index[dev_id] = entry_id
    domain_data["_device_index"] = index


def _get_device_index(hass: HomeAssistant) -> dict[str, str]:
    domain_data = hass.data.get(DOMAIN, {})
    index = domain_data.get("_device_index")
    if index is None:
        rebuild_device_index(hass)
        index = domain_data.get("_device_index", {})
    return index


def _find_config_entry_for_device(hass: HomeAssistant, device_id: str) -> dict | None:
    """Return the config dict for the entry that contains device_id, or None."""
    entry_id = _get_device_index(hass).get(device_id)
    if not entry_id:
        return None
    entry_data = hass.data.get(DOMAIN, {}).get(entry_id)
    if not isinstance(entry_data, dict):
        return None
    return entry_data.get("config")


async def handle_set_relay_mode(hass: HomeAssistant, call: ServiceCall) -> None:
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
                log_error(f"Device {device.get(CONF_DEVICE_NAME)} has no mode select entity configured")
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


async def handle_set_relay_power(hass: HomeAssistant, call: ServiceCall) -> None:
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
                log_error(f"Device {device.get(CONF_DEVICE_NAME)} has no entity configured")
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
