# SunAllocator Translations

This document explains how translations work in the SunAllocator integration using Home Assistant's built-in translation system.

## Overview

SunAllocator uses Home Assistant's built-in translation system to provide a localized user interface. The system automatically loads translations from JSON files in the `translations` directory and applies them to the configuration flow and other UI elements.

## Translation Files

Translation files are stored in the `translations` directory and follow the standard Home Assistant translation format. Each language has its own file, named after the language code (e.g., `en.json` for English, `uk.json` for Ukrainian).

The translation files are structured as follows:

```json
{
  "component.name": "SunAllocator Energy Excess Sensor",
  "component.description": "Sensor for calculating excess solar energy.",
  "config": {
    "step": {
      "user": {
        "title": "Solar Panel Configuration",
        "description": "Configure your solar panel parameters"
      }
    },
    "error": {
      "invalid_vmp": "Invalid Vmp value"
    },
    "field": {
      "pv_power": "PV Power"
    },
    "selector": {
      "panel_configuration": {
        "options": {
          "series": "Series"
        }
      }
    }
  }
}
```

## How It Works

Home Assistant automatically loads translations from the `translations` directory and applies them to the configuration flow and other UI elements. The system uses the following key paths to find translations:

- `component.name`: The name of the integration
- `component.description`: The description of the integration
- `config.step.<step_id>.title`: The title of a configuration step
- `config.step.<step_id>.description`: The description of a configuration step
- `config.error.<error_id>`: An error message
- `config.field.<field_id>`: A field label
- `config.selector.<selector_id>.options.<option_id>`: A selector option

When a configuration flow is displayed, Home Assistant automatically looks up the translations for the step title, description, field labels, and error messages based on the current language setting.

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

## Testing Translations

You can test translations using the `test_translations.py` script in the `tests` directory. This script verifies that translations are loaded correctly and that placeholders are replaced properly.

```bash
cd custom_components/sun_allocator/tests
python test_translations.py
```

## Best Practices

1. **Use placeholders for dynamic content**: Instead of concatenating strings, use placeholders in translations. This makes it easier to translate sentences with different word orders in different languages.

2. **Keep translations organized**: Group related translations together in the translation files to make them easier to find and maintain.

3. **Provide context**: Use descriptive keys for translations to provide context for translators. For example, use `config.step.user.title` instead of just `title`.

4. **Test translations**: Always test translations to make sure they are displayed correctly in the UI.

5. **Update translations when adding new features**: When adding new features, make sure to update all translation files with the new strings.

## References

For more information about Home Assistant's translation system, see the following documentation:

- [Internationalization for Custom Integrations](https://developers.home-assistant.io/docs/internationalization/custom_integration/)
- [Internationalization for Core Integrations](https://developers.home-assistant.io/docs/internationalization/core/)