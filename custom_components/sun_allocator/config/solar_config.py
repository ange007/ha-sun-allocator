"""Solar panel configuration module for Sun Allocator config flow."""

from typing import Dict, Any, Optional

import voluptuous as vol

from ..core.logger import log_error, log_exception
from .solar_config_form import build_solar_hub_schema, build_mppt_input_schema

from ..const import (
    CONF_CONSUMPTION,
    CONF_PANEL_VMP,
    CONF_PANEL_IMP,
    CONF_PANEL_VOC,
    CONF_PANEL_COUNT,
    CONF_BATTERY_POWER,
    CONF_BATTERY_SOC_SENSOR,
    NONE_OPTION,
)


# pylint: disable=too-few-public-methods
class SolarConfigMixin:
    """Mixin for solar panel configuration validation and processing.

    The actual flow steps live in ``SunAllocatorConfigFlow`` and
    ``SunAllocatorOptionsFlowHandler`` (config/__init__.py).
    """

    def _validate_panel_only(self, user_input: Dict[str, Any]) -> Dict[str, str]:
        """Validate per-MPPT panel parameters.

        Used by the mppt_input step. Does NOT validate consumption / battery
        sensors — those are validated at the hub-level step.
        """
        errors: Dict[str, str] = {}

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
            vmp_val = float(user_input.get(CONF_PANEL_VMP, 0))
            if vmp_val <= 0:
                errors[CONF_PANEL_VMP] = "invalid_vmp"
        except (ValueError, TypeError) as exc:
            errors[CONF_PANEL_VMP] = "invalid_vmp"
            log_error(
                "[SolarConfigMixin] Invalid Vmp: %s",
                user_input.get(CONF_PANEL_VMP),
            )
            log_exception("solar_config_vmp", exc)

        try:
            imp_val = float(user_input.get(CONF_PANEL_IMP, 0))
            if imp_val <= 0:
                errors[CONF_PANEL_IMP] = "invalid_imp"
        except (ValueError, TypeError) as exc:
            errors[CONF_PANEL_IMP] = "invalid_imp"
            log_error(
                "[SolarConfigMixin] Invalid Imp: %s",
                user_input.get(CONF_PANEL_IMP),
            )
            log_exception("solar_config_imp", exc)

        return errors

    def _process_hub_config_input(
        self, user_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process hub-level config input (consumption / battery sensors).

        Replaces NONE_OPTION / empty string with None for optional sensor fields.
        """
        for field in [CONF_CONSUMPTION, CONF_BATTERY_POWER, CONF_BATTERY_SOC_SENSOR]:
            if field in user_input and (
                not user_input[field]
                or user_input[field] == NONE_OPTION
                or user_input[field] == ""
            ):
                user_input[field] = None

        return user_input

    def _get_solar_hub_schema(
        self, defaults: Optional[Dict[str, Any]] = None
    ) -> vol.Schema:
        """Get the schema for the hub-level solar form."""
        return build_solar_hub_schema(defaults)

    def _get_mppt_input_schema(
        self, defaults: Optional[Dict[str, Any]] = None
    ) -> vol.Schema:
        """Get the schema for a single per-MPPT input form."""
        return build_mppt_input_schema(defaults)
