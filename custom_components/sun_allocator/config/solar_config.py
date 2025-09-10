"""Solar panel configuration module for Sun Allocator config flow."""
import voluptuous as vol
from homeassistant.core import HomeAssistant
from typing import Dict, Any, Optional

from ..const import (
    STEP_USER,
    CONF_PV_POWER,
    CONF_PV_VOLTAGE,
    CONF_CONSUMPTION,
    CONF_BATTERY_POWER,
    CONF_VMP,
    CONF_IMP,
    CONF_VOC,
    CONF_ISC,
    CONF_PANEL_COUNT,
    CONF_PANEL_CONFIGURATION,
    PANEL_CONFIG_SERIES,
    PANEL_CONFIG_PARALLEL,
    PANEL_CONFIG_PARALLEL_SERIES,
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
        def make_label(e, icon):
            friendly = e.attributes.get("friendly_name", "")
            return f"{icon} {friendly}" if friendly else f"{icon} {e.entity_id}"

        sensor_entities = [e for e in hass.states.async_all() if e.entity_id.startswith("sensor.")]
        power_sensors = [
            {"label": make_label(e, icon_map["power"]), "value": e.entity_id}
            for e in sensor_entities if "power" in e.entity_id
        ]
        voltage_sensors = [
            {"label": make_label(e, icon_map["voltage"]), "value": e.entity_id}
            for e in sensor_entities if "voltage" in e.entity_id
        ]
        consumption_sensors = [
            {"label": make_label(e, icon_map["consumption"]), "value": e.entity_id}
            for e in sensor_entities if "consumption" in e.entity_id or "power" in e.entity_id
        ]
        battery_sensors = [
            {"label": make_label(e, icon_map["battery"]), "value": e.entity_id}
            for e in sensor_entities if "battery" in e.entity_id or "bat" in e.entity_id or "power" in e.entity_id
        ]
        # Add a "None" option
        consumption_sensors = [{"label": "None", "value": NONE_OPTION}] + consumption_sensors
        battery_sensors = [{"label": "None", "value": NONE_OPTION}] + battery_sensors
        return {
            "power_sensors": power_sensors,
            "voltage_sensors": voltage_sensors,
            "consumption_sensors": consumption_sensors,
            "battery_sensors": battery_sensors
        }
    
    def _validate_solar_config(self, user_input: Dict[str, Any]) -> Dict[str, str]:
        """Validate solar panel configuration."""
        errors = {}
        
        # Validate that Voc is not equal to Vmp
        if user_input.get(CONF_VOC) is not None and user_input.get(CONF_VMP) is not None:
            try:
                voc = float(user_input.get(CONF_VOC))
                vmp = float(user_input.get(CONF_VMP))
                if voc == vmp:
                    errors[CONF_VOC] = "voc_equal_to_vmp"
            except (ValueError, TypeError):
                errors["base"] = "invalid_values"
        
        # Validate panel count
        try:
            panel_count = int(user_input.get(CONF_PANEL_COUNT, 1))
            if panel_count <= 0:
                errors[CONF_PANEL_COUNT] = "invalid_panel_count"
        except (ValueError, TypeError):
            errors[CONF_PANEL_COUNT] = "invalid_panel_count"
        
        # Validate Vmp and Imp
        try:
            vmp = float(user_input.get(CONF_VMP, 0))
            if vmp <= 0:
                errors[CONF_VMP] = "invalid_vmp"
        except (ValueError, TypeError):
            errors[CONF_VMP] = "invalid_vmp"
            
        try:
            imp = float(user_input.get(CONF_IMP, 0))
            if imp <= 0:
                errors[CONF_IMP] = "invalid_imp"
        except (ValueError, TypeError):
            errors[CONF_IMP] = "invalid_imp"
        
        return errors
    
    def _process_solar_config_input(self, user_input: Dict[str, Any]) -> Dict[str, Any]:
        """Process and clean solar configuration input."""
        # Convert "None" string to actual None value
        if user_input.get(CONF_CONSUMPTION) == NONE_OPTION:
            user_input[CONF_CONSUMPTION] = None
        
        if user_input.get(CONF_BATTERY_POWER) == NONE_OPTION:
            user_input[CONF_BATTERY_POWER] = None
        
        return user_input
    
    def _get_solar_config_schema(self, sensors: Dict[str, list], defaults: Optional[Dict[str, Any]] = None) -> vol.Schema:
        """Get the schema for solar panel configuration using selectors."""
        from homeassistant.helpers.selector import selector
        if defaults is None:
            defaults = {}
        default_consumption = NONE_OPTION if defaults.get(CONF_CONSUMPTION) is None else defaults.get(CONF_CONSUMPTION)
        default_battery_power = NONE_OPTION if defaults.get(CONF_BATTERY_POWER) is None else defaults.get(CONF_BATTERY_POWER)
        panel_config_options = [
            {"label": "Серійне з'єднання", "value": PANEL_CONFIG_SERIES},
            {"label": "Паралельне з'єднання", "value": PANEL_CONFIG_PARALLEL},
            {"label": "Паралельно-серійне", "value": PANEL_CONFIG_PARALLEL_SERIES},
        ]
        return vol.Schema({
            vol.Required(CONF_PV_POWER, default=defaults.get(CONF_PV_POWER), description={"suggested_value": defaults.get(CONF_PV_POWER)}): selector({"select": {"options": sensors["power_sensors"], "mode": "dropdown"}}),
            vol.Required(CONF_PV_VOLTAGE, default=defaults.get(CONF_PV_VOLTAGE), description={"suggested_value": defaults.get(CONF_PV_VOLTAGE)}): selector({"select": {"options": sensors["voltage_sensors"], "mode": "dropdown"}}),
            vol.Required(CONF_VMP, default=defaults.get(CONF_VMP, 36.0), description={"suggested_value": defaults.get(CONF_VMP, 36.0)}): selector({"number": {"min": 0, "max": 100, "step": 0.1, "mode": "box"}}),
            vol.Required(CONF_IMP, default=defaults.get(CONF_IMP, 8.0), description={"suggested_value": defaults.get(CONF_IMP, 8.0)}): selector({"number": {"min": 0, "max": 100, "step": 0.01, "mode": "box"}}),
            vol.Optional(CONF_VOC, default=defaults.get(CONF_VOC, 44.0), description={"suggested_value": defaults.get(CONF_VOC, 44.0)}): selector({"number": {"min": 0, "max": 100, "step": 0.1, "mode": "box"}}),
            vol.Optional(CONF_ISC, default=defaults.get(CONF_ISC, 8.5), description={"suggested_value": defaults.get(CONF_ISC, 8.5)}): selector({"number": {"min": 0, "max": 100, "step": 0.01, "mode": "box"}}),
            vol.Required(CONF_PANEL_COUNT, default=defaults.get(CONF_PANEL_COUNT, 1), description={"suggested_value": defaults.get(CONF_PANEL_COUNT, 1)}): selector({"number": {"min": 1, "max": 100, "step": 1, "mode": "box"}}),
            vol.Required(CONF_PANEL_CONFIGURATION, default=defaults.get(CONF_PANEL_CONFIGURATION, PANEL_CONFIG_SERIES), description={"suggested_value": defaults.get(CONF_PANEL_CONFIGURATION, PANEL_CONFIG_SERIES)}): selector({"select": {"options": panel_config_options, "mode": "dropdown"}}),
            vol.Optional(CONF_CONSUMPTION, default=default_consumption, description={"suggested_value": default_consumption}): selector({"select": {"options": sensors["consumption_sensors"], "mode": "dropdown"}}),
            vol.Optional(CONF_BATTERY_POWER, default=default_battery_power, description={"suggested_value": default_battery_power}): selector({"select": {"options": sensors["battery_sensors"], "mode": "dropdown"}}),
        })
    
    async def async_step_user(self, user_input=None):
        """Handle the initial step - solar panel configuration."""
        errors = {}
        sensors = self._get_sensor_entities(self.hass)

        if user_input is not None:
            # Validate input
            errors = self._validate_solar_config(user_input)
            
            if not errors:
                # Process input
                user_input = self._process_solar_config_input(user_input)
                
                # Store solar panel configuration
                self._solar_config = user_input
                
                # Proceed to device configuration
                return await self.async_step_devices()

        # Create schema with current values as defaults
        schema = self._get_solar_config_schema(sensors, self._solar_config)
        
        return self.async_show_form(
            step_id=STEP_USER,
            data_schema=schema,
            errors=errors,
        )