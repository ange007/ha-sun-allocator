"""SunAllocator sensor platform."""

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

# Import main sensors
from .sensors import (
    SunAllocatorExcessSensor,
    SunAllocatorMaxPowerSensor,
    SunAllocatorCurrentMaxPowerSensor,
    SunAllocatorUsagePercentSensor,
    SunAllocatorPowerDistributionSensor,
)

# Import the new per-device sensor
from .sensors.device_power_alloc import SunAllocatorDevicePowerSensor

from ..const import DOMAIN, CONF_DEVICES, CONF_DEVICE_ID
from ..core.logger import log_debug


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sun Allocator sensors from a config entry."""

    # Get the current count of entries to create a unique, incrementing index
    root = hass.data.setdefault(DOMAIN, {})
    entry_index = int(root.get("_entry_count", 0)) + 1

    # Create the main sensors
    sensors = [
        SunAllocatorExcessSensor(
            hass, config_entry.data, config_entry.entry_id, entry_index
        ),
        SunAllocatorMaxPowerSensor(
            hass, config_entry.data, config_entry.entry_id, entry_index
        ),
        SunAllocatorCurrentMaxPowerSensor(
            hass, config_entry.data, config_entry.entry_id, entry_index
        ),
        SunAllocatorUsagePercentSensor(
            hass, config_entry.data, config_entry.entry_id, entry_index
        ),
        SunAllocatorPowerDistributionSensor(hass, config_entry.entry_id, entry_index),
    ]

    # Create a sensor for each configured device
    devices = config_entry.data.get(CONF_DEVICES, [])
    for device_config in devices:
        if device_config.get(CONF_DEVICE_ID):
            sensors.append(
                SunAllocatorDevicePowerSensor(
                    hass, config_entry.entry_id, device_config
                )
            )

    log_debug("Sensors: %s", [sensor.entity_id for sensor in sensors])
    async_add_entities(sensors)
