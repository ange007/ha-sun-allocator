"""Solar config form builders for Sun Allocator."""
from voluptuous import Schema, Required, Optional

from homeassistant.helpers.selector import selector
    
from ..utils.ui_helpers import NumberSelectorBuilder, SelectSelectorBuilder

from ..const import (
    CONF_PV_POWER, 
    CONF_PV_VOLTAGE, 
    CONF_VMP, 
    CONF_IMP,
    CONF_VOC, 
    CONF_ISC, 
    CONF_PANEL_COUNT, 
    CONF_PANEL_CONFIGURATION,
    CONF_CONSUMPTION, 
    CONF_BATTERY_POWER, 
    NONE_OPTION, 
    PANEL_CONFIG_SERIES, 
    PANEL_CONFIG_PARALLEL, 
    PANEL_CONFIG_PARALLEL_SERIES,
)


def build_solar_config_schema(sensors, defaults=None):
    if defaults is None:
        defaults = {}

    default_consumption = NONE_OPTION if defaults.get(CONF_CONSUMPTION) is None else defaults.get(CONF_CONSUMPTION)
    default_battery_power = NONE_OPTION if defaults.get(CONF_BATTERY_POWER) is None else defaults.get(CONF_BATTERY_POWER)
    panel_config_options = [
        {"label": "config.step.settings.data.panel_configuration.options.series", "value": PANEL_CONFIG_SERIES},
        {"label": "config.step.settings.data.panel_configuration.options.parallel", "value": PANEL_CONFIG_PARALLEL},
        {"label": "config.step.settings.data.panel_configuration.options.parallel-series", "value": PANEL_CONFIG_PARALLEL_SERIES},
    ]

    return Schema({
        Required(
            CONF_PV_POWER,
            default=defaults.get(CONF_PV_POWER),
            description={
                "suggested_value": defaults.get(CONF_PV_POWER),
                "label": "config.step.settings.data.pv_power"
            },
        ): SelectSelectorBuilder(sensors.get("power_sensors", [])).build(),
        Required(
            CONF_PV_VOLTAGE,
            default=defaults.get(CONF_PV_VOLTAGE),
            description={
                "suggested_value": defaults.get(CONF_PV_VOLTAGE),
                "label": "config.step.settings.data.pv_voltage"
            },
        ): SelectSelectorBuilder(sensors.get("voltage_sensors", [])).build(),
        Required(
            CONF_VMP,
            default=defaults.get(CONF_VMP, 36.0),
            description={
                "suggested_value": defaults.get(CONF_VMP, 36.0),
                "label": "config.step.settings.data.vmp"
            },
        ): NumberSelectorBuilder(0, 100, 0.1).build(),
        Required(
            CONF_IMP,
            default=defaults.get(CONF_IMP, 8.0),
            description={
                "suggested_value": defaults.get(CONF_IMP, 8.0),
                "label": "config.step.settings.data.imp"
            },
        ): NumberSelectorBuilder(0, 100, 0.01).build(),
        Optional(
            CONF_VOC,
            default=defaults.get(CONF_VOC, 44.0),
            description={
                "suggested_value": defaults.get(CONF_VOC, 44.0),
                "label": "config.step.settings.data.voc"
            },
        ): NumberSelectorBuilder(0, 100, 0.1).build(),
        Optional(
            CONF_ISC,
            default=defaults.get(CONF_ISC, 8.5),
            description={
                "suggested_value": defaults.get(CONF_ISC, 8.5),
                "label": "config.step.settings.data.isc"
            },
        ): NumberSelectorBuilder(0, 100, 0.01).build(),
        Required(
            CONF_PANEL_COUNT,
            default=defaults.get(CONF_PANEL_COUNT, 1),
            description={
                "suggested_value": defaults.get(CONF_PANEL_COUNT, 1),
                "label": "config.step.settings.data.panel_count"
            },
        ): NumberSelectorBuilder(1, 100, 1).build(),
        Required(
            CONF_PANEL_CONFIGURATION,
            default=defaults.get(CONF_PANEL_CONFIGURATION, PANEL_CONFIG_SERIES),
            description={
                "suggested_value": defaults.get(CONF_PANEL_CONFIGURATION, PANEL_CONFIG_SERIES),
                "label": "config.step.settings.data.panel_configuration.name"
            },
        ): SelectSelectorBuilder(panel_config_options).build(),
        Optional(
            CONF_CONSUMPTION,
            default=default_consumption,
            description={
                "suggested_value": default_consumption,
                "label": "config.step.settings.data.consumption"
            },
        ): SelectSelectorBuilder(sensors.get("consumption_sensors", [])).build(),
        Required(
            CONF_BATTERY_POWER,
            default=default_battery_power,
            description={
                "suggested_value": default_battery_power,
                "label": "config.step.settings.data.battery_power"
            },
        ): SelectSelectorBuilder(sensors.get("battery_sensors", [])).build(),
    })