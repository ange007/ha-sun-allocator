"""Solar panel configuration form schema for Sun Allocator config flow."""

from voluptuous import Schema, Required, Optional

from homeassistant.helpers import selector

from ..config.ui_helpers import (
    NumberSelectorBuilder,
    SelectSelectorBuilder,
    BooleanSelectorBuilder,
)

from ..const import (
    CONF_PV_POWER,
    CONF_PV_VOLTAGE,
    CONF_PANEL_VMP,
    CONF_PANEL_IMP,
    CONF_PANEL_VOC,
    CONF_PANEL_ISC,
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


def build_solar_config_schema(defaults=None):
    """Build schema for solar panel configuration."""
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

    return Schema({
        Required(
            CONF_PV_POWER,
            default=defaults.get(CONF_PV_POWER, "")
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                multiple=False,
                exclude_entities=[],
                filter=[{"device_class": ["power"]}],
            )
        ),

        Required(
            CONF_PV_VOLTAGE,
            default=defaults.get(CONF_PV_VOLTAGE, "")
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                multiple=False,
                exclude_entities=[],
                filter=[{"device_class": ["voltage"]}],
            )
        ),

        Optional(
            CONF_CONSUMPTION,
            default=default_consumption,
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                multiple=False,
                filter=[{"device_class": ["power"]}],
            )
        ),

        Optional(
            CONF_BATTERY_POWER,
            default=default_battery_power,
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                multiple=False,
                filter=[{"device_class": ["power"]}],
            )
        ),

        Optional(
            CONF_BATTERY_POWER_REVERSED,
            default=defaults.get(CONF_BATTERY_POWER_REVERSED, False),
        ): BooleanSelectorBuilder().build(),

        Required(
            CONF_PANEL_VMP,
            default=defaults.get(CONF_PANEL_VMP, 36.0),
        ): NumberSelectorBuilder(0, 100, 0.1).build(),

        Required(
            CONF_PANEL_IMP,
            default=defaults.get(CONF_PANEL_IMP, 10.0),
        ): NumberSelectorBuilder(0, 100, 0.01).build(),

        Required(
            CONF_PANEL_VOC,
            default=defaults.get(CONF_PANEL_VOC, 36.0),
        ): NumberSelectorBuilder(0, 100, 0.1).build(),

        Optional(
            CONF_PANEL_ISC,
            default=defaults.get(CONF_PANEL_ISC, 10.8),
        ): NumberSelectorBuilder(0, 100, 0.01).build(),

        Required(
            CONF_PANEL_COUNT,
            default=defaults.get(CONF_PANEL_COUNT, 1),
        ): NumberSelectorBuilder(1, 100, 1).build(),

        Required(
            CONF_PANEL_CONFIGURATION,
            default=defaults.get(CONF_PANEL_CONFIGURATION, PANEL_CONFIG_SERIES),
        ): SelectSelectorBuilder(
            options=[
                PANEL_CONFIG_SERIES,
                PANEL_CONFIG_PARALLEL,
                PANEL_CONFIG_PARALLEL_SERIES,
            ],
            translation_key=CONF_PANEL_CONFIGURATION,
        ).build(),
    })

