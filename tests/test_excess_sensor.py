"""Tests for the Sun Allocator excess power sensor calculation."""
import pytest
from unittest.mock import patch

from homeassistant.core import HomeAssistant

from custom_components.sun_allocator.const import (
    CONF_PV_POWER,
    CONF_CONSUMPTION,
    CONF_PARALLEL_DISTRIBUTION_ENABLED,
    CONF_RESERVE_BATTERY_POWER,
)
from custom_components.sun_allocator.sensor.sensors.excess import SunAllocatorExcessSensor


@pytest.fixture
def mock_config():
    """Fixture for mock config data."""
    return {
        CONF_PV_POWER: "sensor.pv_power",
        CONF_CONSUMPTION: "sensor.consumption_power",
        # Add other necessary default config values
        "vmp": 36.0,
        "imp": 8.0,
        "voc": 44.0,
        "isc": 8.5,
        "panel_count": 1,
        "panel_configuration": "series",
        "curve_factor_k": 0.2,
        "efficiency_correction_factor": 1.05,
        "min_inverter_voltage": 100.0,
        "battery_power": "sensor.battery_power",
        "battery_power_reversed": False,
    }


@pytest.mark.asyncio
async def test_parallel_distribution_with_consumption(hass: HomeAssistant, mock_config):
    """Test parallel distribution mode with a consumption sensor."""
    # Arrange
    config = {
        **mock_config,
        CONF_PARALLEL_DISTRIBUTION_ENABLED: True,
        CONF_RESERVE_BATTERY_POWER: 500,
    }
    
    # Mock sensor states
    hass.states.async_set("sensor.pv_power", "3000")
    hass.states.async_set("sensor.consumption_power", "200")
    hass.states.async_set("sensor.battery_power", "0") # Not used in this mode, but required by sensor
    hass.states.async_set("sensor.pv_voltage", "40") # Not used in this mode, but required

    sensor = SunAllocatorExcessSensor(hass, config, "test_entry", 1)

    # Act & Assert
    assert sensor.native_value == 2300  # 3000 (PV) - 500 (Reserve) - 200 (Consumption)


@pytest.mark.asyncio
async def test_parallel_distribution_no_consumption(hass: HomeAssistant, mock_config):
    """Test parallel distribution mode without a consumption sensor."""
    # Arrange
    config = {
        **mock_config,
        CONF_CONSUMPTION: None, # Simulate no consumption sensor configured
        CONF_PARALLEL_DISTRIBUTION_ENABLED: True,
        CONF_RESERVE_BATTERY_POWER: 500,
    }
    
    hass.states.async_set("sensor.pv_power", "3000")
    hass.states.async_set("sensor.battery_power", "0")
    hass.states.async_set("sensor.pv_voltage", "40")

    sensor = SunAllocatorExcessSensor(hass, config, "test_entry", 1)

    # Act & Assert
    assert sensor.native_value == 2500  # 3000 (PV) - 500 (Reserve)


@pytest.mark.asyncio
async def test_parallel_distribution_negative_result(hass: HomeAssistant, mock_config):
    """Test parallel distribution mode resulting in a negative excess value."""
    # Arrange
    config = {
        **mock_config,
        CONF_PARALLEL_DISTRIBUTION_ENABLED: True,
        CONF_RESERVE_BATTERY_POWER: 500,
    }
    
    hass.states.async_set("sensor.pv_power", "1000")
    hass.states.async_set("sensor.consumption_power", "600")
    hass.states.async_set("sensor.battery_power", "0")
    hass.states.async_set("sensor.pv_voltage", "40")

    sensor = SunAllocatorExcessSensor(hass, config, "test_entry", 1)

    # Act & Assert
    assert sensor.native_value == -100  # 1000 - 500 - 600


@pytest.mark.asyncio
async def test_original_logic_regression(hass: HomeAssistant, mock_config):
    """Test that the original logic still works when parallel mode is disabled."""
    # Arrange
    config = {
        **mock_config,
        CONF_PARALLEL_DISTRIBUTION_ENABLED: False,
    }
    
    hass.states.async_set("sensor.pv_power", "2000")
    hass.states.async_set("sensor.consumption_power", "300")
    hass.states.async_set("sensor.battery_power", "500") # Charging
    hass.states.async_set("sensor.pv_voltage", "40")

    sensor = SunAllocatorExcessSensor(hass, config, "test_entry", 1)

    # Mock the complex calculation functions to isolate the sensor's logic flow
    mock_debug_info = {
        "pmax": 3000,
        "calculation_reason": "test",
        "energy_harvesting_possible": True,
        "min_system_voltage": 100.0,
        "light_factor": 0.8,
        "relative_voltage": 0.9,
        "voc_ratio": 1.2
    }

    with patch("custom_components.sun_allocator.sensor.sensors.excess.calculate_current_max_power", return_value=(3000.0, mock_debug_info)) as mock_max_power, \
         patch("custom_components.sun_allocator.sensor.sensors.excess.calculate_excess_power_mppt", return_value=1234.5) as mock_excess:
        
        # Act
        result = sensor.native_value

        # Assert
        # We assert that the original logic path was taken by checking that our mock was called.
        mock_excess.assert_called_once()
        # And the sensor's value is the one returned by the mocked function.
        assert result == 1234.5


@pytest.mark.asyncio
async def test_parallel_distribution_passive_charging(hass: HomeAssistant, mock_config):
    """Test parallel distribution mode when battery is in passive charging state."""
    # Arrange
    config = {
        **mock_config,
        CONF_PARALLEL_DISTRIBUTION_ENABLED: True,
        CONF_RESERVE_BATTERY_POWER: 500,  # High reserve
    }

    # Mock sensor states
    hass.states.async_set("sensor.pv_power", "3000")
    hass.states.async_set("sensor.consumption_power", "200")
    hass.states.async_set("sensor.battery_power", "40")  # Passive charging (less than 50W)
    hass.states.async_set("sensor.pv_voltage", "40")

    sensor = SunAllocatorExcessSensor(hass, config, "test_entry", 1)

    # Act & Assert
    # Effective reserve should be 40W (the actual charge rate), not 500W
    # Excess = 3000 (PV) - 40 (Effective Reserve) - 200 (Consumption) = 2760
    assert sensor.native_value == 2760
