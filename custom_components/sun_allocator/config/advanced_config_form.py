"""Advanced config form builders for Sun Allocator."""
from voluptuous import Schema, Required

from ..utils.ui_helpers import NumberSelectorBuilder, BooleanSelectorBuilder

from ..const import (
    CONF_CURVE_FACTOR_K, 
    CONF_EFFICIENCY_CORRECTION_FACTOR, 
    CONF_MIN_INVERTER_VOLTAGE, 
    CONF_RAMP_UP_STEP, 
    CONF_RAMP_DOWN_STEP,
    CONF_RAMP_DEADBAND, 
    CONF_DEFAULT_MIN_START_W, 
    CONF_HYSTERESIS_W, 
    CONF_BATTERY_POWER_REVERSED, 
    DEFAULT_MIN_START_W, 
    DEFAULT_HYSTERESIS_W,
)


def build_advanced_config_schema(defaults=None):
    if defaults is None:
        defaults = {}
    return Schema({
        Required(
            CONF_CURVE_FACTOR_K,
            default=defaults.get(CONF_CURVE_FACTOR_K, 0.2),
            description={
                "suggested_value": defaults.get(CONF_CURVE_FACTOR_K, 0.2),
                "label": "config.step.advanced_settings.data.curve_factor_k"
            }
        ): NumberSelectorBuilder(0.1, 0.5, 0.01).build(),
        Required(
            CONF_EFFICIENCY_CORRECTION_FACTOR,
            default=defaults.get(CONF_EFFICIENCY_CORRECTION_FACTOR, 1.05),
            description={
                "suggested_value": defaults.get(CONF_EFFICIENCY_CORRECTION_FACTOR, 1.05),
                "label": "config.step.advanced_settings.data.efficiency_correction_factor"
            }
        ): NumberSelectorBuilder(1.0, 1.2, 0.01).build(),
        Required(
            CONF_MIN_INVERTER_VOLTAGE,
            default=defaults.get(CONF_MIN_INVERTER_VOLTAGE, 100.0),
            description={
                "suggested_value": defaults.get(CONF_MIN_INVERTER_VOLTAGE, 100.0),
                "label": "config.step.advanced_settings.data.min_inverter_voltage"
            }
        ): NumberSelectorBuilder(0, 1000, 1).build(),
        Required(
            CONF_RAMP_UP_STEP,
            default=defaults.get(CONF_RAMP_UP_STEP, 10.0),
            description={
                "suggested_value": defaults.get(CONF_RAMP_UP_STEP, 10.0),
                "label": "config.step.advanced_settings.data.ramp_up_step"
            }
        ): NumberSelectorBuilder(0.1, 100.0, 0.1).build(),
        Required(
            CONF_RAMP_DOWN_STEP,
            default=defaults.get(CONF_RAMP_DOWN_STEP, 20.0),
            description={
                "suggested_value": defaults.get(CONF_RAMP_DOWN_STEP, 20.0),
                "label": "config.step.advanced_settings.data.ramp_down_step"
            }
        ): NumberSelectorBuilder(0.1, 100.0, 0.1).build(),
        Required(
            CONF_RAMP_DEADBAND,
            default=defaults.get(CONF_RAMP_DEADBAND, 1.0),
            description={
                "suggested_value": defaults.get(CONF_RAMP_DEADBAND, 1.0),
                "label": "config.step.advanced_settings.data.ramp_deadband"
            }
        ): NumberSelectorBuilder(0.0, 10.0, 0.01).build(),
        Required(
            CONF_DEFAULT_MIN_START_W,
            default=defaults.get(CONF_DEFAULT_MIN_START_W, DEFAULT_MIN_START_W),
            description={
                "suggested_value": defaults.get(CONF_DEFAULT_MIN_START_W, DEFAULT_MIN_START_W),
                "label": "config.step.advanced_settings.data.default_min_start_w"
            }
        ): NumberSelectorBuilder(0, 5000, 1).build(),
        Required(
            CONF_HYSTERESIS_W,
            default=defaults.get(CONF_HYSTERESIS_W, DEFAULT_HYSTERESIS_W),
            description={
                "suggested_value": defaults.get(CONF_HYSTERESIS_W, DEFAULT_HYSTERESIS_W),
                "label": "config.step.advanced_settings.data.hysteresis_w"
            }
        ): NumberSelectorBuilder(0, 5000, 1).build(),
        Required(
            CONF_BATTERY_POWER_REVERSED,
            default=defaults.get(CONF_BATTERY_POWER_REVERSED, False),
            description={
                "suggested_value": defaults.get(CONF_BATTERY_POWER_REVERSED, False),
                "label": "config.step.settings.data.battery_power_reversed"
            }
        ): BooleanSelectorBuilder().build(),
    })
