"""Integration tests for full system functionality."""

import pytest
from unittest.mock import patch
from datetime import timedelta

from conftest import create_test_config_entry, create_test_device
from custom_components.sun_allocator import async_setup_entry, async_unload_entry
from custom_components.sun_allocator.const import (
    CONF_MIN_INVERTER_VOLTAGE,
    CONF_DEVICES,
    CONF_CONSUMPTION,
)


@pytest.mark.asyncio
async def test_full_system_integration_and_device_control(hass):
    """Test complete system from sensor update to device control."""
    device = create_test_device("test_device")
    device["debounce_time"] = 0  # No debounce for this test
    config_entry = create_test_config_entry(
        {
            CONF_MIN_INVERTER_VOLTAGE: 10.0,
            CONF_CONSUMPTION: "sensor.consumption",
            CONF_DEVICES: [device],
        }
    )

    # Set initial states before setting up the component
    hass.states.async_set("switch.test_device", "off")
    hass.states.async_set("sensor.pv_power", "200")
    hass.states.async_set("sensor.pv_voltage", "35")  # > Vmp=30
    hass.states.async_set("sensor.battery_power", "0")
    hass.states.async_set("sensor.consumption", "50")

    with patch("homeassistant.core.ServiceRegistry.async_call") as mock_async_call:
        try:
            # Setup complete system
            assert await async_setup_entry(hass, config_entry)
            await hass.async_block_till_done()

            # Verify sensors are updated
            excess_sensor = hass.states.get(
                f"sensor.sun_allocator_{config_entry.entry_id}_excess"
            )
            assert excess_sensor is not None
            # PV(200) - Consumption(50) - Reserve(0) = 150
            assert float(excess_sensor.state) == 150

            # Verify device control
            mock_async_call.assert_called_with(
                "switch", "turn_on", {"entity_id": "switch.test_device"}, blocking=True
            )
        finally:
            # Clean up
            await async_unload_entry(hass, config_entry)


@pytest.mark.asyncio
async def test_device_turn_on_with_debounce(hass, freezer):
    """Test that a device turns on after the debounce period."""
    device = create_test_device("test_device")
    device["debounce_time"] = 15
    config_entry = create_test_config_entry(
        {
            CONF_MIN_INVERTER_VOLTAGE: 10.0,
            CONF_CONSUMPTION: "sensor.consumption",
            CONF_DEVICES: [device],
        }
    )

    # Set initial states before setting up the component
    hass.states.async_set("switch.test_device", "off")
    hass.states.async_set("sensor.pv_power", "200")
    hass.states.async_set("sensor.pv_voltage", "35")  # > Vmp=30
    hass.states.async_set("sensor.battery_power", "0")
    hass.states.async_set("sensor.consumption", "0")

    with patch("homeassistant.core.ServiceRegistry.async_call") as mock_async_call:
        try:
            # Setup component
            assert await async_setup_entry(hass, config_entry)
            await hass.async_block_till_done()

            # At t=0, device should be off and debouncing
            dist_sensor = hass.states.get(
                f"sensor.sun_allocator_{config_entry.entry_id}_power_distribution"
            )
            assert dist_sensor is not None
            # assert dist_sensor.attributes["reasons"][device["device_id"]] == "Debouncing"
            mock_async_call.assert_not_called()

            # Advance time by 10 seconds (less than debounce time)
            freezer.tick(timedelta(seconds=10))
            hass.states.async_set("sensor.pv_power", "201")  # Trigger update
            await hass.async_block_till_done()

            # Device should still be off
            mock_async_call.assert_not_called()

            # Advance time by another 10 seconds (total 20s > 15s debounce)
            freezer.tick(timedelta(seconds=10))
            hass.states.async_set("sensor.pv_power", "202")  # Trigger update
            await hass.async_block_till_done()

            # Now the device should be turned on
            mock_async_call.assert_called_with(
                "switch", "turn_on", {"entity_id": "switch.test_device"}, blocking=True
            )
        finally:
            # Clean up
            await async_unload_entry(hass, config_entry)
