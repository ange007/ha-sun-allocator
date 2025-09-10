"""Temperature compensation configuration module for Sun Allocator config flow."""
import voluptuous as vol
from homeassistant.core import HomeAssistant
from typing import Dict, Any, List, Optional

from ..const import (
    CONF_TEMPERATURE_COMPENSATION_ENABLED,
    CONF_TEMPERATURE_SENSOR,
    CONF_TEMP_COEFFICIENT_VOC,
    CONF_TEMP_COEFFICIENT_PMAX,
    STEP_TEMPERATURE_COMPENSATION,
    NONE_OPTION,
    DEFAULT_VOC_COEFFICIENT,
    DEFAULT_PMAX_COEFFICIENT,
    CONF_ADVANCED_SETTINGS_ENABLED,
)

# Import helpers for selector building and schema
from ..utils.ui_helpers import EntitySelectorBuilder
from .temperature_config_form import build_temperature_config_schema


class TemperatureConfigMixin:
    """Mixin for temperature compensation configuration steps."""

    def _get_temperature_sensors(self, hass: HomeAssistant) -> list:
        """Get available temperature sensors with label/value for selector (через UI helpers)."""
        icon_map = {"sensor": "🌡️"}
        sensors = [e for e in hass.states.async_all() if e.entity_id.startswith("sensor.") and (
            "temp" in e.entity_id.lower() or
            "temperature" in e.entity_id.lower() or
            (e.attributes.get("unit_of_measurement") in ["°C", "°F", "K"]))]
        builder = EntitySelectorBuilder(icon_map)
        result = builder.build(sensors, none_option=True)
        # NONE_OPTION замість "None"
        if result and result[0]["value"] == "None":
            result[0]["value"] = NONE_OPTION
        return result

    def _validate_temperature_config(self, user_input: Dict[str, Any]) -> Dict[str, str]:
        """Validate temperature compensation configuration."""
        errors = {}

        # Validate temperature coefficients
        try:
            voc_coef = float(user_input.get(CONF_TEMP_COEFFICIENT_VOC, -0.3))
            # VOC coefficient should typically be negative (around -0.3% per °C)
            if voc_coef > 0 or voc_coef < -1.0:
                errors[CONF_TEMP_COEFFICIENT_VOC] = "invalid_voc_coefficient"
        except (ValueError, TypeError):
            errors[CONF_TEMP_COEFFICIENT_VOC] = "invalid_voc_coefficient"

        try:
            pmax_coef = float(user_input.get(CONF_TEMP_COEFFICIENT_PMAX, -0.4))
            # PMAX coefficient should typically be negative (around -0.4% per °C)
            if pmax_coef > 0 or pmax_coef < -1.0:
                errors[CONF_TEMP_COEFFICIENT_PMAX] = "invalid_pmax_coefficient"
        except (ValueError, TypeError):
            errors[CONF_TEMP_COEFFICIENT_PMAX] = "invalid_pmax_coefficient"

        # Validate that temperature sensor is selected if compensation is enabled
        if user_input.get(CONF_TEMPERATURE_COMPENSATION_ENABLED, False):
            temp_sensor = user_input.get(CONF_TEMPERATURE_SENSOR)
            if not temp_sensor or temp_sensor == NONE_OPTION:
                errors[CONF_TEMPERATURE_SENSOR] = "temperature_sensor_required"

        return errors

    def _process_temperature_config_input(self, user_input: Dict[str, Any]) -> Dict[str, Any]:
        """Process and clean temperature compensation configuration input."""
        # Convert "None" string to actual None value for temperature sensor
        if user_input.get(CONF_TEMPERATURE_SENSOR) == NONE_OPTION:
            user_input[CONF_TEMPERATURE_SENSOR] = None

        # If temperature compensation is disabled, clear related settings
        if not user_input.get(CONF_TEMPERATURE_COMPENSATION_ENABLED, False):
            user_input[CONF_TEMPERATURE_SENSOR] = None

        return user_input

    def _get_temperature_config_schema(self, temperature_sensors: list, defaults: Optional[Dict[str, Any]] = None) -> vol.Schema:
        """Get the schema for temperature compensation configuration using temperature_config_form.py."""
        return build_temperature_config_schema(temperature_sensors, defaults)


# Imports moved to the top for PEP8 compliance

    async def async_step_temperature_compensation(self, user_input=None):
        """Handle temperature compensation settings."""
        errors = {}
        temperature_sensors = self._get_temperature_sensors(self.hass)

        if user_input is not None:
            # Validate input
            errors = self._validate_temperature_config(user_input)

            if not errors:
                # Process input
                user_input = self._process_temperature_config_input(user_input)

                # Update solar panel configuration with temperature compensation settings
                self._solar_config.update(user_input)

                # If advanced settings are enabled, chain to advanced settings step next
                if self._solar_config.get(CONF_ADVANCED_SETTINGS_ENABLED, False) and hasattr(self, "async_step_advanced_settings"):
                    return await self.async_step_advanced_settings()

                # Otherwise save configuration and return
                return await self._save_and_return()

        # Create schema with current values as defaults
        schema = self._get_temperature_config_schema(temperature_sensors, self._solar_config)

        return self.async_show_form(
            step_id=STEP_TEMPERATURE_COMPENSATION,
            data_schema=schema,
            errors=errors,
        )

    async def _save_and_return(self):
        """Save configuration and return to appropriate step."""
        # This method should be implemented by the main config flow class
        # to handle saving and returning to the correct step
        raise NotImplementedError("_save_and_return must be implemented by the main config flow class")