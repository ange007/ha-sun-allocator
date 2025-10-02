"""Tests for the Sun Allocator entity control logic."""

import pytest
import asyncio
import logging

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sun_allocator.const import (
    DOMAIN,
    CONF_PV_POWER,
    CONF_PV_VOLTAGE,
    CONF_VMP,
    CONF_IMP,
    CONF_PANEL_COUNT,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_TYPE,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_MIN_EXPECTED_W,
    CONF_DEBOUNCE_TIME,
    CONF_MIN_INVERTER_VOLTAGE,
    DEVICE_TYPE_STANDARD,
    CONF_DEFAULT_MIN_START_W,
    CONF_HYSTERESIS_W,
)
from custom_components.sun_allocator import async_setup_entry, async_unload_entry

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)


@pytest.mark.asyncio
async def test_simple_power_allocation(hass: HomeAssistant) -> None:
    """Test simple power allocation to one device."""
    # Set up a template switch to test service calls
    await async_setup_component(
        hass, "input_boolean", {"input_boolean": {"test_switch": None}}
    )
    await async_setup_component(
        hass,
        "switch",
        {
            "switch": [
                {
                    "platform": "template",
                    "switches": {
                        "test_switch": {
                            "value_template": "{{ states('input_boolean.test_switch') }}",
                            "turn_on": {
                                "service": "input_boolean.turn_on",
                                "entity_id": "input_boolean.test_switch",
                            },
                            "turn_off": {
                                "service": "input_boolean.turn_off",
                                "entity_id": "input_boolean.test_switch",
                            },
                        }
                    },
                }
            ]
        },
    )
    await hass.async_block_till_done()

    # A more complete config entry
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_PV_POWER: "sensor.test_pv_power",
            CONF_PV_VOLTAGE: "sensor.test_pv_voltage",
            CONF_VMP: 30.0,
            CONF_IMP: 10.0,
            CONF_PANEL_COUNT: 1,
            CONF_MIN_INVERTER_VOLTAGE: 10.0,
            CONF_DEFAULT_MIN_START_W: 0,
            CONF_HYSTERESIS_W: 20,
            CONF_DEVICES: [
                {
                    CONF_DEVICE_ID: "test_device",
                    CONF_DEVICE_ENTITY: "switch.test_switch",
                    CONF_DEVICE_TYPE: DEVICE_TYPE_STANDARD,
                    CONF_AUTO_CONTROL_ENABLED: True,
                    CONF_MIN_EXPECTED_W: 50,
                    CONF_DEBOUNCE_TIME: 0,
                }
            ],
        },
        entry_id="test_entry_id",
    )
    config_entry.add_to_hass(hass)

    # Create mock entities for sensors
    hass.states.async_set("sensor.test_pv_power", "100")  # Initial power
    hass.states.async_set(
        "sensor.test_pv_voltage", "25"
    )  # Initial voltage < Vmp, so no excess
    hass.states.async_set(
        "input_boolean.test_switch", "off"
    )  # Ensure switch is off initially
    await hass.async_block_till_done()

    try:
        await async_setup_entry(hass, config_entry)
        await hass.async_block_till_done()

        # At this point, voltage is low, so switch should be off
        assert hass.states.get("switch.test_switch").state == "off"

        # Now, simulate a state change that should generate excess power
        hass.states.async_set("sensor.test_pv_voltage", "35")  # Voltage > Vmp (30)
        hass.states.async_set("sensor.test_pv_power", "250")  # Power is high

        # Add additional wait for changes to be processed
        await hass.async_block_till_done()
        # A small sleep might be necessary for the update to propagate through the event loop
        await asyncio.sleep(0.1)
        await hass.async_block_till_done()

        # Assert that the device is turned on
        assert hass.states.get("switch.test_switch").state == "on"

    finally:
        await async_unload_entry(hass, config_entry)
        await hass.async_block_till_done()
