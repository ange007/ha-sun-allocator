"""SunAllocator number platform."""

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .timed_run import SunAllocatorDeviceTimedRunNumber

from ..const import CONF_DEVICES, CONF_DEVICE_ID, CONF_DEVICE_ENTITY
from ..core.logger import log_debug


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the per-device timed-run number entities."""
    numbers = []
    for device_config in config_entry.data.get(CONF_DEVICES, []):
        # Only devices that actually control an entity can be run on a timer.
        if device_config.get(CONF_DEVICE_ID) and device_config.get(CONF_DEVICE_ENTITY):
            numbers.append(
                SunAllocatorDeviceTimedRunNumber(hass, config_entry, device_config)
            )
    log_debug("Numbers: %s", [n.unique_id for n in numbers])
    async_add_entities(numbers)
