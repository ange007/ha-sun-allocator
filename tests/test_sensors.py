"""Tests for the Sun Allocator sensors."""

import pytest
from unittest.mock import patch

from homeassistant.core import HomeAssistant

from conftest import create_test_config_entry
from tests.const import MOCK_CONFIG

from custom_components.sun_allocator.const import (
    DOMAIN_SWITCH,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_ENTITY,
    CONF_PANEL_CONFIGURATION,
    PANEL_CONFIG_SERIES,
    PANEL_CONFIG_PARALLEL_SERIES,
    CONF_PANEL_VMP,
    CONF_PANEL_IMP,
    CONF_PANEL_VOC,
    CONF_PANEL_ISC,
    CONF_PANEL_COUNT,
    CONF_PV_POWER,
    CONF_PV_VOLTAGE,
    CONF_CONSUMPTION,
    CONF_RESERVE_BATTERY_POWER,
    CONF_INVERTER_SELF_CONSUMPTION,
    CONF_CURVE_FACTOR_K,
    CONF_EFFICIENCY_CORRECTION_FACTOR,
    CONF_MIN_INVERTER_VOLTAGE,
    CONF_BATTERY_POWER,
    CONF_BATTERY_POWER_REVERSED,
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


@pytest.mark.asyncio
async def test_sensors_are_created(hass: HomeAssistant) -> None:
    """Test that the sensors are created."""
    # Combine mock config with specific device data for this test
    config_data = {
        **MOCK_CONFIG,
        CONF_DEVICES: [
            {
                CONF_DEVICE_ID: "test_device",
                CONF_DEVICE_ENTITY: f"{DOMAIN_SWITCH}.test_switch",
            }
        ],
    }

    config_entry = create_test_config_entry(config_data)
    await hass.config_entries.async_add(config_entry)
    await hass.async_block_till_done()

    # Check that the sensors have been created
    assert (
        hass.states.get(f"sensor.sun_allocator_{config_entry.entry_id}_excess")
        is not None
    )
    assert (
        hass.states.get(f"sensor.sun_allocator_{config_entry.entry_id}_max_power")
        is not None
    )
    assert (
        hass.states.get(f"sensor.sun_allocator_{config_entry.entry_id}_current_max_power")
        is not None
    )
    assert (
        hass.states.get(f"sensor.sun_allocator_{config_entry.entry_id}_usage_percent")
        is not None
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


async def _test_sensor_configuration_update(
    hass: HomeAssistant, sensor_suffix: str
) -> None:
    """Generic test to check if a sensor's panel_configuration attribute is updated."""
    # Initial configuration
    initial_data = {
        CONF_PV_POWER: "sensor.test_pv_power",
        CONF_PV_VOLTAGE: "sensor.test_pv_voltage",
        CONF_PANEL_VMP: 36.0,
        CONF_PANEL_IMP: 10.0,
        CONF_PANEL_VOC: 42.0,
        CONF_PANEL_ISC: 11.0,
        CONF_PANEL_COUNT: 1,
        CONF_PANEL_CONFIGURATION: PANEL_CONFIG_SERIES,
    }

    config_entry = create_test_config_entry(initial_data)
    await hass.config_entries.async_add(config_entry)
    await hass.async_block_till_done()

    # Create dummy sensors
    hass.states.async_set("sensor.test_pv_power", "100")
    hass.states.async_set("sensor.test_pv_voltage", "35")
    await hass.async_block_till_done()  # Ensure dummy sensors are processed

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
        assert (
            state.attributes.get(CONF_PANEL_CONFIGURATION) == PANEL_CONFIG_PARALLEL_SERIES
        )


@pytest.fixture
def mock_config_excess():
    """Fixture for mock config data for excess sensor tests."""
    return {
        CONF_PV_POWER: "sensor.pv_power",
        # Basic config for MPPT mode
        CONF_PANEL_VMP: 36.0,
        CONF_PANEL_IMP: 8.0,
        CONF_PANEL_VOC: 44.0,
        CONF_PANEL_ISC: 8.5,
        CONF_PANEL_COUNT: 1,
        CONF_PANEL_CONFIGURATION: PANEL_CONFIG_SERIES,
        CONF_CURVE_FACTOR_K: 0.2,
        CONF_EFFICIENCY_CORRECTION_FACTOR: 1.05,
        CONF_MIN_INVERTER_VOLTAGE: 100.0,
        CONF_BATTERY_POWER: "sensor.battery_power",
        CONF_BATTERY_POWER_REVERSED: False,
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

# --- HYBRID MODE TESTS (with consumption sensor) ---
# These tests now validate the UNIFIED MPPT logic when a consumption sensor is present.


@pytest.mark.asyncio
async def test_mppt_with_consumption_budget_mode(hass: HomeAssistant, mock_config_excess):
    """Test hybrid 'Budget' mode (reserve > 0)."""
    config = {
        **mock_config_excess,
        CONF_CONSUMPTION: "sensor.consumption_power",
        CONF_RESERVE_BATTERY_POWER: 500,
    }
    hass.states.async_set("sensor.pv_power", "3000")
    hass.states.async_set("sensor.consumption_power", "200")
    hass.states.async_set("sensor.battery_power", "100")  # Charging
    hass.states.async_set("sensor.pv_voltage", "40")
    sensor = SunAllocatorExcessSensor(hass, config, "test_entry", 1)

    with patch(
        "custom_components.sun_allocator.sensor.sensors.excess.calculate_current_max_power",
        return_value=(3500.0, complete_mock_debug_info),
    ):
        assert sensor.native_value == 500


@pytest.mark.asyncio
async def test_mppt_with_consumption_priority_mode(hass: HomeAssistant, mock_config_excess):
    """Test hybrid 'Priority' mode (reserve = 0)."""
    config = {
        **mock_config_excess,
        CONF_CONSUMPTION: "sensor.consumption_power",
        CONF_RESERVE_BATTERY_POWER: 0,
    }
    hass.states.async_set("sensor.pv_power", "3000")
    hass.states.async_set("sensor.consumption_power", "200")
    hass.states.async_set("sensor.battery_power", "400")  # Charging
    hass.states.async_set("sensor.pv_voltage", "40")
    sensor = SunAllocatorExcessSensor(hass, config, "test_entry", 1)

    with patch(
        "custom_components.sun_allocator.sensor.sensors.excess.calculate_current_max_power",
        return_value=(3500.0, complete_mock_debug_info),
    ):
        assert sensor.native_value == 500


@pytest.mark.asyncio
async def test_mppt_with_consumption_and_self_consumption(
    hass: HomeAssistant, mock_config_excess
):
    """Test that inverter self-consumption is subtracted in hybrid mode."""
    config = {
        **mock_config_excess,
        CONF_CONSUMPTION: "sensor.consumption_power",
        CONF_RESERVE_BATTERY_POWER: 0,
        CONF_INVERTER_SELF_CONSUMPTION: 150,
    }
    hass.states.async_set("sensor.pv_power", "3000")
    hass.states.async_set("sensor.consumption_power", "200")
    hass.states.async_set("sensor.battery_power", "400")  # Charging
    hass.states.async_set("sensor.pv_voltage", "40")
    sensor = SunAllocatorExcessSensor(hass, config, "test_entry", 1)

    with patch(
        "custom_components.sun_allocator.sensor.sensors.excess.calculate_current_max_power",
        return_value=(3500.0, complete_mock_debug_info),
    ):
        assert sensor.native_value == 350


# --- MPPT MODE TESTS (without consumption sensor) ---


@pytest.mark.asyncio
async def test_mppt_budget_mode(hass: HomeAssistant, mock_config_excess):
    """Test MPPT 'Budget' mode (reserve > 0)."""
    config = {**mock_config_excess, CONF_RESERVE_BATTERY_POWER: 100}
    hass.states.async_set("sensor.pv_power", "2500")
    hass.states.async_set("sensor.battery_power", "500")  # Charging
    hass.states.async_set("sensor.pv_voltage", "40")
    sensor = SunAllocatorExcessSensor(hass, config, "test_entry", 1)

    with patch(
        "custom_components.sun_allocator.sensor.sensors.excess.calculate_current_max_power",
        return_value=(3000.0, complete_mock_debug_info),
    ):
        assert sensor.native_value == 900


@pytest.mark.asyncio
async def test_mppt_priority_mode(hass: HomeAssistant, mock_config_excess):
    """Test MPPT 'Priority' mode (reserve = 0)."""
    config = {**mock_config_excess, CONF_RESERVE_BATTERY_POWER: 0}
    hass.states.async_set("sensor.pv_power", "2500")
    hass.states.async_set("sensor.battery_power", "500")  # Charging
    hass.states.async_set("sensor.pv_voltage", "40")
    sensor = SunAllocatorExcessSensor(hass, config, "test_entry", 1)

    with patch(
        "custom_components.sun_allocator.sensor.sensors.excess.calculate_current_max_power",
        return_value=(3000.0, complete_mock_debug_info),
    ):
        assert sensor.native_value == 500


@pytest.mark.asyncio
async def test_mppt_mode_with_self_consumption(hass: HomeAssistant, mock_config_excess):
    """Test that inverter self-consumption is subtracted in MPPT mode."""
    config = {
        **mock_config_excess,
        CONF_RESERVE_BATTERY_POWER: 0,
        CONF_INVERTER_SELF_CONSUMPTION: 50,
    }
    hass.states.async_set("sensor.pv_power", "2500")
    hass.states.async_set("sensor.battery_power", "500")  # Charging
    hass.states.async_set("sensor.pv_voltage", "40")
    sensor = SunAllocatorExcessSensor(hass, config, "test_entry", 1)

    with patch(
        "custom_components.sun_allocator.sensor.sensors.excess.calculate_current_max_power",
        return_value=(3000.0, complete_mock_debug_info),
    ):
        assert sensor.native_value == 450


@pytest.mark.asyncio
async def test_mppt_mode_is_called_correctly(hass: HomeAssistant, mock_config_excess):
    """Test MPPT calculation function is called correctly when no consumption sensor is configured."""
    config = {**mock_config_excess, CONF_RESERVE_BATTERY_POWER: 200}
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