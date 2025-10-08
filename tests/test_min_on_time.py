import asyncio
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from conftest import create_test_config_entry

from custom_components.sun_allocator import async_setup_entry, async_unload_entry
from custom_components.sun_allocator.const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_TYPE,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_DEVICE_MIN_EXPECTED_W,
    CONF_DEVICE_MIN_ON_TIME,
    CONF_DEVICE_DEBOUNCE_TIME,
    DEVICE_TYPE_STANDARD,
)


@pytest.mark.asyncio
async def test_minimum_on_time_and_refusal_reason(hass: HomeAssistant) -> None:
    """Test minimum on-time logic and diagnostic refusal reasons."""

    entity_id = "input_boolean.test_min_on_time"
    
    # Set up a template switch
    await async_setup_component(
        hass, "input_boolean", {"input_boolean": {"test_min_on_time": None}}
    )
    await hass.async_block_till_done()

    config_data = {
        "devices": [
            {
                CONF_DEVICE_ID: "test_min_on_time",
                CONF_DEVICE_ENTITY: entity_id,
                CONF_DEVICE_TYPE: DEVICE_TYPE_STANDARD,
                CONF_AUTO_CONTROL_ENABLED: True,
                CONF_DEVICE_MIN_EXPECTED_W: 10,
                CONF_DEVICE_MIN_ON_TIME: 2,
                CONF_DEVICE_DEBOUNCE_TIME: 1,
            }
        ],
    }
    config_entry = create_test_config_entry(extra_data=config_data, entry_id="test_min_on_time_entry")
    config_entry.add_to_hass(hass)

    # Set initial states
    hass.states.async_set("sensor.test_battery_power", "0")
    hass.states.async_set("sensor.test_pv_power", "0")
    hass.states.async_set("sensor.test_pv_voltage", "0")
    hass.states.async_set(entity_id, "off")
    await hass.async_block_till_done()

    # Set up the component
    await async_setup_entry(hass, config_entry)
    await hass.async_block_till_done()
    
    # Initial state: No power, switch should be off
    assert hass.states.get(entity_id).state == "off"

    # Turn ON: should activate
    hass.states.async_set("sensor.test_pv_power", "200")
    hass.states.async_set("sensor.test_pv_voltage", "33") # Set voltage > Vmp to simulate excess
    await hass.async_block_till_done()
    
    await asyncio.sleep(1.1) # Wait for debounce time (1s) to pass

    # Re-trigger to ensure the listener picks up the change after debounce
    hass.states.async_set("sensor.test_pv_power", "201") # Change value to ensure listener fires
    await hass.async_block_till_done()
    
    # Workaround: Directly set the switch state to 'on' for testing purposes
    assert hass.states.get(entity_id).state == "on"

    # Try to turn OFF before min_on_time elapsed
    hass.states.async_set("sensor.test_battery_power", "0")
    hass.states.async_set("sensor.test_pv_power", "0")
    await hass.async_block_till_done()
    
    # Wait for debounce
    await asyncio.sleep(1.1) 
    hass.states.async_set("sensor.test_pv_power", "-1") # re-trigger
    await hass.async_block_till_done()
    
    # Check state and refusal reason
    state = hass.states.get(entity_id).state
    entry_data = hass.data["sun_allocator"][config_entry.entry_id]
    status = entry_data["device_status"]["test_min_on_time"]
    assert state == "on", "Device should refuse to turn off due to min_on_time"
    assert any("Minimum on-time" in r for r in status.get("refusal_reasons", [])), "Refusal reason 'Minimum on-time' should be present"

    # Wait for min_on_time to elapse
    await asyncio.sleep(2.1)
    
    # Now turn OFF: should deactivate
    hass.states.async_set("sensor.test_pv_power", "0")
    await hass.async_block_till_done()

    # Re-trigger to allow debounce for turn-off
    await asyncio.sleep(1.1)
    hass.states.async_set("sensor.test_pv_power", "-1") # Final re-trigger
    await hass.async_block_till_done()
    
    # Check final state
    state = hass.states.get(entity_id).state
    entry_data = hass.data["sun_allocator"][config_entry.entry_id]
    status = entry_data["device_status"]["test_min_on_time"]
    assert state == "off", f"Device should turn OFF after min_on_time but state is {state}"
    
    await async_unload_entry(hass, config_entry)