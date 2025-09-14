"""SunAllocator sensor platform."""
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .sensors import (
    SunAllocatorExcessSensor,
    SunAllocatorMaxPowerSensor,
    SunAllocatorCurrentMaxPowerSensor,
    SunAllocatorUsagePercentSensor,
    SunAllocatorPowerDistributionSensor,
)

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sun Allocator sensors from a config entry."""
    
    # Get the current count of entries to create a unique, incrementing index
    root = hass.data.setdefault(DOMAIN, {})
    entry_index = int(root.get("_entry_count", 0)) + 1

    sensors = [
        SunAllocatorExcessSensor(hass, config_entry.data, config_entry.entry_id, entry_index),
        SunAllocatorMaxPowerSensor(hass, config_entry.data, config_entry.entry_id, entry_index),
        SunAllocatorCurrentMaxPowerSensor(hass, config_entry.data, config_entry.entry_id, entry_index),
        SunAllocatorUsagePercentSensor(hass, config_entry.data, config_entry.entry_id, entry_index),
        SunAllocatorPowerDistributionSensor(hass, config_entry.entry_id, entry_index),
    ]
    async_add_entities(sensors)