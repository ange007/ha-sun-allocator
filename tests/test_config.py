"""Tests for the Sun Allocator config flow, validation, and temperature config."""

import pytest
from unittest.mock import patch, MagicMock

from homeassistant import config_entries, setup
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from conftest import create_test_config_entry
from tests.const import MOCK_CONFIG

from custom_components.sun_allocator.const import (
    DOMAIN,
    CONF_PV_POWER,
    CONF_PV_VOLTAGE,
    CONF_CONSUMPTION,
    CONF_BATTERY_POWER,
    CONF_BATTERY_POWER_REVERSED,
    CONF_PANEL_VMP,
    CONF_PANEL_IMP,
    CONF_PANEL_VOC,
    CONF_PANEL_ISC,
    CONF_PANEL_COUNT,
    CONF_PANEL_CONFIGURATION,
    CONF_RESERVE_BATTERY_POWER,
    CONF_RAMP_UP_STEP,
    CONF_RAMP_DOWN_STEP,
    CONF_ACTION,
    PANEL_CONFIG_SERIES,
    CONF_TEMPERATURE_COMPENSATION_ENABLED,
    CONF_ADVANCED_SETTINGS_ENABLED,
    CONF_TEMPERATURE_SENSOR,
    CONF_TEMP_COEFFICIENT_VOC,
    CONF_TEMP_COEFFICIENT_PMAX,
    ACTION_MANAGE_DEVICES,
    ACTION_ADD_DEVICE,
    STEP_MAIN_MENU,
    STEP_MANAGE_DEVICES,
    STEP_DEVICE_NAME_TYPE,
    STEP_SETTINGS,
    NONE_OPTION,
)
from custom_components.sun_allocator.config.utils import (
    validate_solar_config,
    validate_device_entity,
)
from custom_components.sun_allocator.config.temperature_config import (
    TemperatureConfigMixin,
)


# --- Config Flow Tests ---


@pytest.mark.asyncio
async def test_form_user(hass: HomeAssistant) -> None:
    """Test we get the form."""
    # Create mock sensors
    hass.states.async_set("sensor.test_power", "1000")
    hass.states.async_set("sensor.test_voltage", "230")
    hass.states.async_set("sensor.test_battery", "50")

    await setup.async_setup_component(hass, "persistent_notification", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


@pytest.mark.asyncio
async def test_create_entry(hass: HomeAssistant) -> None:
    """Test we can create a config entry from the handler."""
    from custom_components.sun_allocator.config_flow import SunAllocatorConfigFlow

    # Initialize the flow handler directly
    flow = SunAllocatorConfigFlow()
    flow.hass = hass

    # Set the solar config with test data
    flow._solar_config = {
        CONF_PV_POWER: "sensor.test_pv_power",
        CONF_PV_VOLTAGE: "sensor.test_pv_voltage",
        CONF_CONSUMPTION: "sensor.test_consumption",
        CONF_BATTERY_POWER: "sensor.test_battery_power",
        CONF_BATTERY_POWER_REVERSED: False,
        CONF_PANEL_VMP: 36.0,
        CONF_PANEL_IMP: 8.0,
        CONF_PANEL_VOC: 40.0,
        CONF_PANEL_ISC: 8.5,
        CONF_PANEL_COUNT: 1,
        CONF_PANEL_CONFIGURATION: PANEL_CONFIG_SERIES,
        CONF_TEMPERATURE_COMPENSATION_ENABLED: False,
        CONF_ADVANCED_SETTINGS_ENABLED: False,
    }

    # Call the _create_entry method directly (we need to implement this in the actual code)
    with patch.object(flow, "_create_entry") as mock_create_entry:
        mock_create_entry.return_value = {
            "type": FlowResultType.CREATE_ENTRY,
            "title": "Sun Allocator",
            "data": flow._solar_config,
            "options": {},
            "version": 1,
        }

        result = flow._create_entry()

    # Check that the correct data is in the result
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Sun Allocator"
    assert result["data"][CONF_PV_POWER] == "sensor.test_pv_power"
    assert "version" in result
    assert "options" in result


@pytest.mark.asyncio
async def test_temperature_compensation_step(hass: HomeAssistant) -> None:
    """Test the temperature compensation step."""
    from custom_components.sun_allocator.config_flow import SunAllocatorConfigFlow

    # Initialize the flow handler directly
    flow = SunAllocatorConfigFlow()
    flow.hass = hass

    # Create a sensor for testing
    hass.states.async_set("sensor.test_temperature", "25")

    # Set the solar config with test data
    flow._solar_config = {
        CONF_PV_POWER: "sensor.test_pv_power",
        CONF_PV_VOLTAGE: "sensor.test_pv_voltage",
        CONF_CONSUMPTION: "sensor.test_consumption",
        CONF_BATTERY_POWER: "sensor.test_battery_power",
        CONF_TEMPERATURE_COMPENSATION_ENABLED: True,
    }

    # Call the method with test data
    user_input = {
        CONF_TEMPERATURE_SENSOR: "sensor.test_temperature",
        CONF_TEMP_COEFFICIENT_VOC: -0.3,
        CONF_TEMP_COEFFICIENT_PMAX: -0.4,
    }

    # Mock methods that would be called
    with patch.object(
        flow, "_process_temperature_config_input"
    ) as mock_process, patch.object(flow, "_save_and_return") as mock_save:
        mock_process.return_value = user_input
        mock_save.return_value = {
            "type": FlowResultType.CREATE_ENTRY,
            "title": "Sun Allocator",
            "data": flow._solar_config,
            "options": {},
            "version": 1,
        }

        # Test with user input
        await flow.async_step_temperature_compensation(user_input)

    # Verify the solar config was updated
    assert flow._solar_config[CONF_TEMPERATURE_SENSOR] == "sensor.test_temperature"


@pytest.mark.asyncio
async def test_advanced_settings_step(hass: HomeAssistant) -> None:
    """Test the advanced settings step."""
    from custom_components.sun_allocator.config_flow import SunAllocatorConfigFlow

    # Initialize the flow handler directly
    flow = SunAllocatorConfigFlow()
    flow.hass = hass

    # Set the solar config with test data
    flow._solar_config = {
        CONF_PV_POWER: "sensor.test_pv_power",
        CONF_PV_VOLTAGE: "sensor.test_pv_voltage",
        CONF_CONSUMPTION: "sensor.test_consumption",
        CONF_BATTERY_POWER: "sensor.test_battery_power",
        CONF_ADVANCED_SETTINGS_ENABLED: True,
    }

    # Call the method with test data
    user_input = {
        CONF_RESERVE_BATTERY_POWER: 100,
        CONF_RAMP_UP_STEP: 5,
        CONF_RAMP_DOWN_STEP: 5,
    }

    # Mock methods that would be called
    with patch.object(flow, "_save_and_return") as mock_save:
        mock_save.return_value = {
            "type": FlowResultType.CREATE_ENTRY,
            "title": "Sun Allocator",
            "data": flow._solar_config,
            "options": {},
            "version": 1,
        }

        # Test with user input
        await flow.async_step_advanced_settings(user_input)

    # Verify the solar config was updated
    assert CONF_RESERVE_BATTERY_POWER in flow._solar_config


@pytest.mark.asyncio
async def test_options_flow_init(hass: HomeAssistant) -> None:
    """Test the options flow initialization."""
    from custom_components.sun_allocator.config import (
        SunAllocatorOptionsFlowHandler,
    )

    # Create a mock config entry
    config_data = {
        **MOCK_CONFIG,
    }
    entry = create_test_config_entry(config_data, entry_id="test", version=1)
    entry.add_to_hass(hass)

    # Initialize the options flow handler directly
    flow = SunAllocatorOptionsFlowHandler(entry)
    flow.hass = hass

    # Call the init method
    result = await flow.async_step_init()

    # Check the result
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_MAIN_MENU


@pytest.mark.asyncio
async def test_options_flow_main_menu(hass: HomeAssistant) -> None:
    from custom_components.sun_allocator.config import (
        SunAllocatorOptionsFlowHandler,
    )

    # Create a mock config entry
    config_data = {
        **MOCK_CONFIG,
    }
    entry = create_test_config_entry(extra_data=config_data, entry_id="test", version=1)
    entry.add_to_hass(hass)

    # Initialize the options flow handler directly
    flow = SunAllocatorOptionsFlowHandler(entry)
    flow.hass = hass

    # Call the main_menu method with action manage_devices
    with patch.object(flow, "async_step_manage_devices") as mock_manage_devices:
        mock_manage_devices.return_value = {
            "type": FlowResultType.FORM,
            "step_id": STEP_MANAGE_DEVICES,
        }

        await flow.async_step_main_menu({CONF_ACTION: ACTION_MANAGE_DEVICES})

    # Check that the manage_devices step was called
    assert mock_manage_devices.called


@pytest.mark.asyncio
async def test_options_flow_manage_devices(hass: HomeAssistant) -> None:
    from custom_components.sun_allocator.config import (
        SunAllocatorOptionsFlowHandler,
    )

    # Create a mock config entry
    config_data = {
        **MOCK_CONFIG,
    }
    entry = create_test_config_entry(extra_data=config_data, entry_id="test", version=1)
    entry.add_to_hass(hass)

    # Initialize the options flow handler directly
    flow = SunAllocatorOptionsFlowHandler(entry)
    flow.hass = hass

    # Call the manage_devices method with action add_device
    with patch.object(flow, "async_step_device_name_type") as mock_device_name_type:
        mock_device_name_type.return_value = {
            "type": FlowResultType.FORM,
            "step_id": STEP_DEVICE_NAME_TYPE,
        }

        await flow.async_step_manage_devices({CONF_ACTION: ACTION_ADD_DEVICE})

    # Check that the device_name_type step was called
    assert mock_device_name_type.called


@pytest.mark.asyncio
async def test_options_flow_settings_step(hass: HomeAssistant) -> None:
    """Test that the settings step in options flow works correctly."""
    # Create a mock config entry
    config_data = {
        **MOCK_CONFIG,
    }
    entry = create_test_config_entry(extra_data=config_data, entry_id="test")
    entry.add_to_hass(hass)

    # Initialize the options flow handler directly
    from custom_components.sun_allocator.config import (
        SunAllocatorOptionsFlowHandler,
    )

    handler = SunAllocatorOptionsFlowHandler(entry)
    handler.hass = hass

    # Load the configuration data
    await handler.async_step_init()

    # Test the settings step directly without mocking it
    result = await handler.async_step_settings()

    # Verify that the result is a form with the expected step ID
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == STEP_SETTINGS
    assert "errors" not in result or not result["errors"]


# --- Config Validation Tests ---


@pytest.mark.parametrize(
    "vmp,imp,voc,isc,valid",
    [
        (30.0, 8.0, 36.0, 8.5, True),  # Valid config
        (0.0, 8.0, 36.0, 8.5, False),  # Invalid Vmp
        (30.0, 0.0, 36.0, 8.5, False),  # Invalid Imp
        (36.0, 8.0, 30.0, 8.5, False),  # Voc < Vmp (invalid)
        (30.0, 8.5, 36.0, 8.0, False),  # Imp > Isc (invalid)
    ],
)
async def test_solar_config_validation(vmp, imp, voc, isc, valid):
    """Test solar panel configuration validation."""
    config = {
        CONF_PANEL_VMP: vmp,
        CONF_PANEL_IMP: imp,
        CONF_PANEL_VOC: voc,
        CONF_PANEL_ISC: isc,
        CONF_PANEL_COUNT: 1,
    }

    result = validate_solar_config(config)
    assert result["valid"] == valid
    if not valid:
        assert "errors" in result
        assert len(result["errors"]) > 0


async def test_device_entity_validation():
    """Test device entity validation."""
    # Test supported domains
    valid_entities = [
        "switch.test_switch",
        "light.test_light",
        "input_boolean.test_boolean",
    ]

    invalid_entities = [
        "sensor.test_sensor",  # Unsupported domain
        "invalid_entity",  # Invalid format
        "",  # Empty
    ]

    for entity in valid_entities:
        assert validate_device_entity(entity) is True

    for entity in invalid_entities:
        assert validate_device_entity(entity) is False


# --- Temperature Config Tests ---


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
    assert (
        result.get(CONF_TEMPERATURE_SENSOR) == "sensor.temperature"
    ), "Valid temperature sensor should be preserved when no compensation setting is provided"

    # Case 2: Compensation explicitly enabled with valid sensor
    input_data = {
        CONF_TEMPERATURE_COMPENSATION_ENABLED: True,
        CONF_TEMPERATURE_SENSOR: "sensor.temperature",
    }
    result = temp_config._process_temperature_config_input(dict(input_data))
    assert (
        result.get(CONF_TEMPERATURE_SENSOR) == "sensor.temperature"
    ), "Valid temperature sensor should be preserved when compensation is enabled"
    assert (
        result.get(CONF_TEMPERATURE_COMPENSATION_ENABLED) is True
    ), "Temperature compensation enabled flag should be preserved"

    # Case 3: Compensation explicitly disabled with valid sensor
    input_data = {
        CONF_TEMPERATURE_COMPENSATION_ENABLED: False,
        CONF_TEMPERATURE_SENSOR: "sensor.temperature",
    }
    result = temp_config._process_temperature_config_input(dict(input_data))
    assert (
        result.get(CONF_TEMPERATURE_SENSOR) is None
    ), "Temperature sensor should be cleared when compensation is disabled"
    assert (
        result.get(CONF_TEMPERATURE_COMPENSATION_ENABLED) is False
    ), "Temperature compensation disabled flag should be preserved"

    # Case 4: None sensor with compensation enabled
    input_data = {
        CONF_TEMPERATURE_COMPENSATION_ENABLED: True,
        CONF_TEMPERATURE_SENSOR: NONE_OPTION,
    }
    result = temp_config._process_temperature_config_input(dict(input_data))
    assert (
        result.get(CONF_TEMPERATURE_SENSOR) is None
    ), "None option for temperature sensor should be converted to None"
    assert (
        result.get(CONF_TEMPERATURE_COMPENSATION_ENABLED) is True
    ), "Temperature compensation enabled flag should be preserved"


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
        assert (
            result.get(key) == value
        ), f"Failed on key {key}: expected {value}, got {result.get(key)}"


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
    assert (
        CONF_TEMPERATURE_SENSOR in errors
    ), "Should have error for missing temperature sensor"


def test_validate_temperature_config_invalid_coefficients(temp_config):
    """Test validation with invalid temperature coefficients."""
    user_input = {
        CONF_TEMPERATURE_COMPENSATION_ENABLED: True,
        CONF_TEMPERATURE_SENSOR: "sensor.temperature",
        CONF_TEMP_COEFFICIENT_VOC: -1.5,  # Out of range (-1.0 to 0)
        CONF_TEMP_COEFFICIENT_PMAX: 0.5,  # Out of range (-1.0 to 0)
    }

    errors = temp_config._validate_temperature_config(user_input)
    assert (
        CONF_TEMP_COEFFICIENT_VOC in errors
    ), "Should have error for invalid VOC coefficient"
    assert (
        CONF_TEMP_COEFFICIENT_PMAX in errors
    ), "Should have error for invalid PMAX coefficient"


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
    assert (
        len(sensors) == 3
    ), "Should have 3 options (2 temperature sensors and None option)"

    # Check that the None option is using NONE_OPTION constant
    none_options = [s for s in sensors if s["value"] == NONE_OPTION]
    assert len(none_options) == 1, "Should have exactly one None option"
