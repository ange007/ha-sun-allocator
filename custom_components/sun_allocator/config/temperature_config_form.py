"""Temperature config form builders for Sun Allocator."""
from voluptuous import Schema, Required
from ..const import (
    CONF_TEMPERATURE_SENSOR, CONF_TEMP_COEFFICIENT_VOC, CONF_TEMP_COEFFICIENT_PMAX, NONE_OPTION, DEFAULT_VOC_COEFFICIENT, DEFAULT_PMAX_COEFFICIENT
)
from .ui_helpers import NumberSelectorBuilder, SelectSelectorBuilder

def build_temperature_config_schema(temperature_sensors, defaults=None):
    if defaults is None:
        defaults = {}
    default_temp_sensor = NONE_OPTION if defaults.get(CONF_TEMPERATURE_SENSOR) is None else defaults.get(CONF_TEMPERATURE_SENSOR, NONE_OPTION)
    return Schema({
        Required(CONF_TEMPERATURE_SENSOR, default=default_temp_sensor, description={"suggested_value": default_temp_sensor}):
            SelectSelectorBuilder(temperature_sensors).build(),
        Required(CONF_TEMP_COEFFICIENT_VOC, default=defaults.get(CONF_TEMP_COEFFICIENT_VOC, DEFAULT_VOC_COEFFICIENT), description={"suggested_value": defaults.get(CONF_TEMP_COEFFICIENT_VOC, DEFAULT_VOC_COEFFICIENT)}):
            NumberSelectorBuilder(-1.0, 0.0, 0.01).build(),
        Required(CONF_TEMP_COEFFICIENT_PMAX, default=defaults.get(CONF_TEMP_COEFFICIENT_PMAX, DEFAULT_PMAX_COEFFICIENT), description={"suggested_value": defaults.get(CONF_TEMP_COEFFICIENT_PMAX, DEFAULT_PMAX_COEFFICIENT)}):
            NumberSelectorBuilder(-1.0, 0.0, 0.01).build(),
    })
