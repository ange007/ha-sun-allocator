"""Integration tests for full system functionality."""

import asyncio
import pytest
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from conftest import create_test_config_entry, create_test_device

from custom_components.sun_allocator import async_setup_entry, async_unload_entry
from custom_components.sun_allocator.const import (
    CONF_DEVICES,
    CONF_CONSUMPTION,
    CONF_DEVICE_DEBOUNCE_TIME,
    CONF_PV_POWER,
    CONF_PV_VOLTAGE,
    CONF_PANEL_VMP,
    CONF_PANEL_IMP,
    CONF_PANEL_COUNT,
    CONF_DEVICE_ID,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_TYPE,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_DEVICE_MIN_EXPECTED_W,
    CONF_MIN_INVERTER_VOLTAGE,
    DEVICE_TYPE_STANDARD,
    CONF_HYSTERESIS_W,
)


@pytest.mark.parametrize("use_consumption_sensor", [False, True])
@pytest.mark.asyncio
async def test_device_control(
    hass: HomeAssistant, use_consumption_sensor
) -> None:
    """Test complete system from sensor update to device control."""
    device = create_test_device("test_device")
    device[CONF_DEVICE_DEBOUNCE_TIME] = 0  # No debounce for this test

    config_data = {CONF_DEVICES: [device]}
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
            excess_sensor = hass.states.get(f"sensor.sun_allocator_{config_entry.entry_id}_excess")
            assert excess_sensor is not None
            assert float(excess_sensor.state) > 10  # Expected excess power

            # Verify device control
            mock_async_call.assert_called_with(
                "switch", "turn_on", {"entity_id": "switch.test_device"}, blocking=True
            )
        finally:
            # Clean up
            await async_unload_entry(hass, config_entry)


@pytest.mark.asyncio
async def test_device_debounce_on_and_off(hass: HomeAssistant) -> None:
    """Test device deactivation, debounce, and 'not enough power' scenarios."""

    entity_id = "input_boolean.test_switch_debounce"

    # Set up a template switch
    await async_setup_component(
        hass, "input_boolean", {"input_boolean": {"test_switch_debounce": None}}
    )
    await hass.async_block_till_done()

    config_data = {
        CONF_PV_POWER: "sensor.test_pv_power",
        CONF_PV_VOLTAGE: "sensor.test_pv_voltage",
        CONF_PANEL_VMP: 30.0,
        CONF_PANEL_IMP: 10.0,
        CONF_PANEL_COUNT: 1,
        CONF_MIN_INVERTER_VOLTAGE: 10.0,
        CONF_HYSTERESIS_W: 20,
        CONF_DEVICES: [
            {
                CONF_DEVICE_ID: "test_device_debounce",
                CONF_DEVICE_ENTITY: entity_id,
                CONF_DEVICE_TYPE: DEVICE_TYPE_STANDARD,
                CONF_AUTO_CONTROL_ENABLED: True,
                CONF_DEVICE_MIN_EXPECTED_W: 100,
                CONF_DEVICE_DEBOUNCE_TIME: 1,  # 1-second debounce
            }
        ],
    }
    config_entry = create_test_config_entry(
        extra_data=config_data, entry_id="test_debounce_entry"
    )
    config_entry.add_to_hass(hass)

    # Set initial states
    hass.states.async_set("sensor.test_pv_power", "0")
    hass.states.async_set("sensor.test_pv_voltage", "0")
    hass.states.async_set(entity_id, "off")
    await hass.async_block_till_done()

    await async_setup_entry(hass, config_entry)
    await hass.async_block_till_done()

    # Initial state: No power, switch should be off
    assert hass.states.get(entity_id).state == "off"

    # --- Test Turn-On with Debounce ---
    hass.states.async_set("sensor.test_pv_voltage", "35")  # Voltage > Vmp
    hass.states.async_set("sensor.test_pv_power", "7.5")  # Less than min_expected_w
    await hass.async_block_till_done()

    # Switch should remain off, since not enough power
    assert hass.states.get(entity_id).state == "off"

    # Wait for debounce time
    await asyncio.sleep(1)

    # Update again, still not enough power
    hass.states.async_set("sensor.test_pv_power", "7.5")
    await hass.async_block_till_done()

    # State should still be off
    assert hass.states.get(entity_id).state == "off"

    # Clean up
    await async_unload_entry(hass, config_entry)
    await hass.async_block_till_done()