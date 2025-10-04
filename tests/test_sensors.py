"""Tests for the Sun Allocator sensors."""

import pytest

from homeassistant.core import HomeAssistant

from conftest import create_test_config_entry
from tests.const import MOCK_CONFIG

from custom_components.sun_allocator.const import (
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_ENTITY,
    DOMAIN_SWITCH,
)


@pytest.mark.asyncio
async def test_sensors_are_created(hass: HomeAssistant) -> None:
    """Test that the sensors are created."""
    # Combine mock config with specific device data for this test
    config_data = {
        **MOCK_CONFIG, 
        CONF_DEVICES: [
            {
                CONF_DEVICE_ID: "test_device",
                CONF_DEVICE_ENTITY: f"{DOMAIN_SWITCH}.test_switch",
            }
        ]
    }

    config_entry = create_test_config_entry(config_data)
    await hass.config_entries.async_add(config_entry)
    await hass.async_block_till_done()

    # Check that the sensors have been created
    assert (
        hass.states.get(f"sensor.sun_allocator_{config_entry.entry_id}_excess")
        is not None
    )
    assert (
        hass.states.get(f"sensor.sun_allocator_{config_entry.entry_id}_max_power")
        is not None
    )
    assert (
        hass.states.get(
            f"sensor.sun_allocator_{config_entry.entry_id}_current_max_power"
        )
        is not None
    )
    assert (
        hass.states.get(f"sensor.sun_allocator_{config_entry.entry_id}_usage_percent")
        is not None
    )
