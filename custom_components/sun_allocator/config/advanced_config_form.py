"""Advanced config form builders for Sun Allocator."""

from voluptuous import Schema, Required

from ..config.ui_helpers import NumberSelectorBuilder, SelectSelectorBuilder, int_field

from ..const import (
    CONF_MIN_INVERTER_VOLTAGE,
    CONF_RAMP_UP_STEP,
    CONF_RAMP_DOWN_STEP,
    CONF_RAMP_DEADBAND,
    CONF_HYSTERESIS_W,
    DEFAULT_HYSTERESIS_W,
    CONF_RESERVE_BATTERY_POWER,
    CONF_INVERTER_SELF_CONSUMPTION,
    CONF_DEVICE_ALLOCATION_STRATEGY,
    STRATEGY_FILL_ONE_BY_ONE,
    STRATEGY_DISTRIBUTE_EVENLY,
    CONF_BATTERY_DISCHARGE_TOLERANCE_W,
    DEFAULT_BATTERY_DISCHARGE_TOLERANCE_W,
    CONF_PROBE_BATTERY_ASSIST_W,
    DEFAULT_PROBE_BATTERY_ASSIST_W,
    CONF_CALCULATION_METHOD,
    DEFAULT_CALCULATION_METHOD,
    CALC_METHOD_MPPT,
    CALC_METHOD_MPPT_PROBE,
    CALC_METHOD_EXPORT,
)


def build_advanced_config_schema(defaults=None):
    """Build the schema for the advanced config form."""
    if defaults is None:
        defaults = {}

    return Schema(
        {
            Required(
                CONF_CALCULATION_METHOD,
                default=defaults.get(
                    CONF_CALCULATION_METHOD, DEFAULT_CALCULATION_METHOD
                ),
            ): SelectSelectorBuilder(
                options=[
                    CALC_METHOD_MPPT,
                    CALC_METHOD_MPPT_PROBE,
                    CALC_METHOD_EXPORT,
                ],
                translation_key=CONF_CALCULATION_METHOD,
            ).build(),

            Required(
                CONF_RESERVE_BATTERY_POWER,
                default=defaults.get(CONF_RESERVE_BATTERY_POWER, 0),
            ): NumberSelectorBuilder(0, 10000, 50).build(),

            Required(
                CONF_INVERTER_SELF_CONSUMPTION,
                default=defaults.get(CONF_INVERTER_SELF_CONSUMPTION, 0),
            ): int_field(0, 500),

            Required(
                CONF_DEVICE_ALLOCATION_STRATEGY,
                default=defaults.get(CONF_DEVICE_ALLOCATION_STRATEGY, STRATEGY_FILL_ONE_BY_ONE),
            ): SelectSelectorBuilder(
                options=[
                    STRATEGY_FILL_ONE_BY_ONE,
                    STRATEGY_DISTRIBUTE_EVENLY
                ],
                translation_key=CONF_DEVICE_ALLOCATION_STRATEGY,
            ).build(),

            Required(
                CONF_MIN_INVERTER_VOLTAGE,
                default=defaults.get(CONF_MIN_INVERTER_VOLTAGE, 100.0),
            ): int_field(0, 1000),

            Required(
                CONF_RAMP_UP_STEP, default=defaults.get(CONF_RAMP_UP_STEP, 10.0)
            ): NumberSelectorBuilder(0.1, 100.0, 0.1).build(),

            Required(
                CONF_RAMP_DOWN_STEP, default=defaults.get(CONF_RAMP_DOWN_STEP, 20.0)
            ): NumberSelectorBuilder(0.1, 100.0, 0.1).build(),

            Required(
                CONF_RAMP_DEADBAND, default=defaults.get(CONF_RAMP_DEADBAND, 1.0)
            ): NumberSelectorBuilder(0.0, 10.0, 0.01).build(),

            Required(
                CONF_HYSTERESIS_W,
                default=defaults.get(CONF_HYSTERESIS_W, DEFAULT_HYSTERESIS_W),
            ): int_field(0, 5000),

            Required(
                CONF_BATTERY_DISCHARGE_TOLERANCE_W,
                default=defaults.get(
                    CONF_BATTERY_DISCHARGE_TOLERANCE_W, DEFAULT_BATTERY_DISCHARGE_TOLERANCE_W
                ),
            ): NumberSelectorBuilder(0, 500, 10).build(),

            Required(
                CONF_PROBE_BATTERY_ASSIST_W,
                default=defaults.get(
                    CONF_PROBE_BATTERY_ASSIST_W, DEFAULT_PROBE_BATTERY_ASSIST_W
                ),
            ): NumberSelectorBuilder(0, 1000, 10).build(),
        }
    )
