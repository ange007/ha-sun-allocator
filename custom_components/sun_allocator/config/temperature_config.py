"""Temperature compensation configuration module for Sun Allocator config flow."""

from typing import Dict, Any, Optional

import voluptuous as vol

from homeassistant.core import HomeAssistant

from ..core.logger import log_error, log_exception, audit_action
from ..config.ui_helpers import EntitySelectorBuilder
from .temperature_config_form import build_temperature_config_schema

from ..const import (
    CONF_TEMPERATURE_COMPENSATION_ENABLED,
    CONF_TEMPERATURE_SENSOR,
    CONF_TEMP_COEFFICIENT_VOC,
    CONF_TEMP_COEFFICIENT_PMAX,
    STEP_TEMPERATURE_COMPENSATION,
    NONE_OPTION,
    CONF_ADVANCED_SETTINGS_ENABLED,
)


class TemperatureConfigMixin:
    """Mixin for temperature compensation configuration steps."""

    def _get_temperature_sensors(self, hass: HomeAssistant) -> list:
        """Get available temperature sensors with label/value for selector."""
        icon_map = {"sensor": "🌡️"}
        sensors = [
            entity
            for entity in hass.states.async_all()
            if entity.entity_id.startswith("sensor.")
            and (
                "temp" in entity.entity_id.lower()
                or "temperature" in entity.entity_id.lower()
                or (entity.attributes.get("unit_of_measurement") in ["°C", "°F", "K"])
            )
        ]
        builder = EntitySelectorBuilder(icon_map)
        result = builder.build(sensors, none_option=True)
        # NONE_OPTION замість "None"
        if result and result[0]["value"] == "None":
            result[0]["value"] = NONE_OPTION

        return result


    def _validate_temperature_config(
        self, user_input: Dict[str, Any]
    ) -> Dict[str, str]:
        """Validate temperature compensation configuration."""
        errors = {}
        # Validate temperature coefficients
        try:
            voc_coef = float(user_input.get(CONF_TEMP_COEFFICIENT_VOC, -0.3))
            # VOC coefficient should typically be negative (around -0.3% per °C)
            if not -1.0 <= voc_coef <= 0:
                errors[CONF_TEMP_COEFFICIENT_VOC] = "invalid_voc_coefficient"
        except (ValueError, TypeError) as exc:
            errors[CONF_TEMP_COEFFICIENT_VOC] = "invalid_voc_coefficient"
            log_error(
                "[TemperatureConfigMixin] Invalid VOC coefficient: %s",
                user_input.get(CONF_TEMP_COEFFICIENT_VOC),
            )
            log_exception("temperature_config_voc_coef", exc)
        try:
            pmax_coef = float(user_input.get(CONF_TEMP_COEFFICIENT_PMAX, -0.4))
            # PMAX coefficient should typically be negative (around -0.4% per °C)
            if not -1.0 <= pmax_coef <= 0:
                errors[CONF_TEMP_COEFFICIENT_PMAX] = "invalid_pmax_coefficient"
        except (ValueError, TypeError) as exc:
            errors[CONF_TEMP_COEFFICIENT_PMAX] = "invalid_pmax_coefficient"
            log_error(
                "[TemperatureConfigMixin] Invalid PMAX coefficient: %s",
                user_input.get(CONF_TEMP_COEFFICIENT_PMAX),
            )
            log_exception("temperature_config_pmax_coef", exc)
        # Validate that temperature sensor is selected if compensation is enabled
        if user_input.get(CONF_TEMPERATURE_COMPENSATION_ENABLED, False):
            temp_sensor = user_input.get(CONF_TEMPERATURE_SENSOR)
            if not temp_sensor or temp_sensor == NONE_OPTION or temp_sensor == "":
                errors[CONF_TEMPERATURE_SENSOR] = "temperature_sensor_required"

        return errors


    def _process_temperature_config_input(
        self, user_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process and clean temperature compensation configuration input."""
        # Create a copy of the input to avoid modifying the original
        processed_input = dict(user_input)
        
        # Handle the temperature sensor value
        temp_sensor = processed_input.get(CONF_TEMPERATURE_SENSOR)
        
        # Convert "None" option or empty string to actual None value
        if temp_sensor == NONE_OPTION or temp_sensor == "" or temp_sensor is None:
            processed_input[CONF_TEMPERATURE_SENSOR] = None
        # else: preserve the valid sensor value (no change needed)
        
        # If temperature compensation is explicitly disabled, always clear the sensor
        if CONF_TEMPERATURE_COMPENSATION_ENABLED in processed_input and not processed_input[CONF_TEMPERATURE_COMPENSATION_ENABLED]:
            processed_input[CONF_TEMPERATURE_SENSOR] = None
            
        # If no compensation setting is provided but a valid sensor is set,
        # we can assume temperature compensation should be enabled
        elif CONF_TEMPERATURE_COMPENSATION_ENABLED not in processed_input and processed_input.get(CONF_TEMPERATURE_SENSOR) is not None:
            # This is optional - we don't set the flag automatically in the actual implementation
            # but it would be a logical assumption
            pass

        return processed_input


    def _get_temperature_config_schema(
        self, defaults: Optional[Dict[str, Any]] = None
    ) -> vol.Schema:
        """Get the schema for temperature compensation configuration."""
        return build_temperature_config_schema(defaults)


    async def async_step_temperature_compensation(self, user_input=None):
        """Handle temperature compensation settings."""
        errors = {}

        if user_input is not None:
            # Validate input
            errors = self._validate_temperature_config(user_input)

            if not errors:
                # Process input
                user_input = self._process_temperature_config_input(user_input)

                # Update solar panel configuration with temperature settings
                self._solar_config.update(user_input)
                audit_action("temperature_config_saved", {"config": user_input})

                # If advanced settings are enabled, chain to advanced settings step
                if self._solar_config.get(
                    CONF_ADVANCED_SETTINGS_ENABLED, False
                ) and hasattr(self, "async_step_advanced_settings"):
                    return await self.async_step_advanced_settings()

                # Otherwise save configuration and return
                return await self._save_and_return()

        # Create schema with current values as defaults
        schema = self._get_temperature_config_schema(self._solar_config)

        return self.async_show_form(
            step_id=STEP_TEMPERATURE_COMPENSATION,
            data_schema=schema,
            errors=errors,
        )


    async def _save_and_return(self):
        """Save configuration and return to appropriate step."""
        raise NotImplementedError(
            "_save_and_return must be implemented by the main config flow class"
        )
