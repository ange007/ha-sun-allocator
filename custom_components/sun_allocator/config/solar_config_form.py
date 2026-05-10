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
    CONF_PV_CURRENT,
    CONF_MPPT2_ENABLED,
    CONF_PV2_POWER,
    CONF_PV2_VOLTAGE,
    CONF_PV2_CURRENT,
    CONF_PANEL_VMP,
    CONF_PANEL_IMP,
    CONF_PANEL_VOC,
    CONF_PANEL_ISC,
    CONF_PANEL_COUNT,
    CONF_PANEL_CONFIGURATION,
    CONF_PANEL2_VMP,
    CONF_PANEL2_IMP,
    CONF_PANEL2_VOC,
    CONF_PANEL2_ISC,
    CONF_PANEL2_COUNT,
    CONF_PANEL2_CONFIGURATION,
    CONF_CONSUMPTION,
    CONF_BATTERY_POWER,
    CONF_BATTERY_SOC_SENSOR,
    CONF_BATTERY_POWER_REVERSED,
    PANEL_CONFIG_SERIES,
    PANEL_CONFIG_PARALLEL,
    PANEL_CONFIG_PARALLEL_SERIES,
)


def build_solar_config_schema(defaults=None):
    """Build schema for solar panel configuration."""
    if defaults is None:
        defaults = {}

    return Schema({
        Required(
            CONF_PV_POWER,
            default=defaults.get(CONF_PV_POWER)
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
            default=defaults.get(CONF_PV_VOLTAGE)
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                multiple=False,
                exclude_entities=[],
                filter=[{"device_class": ["voltage"]}],
            )
        ),

        Optional(
            CONF_PV_CURRENT,
            description={"suggested_value": defaults.get(CONF_PV_CURRENT)},
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                multiple=False,
                exclude_entities=[],
                filter=[{"device_class": ["current"]}],
            )
        ),

        Optional(
            CONF_MPPT2_ENABLED,
            default=defaults.get(CONF_MPPT2_ENABLED, False),
        ): BooleanSelectorBuilder().build(),

        Optional(
            CONF_PV2_POWER,
            description={"suggested_value": defaults.get(CONF_PV2_POWER)},
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                multiple=False,
                exclude_entities=[],
                filter=[{"device_class": ["power"]}],
            )
        ),

        Optional(
            CONF_PV2_VOLTAGE,
            description={"suggested_value": defaults.get(CONF_PV2_VOLTAGE)},
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                multiple=False,
                exclude_entities=[],
                filter=[{"device_class": ["voltage"]}],
            )
        ),

        Optional(
            CONF_PV2_CURRENT,
            description={"suggested_value": defaults.get(CONF_PV2_CURRENT)},
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                multiple=False,
                exclude_entities=[],
                filter=[{"device_class": ["current"]}],
            )
        ),

        Optional(
            CONF_CONSUMPTION,
            description={"suggested_value": defaults.get(CONF_CONSUMPTION)},
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                multiple=False,
                filter=[
                    {"device_class": ["energy"]},
                    {"device_class": ["power"]}
                ],
            )
        ),

        Optional(
            CONF_BATTERY_POWER,
            description={"suggested_value": defaults.get(CONF_BATTERY_POWER)},
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                multiple=False,
                filter=[
                    {"device_class": ["power"]},
                    {"device_class": ["battery"]},
                    {"device_class": ["bat"]}
                ],
            )
        ),

        Optional(
            CONF_BATTERY_SOC_SENSOR,
            description={"suggested_value": defaults.get(CONF_BATTERY_SOC_SENSOR)},
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                multiple=False,
                filter=[{"device_class": ["battery"]}],
            )
        ),

        Optional(
            CONF_BATTERY_POWER_REVERSED,
            default=defaults.get(CONF_BATTERY_POWER_REVERSED, False),
        ): BooleanSelectorBuilder().build(),

        Required(
            CONF_PANEL_VMP,
            default=defaults.get(CONF_PANEL_VMP, 44.3),
        ): NumberSelectorBuilder(0, 100, 0.1).build(),

        Required(
            CONF_PANEL_IMP,
            default=defaults.get(CONF_PANEL_IMP, 10.05),
        ): NumberSelectorBuilder(0, 100, 0.01).build(),

        Required(
            CONF_PANEL_VOC,
            default=defaults.get(CONF_PANEL_VOC, 52.6),
        ): NumberSelectorBuilder(0, 100, 0.1).build(),

        Optional(
            CONF_PANEL_ISC,
            default=defaults.get(CONF_PANEL_ISC, 10.71),
        ): NumberSelectorBuilder(0, 100, 0.01).build(),

        Required(
            CONF_PANEL_COUNT,
            default=defaults.get(CONF_PANEL_COUNT, 10),
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

        Optional(
            CONF_PANEL2_VMP,
            default=defaults.get(CONF_PANEL2_VMP, defaults.get(CONF_PANEL_VMP, 44.3)),
        ): NumberSelectorBuilder(0, 1000, 0.1).build(),

        Optional(
            CONF_PANEL2_IMP,
            default=defaults.get(CONF_PANEL2_IMP, defaults.get(CONF_PANEL_IMP, 10.05)),
        ): NumberSelectorBuilder(0, 1000, 0.01).build(),

        Optional(
            CONF_PANEL2_VOC,
            default=defaults.get(CONF_PANEL2_VOC, defaults.get(CONF_PANEL_VOC, 52.6)),
        ): NumberSelectorBuilder(0, 1000, 0.1).build(),

        Optional(
            CONF_PANEL2_ISC,
            default=defaults.get(CONF_PANEL2_ISC, defaults.get(CONF_PANEL_ISC, 10.71)),
        ): NumberSelectorBuilder(0, 1000, 0.01).build(),

        Optional(
            CONF_PANEL2_COUNT,
            default=defaults.get(CONF_PANEL2_COUNT, defaults.get(CONF_PANEL_COUNT, 10)),
        ): NumberSelectorBuilder(1, 100, 1).build(),

        Optional(
            CONF_PANEL2_CONFIGURATION,
            default=defaults.get(
                CONF_PANEL2_CONFIGURATION,
                defaults.get(CONF_PANEL_CONFIGURATION, PANEL_CONFIG_SERIES),
            ),
        ): SelectSelectorBuilder(
            options=[
                PANEL_CONFIG_SERIES,
                PANEL_CONFIG_PARALLEL,
                PANEL_CONFIG_PARALLEL_SERIES,
            ],
            translation_key=CONF_PANEL_CONFIGURATION,
        ).build(),
    })

