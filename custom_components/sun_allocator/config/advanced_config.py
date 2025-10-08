"""Advanced settings configuration module for Sun Allocator config flow."""

from typing import Dict, Any, Optional

import voluptuous as vol

from ..core.logger import log_error, log_exception, audit_action
from .advanced_config_form import build_advanced_config_schema

from ..const import (
    STEP_ADVANCED_SETTINGS,
    CONF_MIN_INVERTER_VOLTAGE,
    CONF_RAMP_UP_STEP,
    CONF_RAMP_DOWN_STEP,
    CONF_RAMP_DEADBAND,
    CONF_HYSTERESIS_W,
    DEFAULT_HYSTERESIS_W,
    CONF_INVERTER_SELF_CONSUMPTION,
)


class AdvancedConfigMixin:
    """Mixin for advanced settings configuration steps."""

    def _validate_advanced_config(self, user_input: Dict[str, Any]) -> Dict[str, str]:
        """Validate advanced settings configuration."""
        errors = {}
        # Validate minimum inverter voltage
        try:
            min_voltage = float(user_input.get(CONF_MIN_INVERTER_VOLTAGE, 100.0))
            if min_voltage < 0:
                errors[CONF_MIN_INVERTER_VOLTAGE] = "invalid_min_voltage"
        except (ValueError, TypeError) as e:
            errors[CONF_MIN_INVERTER_VOLTAGE] = "invalid_min_voltage"
            log_error(
                "[AdvancedConfigMixin] Invalid min inverter voltage: %s",
                user_input.get(CONF_MIN_INVERTER_VOLTAGE),
            )
            log_exception("advanced_config_min_voltage", e)
        # Validate inverter self consumption
        try:
            inverter_self_consumption = float(user_input.get(CONF_INVERTER_SELF_CONSUMPTION, 0.0))
            if not 0 <= inverter_self_consumption <= 500:
                errors[CONF_INVERTER_SELF_CONSUMPTION] = "invalid_inverter_self_consumption"
        except (ValueError, TypeError) as e:
            errors[CONF_INVERTER_SELF_CONSUMPTION] = "invalid_inverter_self_consumption"
            log_error(
                "[AdvancedConfigMixin] Invalid inverter self consumption: %s",
                user_input.get(CONF_INVERTER_SELF_CONSUMPTION),
            )
            log_exception("advanced_config_inverter_self_consumption", e)
        # Validate ramp/hysteresis tunables
        try:
            up = float(user_input.get(CONF_RAMP_UP_STEP, 10.0))
            if not 0 < up <= 100:
                errors[CONF_RAMP_UP_STEP] = "invalid_ramp_up_step"
        except (ValueError, TypeError) as e:
            errors[CONF_RAMP_UP_STEP] = "invalid_ramp_up_step"
            log_error(
                "[AdvancedConfigMixin] Invalid ramp up step: %s",
                user_input.get(CONF_RAMP_UP_STEP),
            )
            log_exception("advanced_config_ramp_up_step", e)
        try:
            down = float(user_input.get(CONF_RAMP_DOWN_STEP, 20.0))
            if not 0 < down <= 100:
                errors[CONF_RAMP_DOWN_STEP] = "invalid_ramp_down_step"
        except (ValueError, TypeError) as e:
            errors[CONF_RAMP_DOWN_STEP] = "invalid_ramp_down_step"
            log_error(
                "[AdvancedConfigMixin] Invalid ramp down step: %s",
                user_input.get(CONF_RAMP_DOWN_STEP),
            )
            log_exception("advanced_config_ramp_down_step", e)
        try:
            db = float(user_input.get(CONF_RAMP_DEADBAND, 1.0))
            if not 0 <= db <= 10:
                errors[CONF_RAMP_DEADBAND] = "invalid_ramp_deadband"
        except (ValueError, TypeError) as e:
            errors[CONF_RAMP_DEADBAND] = "invalid_ramp_deadband"
            log_error(
                "[AdvancedConfigMixin] Invalid ramp deadband: %s",
                user_input.get(CONF_RAMP_DEADBAND),
            )
            log_exception("advanced_config_ramp_deadband", e)

        try:
            hyst = float(user_input.get(CONF_HYSTERESIS_W, DEFAULT_HYSTERESIS_W))
            if not 0 <= hyst <= 5000:
                errors[CONF_HYSTERESIS_W] = "invalid_hysteresis_w"
        except (ValueError, TypeError) as e:
            errors[CONF_HYSTERESIS_W] = "invalid_hysteresis_w"
            log_error(
                "[AdvancedConfigMixin] Invalid hysteresis W: %s",
                user_input.get(CONF_HYSTERESIS_W),
            )
            log_exception("advanced_config_hysteresis_w", e)
        return errors


    def _get_advanced_config_schema(
        self, defaults: Optional[Dict[str, Any]] = None
    ) -> vol.Schema:
        """Get the schema for advanced settings configuration."""
        return build_advanced_config_schema(defaults)


    async def async_step_advanced_settings(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Handle the advanced settings step."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            # Validate input
            errors = self._validate_advanced_config(user_input)

            if not errors:
                # Process input
                self._solar_config.update(user_input)
                audit_action("advanced_settings_update", self._solar_config)
                # Save and proceed
                return await self._save_and_return()

        schema = self._get_advanced_config_schema(self._solar_config)

        return self.async_show_form(
            step_id=STEP_ADVANCED_SETTINGS,
            data_schema=schema,
            errors=errors,
        )
