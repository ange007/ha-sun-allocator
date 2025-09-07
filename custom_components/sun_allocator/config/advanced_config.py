"""Advanced settings configuration module for Sun Allocator config flow."""
import voluptuous as vol
from typing import Dict, Any, Optional

from ..const import (
    CONF_ADVANCED_SETTINGS_ENABLED,
    CONF_BATTERY_POWER_REVERSED,
    CONF_CURVE_FACTOR_K,
    CONF_EFFICIENCY_CORRECTION_FACTOR,
    CONF_MIN_INVERTER_VOLTAGE,
    STEP_ADVANCED_SETTINGS,
    CONF_RAMP_UP_STEP,
    CONF_RAMP_DOWN_STEP,
    CONF_RAMP_DEADBAND,
    CONF_DEFAULT_MIN_START_W,
    CONF_HYSTERESIS_W,
    DEFAULT_MIN_START_W,
    DEFAULT_HYSTERESIS_W,
)


class AdvancedConfigMixin:
    """Mixin for advanced settings configuration steps."""

    def _validate_advanced_config(self, user_input: Dict[str, Any]) -> Dict[str, str]:
        """Validate advanced settings configuration."""
        errors = {}

        # Validate curve factor
        try:
            curve_factor = float(user_input.get(CONF_CURVE_FACTOR_K, 0.2))
            if curve_factor <= 0 or curve_factor > 1.0:
                errors[CONF_CURVE_FACTOR_K] = "invalid_curve_factor"
        except (ValueError, TypeError):
            errors[CONF_CURVE_FACTOR_K] = "invalid_curve_factor"

        # Validate efficiency correction factor
        try:
            efficiency_factor = float(user_input.get(CONF_EFFICIENCY_CORRECTION_FACTOR, 1.05))
            if efficiency_factor < 1.0 or efficiency_factor > 1.5:
                errors[CONF_EFFICIENCY_CORRECTION_FACTOR] = "invalid_efficiency_factor"
        except (ValueError, TypeError):
            errors[CONF_EFFICIENCY_CORRECTION_FACTOR] = "invalid_efficiency_factor"

        # Validate minimum inverter voltage
        try:
            min_voltage = float(user_input.get(CONF_MIN_INVERTER_VOLTAGE, 100.0))
            if min_voltage < 0:
                errors[CONF_MIN_INVERTER_VOLTAGE] = "invalid_min_voltage"
        except (ValueError, TypeError):
            errors[CONF_MIN_INVERTER_VOLTAGE] = "invalid_min_voltage"

        # Validate ramp/hysteresis tunables
        try:
            up = float(user_input.get(CONF_RAMP_UP_STEP, 10.0))
            if up <= 0 or up > 100:
                errors[CONF_RAMP_UP_STEP] = "invalid_ramp_up_step"
        except (ValueError, TypeError):
            errors[CONF_RAMP_UP_STEP] = "invalid_ramp_up_step"
        try:
            down = float(user_input.get(CONF_RAMP_DOWN_STEP, 20.0))
            if down <= 0 or down > 100:
                errors[CONF_RAMP_DOWN_STEP] = "invalid_ramp_down_step"
        except (ValueError, TypeError):
            errors[CONF_RAMP_DOWN_STEP] = "invalid_ramp_down_step"
        try:
            db = float(user_input.get(CONF_RAMP_DEADBAND, 1.0))
            if db < 0 or db > 10:
                errors[CONF_RAMP_DEADBAND] = "invalid_ramp_deadband"
        except (ValueError, TypeError):
            errors[CONF_RAMP_DEADBAND] = "invalid_ramp_deadband"
        try:
            dmin = float(user_input.get(CONF_DEFAULT_MIN_START_W, DEFAULT_MIN_START_W))
            if dmin < 0 or dmin > 5000:
                errors[CONF_DEFAULT_MIN_START_W] = "invalid_default_min_start_w"
        except (ValueError, TypeError):
            errors[CONF_DEFAULT_MIN_START_W] = "invalid_default_min_start_w"
        try:
            hyst = float(user_input.get(CONF_HYSTERESIS_W, DEFAULT_HYSTERESIS_W))
            if hyst < 0 or hyst > 5000:
                errors[CONF_HYSTERESIS_W] = "invalid_hysteresis_w"
        except (ValueError, TypeError):
            errors[CONF_HYSTERESIS_W] = "invalid_hysteresis_w"

        return errors

    def _process_advanced_config_input(self, user_input: Dict[str, Any]) -> Dict[str, Any]:
        """Process and clean advanced settings configuration input."""
        # No special processing needed for now
        return user_input

    def _get_advanced_config_schema(self, defaults: Optional[Dict[str, Any]] = None) -> vol.Schema:
        """Get the schema for advanced settings configuration."""
        if defaults is None:
            defaults = {}

        return vol.Schema({
            # MPPT algorithm parameters
            vol.Required(CONF_CURVE_FACTOR_K, default=defaults.get(CONF_CURVE_FACTOR_K, 0.2), 
                        description={"suggested_value": defaults.get(CONF_CURVE_FACTOR_K, 0.2)}): 
                vol.All(vol.Coerce(float), vol.Range(min=0.1, max=0.5)),
            vol.Required(CONF_EFFICIENCY_CORRECTION_FACTOR, default=defaults.get(CONF_EFFICIENCY_CORRECTION_FACTOR, 1.05), 
                        description={"suggested_value": defaults.get(CONF_EFFICIENCY_CORRECTION_FACTOR, 1.05)}): 
                vol.All(vol.Coerce(float), vol.Range(min=1.0, max=1.2)),
            vol.Required(CONF_MIN_INVERTER_VOLTAGE, default=defaults.get(CONF_MIN_INVERTER_VOLTAGE, 100.0), 
                        description={"suggested_value": defaults.get(CONF_MIN_INVERTER_VOLTAGE, 100.0)}): 
                vol.Coerce(float),

            # Ramp/hysteresis tunables
            vol.Required(CONF_RAMP_UP_STEP, default=defaults.get(CONF_RAMP_UP_STEP, 10.0),
                        description={"suggested_value": defaults.get(CONF_RAMP_UP_STEP, 10.0)}):
                vol.All(vol.Coerce(float), vol.Range(min=0.1, max=100.0)),
            vol.Required(CONF_RAMP_DOWN_STEP, default=defaults.get(CONF_RAMP_DOWN_STEP, 20.0),
                        description={"suggested_value": defaults.get(CONF_RAMP_DOWN_STEP, 20.0)}):
                vol.All(vol.Coerce(float), vol.Range(min=0.1, max=100.0)),
            vol.Required(CONF_RAMP_DEADBAND, default=defaults.get(CONF_RAMP_DEADBAND, 1.0),
                        description={"suggested_value": defaults.get(CONF_RAMP_DEADBAND, 1.0)}):
                vol.All(vol.Coerce(float), vol.Range(min=0.0, max=10.0)),
            vol.Required(CONF_DEFAULT_MIN_START_W, default=defaults.get(CONF_DEFAULT_MIN_START_W, DEFAULT_MIN_START_W),
                        description={"suggested_value": defaults.get(CONF_DEFAULT_MIN_START_W, DEFAULT_MIN_START_W)}):
                vol.Coerce(float),
            vol.Required(CONF_HYSTERESIS_W, default=defaults.get(CONF_HYSTERESIS_W, DEFAULT_HYSTERESIS_W),
                        description={"suggested_value": defaults.get(CONF_HYSTERESIS_W, DEFAULT_HYSTERESIS_W)}):
                vol.Coerce(float),
            
            # Battery power reverse setting
            vol.Required(CONF_BATTERY_POWER_REVERSED, default=defaults.get(CONF_BATTERY_POWER_REVERSED, False), 
                        description={"suggested_value": defaults.get(CONF_BATTERY_POWER_REVERSED, False)}): 
                bool,
        })

    async def async_step_advanced_settings(self, user_input=None):
        """Handle advanced settings."""
        errors = {}

        if user_input is not None:
            # Validate input
            errors = self._validate_advanced_config(user_input)

            if not errors:
                # Process input
                user_input = self._process_advanced_config_input(user_input)

                # Update solar panel configuration with advanced settings
                self._solar_config.update(user_input)

                # Save configuration and return to main menu or complete setup
                return await self._save_and_return()

        # Create schema with current values as defaults
        schema = self._get_advanced_config_schema(self._solar_config)

        return self.async_show_form(
            step_id=STEP_ADVANCED_SETTINGS,
            data_schema=schema,
            errors=errors,
        )

    async def _save_and_return(self):
        """Save configuration and return to appropriate step."""
        # This method should be implemented by the main config flow class
        # to handle saving and returning to the correct step
        raise NotImplementedError("_save_and_return must be implemented by the main config flow class")