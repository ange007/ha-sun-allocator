"""SunAllocator switch platform."""

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .auto_control_switch import SunAllocatorDeviceAutoControlSwitch
from ..const import CONF_DEVICES, CONF_DEVICE_ID


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sun Allocator switch entities from a config entry."""
    devices = config_entry.data.get(CONF_DEVICES, [])
    switches = [
        SunAllocatorDeviceAutoControlSwitch(hass, config_entry.entry_id, device_config)
        for device_config in devices
        if device_config.get(CONF_DEVICE_ID)
    ]
    async_add_entities(switches)
