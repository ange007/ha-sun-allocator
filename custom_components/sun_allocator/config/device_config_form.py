"""Device config form builders for Sun Allocator.

# NOTE: Custom SelectSelectorBuilder is kept here because:
#  - Device dropdown requires emoji and friendly_name in label, value=entity_id
#  - Supports 'None' option and custom filtering (ESPHome/standard devices)
#  - Standard Home Assistant selector does not support these UI/UX requirements
"""

from voluptuous import Schema, Required, Optional

from homeassistant.helpers.selector import selector

from ..config.ui_helpers import SelectSelectorBuilder, NumberSelectorBuilder

from ..const import (
    CONF_DEVICE_NAME,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_CONTROL_MODE,
    CONTROL_MODE_ON_OFF,
    CONTROL_MODE_PROPORTIONAL,
    DOMAIN_CLIMATE,
    NONE_OPTION,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_DEVICE_MIN_EXPECTED_W,
    CONF_DEVICE_MAX_EXPECTED_W,
    CONF_DEVICE_PRIORITY,
    CONF_DEVICE_SCHEDULE_MODE,
    SCHEDULE_MODE_DISABLED,
    SCHEDULE_MODE_STANDARD,
    SCHEDULE_MODE_HELPER,
    CONF_DEVICE_SCHEDULE_HELPER_ENTITY,
    DAYS_OF_WEEK,
    CONF_START_TIME,
    CONF_END_TIME,
    CONF_DAYS_OF_WEEK,
    CONF_DEVICE_DEBOUNCE_TIME,
    DEFAULT_DEBOUNCE_TIME,
    CONF_DEVICE_MIN_ON_TIME,
    CONF_DEVICE_START_BATTERY_SOC,
    CONF_DEVICE_STOP_BATTERY_SOC,
    DEFAULT_DEVICE_STOP_BATTERY_SOC,
    CONF_DEVICE_TURN_OFF_ON_AUTO_CONTROL_DISABLE,
    CONF_DEVICE_ACTUAL_POWER_SENSOR,
    CONF_DEVICE_ACTUAL_POWER_THRESHOLD_W,
    DEFAULT_ACTUAL_POWER_THRESHOLD_W,
    CONF_DEVICE_CHECK_USABLE_TEMPLATE,
    CONF_DEVICE_MAX_ON_TIME_PER_DAY,
    CONF_DEVICE_ALLOW_PROBE,
    DEFAULT_DEVICE_ALLOW_PROBE,
)


def build_device_name_selection_schema(entities, defaults=None):
    """Builds the combined schema for device name + entity selection.

    The control mode (on/off vs proportional) is encoded in the entity-picker
    option suffix (``entity|on_off`` / ``entity|proportional``); climate keeps
    its ``entity|hvac_mode`` suffix. No separate mode field is shown — ESPHome
    relays auto-pair their select entity at save time.
    """
    if defaults is None:
        defaults = {}

    options = [
        {"label": label, "value": value} for value, label, _ in entities["all_entities"]
    ]

    default_entity = (
        NONE_OPTION
        if defaults.get(CONF_DEVICE_ENTITY) is None
        else defaults.get(CONF_DEVICE_ENTITY)
    )

    # Options carry a mode suffix but stored defaults are cleaned — reconstruct
    # the full value so the saved row pre-selects on edit. Climate uses hvac_mode;
    # everything else uses the control_mode.
    if default_entity != NONE_OPTION:
        if defaults.get("hvac_mode"):
            default_entity = f"{default_entity}|{defaults['hvac_mode']}"
        elif "." in default_entity and default_entity.split(".")[0] != DOMAIN_CLIMATE:
            control_mode = defaults.get(CONF_DEVICE_CONTROL_MODE, CONTROL_MODE_ON_OFF)
            default_entity = f"{default_entity}|{control_mode}"

    schema_dict = {
        Required(
            CONF_DEVICE_NAME,
            default=defaults.get(CONF_DEVICE_NAME, ""),
        ): str,
        Optional(
            CONF_DEVICE_ENTITY,
            default=default_entity,
        ): SelectSelectorBuilder(options).build(),
    }

    return Schema(schema_dict)


def _get_schedule_mode_default(defaults):
    """Get schedule mode default."""
    return defaults.get(CONF_DEVICE_SCHEDULE_MODE, SCHEDULE_MODE_DISABLED)


def build_device_basic_settings_schema(defaults=None):
    """Builds the schema for the essential per-device settings (Basic step).

    Everyday knobs only; the fine-tuning fields live on the Advanced step
    (:func:`build_device_advanced_settings_schema`).
    """
    if defaults is None:
        defaults = {}

    schema_dict = {
        Required(
            CONF_AUTO_CONTROL_ENABLED,
            default=defaults.get(CONF_AUTO_CONTROL_ENABLED, False),
        ): selector({"boolean": {}}),

        Required(
            CONF_DEVICE_TURN_OFF_ON_AUTO_CONTROL_DISABLE,
            default=defaults.get(CONF_DEVICE_TURN_OFF_ON_AUTO_CONTROL_DISABLE, False),
        ): selector({"boolean": {}}),

        Required(
            CONF_DEVICE_PRIORITY,
            default=str(defaults.get(CONF_DEVICE_PRIORITY, 50)),
        ): SelectSelectorBuilder(
            options=["100", "75", "50", "25", "1"],
            translation_key=CONF_DEVICE_PRIORITY
        ).build(),

        Required(
            CONF_DEVICE_MIN_EXPECTED_W,
            default=defaults.get(CONF_DEVICE_MIN_EXPECTED_W, 10.0),
        ): NumberSelectorBuilder(5, 10000, 1, unit="W").build(),
    }

    needs_max_w = defaults.get(CONF_DEVICE_CONTROL_MODE) == CONTROL_MODE_PROPORTIONAL
    if needs_max_w:
        schema_dict[
            Required(
                CONF_DEVICE_MAX_EXPECTED_W,
                default=defaults.get(CONF_DEVICE_MAX_EXPECTED_W, 100.0),
            )
        ] = NumberSelectorBuilder(1, 50000, 1, unit="W").build()

    schema_dict[
        Required(
            CONF_DEVICE_SCHEDULE_MODE,
            default=_get_schedule_mode_default(defaults),
        )
    ] = SelectSelectorBuilder(
        options=[SCHEDULE_MODE_DISABLED, SCHEDULE_MODE_STANDARD, SCHEDULE_MODE_HELPER],
        translation_key=CONF_DEVICE_SCHEDULE_MODE,
    ).build()

    return Schema(schema_dict)


def build_device_advanced_settings_schema(defaults=None):
    """Builds the schema for the fine-tuning per-device settings (Advanced step)."""
    if defaults is None:
        defaults = {}

    schema_dict = {
        Optional(
            CONF_DEVICE_DEBOUNCE_TIME,
            default=defaults.get(CONF_DEVICE_DEBOUNCE_TIME, DEFAULT_DEBOUNCE_TIME),
        ): NumberSelectorBuilder(5, 600, 1, unit="s").build(),

        Optional(
            CONF_DEVICE_MIN_ON_TIME,
            default=defaults.get(CONF_DEVICE_MIN_ON_TIME, 0),
        ): NumberSelectorBuilder(0, 3600, 1, unit="s").build(),

        Required(
            CONF_DEVICE_ALLOW_PROBE,
            default=defaults.get(CONF_DEVICE_ALLOW_PROBE, DEFAULT_DEVICE_ALLOW_PROBE),
        ): selector({"boolean": {}}),

        # START (charge-side): begin only when SOC >= this. 0 = off.
        Optional(
            CONF_DEVICE_START_BATTERY_SOC,
            default=defaults.get(CONF_DEVICE_START_BATTERY_SOC, 0),
        ): NumberSelectorBuilder(0, 100, 1, unit="%").build(),

        # STOP (discharge-side): keep running until SOC drops to this while discharging.
        # 100 = never discharge the battery for this device. Clamped to the global
        # battery_protection_soc by the flow before this schema is built.
        Optional(
            CONF_DEVICE_STOP_BATTERY_SOC,
            default=defaults.get(CONF_DEVICE_STOP_BATTERY_SOC, DEFAULT_DEVICE_STOP_BATTERY_SOC),
        ): NumberSelectorBuilder(0, 100, 1, unit="%").build(),
    }

    actual_sensor_val = defaults.get(CONF_DEVICE_ACTUAL_POWER_SENSOR)
    schema_dict[
        Optional(
            CONF_DEVICE_ACTUAL_POWER_SENSOR,
            **({"default": actual_sensor_val} if actual_sensor_val else {}),
            description={"suggested_value": actual_sensor_val},
        )
    ] = selector({"entity": {"domain": "sensor", "device_class": "power"}})

    schema_dict[
        Optional(
            CONF_DEVICE_ACTUAL_POWER_THRESHOLD_W,
            default=defaults.get(CONF_DEVICE_ACTUAL_POWER_THRESHOLD_W, DEFAULT_ACTUAL_POWER_THRESHOLD_W),
        )
    ] = NumberSelectorBuilder(0, 10000, 1, unit="W").build()

    schema_dict[
        Optional(
            CONF_DEVICE_MAX_ON_TIME_PER_DAY,
            default=defaults.get(CONF_DEVICE_MAX_ON_TIME_PER_DAY, 0),
        )
    ] = NumberSelectorBuilder(0, 1440, 1, unit="min").build()

    usable_template_val = defaults.get(CONF_DEVICE_CHECK_USABLE_TEMPLATE)
    schema_dict[
        Optional(
            CONF_DEVICE_CHECK_USABLE_TEMPLATE,
            **({"default": usable_template_val} if usable_template_val else {}),
            description={"suggested_value": usable_template_val},
        )
    ] = selector({"template": {}})

    return Schema(schema_dict)


def build_device_schedule_helper_schema(defaults=None):
    """Builds the schema for selecting a HA Schedule Helper entity."""
    if defaults is None:
        defaults = {}

    return Schema(
        {
            Required(
                CONF_DEVICE_SCHEDULE_HELPER_ENTITY,
                default=defaults.get(CONF_DEVICE_SCHEDULE_HELPER_ENTITY, ""),
                # Runtime (core/schedule.py) gates on any entity's on/off state, so allow
                # the common on/off helpers — not just `schedule` (which the docs and the
                # runtime both already support).
            ): selector({"entity": {"domain": ["schedule", "input_boolean", "switch"]}}),
        }
    )


def build_device_schedule_schema(defaults=None):
    """Builds the schema for device schedule configuration."""
    if defaults is None:
        defaults = {}

    default_days = defaults.get(CONF_DAYS_OF_WEEK, DAYS_OF_WEEK)

    days_schema = {}
    for day in DAYS_OF_WEEK:
        days_schema[
            Required(
                day,
                default=day in default_days,
            )
        ] = selector({"boolean": {}})

    return Schema(
        {
            Required(
                CONF_START_TIME,
                default=defaults.get(CONF_START_TIME, "08:00"),
            ): selector({"time": {}}),

            Required(
                CONF_END_TIME,
                default=defaults.get(CONF_END_TIME, "20:00"),
            ): selector({"time": {}}),

            **days_schema,
        }
    )
