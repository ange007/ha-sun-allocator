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
    CONF_DEVICE_TYPE,
    DEVICE_TYPE_NONE,
    DEVICE_TYPE_CUSTOM,
    DEVICE_TYPE_STANDARD,
    CONF_DEVICE_ENTITY,
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
)


def build_device_name_type_schema(defaults=None):
    """Builds the schema for device name and type configuration."""
    if defaults is None:
        defaults = {}

    default_type = defaults.get(CONF_DEVICE_TYPE, DEVICE_TYPE_STANDARD)
    if default_type == DEVICE_TYPE_NONE:
        default_type = DEVICE_TYPE_STANDARD

    return Schema(
        {
            Required(
                CONF_DEVICE_NAME,
                default=defaults.get(CONF_DEVICE_NAME, ""),
            ): str,
            Required(
                CONF_DEVICE_TYPE,
                default=default_type,
            ): SelectSelectorBuilder(
                options=[DEVICE_TYPE_STANDARD, DEVICE_TYPE_CUSTOM],
                translation_key=CONF_DEVICE_TYPE,
            ).build(),
        }
    )


def build_device_selection_schema(entities, defaults=None):
    """Builds the schema for device selection configuration."""
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

    # For climate devices, reconstruct the full entity ID with mode suffix
    # since options include the mode but stored defaults are cleaned
    if default_entity != NONE_OPTION and defaults.get("hvac_mode"):
        default_entity = f"{default_entity}|{defaults['hvac_mode']}"

    return Schema(
        {
            Optional(
                CONF_DEVICE_ENTITY,
                default=default_entity,
            ): SelectSelectorBuilder(options).build()
        }
    )


def _get_schedule_mode_default(defaults):
    """Get schedule mode default."""
    return defaults.get(CONF_DEVICE_SCHEDULE_MODE, SCHEDULE_MODE_DISABLED)


def build_device_basic_settings_schema(defaults=None):
    """Builds the schema for device basic settings configuration."""
    if defaults is None:
        defaults = {}

    device_type = defaults.get(CONF_DEVICE_TYPE, DEVICE_TYPE_STANDARD)

    schema_dict = {
        Required(
            CONF_DEVICE_MIN_EXPECTED_W,
            default=defaults.get(CONF_DEVICE_MIN_EXPECTED_W, 10.0),
        ): NumberSelectorBuilder(5, 10000, 1, unit="W").build(),

        Required(
            CONF_DEVICE_PRIORITY,
            default=str(defaults.get(CONF_DEVICE_PRIORITY, 50)),
        ): SelectSelectorBuilder(
            options=["100", "75", "50", "25", "1"], 
            translation_key=CONF_DEVICE_PRIORITY
        ).build(),

        Optional(
            CONF_DEVICE_DEBOUNCE_TIME,
            default=defaults.get(CONF_DEVICE_DEBOUNCE_TIME, DEFAULT_DEBOUNCE_TIME),
        ): NumberSelectorBuilder(5, 600, 1, unit="s").build(),

        Optional(
            CONF_DEVICE_MIN_ON_TIME,
            default=defaults.get(CONF_DEVICE_MIN_ON_TIME, 0),
        ): NumberSelectorBuilder(0, 3600, 1, unit="s").build(),

        Required(
            CONF_AUTO_CONTROL_ENABLED,
            default=defaults.get(CONF_AUTO_CONTROL_ENABLED, False),
        ): selector({"boolean": {}}),

        Required(
            CONF_DEVICE_SCHEDULE_MODE,
            default=_get_schedule_mode_default(defaults),
        ): SelectSelectorBuilder(
            options=[SCHEDULE_MODE_DISABLED, SCHEDULE_MODE_STANDARD, SCHEDULE_MODE_HELPER],
            translation_key=CONF_DEVICE_SCHEDULE_MODE,
        ).build(),
    }

    if device_type == DEVICE_TYPE_CUSTOM:
        schema_dict[
            Required(
                CONF_DEVICE_MAX_EXPECTED_W,
                default=defaults.get(CONF_DEVICE_MAX_EXPECTED_W, 100.0),
            )
        ] = NumberSelectorBuilder(1, 50000, 1, unit="W").build()

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
            ): selector({"entity": {"domain": "schedule"}}),
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
