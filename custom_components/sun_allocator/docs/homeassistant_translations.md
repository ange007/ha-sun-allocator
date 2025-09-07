# Home Assistant Standard Translation System Implementation

This document explains the implementation of Home Assistant's standard translation system in the SunAllocator integration, replacing the previous custom translation system.

## Overview

SunAllocator now uses Home Assistant's built-in translation system, which automatically loads translations from JSON files in the `translations` directory and applies them to configuration flows and UI elements based on the user's language settings.

## Changes Made

### 1. Translation Files Structure ✓

The translation files already had the correct Home Assistant standard format:

```
custom_components/sun_allocator/translations/
├── en.json    # English translations
└── uk.json    # Ukrainian translations
```

Both files follow the proper hierarchical structure:
- `config.step.<step_id>.title` - Step titles
- `config.step.<step_id>.description` - Step descriptions  
- `config.field.<field_id>` - Field labels
- `config.error.<error_id>` - Error messages
- `config.selector.<selector_id>.options.<option_id>` - Selector options

### 2. Schema Field Descriptions ✓

Updated all configuration schemas to include `description` parameters that connect to the translation system:

#### Solar Config Schema (`solar_config.py`)
```python
vol.Required(CONF_PV_POWER, default=defaults.get(CONF_PV_POWER), description={"suggested_value": defaults.get(CONF_PV_POWER)}): vol.In(sensors["power_sensors"]),
vol.Required(CONF_VMP, default=defaults.get(CONF_VMP, 36.0), description={"suggested_value": defaults.get(CONF_VMP, 36.0)}): vol.Coerce(float),
```

#### Device Config Schemas (`device_config.py`)
```python
vol.Required(CONF_DEVICE_NAME, default=defaults.get(CONF_DEVICE_NAME, ""), description={"suggested_value": defaults.get(CONF_DEVICE_NAME, "")}): str,
vol.Required(CONF_AUTO_CONTROL_ENABLED, default=defaults.get(CONF_AUTO_CONTROL_ENABLED, False), description={"suggested_value": defaults.get(CONF_AUTO_CONTROL_ENABLED, False)}): bool,
```

#### Temperature Config Schema (`temperature_config.py`)
```python
vol.Required(CONF_TEMPERATURE_SENSOR, default=default_temp_sensor, description={"suggested_value": default_temp_sensor}): vol.In(temperature_sensors),
vol.Required(CONF_TEMP_COEFFICIENT_VOC, default=defaults.get(CONF_TEMP_COEFFICIENT_VOC, DEFAULT_VOC_COEFFICIENT), description={"suggested_value": defaults.get(CONF_TEMP_COEFFICIENT_VOC, DEFAULT_VOC_COEFFICIENT)}): vol.All(vol.Coerce(float), vol.Range(min=-1.0, max=0.0)),
```

#### Main Config Schemas (`__init__.py`)
```python
vol.Required("action", default=ACTION_SETTINGS, description={"suggested_value": ACTION_SETTINGS}): vol.In(options),
vol.Optional("curve_factor_k", default=self._solar_config.get("curve_factor_k", 0.2), description={"suggested_value": self._solar_config.get("curve_factor_k", 0.2)}): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=0.5)),
```

### 3. How It Works

Home Assistant's translation system works automatically:

1. **Language Detection**: Home Assistant detects the user's language from their browser/system settings
2. **Translation Loading**: The system loads the appropriate translation file from the `translations` directory
3. **Automatic Translation**: Field labels, step titles, descriptions, and error messages are automatically translated based on:
   - Field IDs matching `config.field.<field_id>` keys
   - Step IDs matching `config.step.<step_id>.title` and `config.step.<step_id>.description` keys
   - Error IDs matching `config.error.<error_id>` keys
   - Selector options matching `config.selector.<selector_id>.options.<option_id>` keys

### 4. Translation Key Mapping

The system uses the following mapping:

| UI Element | Translation Key | Example |
|------------|----------------|---------|
| Field Label | `config.field.<field_id>` | `config.field.pv_power` → "PV Power" |
| Step Title | `config.step.<step_id>.title` | `config.step.user.title` → "Solar Panel Configuration" |
| Step Description | `config.step.<step_id>.description` | `config.step.user.description` → "Configure your solar panel parameters" |
| Error Message | `config.error.<error_id>` | `config.error.invalid_vmp` → "Invalid Vmp value" |
| Selector Option | `config.selector.<selector_id>.options.<option_id>` | `config.selector.panel_configuration.options.series` → "Series" |

### 5. Supported Languages

Currently supported languages:
- **English** (`en.json`) - Default language
- **Ukrainian** (`uk.json`) - Full translation

## Benefits of Home Assistant Standard System

1. **Automatic Integration**: No custom code needed for translation loading
2. **Performance**: Built-in caching and optimization
3. **Consistency**: Follows Home Assistant standards and conventions
4. **Maintainability**: Easier to maintain and extend
5. **User Experience**: Seamless integration with Home Assistant's language settings

## Adding New Languages

To add a new language:

1. Create a new JSON file in `translations/` directory (e.g., `fr.json` for French)
2. Copy the structure from `en.json`
3. Translate all string values while preserving keys and structure
4. Test the translation by changing Home Assistant's language setting

Example for French (`fr.json`):
```json
{
  "component.name": "Capteur d'excès d'énergie SunAllocator",
  "config": {
    "step": {
      "user": {
        "title": "Configuration des panneaux solaires",
        "description": "Configurez les paramètres de vos panneaux solaires"
      }
    },
    "field": {
      "pv_power": "Puissance PV",
      "panel_count": "Nombre de panneaux"
    }
  }
}
```

## Testing

The translation system can be tested using the test script:

```bash
cd custom_components/sun_allocator/tests
python test_translations.py
```

This verifies:
- Translation files load correctly
- All translation keys are accessible
- Placeholder replacement works properly
- Fallback to English works for missing translations

## Migration from Custom System

The previous custom translation system has been completely removed:
- ❌ `utils/translation_helper.py` - Removed
- ❌ `config/translation_mixin.py` - Removed  
- ❌ `config/translated_config_flow_mixin.py` - Removed
- ✅ Home Assistant's built-in system - Now used

## Troubleshooting

If translations don't appear:

1. **Check file structure**: Ensure translation files are in `translations/` directory
2. **Verify JSON format**: Ensure files are valid JSON with proper encoding (UTF-8)
3. **Check keys**: Verify translation keys match field IDs, step IDs, etc.
4. **Restart Home Assistant**: Changes to translation files require a restart
5. **Check language setting**: Verify Home Assistant is set to the correct language
6. **Review logs**: Check Home Assistant logs for translation-related errors

## Conclusion

The implementation of Home Assistant's standard translation system provides a robust, maintainable, and user-friendly solution for internationalization in the SunAllocator integration. The system automatically handles language detection, translation loading, and UI element translation without requiring custom code or complex initialization procedures.