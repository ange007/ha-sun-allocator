"""Tests for the Sun Allocator sensors."""

import pytest

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sun_allocator.const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_ENTITY,
    DOMAIN_SWITCH,
)


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
