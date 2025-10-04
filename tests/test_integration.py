"""Integration tests for full system functionality."""

import pytest
from unittest.mock import patch
from datetime import timedelta

from conftest import create_test_config_entry, create_test_device
from custom_components.sun_allocator import async_setup_entry, async_unload_entry
from custom_components.sun_allocator.const import (
    CONF_DEVICES,
    CONF_CONSUMPTION,
    CONF_DEBOUNCE_TIME,
)


@pytest.mark.parametrize("use_consumption_sensor", [False, True])
@pytest.mark.asyncio
async def test_full_system_integration_and_device_control(hass, use_consumption_sensor):
    """Test complete system from sensor update to device control."""
    device = create_test_device("test_device")
    device[CONF_DEBOUNCE_TIME] = 0  # No debounce for this test
    
    config_data = { CONF_DEVICES: [device] }
    if use_consumption_sensor:
        config_data[CONF_CONSUMPTION] = "sensor.test_consumption"
        
    config_entry = create_test_config_entry(config_data)

    # Set initial states before setting up the component
    hass.states.async_set("switch.test_device", "off")
    hass.states.async_set("sensor.test_pv_power", "200")
    hass.states.async_set("sensor.test_pv_voltage", "35")  # > Vmp=30
    hass.states.async_set("sensor.test_battery_power", "0")

    if use_consumption_sensor:
        hass.states.async_set("sensor.test_consumption", "30")
    else:
        hass.states.async_set("sensor.test_consumption", "0")

    await hass.async_block_till_done()  # Ensure states are processed

    with patch("homeassistant.core.ServiceRegistry.async_call") as mock_async_call:
        try:
            assert await async_setup_entry(hass, config_entry)
            await hass.async_block_till_done()

            # Trigger an update by changing a source sensor's state
            hass.states.async_set("sensor.test_pv_power", "201")
            await hass.async_block_till_done()

            # Verify sensors are updated
            excess_sensor = hass.states.get(
                f"sensor.sun_allocator_{config_entry.entry_id}_excess"
            )
            assert excess_sensor is not None
            assert float(excess_sensor.state) > 10  # Expected excess power
            
            # Verify device control
            mock_async_call.assert_called_with(
                "switch", "turn_on", {"entity_id": "switch.test_device"}, blocking=True
            )
        finally:
            # Clean up
            await async_unload_entry(hass, config_entry)
        
@pytest.mark.parametrize("use_consumption_sensor", [False, True])
@pytest.mark.asyncio
async def test_device_debounce_turn_on(hass, freezer, use_consumption_sensor):
    """Test that a device turns on after the debounce period."""
    device = create_test_device("test_device")
    device[CONF_DEBOUNCE_TIME] = 15

    config_data = { CONF_DEVICES: [device] }
    if use_consumption_sensor:
        config_data[CONF_CONSUMPTION] = "sensor.test_consumption"
        
    config_entry = create_test_config_entry(config_data)

    # Set initial states before setting up the component
    hass.states.async_set("switch.test_device", "off")
    hass.states.async_set("sensor.test_pv_power", "200")
    hass.states.async_set("sensor.test_pv_voltage", "35")  # > Vmp=30
    hass.states.async_set("sensor.test_battery_power", "0")
    
    if use_consumption_sensor:
        hass.states.async_set("sensor.test_consumption", "30")
    else:
        hass.states.async_set("sensor.test_consumption", "0")

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
            assert dist_sensor.attributes.get("reasons", {}).get(device["device_id"]) == "Debouncing"
            mock_async_call.assert_not_called()
            
            # Advance time by 10 seconds (less than debounce time)
            freezer.tick(timedelta(seconds=10))
            hass.states.async_set("sensor.test_pv_power", "201")  # Trigger update
            await hass.async_block_till_done()
 
            # Device should still be off
            mock_async_call.assert_not_called()

            # Advance time by another 10 seconds (total 20s > 15s debounce)
            freezer.tick(timedelta(seconds=10))
            hass.states.async_set("sensor.test_pv_power", "202")  # Trigger update
            await hass.async_block_till_done()

            # Now the device should be turned on
            # After the debounce period, the device should be turned on.
            # The mock_async_call might have multiple calls, we check for the last relevant one.
            mock_async_call.assert_any_call(
                "switch", "turn_on", {"entity_id": "switch.test_device"}, blocking=True
            )

        finally:
            # Clean up
            await async_unload_entry(hass, config_entry)

