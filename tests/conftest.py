import sys
import unittest.mock
import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME

# Mock the 'resource' module on Windows
if sys.platform == "win32":
    sys.modules["resource"] = unittest.mock.MagicMock()


# Automatically enable custom integrations defined in the test environment
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def create_test_config_entry(extra_data=None):
    """Create a test config entry for Sun Allocator."""
    data = {
        CONF_NAME: "Test Sun Allocator",
        "pv_power": "sensor.pv_power",
        "pv_voltage": "sensor.pv_voltage",
        "vmp": 30.0,
        "imp": 8.0,
        "panel_count": 1,
        "panel_configuration": "series",
        "devices": [],
    }
    if extra_data:
        data.update(extra_data)

    return ConfigEntry(
        version=1,
        domain="sun_allocator",
        title="Test Sun Allocator",
        data=data,
        options={},
        source="user",
        entry_id="test_entry_id",
        unique_id="test_unique_id",
    )


def create_test_device(device_name):
    """Create a test device configuration."""
    return {
        "device_id": device_name,
        "device_name": device_name,
        "device_type": "standard",
        "device_entity": f"switch.{device_name}",
        "priority": 50,
        "min_expected_w": 10,
        "max_expected_w": 100,
        "auto_control_enabled": True,
        "schedule_enabled": False,
    }
