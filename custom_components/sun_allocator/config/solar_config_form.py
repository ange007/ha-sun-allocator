"""Solar panel configuration form schemas for Sun Allocator config flow."""

from typing import Any, Dict, Optional

from voluptuous import Schema, Required, Optional as VolOptional

from homeassistant.helpers import selector

import voluptuous as vol

from ..config.ui_helpers import (
    SelectSelectorBuilder,
    BooleanSelectorBuilder,
    float_field,
)

from ..const import (
    CONF_MPPT_COUNT,
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
    CONF_BATTERY_SOC_SENSOR,
    MPPT_MAX_COUNT,
    PANEL_CONFIG_SERIES,
    PANEL_CONFIG_PARALLEL,
    PANEL_CONFIG_PARALLEL_SERIES,
)


def _opt_entity_key(field: str, defaults: dict):
    """Build VolOptional key with default pre-fill when a saved value exists."""
    val = defaults.get(field)
    kwargs = {"description": {"suggested_value": val}}
    if val:
        kwargs["default"] = val
    return VolOptional(field, **kwargs)


def build_solar_hub_schema(defaults: Optional[Dict[str, Any]] = None) -> Schema:
    """Build schema for hub-level solar config: tracker count + shared sensors."""
    if defaults is None:
        defaults = {}

    return Schema({
        Required(
            CONF_MPPT_COUNT,
            default=str(defaults.get(CONF_MPPT_COUNT, 1)),
        ): SelectSelectorBuilder(
            options=[str(i) for i in range(1, MPPT_MAX_COUNT + 1)],
        ).build(),

        _opt_entity_key(CONF_CONSUMPTION, defaults): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                multiple=False,
                filter=[
                    {"device_class": ["energy"]},
                    {"device_class": ["power"]},
                ],
            )
        ),

        _opt_entity_key(CONF_BATTERY_POWER, defaults): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                multiple=False,
                filter=[
                    {"device_class": ["power"]},
                    {"device_class": ["battery"]},
                    {"device_class": ["bat"]},
                ],
            )
        ),

        VolOptional(
            CONF_BATTERY_POWER_REVERSED,
            default=defaults.get(CONF_BATTERY_POWER_REVERSED, False),
        ): BooleanSelectorBuilder().build(),

        _opt_entity_key(CONF_BATTERY_SOC_SENSOR, defaults): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                multiple=False,
                filter=[{"device_class": ["battery"]}],
            )
        ),
    })


def build_mppt_input_schema(defaults: Optional[Dict[str, Any]] = None) -> Schema:
    """Build schema for a single per-MPPT input: power/voltage sensors + panel params."""
    if defaults is None:
        defaults = {}

    return Schema({
        Required(
            CONF_PV_POWER,
            default=defaults.get(CONF_PV_POWER),
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                multiple=False,
                filter=[{"device_class": ["power"]}],
            )
        ),

        Required(
            CONF_PV_VOLTAGE,
            default=defaults.get(CONF_PV_VOLTAGE),
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                multiple=False,
                filter=[{"device_class": ["voltage"]}],
            )
        ),

        Required(
            CONF_PANEL_VMP,
            default=defaults.get(CONF_PANEL_VMP, 44.3),
        ): float_field(0, 100),

        Required(
            CONF_PANEL_IMP,
            default=defaults.get(CONF_PANEL_IMP, 10.05),
        ): float_field(0, 100),

        Required(
            CONF_PANEL_VOC,
            default=defaults.get(CONF_PANEL_VOC, 52.6),
        ): float_field(0, 100),

        VolOptional(
            CONF_PANEL_ISC,
            default=defaults.get(CONF_PANEL_ISC, 10.71),
        ): float_field(0, 100),

        Required(
            CONF_PANEL_COUNT,
            default=defaults.get(CONF_PANEL_COUNT, 10),
        ): vol.Coerce(int),

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
