"""Solar config form builders for Sun Allocator."""
from voluptuous import Schema, Required, Optional

from ..config.ui_helpers import (
    NumberSelectorBuilder,
    SelectSelectorBuilder,
    BooleanSelectorBuilder,
)

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
    CONF_BATTERY_POWER_REVERSED,
    NONE_OPTION,
    PANEL_CONFIG_SERIES,
    PANEL_CONFIG_PARALLEL,
    PANEL_CONFIG_PARALLEL_SERIES,
)


def build_solar_config_schema(sensors, defaults=None):
    """Builds the schema for solar panel configuration."""
    if defaults is None:
        defaults = {}

    default_consumption = (
        NONE_OPTION
        if defaults.get(CONF_CONSUMPTION) is None
        else defaults.get(CONF_CONSUMPTION)
    )
    default_battery_power = (
        NONE_OPTION
        if defaults.get(CONF_BATTERY_POWER) is None
        else defaults.get(CONF_BATTERY_POWER)
    )

    return Schema(
        {
            Required(
                CONF_PV_POWER,
                default=defaults.get(CONF_PV_POWER),
            ): SelectSelectorBuilder(sensors.get("power_sensors", [])).build(),
            Required(
                CONF_PV_VOLTAGE,
                default=defaults.get(CONF_PV_VOLTAGE),
            ): SelectSelectorBuilder(sensors.get("voltage_sensors", [])).build(),
            Optional(
                CONF_CONSUMPTION,
                default=default_consumption,
            ): SelectSelectorBuilder(
                sensors.get("consumption_sensors", [])
            ).build(),
            Required(
                CONF_BATTERY_POWER,
                default=default_battery_power,
            ): SelectSelectorBuilder(sensors.get("battery_sensors", [])).build(),
            Required(
                CONF_BATTERY_POWER_REVERSED,
                default=defaults.get(CONF_BATTERY_POWER_REVERSED, False),
            ): BooleanSelectorBuilder().build(),
            Required(
                CONF_VMP,
                default=defaults.get(CONF_VMP, 36.0),
            ): NumberSelectorBuilder(0, 100, 0.1).build(),
            Required(
                CONF_IMP,
                default=defaults.get(CONF_IMP, 8.0),
            ): NumberSelectorBuilder(0, 100, 0.01).build(),
            Optional(
                CONF_VOC,
                default=defaults.get(CONF_VOC, 44.0),
            ): NumberSelectorBuilder(0, 100, 0.1).build(),
            Optional(
                CONF_ISC,
                default=defaults.get(CONF_ISC, 8.5),
            ): NumberSelectorBuilder(0, 100, 0.01).build(),
            Required(
                CONF_PANEL_COUNT,
                default=defaults.get(CONF_PANEL_COUNT, 1),
            ): NumberSelectorBuilder(1, 100, 1).build(),
            Required(
                CONF_PANEL_CONFIGURATION,
                default=defaults.get(CONF_PANEL_CONFIGURATION, PANEL_CONFIG_SERIES),
            ): SelectSelectorBuilder(
                options=[PANEL_CONFIG_SERIES, PANEL_CONFIG_PARALLEL, PANEL_CONFIG_PARALLEL_SERIES],
                translation_key="config.step.settings.data.panel_configuration_options"
            ).build(),
        }
    )