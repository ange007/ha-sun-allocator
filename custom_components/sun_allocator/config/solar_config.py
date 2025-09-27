"""Solar panel configuration module for Sun Allocator config flow."""
from typing import Dict, Any, Optional

import voluptuous as vol

from homeassistant.core import HomeAssistant

from ..core.logger import log_error, log_exception, audit_action
from ..config.ui_helpers import EntitySelectorBuilder
from .solar_config_form import build_solar_config_schema

from ..const import (
    STEP_USER,
    CONF_CONSUMPTION,
    CONF_VMP,
    CONF_IMP,
    CONF_VOC,
    CONF_PANEL_COUNT,
    NONE_OPTION,
)


class SolarConfigMixin:
    """Mixin for solar panel configuration steps."""

    def _get_sensor_entities(self, hass: HomeAssistant) -> Dict[str, list]:
        """Get available sensor entities categorized by type, with label/value for selector."""
        icon_map = {
            "power": "⚡",
            "voltage": "🔋",
            "consumption": "🏠",
            "battery": "🔋",
        }
        sensor_entities = [
            entity
            for entity in hass.states.async_all()
            if entity.entity_id.startswith("sensor.")
        ]

        def filter_entities(entities_list, key):
            if key == "power":
                return [e for e in entities_list if "power" in e.entity_id]
            if key == "voltage":
                return [e for e in entities_list if "voltage" in e.entity_id]
            if key == "consumption":
                return [
                    e
                    for e in entities_list
                    if "consumption" in e.entity_id or "power" in e.entity_id
                ]
            if key == "battery":
                return [
                    e
                    for e in entities_list
                    if "battery" in e.entity_id
                    or "bat" in e.entity_id
                    or "power" in e.entity_id
                ]
            return []

        builder = EntitySelectorBuilder(icon_map)
        power_sensors = builder.build(
            filter_entities(sensor_entities, "power"), none_option=False
        )
        voltage_sensors = builder.build(
            filter_entities(sensor_entities, "voltage"), none_option=False
        )
        consumption_sensors = builder.build(
            filter_entities(sensor_entities, "consumption"), none_option=False
        )
        battery_sensors = builder.build(
            filter_entities(sensor_entities, "battery"), none_option=False
        )
        consumption_sensors = (
            [{"label": "None", "value": NONE_OPTION}] + consumption_sensors
        )

        return {
            "power_sensors": power_sensors,
            "voltage_sensors": voltage_sensors,
            "consumption_sensors": consumption_sensors,
            "battery_sensors": battery_sensors,
        }

    def _validate_solar_config(self, user_input: Dict[str, Any]) -> Dict[str, str]:
        """Validate solar panel configuration."""
        errors = {}
        if user_input.get(CONF_VOC) is not None and user_input.get(CONF_VMP) is not None:
            try:
                voc = float(user_input.get(CONF_VOC))
                vmp = float(user_input.get(CONF_VMP))
                if voc == vmp:
                    errors[CONF_VOC] = "voc_equal_to_vmp"
            except (ValueError, TypeError) as exc:
                errors["base"] = "invalid_values"
                log_error(
                    "[SolarConfigMixin] Invalid Voc/Vmp: VOC=%s, VMP=%s",
                    user_input.get(CONF_VOC),
                    user_input.get(CONF_VMP),
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
            vmp = float(user_input.get(CONF_VMP, 0))
            if vmp <= 0:
                errors[CONF_VMP] = "invalid_vmp"
        except (ValueError, TypeError) as exc:
            errors[CONF_VMP] = "invalid_vmp"
            log_error("[SolarConfigMixin] Invalid Vmp: %s", user_input.get(CONF_VMP))
            log_exception("solar_config_vmp", exc)
        try:
            imp = float(user_input.get(CONF_IMP, 0))
            if imp <= 0:
                errors[CONF_IMP] = "invalid_imp"
        except (ValueError, TypeError) as exc:
            errors[CONF_IMP] = "invalid_imp"
            log_error("[SolarConfigMixin] Invalid Imp: %s", user_input.get(CONF_IMP))
            log_exception("solar_config_imp", exc)
        return errors

    def _process_solar_config_input(self, user_input: Dict[str, Any]) -> Dict[str, Any]:
        """Process and clean solar configuration input."""
        if user_input.get(CONF_CONSUMPTION) == NONE_OPTION:
            user_input[CONF_CONSUMPTION] = None

        return user_input

    def _get_solar_config_schema(
        self, sensors: Dict[str, list], defaults: Optional[Dict[str, Any]] = None
    ) -> vol.Schema:
        """Get the schema for solar panel configuration using solar_config_form.py."""
        return build_solar_config_schema(sensors, defaults)

    async def async_step_user(self, user_input=None):
        """Handle the initial step - solar panel configuration."""
        errors = {}
        sensors = self._get_sensor_entities(self.hass)

        if not sensors["power_sensors"]:
            return self.async_abort(reason="no_power_sensors")
        if not sensors["voltage_sensors"]:
            return self.async_abort(reason="no_voltage_sensors")
        if not sensors["battery_sensors"]:
            return self.async_abort(reason="no_battery_sensors")

        if user_input is not None:
            errors = self._validate_solar_config(user_input)

            if not errors:
                user_input = self._process_solar_config_input(user_input)

                self._solar_config = user_input
                audit_action("solar_config_saved", {"config": user_input})
                return await self.async_step_devices()

        schema = self._get_solar_config_schema(sensors, self._solar_config)

        return self.async_show_form(
            step_id=STEP_USER,
            data_schema=schema,
            errors=errors,
        )
