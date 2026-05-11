"""Tests for per-device SunAllocator sensors."""

from unittest.mock import MagicMock

from custom_components.sun_allocator.const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_POWER_DISTRIBUTION,
)
from custom_components.sun_allocator.sensor.sensors.device_power_alloc import (
    SunAllocatorDevicePowerSensor,
)
from custom_components.sun_allocator.sensor.sensors.device_power_percent import (
    SunAllocatorDevicePowerPercentSensor,
)
from custom_components.sun_allocator.sensor.sensors.device_status import (
    SunAllocatorDeviceStatusSensor,
)
from custom_components.sun_allocator.sensor.utils import (
    DEVICE_STATUS_OPTIONS,
    is_device_auto_control_enabled,
)


def _hass_with_data(entry_id, data):
    hass = MagicMock()
    hass.data = {DOMAIN: {entry_id: data}}
    return hass


def _device_config(device_id, **extra):
    cfg = {CONF_DEVICE_ID: device_id, CONF_AUTO_CONTROL_ENABLED: True}
    cfg.update(extra)
    return cfg


def test_unique_id_pattern_is_stable_across_sensor_types():
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    cfg = _device_config("dev1")

    power = SunAllocatorDevicePowerSensor(hass, "entry_x", cfg)
    pct = SunAllocatorDevicePowerPercentSensor(hass, "entry_x", cfg)
    status = SunAllocatorDeviceStatusSensor(hass, "entry_x", cfg)

    assert power.unique_id == "entry_x_dev1_power"
    assert pct.unique_id == "entry_x_dev1_power_percent"
    assert status.unique_id == "entry_x_dev1_status"


def test_status_sensor_emits_valid_enum_values():
    cfg = _device_config("dev1")
    entry_data = {
        "config": {CONF_DEVICES: [cfg]},
        CONF_POWER_DISTRIBUTION: {"allocation": {"dev1": 50.0}},
        "device_status": {"dev1": {"is_active_candidate": True}},
    }
    hass = _hass_with_data("entry_x", entry_data)

    sensor = SunAllocatorDeviceStatusSensor(hass, "entry_x", cfg)
    sensor.async_write_ha_state = MagicMock()
    sensor._update_state()

    assert sensor.native_value in DEVICE_STATUS_OPTIONS
    assert sensor.native_value == "active"
    assert sensor.extra_state_attributes["auto_control"] is True


def test_status_sensor_reports_auto_control_off_when_disabled_in_config():
    """Switch state is mirrored into config; the status sensor must reflect that change."""
    cfg = _device_config("dev1", **{CONF_AUTO_CONTROL_ENABLED: False})
    entry_data = {
        "config": {CONF_DEVICES: [cfg]},
        CONF_POWER_DISTRIBUTION: {"allocation": {"dev1": 0.0}},
        "device_status": {"dev1": {}},
    }
    hass = _hass_with_data("entry_x", entry_data)

    sensor = SunAllocatorDeviceStatusSensor(hass, "entry_x", cfg)
    sensor.async_write_ha_state = MagicMock()
    sensor._update_state()

    assert sensor.native_value == "auto_control_off"
    assert sensor.extra_state_attributes["auto_control"] is False


def test_power_sensor_reports_allocated_w():
    cfg = _device_config("dev1")
    entry_data = {
        "config": {CONF_DEVICES: [cfg]},
        CONF_POWER_DISTRIBUTION: {"allocation": {"dev1": 123.4}},
        "device_status": {"dev1": {"percent_actual": 80.0}},
    }
    hass = _hass_with_data("entry_x", entry_data)

    sensor = SunAllocatorDevicePowerSensor(hass, "entry_x", cfg)
    sensor.async_write_ha_state = MagicMock()
    sensor._update_state()

    assert sensor.native_value == 123.4
    assert sensor.extra_state_attributes["power_percent"] == 80.0


def test_status_sensor_uses_live_feedback_when_allocation_is_zero():
    cfg = _device_config("dev1")
    entry_data = {
        "config": {CONF_DEVICES: [cfg]},
        CONF_POWER_DISTRIBUTION: {"allocation": {"dev1": 0.0}},
        "device_status": {
            "dev1": {
                "is_active_candidate": True,
                "actual_power_valid": True,
                "is_consuming": True,
                "actual_power_source": "binary_feedback",
                "actual_power_w": 900.0,
            }
        },
    }
    hass = _hass_with_data("entry_x", entry_data)

    sensor = SunAllocatorDeviceStatusSensor(hass, "entry_x", cfg)
    sensor.async_write_ha_state = MagicMock()
    sensor._update_state()

    assert sensor.native_value == "active"
    assert sensor.extra_state_attributes["is_active"] is True


def test_is_device_auto_control_enabled_helper():
    config = {
        CONF_DEVICES: [
            {CONF_DEVICE_ID: "a", CONF_AUTO_CONTROL_ENABLED: True},
            {CONF_DEVICE_ID: "b", CONF_AUTO_CONTROL_ENABLED: False},
            {CONF_DEVICE_ID: "c"},  # Missing key — defaults to False.
        ]
    }
    assert is_device_auto_control_enabled(config, "a") is True
    assert is_device_auto_control_enabled(config, "b") is False
    assert is_device_auto_control_enabled(config, "c") is False
    assert is_device_auto_control_enabled(config, "missing") is False
    assert is_device_auto_control_enabled(config, None) is False
