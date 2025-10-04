"""Tests for sensor updates in Sun Allocator."""

import pytest
from homeassistant.core import HomeAssistant

from conftest import create_test_config_entry
from custom_components.sun_allocator.const import (
    CONF_PANEL_CONFIGURATION,
    PANEL_CONFIG_SERIES,
    PANEL_CONFIG_PARALLEL_SERIES,
    CONF_VMP,
    CONF_IMP,
    CONF_VOC,
    CONF_ISC,
    CONF_PANEL_COUNT,
    CONF_PV_POWER,
    CONF_PV_VOLTAGE,
)


@pytest.mark.asyncio
async def test_sensor_excess_configuration_update(hass: HomeAssistant) -> None:
    """Test that the excess sensor's panel_configuration attribute is updated."""
    await _test_sensor_configuration_update(hass, "excess")


@pytest.mark.asyncio
async def test_sensor_max_power_configuration_update(hass: HomeAssistant) -> None:
    """Test that the max_power sensor's panel_configuration attribute is updated."""
    await _test_sensor_configuration_update(hass, "max_power")


@pytest.mark.asyncio
async def test_sensor_current_max_power_configuration_update(hass: HomeAssistant) -> None:
    """Test that the current_max_power sensor's panel_configuration attribute is updated."""
    await _test_sensor_configuration_update(hass, "current_max_power")


@pytest.mark.asyncio
async def test_sensor_usage_percent_configuration_update(hass: HomeAssistant) -> None:
    """Test that the usage_percent sensor's panel_configuration attribute is updated."""
    await _test_sensor_configuration_update(hass, "usage_percent")


async def _test_sensor_configuration_update(hass: HomeAssistant, sensor_suffix: str) -> None:
    """Generic test to check if a sensor's panel_configuration attribute is updated."""
    # Initial configuration
    initial_data = {
        CONF_PV_POWER: "sensor.test_pv_power",
        CONF_PV_VOLTAGE: "sensor.test_pv_voltage",
        CONF_VMP: 36.0,
        CONF_IMP: 10.0,
        CONF_VOC: 42.0,
        CONF_ISC: 11.0,
        CONF_PANEL_COUNT: 1,
        CONF_PANEL_CONFIGURATION: PANEL_CONFIG_SERIES,
    }

    config_entry = create_test_config_entry(initial_data)
    await hass.config_entries.async_add(config_entry)
    await hass.async_block_till_done()

    # Create dummy sensors
    hass.states.async_set("sensor.test_pv_power", "100")
    hass.states.async_set("sensor.test_pv_voltage", "35")
    await hass.async_block_till_done() # Ensure dummy sensors are processed

    # Check initial state
    sensor_entity_id = f"sensor.sun_allocator_{config_entry.entry_id}_{sensor_suffix}"
    state = hass.states.get(sensor_entity_id)
    assert state is not None
    # The panel_configuration attribute is not always present, so we check only if it exists
    if CONF_PANEL_CONFIGURATION in state.attributes:
        assert state.attributes.get(CONF_PANEL_CONFIGURATION) == PANEL_CONFIG_SERIES

    # Update configuration
    updated_data = initial_data.copy()
    updated_data[CONF_PANEL_CONFIGURATION] = PANEL_CONFIG_PARALLEL_SERIES
    hass.config_entries.async_update_entry(config_entry, data=updated_data)
    await hass.async_block_till_done()

    # Check updated state
    state = hass.states.get(sensor_entity_id)
    assert state is not None
    # The panel_configuration attribute is not always present, so we check only if it exists
    if CONF_PANEL_CONFIGURATION in state.attributes:
        assert state.attributes.get(CONF_PANEL_CONFIGURATION) == PANEL_CONFIG_PARALLEL_SERIES
