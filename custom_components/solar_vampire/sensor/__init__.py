"""Solar Vampire sensor platform."""
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .sensors import (
    SolarVampireExcessSensor,
    SolarVampireMaxPowerSensor,
    SolarVampireCurrentMaxPowerSensor,
    SolarVampireUsagePercentSensor,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solar Vampire sensors from a config entry."""
    sensors = [
        SolarVampireExcessSensor(hass, config_entry.data, config_entry.entry_id),
        SolarVampireMaxPowerSensor(hass, config_entry.data, config_entry.entry_id),
        SolarVampireCurrentMaxPowerSensor(hass, config_entry.data, config_entry.entry_id),
        SolarVampireUsagePercentSensor(hass, config_entry.data, config_entry.entry_id),
    ]
    async_add_entities(sensors)