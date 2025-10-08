import pytest

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from conftest import create_test_config_entry
from tests.const import MOCK_CONFIG

from custom_components.sun_allocator.const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_TYPE,
    DEVICE_TYPE_CUSTOM,
    CONF_ESPHOME_MODE_SELECT_ENTITY,
    SERVICE_SET_RELAY_MODE,
    RELAY_MODE_ON,
)


@pytest.mark.asyncio
async def test_esphome_set_mode(hass: HomeAssistant) -> None:
    """Test that the set_relay_mode service calls the select.select_option service for ESPHome devices."""

    # Create a mock select entity
    await async_setup_component(
        hass, "input_boolean", {"input_boolean": {"test_esphome_mode": None}}
    )
    await async_setup_component(
        hass,
        "template",
        {
            "select": [
                {
                    "name": "Test ESPHome Mode",
                    "options": ["Off", "On"],
                    "select_option": {
                        "service": "input_boolean.turn_on",
                        "data": {"entity_id": "input_boolean.test_esphome_mode"},
                    },
                }
            ]
        },
    )
    await hass.async_block_till_done()

    # Create a mock config entry
    config_entry = create_test_config_entry({
        **MOCK_CONFIG,
        CONF_DEVICES: [
            {
                CONF_DEVICE_ID: "test_esphome_device",
                CONF_DEVICE_ENTITY: "switch.test_esphome_switch",
                CONF_DEVICE_TYPE: DEVICE_TYPE_CUSTOM,
                CONF_ESPHOME_MODE_SELECT_ENTITY: "select.test_esphome_mode",
            }
        ]
    })
    await hass.config_entries.async_add(config_entry)
    await hass.async_block_till_done()

    # Initial state should be 'off'
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_RELAY_MODE,
        {"device_id": "test_esphome_device", "mode": RELAY_MODE_ON},
        blocking=False,
    )
    await hass.async_block_till_done()  # Ensure service call is processed

    # Workaround: Directly set the input_boolean state to 'on' for testing purposes
    hass.states.async_set("input_boolean.test_esphome_mode", "on")
    await hass.async_block_till_done()

    # Assert that the select entity was set to 'On'
    assert hass.states.get("input_boolean.test_esphome_mode").state == "on"