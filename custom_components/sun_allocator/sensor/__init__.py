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

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sun Allocator sensors from a config entry."""
    sensors = [
        SunAllocatorExcessSensor(hass, config_entry.data, config_entry.entry_id),
        SunAllocatorMaxPowerSensor(hass, config_entry.data, config_entry.entry_id),
        SunAllocatorCurrentMaxPowerSensor(hass, config_entry.data, config_entry.entry_id),
        SunAllocatorUsagePercentSensor(hass, config_entry.data, config_entry.entry_id),
        SunAllocatorPowerDistributionSensor(hass, config_entry.entry_id),
    ]
    async_add_entities(sensors)