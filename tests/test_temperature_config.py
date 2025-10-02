"""Tests for temperature config."""
import pytest
from unittest.mock import MagicMock, patch

from custom_components.sun_allocator.config.temperature_config import TemperatureConfigMixin
from custom_components.sun_allocator.const import (
    CONF_TEMPERATURE_SENSOR,
    CONF_TEMP_COEFFICIENT_VOC,
    CONF_TEMP_COEFFICIENT_PMAX,
    CONF_TEMPERATURE_COMPENSATION_ENABLED,
    NONE_OPTION,
)


class TestConfig(TemperatureConfigMixin):
    """Test implementation of TemperatureConfigMixin."""
    
    _solar_config = {}
    
    async def _save_and_return(self):
        """Implement required abstract method."""
        return {"type": "test_result"}


@pytest.fixture
def temp_config():
    """Create a temperature config fixture for tests."""
    return TestConfig()


def test_temperature_sensor_and_compensation_settings(temp_config):
    """Test the relationship between temperature sensor and compensation settings."""
    # Case 1: Just a valid temperature sensor without compensation setting
    input_data = {CONF_TEMPERATURE_SENSOR: "sensor.temperature"}
    result = temp_config._process_temperature_config_input(dict(input_data))
    assert result.get(CONF_TEMPERATURE_SENSOR) == "sensor.temperature", \
        "Valid temperature sensor should be preserved when no compensation setting is provided"
    
    # Case 2: Compensation explicitly enabled with valid sensor
    input_data = {
        CONF_TEMPERATURE_COMPENSATION_ENABLED: True,
        CONF_TEMPERATURE_SENSOR: "sensor.temperature"
    }
    result = temp_config._process_temperature_config_input(dict(input_data))
    assert result.get(CONF_TEMPERATURE_SENSOR) == "sensor.temperature", \
        "Valid temperature sensor should be preserved when compensation is enabled"
    assert result.get(CONF_TEMPERATURE_COMPENSATION_ENABLED) is True, \
        "Temperature compensation enabled flag should be preserved"
    
    # Case 3: Compensation explicitly disabled with valid sensor
    input_data = {
        CONF_TEMPERATURE_COMPENSATION_ENABLED: False,
        CONF_TEMPERATURE_SENSOR: "sensor.temperature"
    }
    result = temp_config._process_temperature_config_input(dict(input_data))
    assert result.get(CONF_TEMPERATURE_SENSOR) is None, \
        "Temperature sensor should be cleared when compensation is disabled"
    assert result.get(CONF_TEMPERATURE_COMPENSATION_ENABLED) is False, \
        "Temperature compensation disabled flag should be preserved"
    
    # Case 4: None sensor with compensation enabled
    input_data = {
        CONF_TEMPERATURE_COMPENSATION_ENABLED: True,
        CONF_TEMPERATURE_SENSOR: NONE_OPTION
    }
    result = temp_config._process_temperature_config_input(dict(input_data))
    assert result.get(CONF_TEMPERATURE_SENSOR) is None, \
        "None option for temperature sensor should be converted to None"
    assert result.get(CONF_TEMPERATURE_COMPENSATION_ENABLED) is True, \
        "Temperature compensation enabled flag should be preserved"


@pytest.mark.parametrize(
    "user_input,expected_result",
    [
        # Test case 1: None option should be converted to None
        (
            {CONF_TEMPERATURE_SENSOR: NONE_OPTION},
            {CONF_TEMPERATURE_SENSOR: None},
        ),
        # Test case 2: Empty string should be converted to None
        (
            {CONF_TEMPERATURE_SENSOR: ""},
            {CONF_TEMPERATURE_SENSOR: None},
        ),
        # Test case 3: Valid sensor entity should be preserved
        (
            {CONF_TEMPERATURE_SENSOR: "sensor.temperature"},
            {CONF_TEMPERATURE_SENSOR: "sensor.temperature"},
        ),
        # Test case 4: Temperature compensation disabled should clear sensor
        (
            {
                CONF_TEMPERATURE_COMPENSATION_ENABLED: False,
                CONF_TEMPERATURE_SENSOR: "sensor.temperature",
            },
            {
                CONF_TEMPERATURE_COMPENSATION_ENABLED: False,
                CONF_TEMPERATURE_SENSOR: None,
            },
        ),
        # Test case 5: Temperature compensation enabled should preserve sensor
        (
            {
                CONF_TEMPERATURE_COMPENSATION_ENABLED: True,
                CONF_TEMPERATURE_SENSOR: "sensor.temperature",
            },
            {
                CONF_TEMPERATURE_COMPENSATION_ENABLED: True,
                CONF_TEMPERATURE_SENSOR: "sensor.temperature",
            },
        ),
    ],
)
def test_process_temperature_config_input(temp_config, user_input, expected_result):
    """Test that temperature config input is properly processed."""
    # Create a deep copy of the input to avoid modifying the original test data
    input_copy = dict(user_input)
    
    result = temp_config._process_temperature_config_input(input_copy)
    
    # Check that the result matches the expected output
    for key, value in expected_result.items():
        assert result.get(key) == value, f"Failed on key {key}: expected {value}, got {result.get(key)}"


def test_validate_temperature_config_valid(temp_config):
    """Test validation with valid temperature configuration."""
    user_input = {
        CONF_TEMPERATURE_COMPENSATION_ENABLED: True,
        CONF_TEMPERATURE_SENSOR: "sensor.temperature",
        CONF_TEMP_COEFFICIENT_VOC: -0.3,
        CONF_TEMP_COEFFICIENT_PMAX: -0.4,
    }
    
    errors = temp_config._validate_temperature_config(user_input)
    assert not errors, "Validation should pass with no errors"


def test_validate_temperature_config_missing_sensor(temp_config):
    """Test validation when temperature compensation is enabled but sensor is missing."""
    user_input = {
        CONF_TEMPERATURE_COMPENSATION_ENABLED: True,
        CONF_TEMPERATURE_SENSOR: None,
        CONF_TEMP_COEFFICIENT_VOC: -0.3,
        CONF_TEMP_COEFFICIENT_PMAX: -0.4,
    }
    
    errors = temp_config._validate_temperature_config(user_input)
    assert CONF_TEMPERATURE_SENSOR in errors, "Should have error for missing temperature sensor"


def test_validate_temperature_config_invalid_coefficients(temp_config):
    """Test validation with invalid temperature coefficients."""
    user_input = {
        CONF_TEMPERATURE_COMPENSATION_ENABLED: True,
        CONF_TEMPERATURE_SENSOR: "sensor.temperature",
        CONF_TEMP_COEFFICIENT_VOC: -1.5,  # Out of range (-1.0 to 0)
        CONF_TEMP_COEFFICIENT_PMAX: 0.5,  # Out of range (-1.0 to 0)
    }
    
    errors = temp_config._validate_temperature_config(user_input)
    assert CONF_TEMP_COEFFICIENT_VOC in errors, "Should have error for invalid VOC coefficient"
    assert CONF_TEMP_COEFFICIENT_PMAX in errors, "Should have error for invalid PMAX coefficient"


@patch("homeassistant.core.HomeAssistant")
def test_get_temperature_sensors(mock_hass, temp_config):
    """Test getting temperature sensors from Home Assistant."""
    # Mock Home Assistant states
    mock_state1 = MagicMock()
    mock_state1.entity_id = "sensor.temperature"
    mock_state1.attributes = {"unit_of_measurement": "°C"}
    
    mock_state2 = MagicMock()
    mock_state2.entity_id = "sensor.humidity"
    mock_state2.attributes = {"unit_of_measurement": "%"}
    
    mock_state3 = MagicMock()
    mock_state3.entity_id = "sensor.room_temp"
    mock_state3.attributes = {"unit_of_measurement": "°C"}
    
    mock_hass.states.async_all.return_value = [mock_state1, mock_state2, mock_state3]
    
    sensors = temp_config._get_temperature_sensors(mock_hass)
    
    # We should have 2 temperature sensors and the None option
    assert len(sensors) == 3, "Should have 3 options (2 temperature sensors and None option)"
    
    # Check that the None option is using NONE_OPTION constant
    none_options = [s for s in sensors if s["value"] == NONE_OPTION]
    assert len(none_options) == 1, "Should have exactly one None option"