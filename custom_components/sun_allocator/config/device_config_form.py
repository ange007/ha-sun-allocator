"""Device config form builders for Sun Allocator."""
from voluptuous import Schema, Required, Optional
from ..utils.ui_helpers import SelectSelectorBuilder, NumberSelectorBuilder, BooleanSelectorBuilder

from ..const import (
    CONF_DEVICE_NAME, CONF_DEVICE_TYPE, DEVICE_TYPE_NONE, DEVICE_TYPE_CUSTOM, DEVICE_TYPE_STANDARD,
    CONF_DEVICE_ENTITY, NONE_OPTION, CONF_AUTO_CONTROL_ENABLED, CONF_MIN_EXPECTED_W, CONF_MAX_EXPECTED_W,
    CONF_DEVICE_PRIORITY, CONF_SCHEDULE_ENABLED, DAYS_OF_WEEK, CONF_START_TIME, CONF_END_TIME, CONF_DAYS_OF_WEEK
)

def build_device_name_type_schema(defaults=None):
    if defaults is None:
        defaults = {}
    default_type = defaults.get(CONF_DEVICE_TYPE, DEVICE_TYPE_CUSTOM)
    if default_type == DEVICE_TYPE_NONE:
        default_type = DEVICE_TYPE_CUSTOM
    return Schema({
        Required(
            CONF_DEVICE_NAME,
            default=defaults.get(CONF_DEVICE_NAME, ""),
            description={
                "suggested_value": defaults.get(CONF_DEVICE_NAME, ""),
                "label": "config.step.device_name_type.data.name"
            }
        ): str,
        Required(
            CONF_DEVICE_TYPE,
            default=default_type,
            description={
                "suggested_value": default_type,
                "label": "config.step.device_name_type.data.device_type.name"
            }
        ): SelectSelectorBuilder([
            {"label": "config.step.device_name_type.data.device_type.options.standard", "value": DEVICE_TYPE_STANDARD},
            {"label": "config.step.device_name_type.data.device_type.options.custom", "value": DEVICE_TYPE_CUSTOM}
        ]).build()
    })

def build_device_selection_schema(entities, device_type, defaults=None):
    if defaults is None:
        defaults = {}
    options = [
        {"label": label, "value": value}
        for value, label, _ in entities["all_entities"]
    ]
    default_entity = NONE_OPTION if defaults.get(CONF_DEVICE_ENTITY) is None else defaults.get(CONF_DEVICE_ENTITY, NONE_OPTION)
    if len(options) <= 1:
        options.append({"label": "config.step.device_selection.data.no_devices_found", "value": NONE_OPTION})
    return Schema({
        Optional(
            CONF_DEVICE_ENTITY,
            default=default_entity,
            description={
                "suggested_value": default_entity,
                "label": "config.step.device_selection.data.esphome_relay_entity"
            }
        ): SelectSelectorBuilder(options).build()
    })

def build_device_basic_settings_schema(defaults=None):
    if defaults is None:
        defaults = {}
    device_type = defaults.get(CONF_DEVICE_TYPE, DEVICE_TYPE_STANDARD)
    schema_dict = {
        Required(
            CONF_AUTO_CONTROL_ENABLED,
            default=defaults.get(CONF_AUTO_CONTROL_ENABLED, False),
            description={
                "suggested_value": defaults.get(CONF_AUTO_CONTROL_ENABLED, False),
                "label": "config.step.device_basic_settings.data.auto_control_enabled"
            }
        ): BooleanSelectorBuilder().build(),
        Optional(
            CONF_MIN_EXPECTED_W,
            default=defaults.get(CONF_MIN_EXPECTED_W, 0.0),
            description={"suggested_value": defaults.get(CONF_MIN_EXPECTED_W, 0.0)}
        ): NumberSelectorBuilder(0, 10000, 1, unit="Вт").build(),
        Required(
            CONF_DEVICE_PRIORITY,
            default=defaults.get(CONF_DEVICE_PRIORITY, 50),
            description={"suggested_value": defaults.get(CONF_DEVICE_PRIORITY, 50)}
        ): NumberSelectorBuilder(1, 100, 1, mode="slider").build(),
        Required(
            CONF_SCHEDULE_ENABLED,
            default=defaults.get(CONF_SCHEDULE_ENABLED, False),
            description={"suggested_value": defaults.get(CONF_SCHEDULE_ENABLED, False)}
        ): BooleanSelectorBuilder().build(),
    }
    if device_type == DEVICE_TYPE_CUSTOM:
        schema_dict[Optional(
            CONF_MAX_EXPECTED_W,
            default=defaults.get(CONF_MAX_EXPECTED_W, 0.0),
            description={"suggested_value": defaults.get(CONF_MAX_EXPECTED_W, 0.0)}
        )] = NumberSelectorBuilder(0, 10000, 1, unit="Вт").build()
    return Schema(schema_dict)

def build_device_schedule_schema(defaults=None):
    from homeassistant.helpers.selector import selector
    if defaults is None:
        defaults = {}
    default_days = defaults.get(CONF_DAYS_OF_WEEK, DAYS_OF_WEEK)
    days_schema = {}
    for day in DAYS_OF_WEEK:
        days_schema[Required(
            day,
            default=day in default_days,
            description={"suggested_value": day in default_days}
        )] = BooleanSelectorBuilder().build()
    return Schema({
        Required(
            CONF_START_TIME,
            default=defaults.get(CONF_START_TIME, "08:00"),
            description={"suggested_value": defaults.get(CONF_START_TIME, "08:00")}
        ): selector({"time": {}}),
        Required(
            CONF_END_TIME,
            default=defaults.get(CONF_END_TIME, "20:00"),
            description={"suggested_value": defaults.get(CONF_END_TIME, "20:00")}
        ): selector({"time": {}}),
        **days_schema
    })
