"""Tests for save-time check_usable_template validation in DeviceConfigMixin."""

from unittest.mock import MagicMock, patch

from homeassistant.exceptions import TemplateError

from custom_components.sun_allocator.config.device_config import DeviceConfigMixin
from custom_components.sun_allocator.const import (
    CONF_DEVICE_PRIORITY,
    CONF_DEVICE_MIN_EXPECTED_W,
    CONF_DEVICE_CHECK_USABLE_TEMPLATE,
)


def _mixin():
    m = DeviceConfigMixin.__new__(DeviceConfigMixin)
    m.hass = MagicMock()
    m._device_config = {}
    m._devices = []
    return m


def _base_input(template):
    return {
        CONF_DEVICE_PRIORITY: 50,
        CONF_DEVICE_MIN_EXPECTED_W: 100,
        CONF_DEVICE_CHECK_USABLE_TEMPLATE: template,
    }


def test_invalid_template_is_rejected():
    m = _mixin()
    # Template that raises on render (the real user bug: bare `sensor.x`).
    fake = MagicMock()
    fake.async_render.side_effect = TemplateError(Exception("undefined"))
    with patch("custom_components.sun_allocator.config.device_config.Template",
               return_value=fake):
        errors = m._validate_basic_settings(_base_input("{{ sensor.x > 21.5 }}"))
    assert errors.get(CONF_DEVICE_CHECK_USABLE_TEMPLATE) == "invalid_check_usable_template"


def test_valid_template_accepted():
    m = _mixin()
    fake = MagicMock()
    fake.async_render.return_value = True
    with patch("custom_components.sun_allocator.config.device_config.Template",
               return_value=fake):
        errors = m._validate_basic_settings(
            _base_input("{{ states('sensor.x')|float(0) > 21.5 }}")
        )
    assert CONF_DEVICE_CHECK_USABLE_TEMPLATE not in errors


def test_no_template_no_check():
    m = _mixin()
    with patch("custom_components.sun_allocator.config.device_config.Template") as T:
        errors = m._validate_basic_settings(_base_input(None))
    assert CONF_DEVICE_CHECK_USABLE_TEMPLATE not in errors
    T.assert_not_called()
