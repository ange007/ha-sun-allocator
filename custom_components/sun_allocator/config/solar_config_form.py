"""Solar panel configuration form schemas for Sun Allocator config flow."""

from typing import Any, Dict, Optional

from voluptuous import Schema, Required, Optional as VolOptional

from homeassistant.helpers import selector

import voluptuous as vol

from ..config.ui_helpers import (
    SelectSelectorBuilder,
    BooleanSelectorBuilder,
    NumberSelectorBuilder,
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
    CONF_BATTERY_SHARING_SOC,
    CONF_BATTERY_PROTECTION_SOC,
    CONF_RESERVE_BATTERY_POWER,
    CONF_BATTERY_DISCHARGE_TOLERANCE_W,
    DEFAULT_BATTERY_DISCHARGE_TOLERANCE_W,
    CONF_GRID_VOLTAGE_SENSOR,
    CONF_GRID_MIN_VOLTAGE,
    DEFAULT_GRID_MIN_VOLTAGE,
    CONF_PV_FORECAST_SENSOR,
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

        # Optional external PV-production forecast (W) — diagnostic metric only.
        # Combine multi-slope forecasts into one entity via a helper.
        _opt_entity_key(CONF_PV_FORECAST_SENSOR, defaults): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                multiple=False,
                filter=[{"device_class": ["power"]}],
            )
        ),
    })


def build_battery_schema(defaults: Optional[Dict[str, Any]] = None) -> Schema:
    """Build the schema for the dedicated Battery page.

    Groups every battery knob in one place with the distinct roles spelled out:
      * reserve_battery_power — watts always held back for charging;
      * battery_sharing_soc   — SOC above which surplus is released (below it the
        battery keeps absolute charge priority);
      * battery_protection_soc — absolute hard floor: below it every device is forced
        off (any charge direction), and the hard minimum for a per-device stop SOC.
    """
    if defaults is None:
        defaults = {}

    return Schema({
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

        # Watts always reserved for charging (kept from the surplus pool).
        VolOptional(
            CONF_RESERVE_BATTERY_POWER,
            default=defaults.get(CONF_RESERVE_BATTERY_POWER, 0),
        ): NumberSelectorBuilder(0, 10000, 50).build(),

        # Share surplus above this SOC: below it the battery takes absolute
        # charge priority (reserve forced to unlimited). 0 = disabled.
        VolOptional(
            CONF_BATTERY_SHARING_SOC,
            default=defaults.get(CONF_BATTERY_SHARING_SOC, 0),
        ): NumberSelectorBuilder(0, 100, 1, unit="%").build(),

        # Absolute battery-protection floor: SOC below this forces EVERY device off
        # (any charge direction) and is the hard minimum for per-device stop SOC.
        # 0 = disabled.
        VolOptional(
            CONF_BATTERY_PROTECTION_SOC,
            default=defaults.get(CONF_BATTERY_PROTECTION_SOC, 0),
        ): NumberSelectorBuilder(0, 100, 1, unit="%").build(),

        # Max battery discharge (W) treated as neutral jitter (not a real discharge)
        # for excess + the discharge-side stop floor.
        VolOptional(
            CONF_BATTERY_DISCHARGE_TOLERANCE_W,
            default=defaults.get(
                CONF_BATTERY_DISCHARGE_TOLERANCE_W, DEFAULT_BATTERY_DISCHARGE_TOLERANCE_W
            ),
        ): NumberSelectorBuilder(0, 500, 10).build(),

        # Optional grid-voltage sensor: when it reads at/above the min voltage below, a
        # MANUALLY-forced device ignores the battery-protection floor (the grid covers
        # the load). Leave empty to disable. Auto-control is never affected.
        _opt_entity_key(CONF_GRID_VOLTAGE_SENSOR, defaults): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                multiple=False,
                filter=[{"device_class": ["voltage"]}],
            )
        ),

        VolOptional(
            CONF_GRID_MIN_VOLTAGE,
            default=defaults.get(CONF_GRID_MIN_VOLTAGE, DEFAULT_GRID_MIN_VOLTAGE),
        ): NumberSelectorBuilder(0, 300, 5, unit="V").build(),
    })


def build_mppt_input_schema(defaults: Optional[Dict[str, Any]] = None) -> Schema:
    """Build schema for a single per-MPPT input: power/voltage sensors + panel params."""
    if defaults is None:
        defaults = {}

    # Panel spec fields carry NO placeholder default: they must come from the user's own
    # datasheet — a plausible-looking prefilled value (e.g. a random 445 W panel) that a
    # novice submits unchanged silently drives a wrong I-V / Pmax / excess model. On EDIT
    # the previously-saved value prefills (from ``defaults``); on ADD the field is empty
    # and required. (Sensor pickers already work this way.)
    def _panel_required(key):
        val = defaults.get(key)
        return Required(key, default=val) if val is not None else Required(key)

    def _panel_optional(key):
        val = defaults.get(key)
        return VolOptional(key, default=val) if val is not None else VolOptional(key)

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

        _panel_required(CONF_PANEL_VMP): float_field(0, 100),

        _panel_required(CONF_PANEL_IMP): float_field(0, 100),

        _panel_required(CONF_PANEL_VOC): float_field(0, 100),

        _panel_optional(CONF_PANEL_ISC): float_field(0, 100),

        _panel_required(CONF_PANEL_COUNT): vol.Coerce(int),

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
