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
        """Get available sensor entities categorized by type, with label/value for selector (через UI helpers)."""
        from ..ui_helpers import EntitySelectorBuilder
        icon_map = {"power": "⚡", "voltage": "🔋", "consumption": "🏠", "battery": "🔋"}
        sensor_entities = [e for e in hass.states.async_all() if e.entity_id.startswith("sensor.")]
        def filter_entities(entities, key):
            if key == "power":
                return [e for e in entities if "power" in e.entity_id]
            if key == "voltage":
                return [e for e in entities if "voltage" in e.entity_id]
            if key == "consumption":
                return [e for e in entities if "consumption" in e.entity_id or "power" in e.entity_id]
            if key == "battery":
                return [e for e in entities if "battery" in e.entity_id or "bat" in e.entity_id or "power" in e.entity_id]
            return []
        builder = EntitySelectorBuilder(icon_map)
        power_sensors = builder.build(filter_entities(sensor_entities, "power"), none_option=False)
        voltage_sensors = builder.build(filter_entities(sensor_entities, "voltage"), none_option=False)
        consumption_sensors = builder.build(filter_entities(sensor_entities, "consumption"), none_option=False)
        battery_sensors = builder.build(filter_entities(sensor_entities, "battery"), none_option=False)
        # Add None option
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
        """Get the schema for solar panel configuration using solar_config_form.py."""
        from .solar_config_form import build_solar_config_schema
        return build_solar_config_schema(sensors, defaults)
    
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