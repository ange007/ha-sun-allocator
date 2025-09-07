# Translation Fix for SunAllocator Configuration UI

## Issue Description

The configuration UI for SunAllocator was not displaying translated field labels, titles, and descriptions, even though translations were properly defined in the translation files (`translations/en.json` and `translations/uk.json`).

## Root Cause

The issue was identified in the `async_step_settings` method in `config/__init__.py`. This method was manipulating the schema dictionary directly instead of using the `vol.Schema` constructor or the `extend` method, which bypassed the translation system.

```python
# Problematic code
schema_dict = self._get_solar_config_schema(sensors, self._solar_config).schema
schema_dict.update({
    # Additional fields
})
return self.async_show_form(
    step_id=STEP_SETTINGS,
    data_schema=vol.Schema(schema_dict),
    errors=errors,
)
```

The `TranslatedConfigFlowMixin._get_translated_schema` method expects to receive a `vol.Schema` object, not a manipulated dictionary. When the schema dictionary is manipulated directly and then wrapped in a new `vol.Schema` object, the translation system doesn't have a chance to translate the field labels.

## Solution

The solution was to use the `extend` method of `vol.Schema` instead of manipulating the schema dictionary directly:

```python
# Fixed code
original_schema = self._get_solar_config_schema(sensors, self._solar_config)
extended_schema = original_schema.extend({
    # Additional fields
})
return self.async_show_form(
    step_id=STEP_SETTINGS,
    data_schema=extended_schema,
    errors=errors,
)
```

This approach ensures that the translation system can properly translate the field labels because it's receiving a `vol.Schema` object that hasn't been manipulated directly.

## Testing

To verify that the fix works correctly, you should:

1. Restart Home Assistant to load the updated code
2. Go to **Settings → Devices & Services**
3. Find your **SunAllocator** integration
4. Click the **"CONFIGURE"** button
5. Choose **"Settings"** from the main menu
6. Verify that the field labels are translated according to your language settings
7. Check that titles and descriptions are also translated
8. Verify that selector options (like panel_configuration options) are translated

## Translation System Architecture

SunAllocator uses a custom translation system that loads translations from JSON files in the `translations` directory. The system supports multiple languages and automatically falls back to English if a translation is not available in the requested language.

The translation system is implemented in the following files:

- `utils/translation_helper.py`: Contains the core translation functionality
- `config/translation_mixin.py`: Provides a mixin class for translation support in configuration flows
- `config/translated_config_flow_mixin.py`: Provides a mixin that automatically applies translations to configuration forms

The `TranslatedConfigFlowMixin` class overrides the `async_show_form` method to automatically translate schemas, description placeholders, and errors before displaying the form.

## Adding New Translations

To add a new translation:

1. Create a new JSON file in the `translations` directory, named after the language code (e.g., `fr.json` for French).
2. Copy the contents of `en.json` to the new file.
3. Translate all strings in the new file.
4. Make sure to preserve the structure of the file and all keys.

Example of adding a French translation:

```json
{
  "component.name": "Capteur d'excès d'énergie SunAllocator",
  "component.description": "Capteur pour calculer l'excès d'énergie solaire.",
  "config": {
    "step": {
      "user": {
        "title": "Configuration des panneaux solaires",
        "description": "Configurez les paramètres de vos panneaux solaires"
      }
    },
    "field": {
      "pv_power": "Puissance PV",
      "panel_count": "Nombre de panneaux",
      "panel_configuration": "Configuration des panneaux",
      "temperature_compensation_enabled": "Activer la compensation de température"
    }
  }
}
```

## Best Practices for Schema Creation

When creating schemas for configuration forms, follow these best practices to ensure that translations work correctly:

1. **Use `vol.Schema` constructor**: Always create schemas using the `vol.Schema` constructor, not by manipulating dictionaries directly.

2. **Use `extend` method for adding fields**: If you need to add fields to an existing schema, use the `extend` method instead of manipulating the schema dictionary directly.

3. **Use constants for field IDs**: Use constants from `const.py` for field IDs to ensure consistency and make it easier to update field names in the future.

4. **Match field IDs with translation keys**: Make sure that field IDs match the translation keys in the translation files. For example, if a field ID is `"panel_count"`, there should be a translation key `"config.field.panel_count"` in the translation files.

5. **Test translations**: Always test translations to make sure they are displayed correctly in the UI.