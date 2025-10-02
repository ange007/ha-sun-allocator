"""Test translations."""
import json
from pathlib import Path

from custom_components.sun_allocator.const import (
    # Configuration steps
    STEP_USER,
    STEP_MAIN_MENU,
    STEP_SETTINGS,
    STEP_MANAGE_DEVICES,
    STEP_TEMPERATURE_COMPENSATION,
    STEP_ADVANCED_SETTINGS,
    STEP_DEVICE_NAME_TYPE,
    STEP_DEVICE_SELECTION,
    STEP_DEVICE_BASIC_SETTINGS,
    STEP_DEVICE_SCHEDULE,
    STEP_CONFIRM_REMOVE,
    
    # Configuration fields
    CONF_PV_POWER,
    CONF_PV_VOLTAGE,
    CONF_CONSUMPTION,
    CONF_BATTERY_POWER,
    CONF_BATTERY_POWER_REVERSED,
    CONF_VMP,
    CONF_IMP,
    CONF_VOC,
    CONF_ISC,
    CONF_PANEL_COUNT,
    CONF_PANEL_CONFIGURATION,
    CONF_TEMPERATURE_COMPENSATION_ENABLED,
    CONF_ADVANCED_SETTINGS_ENABLED,
    CONF_TEMPERATURE_SENSOR,
    CONF_TEMP_COEFFICIENT_VOC,
    CONF_TEMP_COEFFICIENT_PMAX,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_DEVICE_ENTITY,
    CONF_ESPHOME_MODE_SELECT_ENTITY,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_MIN_EXCESS_POWER,
    CONF_MIN_EXPECTED_W,
    CONF_MAX_EXPECTED_W,
    CONF_DEVICE_PRIORITY,
    CONF_DEBOUNCE_TIME,
    CONF_SCHEDULE_ENABLED,
    CONF_START_TIME,
    CONF_END_TIME,
    CONF_ACTION,
    CONF_DEVICE_ID,
    CONF_CONFIRM,
    
    # Advanced settings
    CONF_RESERVE_BATTERY_POWER,
    CONF_CURVE_FACTOR_K,
    CONF_EFFICIENCY_CORRECTION_FACTOR,
    CONF_MIN_INVERTER_VOLTAGE,
    CONF_RAMP_UP_STEP,
    CONF_RAMP_DOWN_STEP,
    CONF_RAMP_DEADBAND,
    CONF_DEFAULT_MIN_START_W,
    CONF_HYSTERESIS_W,
    
    # Days of week
    DAY_MONDAY,
    DAY_TUESDAY,
    DAY_WEDNESDAY,
    DAY_THURSDAY,
    DAY_FRIDAY,
    DAY_SATURDAY,
    DAY_SUNDAY,
    
    # Panel configuration
    PANEL_CONFIG_SERIES,
    PANEL_CONFIG_PARALLEL,
    PANEL_CONFIG_PARALLEL_SERIES,
    
    # Actions
    ACTION_ADD_DEVICE,
    ACTION_EDIT,
    ACTION_REMOVE,
    ACTION_SETTINGS,
    ACTION_MANAGE_DEVICES,
    ACTION_BACK,
    
    # Device types
    DEVICE_TYPE_STANDARD,
    DEVICE_TYPE_CUSTOM,
)


def test_translation_files_exist():
    """Test that translation files exist."""
    base_path = Path("custom_components/sun_allocator/translations")

    assert (base_path / "en.json").exists(), "English translation file missing"
    assert (base_path / "uk.json").exists(), "Ukrainian translation file missing"


def test_translation_files_valid_json():
    """Test that translation files are valid JSON."""
    base_path = Path("custom_components/sun_allocator/translations")

    for lang in ["en", "uk"]:
        file_path = base_path / f"{lang}.json"
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        assert isinstance(data, dict), f"{lang}.json is not a valid dictionary"
        assert "config" in data, f"{lang}.json missing 'config' section"


def test_required_step_translations():
    """Test that required steps have translations."""
    base_path = Path("custom_components/sun_allocator/translations")

    # Use constants from the code
    required_steps = [
        STEP_USER,
        STEP_MAIN_MENU,
        STEP_SETTINGS,
        STEP_MANAGE_DEVICES,
        STEP_TEMPERATURE_COMPENSATION,
        STEP_ADVANCED_SETTINGS,
        STEP_DEVICE_NAME_TYPE,
        STEP_DEVICE_SELECTION,
        STEP_DEVICE_BASIC_SETTINGS,
        STEP_DEVICE_SCHEDULE,
        STEP_CONFIRM_REMOVE,
    ]

    for lang in ["en", "uk"]:
        file_path = base_path / f"{lang}.json"
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        steps = data.get("config", {}).get("step", {})

        for step in required_steps:
            assert step in steps, f"{lang}.json missing step '{step}'"
            assert "title" in steps[step], f"{lang}.json step '{step}' missing title"


def test_step_field_translations():
    """Test that step fields have translations."""
    base_path = Path("custom_components/sun_allocator/translations")

    # Map steps to their required fields using constants
    step_fields = {
        STEP_USER: [
            CONF_PV_POWER,
            CONF_PV_VOLTAGE,
            CONF_CONSUMPTION,
            CONF_BATTERY_POWER,
            CONF_BATTERY_POWER_REVERSED,
            CONF_VMP,
            CONF_IMP,
            CONF_VOC,
            CONF_ISC,
            CONF_PANEL_COUNT,
            CONF_PANEL_CONFIGURATION,
            CONF_TEMPERATURE_COMPENSATION_ENABLED,
            CONF_ADVANCED_SETTINGS_ENABLED,
        ],
        STEP_SETTINGS: [
            CONF_PV_POWER,
            CONF_PV_VOLTAGE,
            CONF_CONSUMPTION,
            CONF_BATTERY_POWER,
            CONF_BATTERY_POWER_REVERSED,
            CONF_VMP,
            CONF_IMP,
            CONF_VOC,
            CONF_ISC,
            CONF_PANEL_COUNT,
            CONF_PANEL_CONFIGURATION,
            CONF_TEMPERATURE_COMPENSATION_ENABLED,
            CONF_ADVANCED_SETTINGS_ENABLED,
        ],
        STEP_MAIN_MENU: [
            CONF_ACTION,
        ],
        STEP_MANAGE_DEVICES: [
            CONF_ACTION,
            CONF_DEVICE_ID,
        ],
        STEP_TEMPERATURE_COMPENSATION: [
            CONF_TEMPERATURE_SENSOR,
            CONF_TEMP_COEFFICIENT_VOC,
            CONF_TEMP_COEFFICIENT_PMAX,
        ],
        STEP_ADVANCED_SETTINGS: [
            CONF_RESERVE_BATTERY_POWER,
            CONF_CURVE_FACTOR_K,
            CONF_EFFICIENCY_CORRECTION_FACTOR,
            CONF_MIN_INVERTER_VOLTAGE,
            CONF_RAMP_UP_STEP,
            CONF_RAMP_DOWN_STEP,
            CONF_RAMP_DEADBAND,
            CONF_DEFAULT_MIN_START_W,
            CONF_HYSTERESIS_W,
        ],
        STEP_DEVICE_NAME_TYPE: [
            CONF_DEVICE_NAME,
            CONF_DEVICE_TYPE,
        ],
        STEP_DEVICE_SELECTION: [
            CONF_DEVICE_ENTITY,
            CONF_ESPHOME_MODE_SELECT_ENTITY,
        ],
        STEP_DEVICE_BASIC_SETTINGS: [
            CONF_AUTO_CONTROL_ENABLED,
            CONF_MIN_EXCESS_POWER,
            CONF_MIN_EXPECTED_W,
            CONF_MAX_EXPECTED_W,
            CONF_DEVICE_PRIORITY,
            CONF_DEBOUNCE_TIME,
            CONF_SCHEDULE_ENABLED,
        ],
        STEP_DEVICE_SCHEDULE: [
            CONF_START_TIME,
            CONF_END_TIME,
            DAY_MONDAY,
            DAY_TUESDAY,
            DAY_WEDNESDAY,
            DAY_THURSDAY,
            DAY_FRIDAY,
            DAY_SATURDAY,
            DAY_SUNDAY,
        ],
        STEP_CONFIRM_REMOVE: [
            CONF_CONFIRM,
        ],
    }

    for lang in ["en", "uk"]:
        file_path = base_path / f"{lang}.json"
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        steps = data.get("config", {}).get("step", {})

        for step_name, fields in step_fields.items():
            if step_name not in steps:
                continue  # Skip if step doesn't exist (already tested above)
            
            step_data = steps[step_name].get("data", {})
            
            for field in fields:
                assert field in step_data, \
                    f"{lang}.json missing field '{field}' in step '{step_name}'"


def test_selector_translations():
    """Test that selector translations are present."""
    base_path = Path("custom_components/sun_allocator/translations")

    # Use constants for selector keys
    required_selectors = {
        "main_menu_action": [ACTION_SETTINGS, ACTION_MANAGE_DEVICES],
        "manage_devices_action": [ACTION_ADD_DEVICE, ACTION_EDIT, ACTION_REMOVE, ACTION_BACK],
        "panel_configuration": [PANEL_CONFIG_SERIES, PANEL_CONFIG_PARALLEL, PANEL_CONFIG_PARALLEL_SERIES],
        "device_type": [DEVICE_TYPE_STANDARD, DEVICE_TYPE_CUSTOM],
    }

    for lang in ["en", "uk"]:
        file_path = base_path / f"{lang}.json"
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        selectors = data.get("selector", {})

        for selector_key, expected_options in required_selectors.items():
            assert selector_key in selectors, \
                f"{lang}.json missing selector '{selector_key}'"
            assert "options" in selectors[selector_key], \
                f"{lang}.json selector '{selector_key}' missing options"
            
            # Check that all expected options are present
            selector_options = selectors[selector_key]["options"]
            for option in expected_options:
                assert option in selector_options, \
                    f"{lang}.json selector '{selector_key}' missing option '{option}'"


def test_translation_keys_match():
    """Test that EN and UK have matching keys."""
    base_path = Path("custom_components/sun_allocator/translations")

    with open(base_path / "en.json", 'r', encoding='utf-8') as f:
        en_data = json.load(f)

    with open(base_path / "uk.json", 'r', encoding='utf-8') as f:
        uk_data = json.load(f)

    def get_all_keys(d, prefix=''):
        """Recursively get all keys."""
        keys = set()
        for k, v in d.items():
            current_key = f"{prefix}.{k}" if prefix else k
            keys.add(current_key)
            if isinstance(v, dict) and k not in ['state_attributes']:
                keys.update(get_all_keys(v, current_key))
        return keys

    # Allow some flexibility for entity translations
    config_en = get_all_keys(en_data.get('config', {}), 'config')
    config_uk = get_all_keys(uk_data.get('config', {}), 'config')

    missing_in_uk = config_en - config_uk
    assert len(missing_in_uk) == 0, \
        f"Keys in EN but missing in UK: {missing_in_uk}"


def test_panel_configuration_options():
    """Test that panel configuration options are translated."""
    base_path = Path("custom_components/sun_allocator/translations")

    panel_configs = [
        PANEL_CONFIG_SERIES,
        PANEL_CONFIG_PARALLEL,
        PANEL_CONFIG_PARALLEL_SERIES,
    ]

    for lang in ["en", "uk"]:
        file_path = base_path / f"{lang}.json"
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        selector_options = data.get("selector", {}).get("panel_configuration", {}).get("options", {})

        for config in panel_configs:
            assert config in selector_options, \
                f"{lang}.json missing panel configuration option '{config}'"


def test_device_type_options():
    """Test that device type options are translated."""
    base_path = Path("custom_components/sun_allocator/translations")

    device_types = [
        DEVICE_TYPE_STANDARD,
        DEVICE_TYPE_CUSTOM,
    ]

    for lang in ["en", "uk"]:
        file_path = base_path / f"{lang}.json"
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        selector_options = data.get("selector", {}).get("device_type", {}).get("options", {})

        for device_type in device_types:
            assert device_type in selector_options, \
                f"{lang}.json missing device type option '{device_type}'"


def test_action_options():
    """Test that action options are translated."""
    base_path = Path("custom_components/sun_allocator/translations")

    actions = [
        ACTION_SETTINGS,
        ACTION_MANAGE_DEVICES,
        ACTION_ADD_DEVICE,
        ACTION_EDIT,
        ACTION_REMOVE,
        ACTION_BACK,
    ]

    for lang in ["en", "uk"]:
        file_path = base_path / f"{lang}.json"
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Check in different selector sections
        selectors = data.get("selector", {})
        
        # Collect all action options from all selectors
        all_action_options = {}
        for selector_name, selector_data in selectors.items():
            if "action" in selector_name and "options" in selector_data:
                all_action_options.update(selector_data["options"])

        for action in actions:
            assert action in all_action_options, \
                f"{lang}.json missing action option '{action}'"
