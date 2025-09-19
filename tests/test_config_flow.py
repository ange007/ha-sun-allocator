"""Tests for the Sun Allocator config flow."""
from unittest.mock import patch

import pytest
from homeassistant import config_entries, setup
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.sun_allocator.const import (
    DOMAIN,
    CONF_PV_POWER,
    CONF_PV_VOLTAGE,
    CONF_CONSUMPTION,
    CONF_BATTERY_POWER,
    CONF_BATTERY_POWER_REVERSED,
    CONF_VMP,
    CONF_IMP,
    CONF_PANEL_COUNT,
    CONF_PANEL_CONFIGURATION,
    PANEL_CONFIG_SERIES,
    STEP_DEVICES,
    ACTION_ADD,
    STEP_DEVICE_NAME_TYPE,
    STEP_DEVICE_SELECTION,
    STEP_DEVICE_BASIC_SETTINGS,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_DEVICE_ENTITY,
)


@pytest.mark.asyncio
async def test_form_user(hass: HomeAssistant) -> None:
    """Test we get the form."""
    # Create mock sensors
    hass.states.async_set("sensor.sun_allocator_test_power", "1000")
    hass.states.async_set("sensor.sun_allocator_test_voltage", "230")
    hass.states.async_set("sensor.sun_allocator_test_battery", "50")

    await setup.async_setup_component(hass, "persistent_notification", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


@pytest.mark.asyncio
async def test_form_device_selection_step(hass: HomeAssistant) -> None:
    """Test that the device selection step works."""
    # Create mock sensors
    hass.states.async_set("sensor.sun_allocator_test_pv_power", "1000")
    hass.states.async_set("sensor.sun_allocator_test_pv_voltage", "230")
    hass.states.async_set("sensor.sun_allocator_test_battery_power", "50")
    hass.states.async_set("sensor.sun_allocator_test_consumption", "500")
    
    # Create a mock switch entity
    hass.states.async_set("switch.test_switch", "on", {"friendly_name": "Test Switch"})

    # Start the config flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Provide user input for the first step
    with patch(
        "custom_components.sun_allocator.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_PV_POWER: "sensor.sun_allocator_test_pv_power",
                CONF_PV_VOLTAGE: "sensor.sun_allocator_test_pv_voltage",
                CONF_CONSUMPTION: "sensor.sun_allocator_test_consumption",
                CONF_BATTERY_POWER: "sensor.sun_allocator_test_battery_power",
                CONF_BATTERY_POWER_REVERSED: False,
                CONF_VMP: 36.0,
                CONF_IMP: 8.0,
                CONF_PANEL_COUNT: 1,
                CONF_PANEL_CONFIGURATION: PANEL_CONFIG_SERIES,
            },
        )
        await hass.async_block_till_done()

    # We should now be at the device management step
    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == STEP_DEVICES

    # "Press" the "add device" option
    result3 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        {"action": ACTION_ADD},
    )
    await hass.async_block_till_done()
    
    # We should now be at the device name/type step
    assert result3["type"] == FlowResultType.FORM
    assert result3["step_id"] == STEP_DEVICE_NAME_TYPE

    # Provide device name and type
    result4 = await hass.config_entries.flow.async_configure(
        result3["flow_id"],
        {
            CONF_DEVICE_NAME: "Test Device",
            CONF_DEVICE_TYPE: "standard",
        },
    )
    await hass.async_block_till_done()

    # We should now be at the device selection step, which is what we want to test
    assert result4["type"] == FlowResultType.FORM
    assert result4["step_id"] == STEP_DEVICE_SELECTION

    # Submit the device selection form
    result5 = await hass.config_entries.flow.async_configure(
        result4["flow_id"],
        {CONF_DEVICE_ENTITY: "switch.test_switch"},
    )
    await hass.async_block_till_done()

    # Check if we successfully moved to the next step
    assert result5["type"] == FlowResultType.FORM, f"Expected a form, but got {result5}"
    assert result5["step_id"] == STEP_DEVICE_BASIC_SETTINGS
    assert "errors" not in result5 or not result5["errors"]