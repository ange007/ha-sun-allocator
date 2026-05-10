"""Solar panel configuration module for Sun Allocator config flow."""

from typing import Dict, Any, Optional

import voluptuous as vol

from ..core.logger import log_error, log_exception, audit_action
from .solar_config_form import build_solar_config_schema

from ..const import (
    STEP_USER,
    CONF_CONSUMPTION,
    CONF_MPPT2_ENABLED,
    CONF_PANEL_VMP,
    CONF_PANEL_IMP,
    CONF_PANEL_VOC,
    CONF_PANEL_COUNT,
    CONF_PANEL2_VMP,
    CONF_PANEL2_IMP,
    CONF_PANEL2_VOC,
    CONF_PANEL2_COUNT,
    CONF_PV_CURRENT,
    CONF_PV2_POWER,
    CONF_PV2_VOLTAGE,
    CONF_PV2_CURRENT,
    CONF_BATTERY_POWER,
    CONF_BATTERY_SOC_SENSOR,
    NONE_OPTION,
)


class SolarConfigMixin:
    """Mixin for solar panel configuration steps."""

    def _is_mppt2_requested(self, user_input: Dict[str, Any]) -> bool:
        """Return whether the submitted config should use a second MPPT input."""
        if CONF_MPPT2_ENABLED in user_input:
            return bool(user_input.get(CONF_MPPT2_ENABLED))

        return bool(
            user_input.get(CONF_PV2_POWER)
            or user_input.get(CONF_PV2_VOLTAGE)
            or user_input.get(CONF_PV2_CURRENT)
        )

    def _validate_mppt2_config(
        self, user_input: Dict[str, Any], errors: Dict[str, str]
    ) -> None:
        """Validate optional second-MPPT settings."""
        if not self._is_mppt2_requested(user_input):
            return

        if not user_input.get(CONF_PV2_VOLTAGE):
            errors[CONF_PV2_VOLTAGE] = "pv2_voltage_required"

        if not user_input.get(CONF_PV2_POWER) and not user_input.get(CONF_PV2_CURRENT):
            errors[CONF_PV2_POWER] = "pv2_power_or_current_required"

        try:
            panel_count = int(
                user_input.get(CONF_PANEL2_COUNT)
                or user_input.get(CONF_PANEL_COUNT, 1)
            )
            if panel_count <= 0:
                errors[CONF_PANEL2_COUNT] = "invalid_panel_count"
        except (ValueError, TypeError):
            errors[CONF_PANEL2_COUNT] = "invalid_panel_count"

        try:
            vmp = float(
                user_input.get(CONF_PANEL2_VMP)
                or user_input.get(CONF_PANEL_VMP, 0)
            )
            if vmp <= 0:
                errors[CONF_PANEL2_VMP] = "invalid_vmp"
        except (ValueError, TypeError):
            errors[CONF_PANEL2_VMP] = "invalid_vmp"

        try:
            imp = float(
                user_input.get(CONF_PANEL2_IMP)
                or user_input.get(CONF_PANEL_IMP, 0)
            )
            if imp <= 0:
                errors[CONF_PANEL2_IMP] = "invalid_imp"
        except (ValueError, TypeError):
            errors[CONF_PANEL2_IMP] = "invalid_imp"

        try:
            voc = float(
                user_input.get(CONF_PANEL2_VOC)
                or user_input.get(CONF_PANEL_VOC, 0)
            )
            vmp = float(
                user_input.get(CONF_PANEL2_VMP)
                or user_input.get(CONF_PANEL_VMP, 0)
            )
            if voc == vmp:
                errors[CONF_PANEL2_VOC] = "voc_equal_to_vmp"
        except (ValueError, TypeError):
            errors[CONF_PANEL2_VOC] = "invalid_values"

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

        self._validate_mppt2_config(user_input, errors)
        return errors


    def _process_solar_config_input(self, user_input: Dict[str, Any]) -> Dict[str, Any]:
        """Process and clean solar configuration input."""
        for field in [
            CONF_CONSUMPTION,
            CONF_BATTERY_POWER,
            CONF_BATTERY_SOC_SENSOR,
            CONF_PV_CURRENT,
            CONF_PV2_POWER,
            CONF_PV2_VOLTAGE,
            CONF_PV2_CURRENT,
        ]:
            if field in user_input and (not user_input[field] or user_input[field] == NONE_OPTION or user_input[field] == ""):
                user_input[field] = None

        if self._is_mppt2_requested(user_input):
            user_input[CONF_MPPT2_ENABLED] = True

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
