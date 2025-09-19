"""Tests for the Sun Allocator sensors."""
import pytest

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sun_allocator.const import DOMAIN, SENSOR_ID_PREFIX, SENSOR_EXCESS_SUFFIX, SENSOR_MAX_POWER_SUFFIX, SENSOR_CURRENT_MAX_POWER_SUFFIX, SENSOR_USAGE_PERCENT_SUFFIX, CONF_DEVICES, CONF_DEVICE_ID, CONF_DEVICE_ENTITY, DOMAIN_SWITCH


@pytest.mark.asyncio
async def test_sensors_are_created(hass: HomeAssistant) -> None:
    """Test that the sensors are created."""
    # Setup the component with a mock entry
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DEVICES: [
                {
                    CONF_DEVICE_ID: "test_device",
                    CONF_DEVICE_ENTITY: f"{DOMAIN_SWITCH}.test_switch",
                }
            ]
        },
        entry_id="test_entry_id",
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Check that the sensors have been created
    assert hass.states.get(f"sensor.{SENSOR_ID_PREFIX}_{SENSOR_EXCESS_SUFFIX}_1") is not None
    assert hass.states.get(f"sensor.{SENSOR_ID_PREFIX}_{SENSOR_MAX_POWER_SUFFIX}_1") is not None
    assert hass.states.get(f"sensor.{SENSOR_ID_PREFIX}_{SENSOR_CURRENT_MAX_POWER_SUFFIX}_1") is not None
    assert hass.states.get(f"sensor.{SENSOR_ID_PREFIX}_{SENSOR_USAGE_PERCENT_SUFFIX}_1") is not None
