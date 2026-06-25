"""Tests for the battery-power sign sanity check (`_check_battery_sign`)."""

from unittest.mock import MagicMock

from custom_components.sun_allocator.const import DOMAIN, CONF_BATTERY_POWER_REVERSED
from custom_components.sun_allocator.sensor.sensors.base import BaseSunAllocatorSensor


def _sensor(reversed_flag=False, entry_id="e1"):
    class _Stub(BaseSunAllocatorSensor):
        def _calculate_value(self, **_kwargs):  # pragma: no cover
            return 0.0

    s = _Stub.__new__(_Stub)
    s._hass = MagicMock()
    s._hass.data = {DOMAIN: {entry_id: {}}}
    s._entry_id = entry_id
    s._battery_power = "sensor.batt"
    s._config = {CONF_BATTERY_POWER_REVERSED: reversed_flag}
    return s


def _state(s):
    return s._hass.data[DOMAIN][s._entry_id].get("_battery_sign_check", {})


def test_warns_when_only_nonnegative_over_threshold():
    s = _sensor()
    for _ in range(BaseSunAllocatorSensor._BATTERY_SIGN_MIN_SAMPLES):
        s._check_battery_sign(225.0)  # always charging-magnitude, never negative
    s._check_battery_sign(225.0)
    assert _state(s)["warned"] is True


def test_no_warn_if_ever_negative():
    s = _sensor()
    for i in range(BaseSunAllocatorSensor._BATTERY_SIGN_MIN_SAMPLES + 10):
        s._check_battery_sign(-50.0 if i == 5 else 100.0)
    assert _state(s)["warned"] is False
    assert _state(s)["saw_negative"] is True


def test_no_warn_when_reversed_enabled():
    s = _sensor(reversed_flag=True)
    for _ in range(BaseSunAllocatorSensor._BATTERY_SIGN_MIN_SAMPLES + 10):
        s._check_battery_sign(225.0)
    # reversed → check returns early, no state recorded
    assert _state(s) == {}


def test_no_warn_before_threshold():
    s = _sensor()
    for _ in range(10):
        s._check_battery_sign(225.0)
    assert _state(s)["warned"] is False
