"""Solar panel configuration module for Sun Allocator config flow."""

from typing import Dict, Any, Optional

import voluptuous as vol

from ..core.logger import log_error, log_exception, audit_action
from .solar_config_form import build_solar_config_schema

from ..const import (
    STEP_USER,
    CONF_CONSUMPTION,
    CONF_PANEL_VMP,
    CONF_PANEL_IMP,
    CONF_PANEL_VOC,
    CONF_PANEL_COUNT,
    CONF_BATTERY_POWER,
    NONE_OPTION,
)


class SolarConfigMixin:
    """Mixin for solar panel configuration steps."""

    def _validate_solar_config(self, user_input: Dict[str, Any]) -> Dict[str, str]:
        """Validate solar panel configuration."""
        errors = {}
        
        if (
            user_input.get(CONF_PANEL_VOC) is not None
            and user_input.get(CONF_PANEL_VMP) is not None
        ):
            try:
                voc = float(user_input.get(CONF_PANEL_VOC))
                vmp = float(user_input.get(CONF_PANEL_VMP))
                if voc == vmp:
                    errors[CONF_PANEL_VOC] = "voc_equal_to_vmp"
            except (ValueError, TypeError) as exc:
                errors["base"] = "invalid_values"
                log_error(
                    "[SolarConfigMixin] Invalid Voc/Vmp: VOC=%s, VMP=%s",
                    user_input.get(CONF_PANEL_VOC),
                    user_input.get(CONF_PANEL_VMP),
                )
                log_exception("solar_config_voc_vmp", exc)
                
        try:
            panel_count = int(user_input.get(CONF_PANEL_COUNT, 1))
            if panel_count <= 0:
                errors[CONF_PANEL_COUNT] = "invalid_panel_count"
        except (ValueError, TypeError) as exc:
            errors[CONF_PANEL_COUNT] = "invalid_panel_count"
            log_error(
                "[SolarConfigMixin] Invalid panel count: %s",
                user_input.get(CONF_PANEL_COUNT),
            )
            log_exception("solar_config_panel_count", exc)
            
        try:
            vmp = float(user_input.get(CONF_PANEL_VMP, 0))
            if vmp <= 0:
                errors[CONF_PANEL_VMP] = "invalid_vmp"
        except (ValueError, TypeError) as exc:
            errors[CONF_PANEL_VMP] = "invalid_vmp"
            log_error("[SolarConfigMixin] Invalid Vmp: %s", user_input.get(CONF_PANEL_VMP))
            log_exception("solar_config_vmp", exc)
            
        try:
            imp = float(user_input.get(CONF_PANEL_IMP, 0))
            if imp <= 0:
                errors[CONF_PANEL_IMP] = "invalid_imp"
        except (ValueError, TypeError) as exc:
            errors[CONF_PANEL_IMP] = "invalid_imp"
            log_error("[SolarConfigMixin] Invalid Imp: %s", user_input.get(CONF_PANEL_IMP))
            log_exception("solar_config_imp", exc)
        return errors


    def _process_solar_config_input(self, user_input: Dict[str, Any]) -> Dict[str, Any]:
        """Process and clean solar configuration input."""
        for field in [CONF_CONSUMPTION, CONF_BATTERY_POWER]:
            if field in user_input and (not user_input[field] or user_input[field] == NONE_OPTION or user_input[field] == ""):
                user_input[field] = None

        return user_input


    def _get_solar_config_schema(
        self, defaults: Optional[Dict[str, Any]] = None
    ) -> vol.Schema:
        """Get the schema for solar panel configuration using solar_config_form.py."""
        return build_solar_config_schema(defaults)


    async def async_step_user(self, user_input=None):
        """Handle the initial step - solar panel configuration."""
        errors = {}

        if user_input is not None:
            errors = self._validate_solar_config(user_input)

            if not errors:
                user_input = self._process_solar_config_input(user_input)

                self._solar_config = user_input
                audit_action("solar_config_saved", {"config": user_input})
                return await self.async_step_devices()

        schema = self._get_solar_config_schema(self._solar_config)

        return self.async_show_form(
            step_id=STEP_USER,
            data_schema=schema,
            errors=errors,
        )
