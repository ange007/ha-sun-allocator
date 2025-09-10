"""Solar config form builders for Sun Allocator."""
from voluptuous import Schema, Required, Optional
from ..const import (
    CONF_PV_POWER, CONF_PV_VOLTAGE, CONF_VMP, CONF_IMP, CONF_VOC, CONF_ISC, CONF_PANEL_COUNT, CONF_PANEL_CONFIGURATION,
    CONF_CONSUMPTION, CONF_BATTERY_POWER, NONE_OPTION, PANEL_CONFIG_SERIES, PANEL_CONFIG_PARALLEL, PANEL_CONFIG_PARALLEL_SERIES
)
from .ui_helpers import NumberSelectorBuilder, SelectSelectorBuilder

def build_solar_config_schema(sensors, defaults=None):
    if defaults is None:
        defaults = {}
    default_consumption = NONE_OPTION if defaults.get(CONF_CONSUMPTION) is None else defaults.get(CONF_CONSUMPTION)
    default_battery_power = NONE_OPTION if defaults.get(CONF_BATTERY_POWER) is None else defaults.get(CONF_BATTERY_POWER)
    panel_config_options = [
        {"label": "Серійне з'єднання", "value": PANEL_CONFIG_SERIES},
        {"label": "Паралельне з'єднання", "value": PANEL_CONFIG_PARALLEL},
        {"label": "Паралельно-серійне", "value": PANEL_CONFIG_PARALLEL_SERIES},
    ]
    return Schema({
        Required(CONF_PV_POWER, default=defaults.get(CONF_PV_POWER), description={"suggested_value": defaults.get(CONF_PV_POWER)}):
            SelectSelectorBuilder(sensors["power_sensors"]).build(),
        Required(CONF_PV_VOLTAGE, default=defaults.get(CONF_PV_VOLTAGE), description={"suggested_value": defaults.get(CONF_PV_VOLTAGE)}):
            SelectSelectorBuilder(sensors["voltage_sensors"]).build(),
        Required(CONF_VMP, default=defaults.get(CONF_VMP, 36.0), description={"suggested_value": defaults.get(CONF_VMP, 36.0)}):
            NumberSelectorBuilder(0, 100, 0.1).build(),
        Required(CONF_IMP, default=defaults.get(CONF_IMP, 8.0), description={"suggested_value": defaults.get(CONF_IMP, 8.0)}):
            NumberSelectorBuilder(0, 100, 0.01).build(),
        Optional(CONF_VOC, default=defaults.get(CONF_VOC, 44.0), description={"suggested_value": defaults.get(CONF_VOC, 44.0)}):
            NumberSelectorBuilder(0, 100, 0.1).build(),
        Optional(CONF_ISC, default=defaults.get(CONF_ISC, 8.5), description={"suggested_value": defaults.get(CONF_ISC, 8.5)}):
            NumberSelectorBuilder(0, 100, 0.01).build(),
        Required(CONF_PANEL_COUNT, default=defaults.get(CONF_PANEL_COUNT, 1), description={"suggested_value": defaults.get(CONF_PANEL_COUNT, 1)}):
            NumberSelectorBuilder(1, 100, 1).build(),
        Required(CONF_PANEL_CONFIGURATION, default=defaults.get(CONF_PANEL_CONFIGURATION, PANEL_CONFIG_SERIES), description={"suggested_value": defaults.get(CONF_PANEL_CONFIGURATION, PANEL_CONFIG_SERIES)}):
            SelectSelectorBuilder(panel_config_options).build(),
        Optional(CONF_CONSUMPTION, default=default_consumption, description={"suggested_value": default_consumption}):
            SelectSelectorBuilder(sensors["consumption_sensors"]).build(),
        Optional(CONF_BATTERY_POWER, default=default_battery_power, description={"suggested_value": default_battery_power}):
            SelectSelectorBuilder(sensors["battery_sensors"]).build(),
    })
