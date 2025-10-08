import sys
import unittest.mock
import pytest

from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.const import CONF_NAME

from tests.const import MOCK_CONFIG

from custom_components.sun_allocator.const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_PRIORITY,
    CONF_DEVICE_TYPE,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_DEVICE_MIN_EXPECTED_W,
    CONF_DEVICE_MAX_EXPECTED_W,
    CONF_DEVICE_SCHEDULE_ENABLED,
)

# Mock the 'resource' module on Windows
if sys.platform == "win32":
    sys.modules["resource"] = unittest.mock.MagicMock()


# Automatically enable custom integrations defined in the test environment
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def create_test_config_entry(extra_data=None, **kwargs):
    """Create a test config entry for Sun Allocator."""
    data = {
        CONF_NAME: "Test Sun Allocator",
        **MOCK_CONFIG,
        CONF_DEVICES: [],
    }
    if extra_data:
        data.update(extra_data)

    config = {
        "domain": DOMAIN,
        "title": "Test Sun Allocator",
        "data": data,
        "version": 1,
        "entry_id": "test_entry_id",
        "unique_id": "test_unique_id",
        "source": "user",
        "options": {},
        **kwargs,
    }

    return MockConfigEntry(**config)


def create_test_device(device_name, extra_data=None):
    """Create a test device configuration."""
    data = {
        CONF_DEVICE_ID: device_name,
        CONF_DEVICE_NAME: device_name,
        CONF_DEVICE_TYPE: "standard",
        CONF_DEVICE_ENTITY: f"switch.{device_name}",
        CONF_DEVICE_PRIORITY: 50,
        CONF_DEVICE_MIN_EXPECTED_W: 10,
        CONF_DEVICE_MAX_EXPECTED_W: 100,
        CONF_AUTO_CONTROL_ENABLED: True,
        CONF_DEVICE_SCHEDULE_ENABLED: False,
    }
    
    if extra_data:
        data.update(extra_data)
        
    return data