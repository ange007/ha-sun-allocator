"""Tests for configuration validation."""

import pytest
from custom_components.sun_allocator.config.utils import validate_solar_config
from custom_components.sun_allocator.const import (
    CONF_VMP,
    CONF_IMP,
    CONF_VOC,
    CONF_ISC,
    CONF_PANEL_COUNT,
)


@pytest.mark.parametrize(
    "vmp,imp,voc,isc,valid",
    [
        (30.0, 8.0, 36.0, 8.5, True),  # Valid config
        (0.0, 8.0, 36.0, 8.5, False),  # Invalid Vmp
        (30.0, 0.0, 36.0, 8.5, False),  # Invalid Imp
        (36.0, 8.0, 30.0, 8.5, False),  # Voc < Vmp (invalid)
        (30.0, 8.5, 36.0, 8.0, False),  # Imp > Isc (invalid)
    ],
)
async def test_solar_config_validation(vmp, imp, voc, isc, valid):
    """Test solar panel configuration validation."""
    config = {
        CONF_VMP: vmp,
        CONF_IMP: imp,
        CONF_VOC: voc,
        CONF_ISC: isc,
        CONF_PANEL_COUNT: 1,
    }

    result = validate_solar_config(config)
    assert result["valid"] == valid
    if not valid:
        assert "errors" in result
        assert len(result["errors"]) > 0


async def test_device_entity_validation():
    """Test device entity validation."""
    from custom_components.sun_allocator.config.utils import validate_device_entity

    # Test supported domains
    valid_entities = [
        "switch.test_switch",
        "light.test_light",
        "input_boolean.test_boolean",
    ]

    invalid_entities = [
        "sensor.test_sensor",  # Unsupported domain
        "invalid_entity",  # Invalid format
        "",  # Empty
    ]

    for entity in valid_entities:
        assert validate_device_entity(entity) is True

    for entity in invalid_entities:
        assert validate_device_entity(entity) is False
