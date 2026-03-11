"""Temperature config form builders for Sun Allocator."""

from voluptuous import Schema, Required

from homeassistant.helpers import selector

from ..config.ui_helpers import NumberSelectorBuilder

from ..const import (
    CONF_TEMPERATURE_SENSOR,
    CONF_TEMP_COEFFICIENT_VOC,
    CONF_TEMP_COEFFICIENT_PMAX,
    DEFAULT_VOC_COEFFICIENT,
    DEFAULT_PMAX_COEFFICIENT,
)


def build_temperature_config_schema(defaults=None):
    """Builds the schema for temperature compensation configuration."""
    if defaults is None:
        defaults = {}

    return Schema(
        {
            Required(
                CONF_TEMPERATURE_SENSOR,
                default=defaults.get(CONF_TEMPERATURE_SENSOR),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor",
                    multiple=False,
                    exclude_entities=[],
                    filter=[{"device_class": ["temperature"]}],
                )
            ),
            
            Required(
                CONF_TEMP_COEFFICIENT_VOC,
                default=defaults.get(
                    CONF_TEMP_COEFFICIENT_VOC, DEFAULT_VOC_COEFFICIENT
                ),
            ): NumberSelectorBuilder(-1.0, 0.0, 0.01).build(),
            
            Required(
                CONF_TEMP_COEFFICIENT_PMAX,
                default=defaults.get(
                    CONF_TEMP_COEFFICIENT_PMAX, DEFAULT_PMAX_COEFFICIENT
                ),
            ): NumberSelectorBuilder(-1.0, 0.0, 0.01).build(),
        }
    )
