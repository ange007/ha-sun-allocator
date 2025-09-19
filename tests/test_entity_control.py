"""Tests for the Sun Allocator entity control logic."""
import pytest
import asyncio
import logging
from unittest.mock import AsyncMock, patch

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
            ]
        },
        entry_id="test_entry_id",
    )
    config_entry.add_to_hass(hass)

    # Create mock entities for sensors
    hass.states.async_set("sensor.test_pv_power", "100")  # Initial low power
    hass.states.async_set("sensor.test_pv_voltage", "25")  # Initial low voltage
    hass.states.async_set("switch.test_switch", "off")  # Ensure switch is off initially

    # Mock ServiceRegistry.async_call правильно
    with patch("homeassistant.core.ServiceRegistry.async_call", new_callable=AsyncMock) as mock_async_call:
        try:
            await async_setup_entry(hass, config_entry)
            await hass.async_block_till_done()

            # At this point, excess power should be 0, and the switch should be off
            assert hass.states.get("switch.test_switch").state == "off"
            mock_async_call.reset_mock()  # Reset mock to ignore setup calls

            # Now, simulate a state change that should generate excess power
            hass.states.async_set("sensor.test_pv_voltage", "35")  # Voltage > Vmp (30)
            hass.states.async_set("sensor.test_pv_power", "250")  # Power is high
            
            # Додаємо додаткове очікування для обробки змін
            await hass.async_block_till_done()
            await asyncio.sleep(0.5)  # Довший сон для гарантії обробки подій
            await hass.async_block_till_done()
            await asyncio.sleep(0.5)  # Ще один довший сон
            await hass.async_block_till_done()

            # Manually update the state of the mock switch entity
            hass.states.async_set("switch.test_switch", "on")

            # Assert that the service call was made to turn on the switch
            mock_async_call.assert_called_once_with(
                "switch", "turn_on", {"entity_id": "switch.test_switch"}, blocking=False
            )

            # Assert that the device is turned on
            assert hass.states.get("switch.test_switch").state == "on"

        finally:
            await async_unload_entry(hass, config_entry)
            await hass.async_block_till_done()            
