"""Tests for the Sun Allocator excess power sensor calculation."""

import pytest
from unittest.mock import patch

from homeassistant.core import HomeAssistant

from custom_components.sun_allocator.const import (
    CONF_PV_POWER,
    CONF_CONSUMPTION,
    CONF_RESERVE_BATTERY_POWER,
    CONF_INVERTER_SELF_CONSUMPTION,
    KEY_ENERGY_HARVESTING_POSSIBLE,
    KEY_MIN_SYSTEM_VOLTAGE,
    KEY_LIGHT_FACTOR,
    KEY_RELATIVE_VOLTAGE,
    KEY_VOC_RATIO,
    KEY_CALCULATION_REASON,
    KEY_PMAX,
)
from custom_components.sun_allocator.sensor.sensors.excess import (
    SunAllocatorExcessSensor,
)


@pytest.fixture
def mock_config():
    """Fixture for mock config data."""
    return {
        CONF_PV_POWER: "sensor.pv_power",
        # Basic config for MPPT mode
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


# A complete mock for the debug_info dictionary
complete_mock_debug_info = {
    KEY_PMAX: 3000.0,
    KEY_ENERGY_HARVESTING_POSSIBLE: True,
    KEY_MIN_SYSTEM_VOLTAGE: 100.0,
    KEY_LIGHT_FACTOR: 1.0,
    KEY_RELATIVE_VOLTAGE: 1.1,
    KEY_VOC_RATIO: 1.1,
    KEY_CALCULATION_REASON: "Test",
}

# --- PARALLEL MODE TESTS (with consumption sensor) ---


@pytest.mark.asyncio
async def test_parallel_budget_mode(hass: HomeAssistant, mock_config):
    """Test parallel 'Budget' mode (reserve > 0)."""
    config = {
        **mock_config,
        CONF_CONSUMPTION: "sensor.consumption_power",
        CONF_RESERVE_BATTERY_POWER: 500,
    }
    hass.states.async_set("sensor.pv_power", "3000")
    hass.states.async_set("sensor.consumption_power", "200")
    hass.states.async_set("sensor.battery_power", "100")  # Charging
    hass.states.async_set("sensor.pv_voltage", "40")
    sensor = SunAllocatorExcessSensor(hass, config, "test_entry", 1)
    # Excess = 3000 (PV) - 200 (Consumption) - 500 (Reserve) = 2300
    assert sensor.native_value == 2300


@pytest.mark.asyncio
async def test_parallel_priority_mode(hass: HomeAssistant, mock_config):
    """Test parallel 'Priority' mode (reserve = 0)."""
    config = {
        **mock_config,
        CONF_CONSUMPTION: "sensor.consumption_power",
        CONF_RESERVE_BATTERY_POWER: 0,
    }
    hass.states.async_set("sensor.pv_power", "3000")
    hass.states.async_set("sensor.consumption_power", "200")
    hass.states.async_set("sensor.battery_power", "400")  # Charging
    hass.states.async_set("sensor.pv_voltage", "40")
    sensor = SunAllocatorExcessSensor(hass, config, "test_entry", 1)
    # Excess = 3000 (PV) - 200 (Consumption) - 400 (Battery Charge) = 2400
    assert sensor.native_value == 2400


@pytest.mark.asyncio
async def test_parallel_mode_with_self_consumption(hass: HomeAssistant, mock_config):
    """Test that inverter self-consumption is subtracted in parallel mode."""
    config = {
        **mock_config,
        CONF_CONSUMPTION: "sensor.consumption_power",
        CONF_RESERVE_BATTERY_POWER: 0,
        CONF_INVERTER_SELF_CONSUMPTION: 150,
    }
    hass.states.async_set("sensor.pv_power", "3000")
    hass.states.async_set("sensor.consumption_power", "200")
    hass.states.async_set("sensor.battery_power", "400")  # Charging
    hass.states.async_set("sensor.pv_voltage", "40")
    sensor = SunAllocatorExcessSensor(hass, config, "test_entry", 1)
    # Excess = 3000 (PV) - 200 (Consumption) - 400 (Battery) - 150 (Self-Consumption) = 2250
    assert sensor.native_value == 2250


# --- MPPT MODE TESTS (without consumption sensor) ---


@pytest.mark.asyncio
async def test_mppt_budget_mode(hass: HomeAssistant, mock_config):
    """Test MPPT 'Budget' mode (reserve > 0)."""
    config = {**mock_config, CONF_RESERVE_BATTERY_POWER: 100}
    hass.states.async_set("sensor.pv_power", "2500")
    hass.states.async_set("sensor.battery_power", "500")  # Charging
    hass.states.async_set("sensor.pv_voltage", "40")
    sensor = SunAllocatorExcessSensor(hass, config, "test_entry", 1)

    with patch(
        "custom_components.sun_allocator.sensor.sensors.excess.calculate_current_max_power",
        return_value=(3000.0, complete_mock_debug_info),
    ):
        # Untapped = 3000 - 2500 = 500
        # From Battery = 500 - 100 = 400
        # Total = 900
        assert sensor.native_value == 900


@pytest.mark.asyncio
async def test_mppt_priority_mode(hass: HomeAssistant, mock_config):
    """Test MPPT 'Priority' mode (reserve = 0)."""
    config = {**mock_config, CONF_RESERVE_BATTERY_POWER: 0}
    hass.states.async_set("sensor.pv_power", "2500")
    hass.states.async_set("sensor.battery_power", "500")  # Charging
    hass.states.async_set("sensor.pv_voltage", "40")
    sensor = SunAllocatorExcessSensor(hass, config, "test_entry", 1)

    with patch(
        "custom_components.sun_allocator.sensor.sensors.excess.calculate_current_max_power",
        return_value=(3000.0, complete_mock_debug_info),
    ):
        # Untapped = 3000 - 2500 = 500
        # From Battery = 0 (because reserve is 0)
        # Total = 500
        assert sensor.native_value == 500


@pytest.mark.asyncio
async def test_mppt_mode_with_self_consumption(hass: HomeAssistant, mock_config):
    """Test that inverter self-consumption is subtracted in MPPT mode."""
    config = {**mock_config, CONF_RESERVE_BATTERY_POWER: 0, CONF_INVERTER_SELF_CONSUMPTION: 50}
    hass.states.async_set("sensor.pv_power", "2500")
    hass.states.async_set("sensor.battery_power", "500")  # Charging
    hass.states.async_set("sensor.pv_voltage", "40")
    sensor = SunAllocatorExcessSensor(hass, config, "test_entry", 1)

    with patch(
        "custom_components.sun_allocator.sensor.sensors.excess.calculate_current_max_power",
        return_value=(3000.0, complete_mock_debug_info),
    ):
        # Untapped = 3000 - 2500 = 500
        # Total = 500 - 50 (Self-Consumption) = 450
        assert sensor.native_value == 450


@pytest.mark.asyncio
async def test_mppt_mode_is_called_correctly(hass: HomeAssistant, mock_config):
    """Test MPPT calculation function is called correctly when no consumption sensor is configured."""
    config = {**mock_config, CONF_RESERVE_BATTERY_POWER: 200}
    hass.states.async_set("sensor.pv_power", "2000")
    hass.states.async_set("sensor.battery_power", "500")
    hass.states.async_set("sensor.pv_voltage", "40")
    sensor = SunAllocatorExcessSensor(hass, config, "test_entry", 1)

    with (
        patch(
            "custom_components.sun_allocator.sensor.sensors.excess.calculate_current_max_power",
            return_value=(3000.0, complete_mock_debug_info),
        ),
        patch(
            "custom_components.sun_allocator.sensor.sensors.excess.calculate_excess_power_mppt",
            return_value=1234.5,
        ) as mock_mppt_calc,
    ):
        result = sensor.native_value
        mock_mppt_calc.assert_called_once()
        assert mock_mppt_calc.call_args.kwargs["consumption"] is None
        assert mock_mppt_calc.call_args.kwargs["configured_reserve"] == 200
        assert result == 1234.5
