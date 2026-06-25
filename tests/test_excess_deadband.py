"""Tests for the excess sensor write deadband (`_should_skip_update`).

Sub-threshold fluctuations are suppressed (no state write); meaningful changes
and 0-crossings always publish.
"""

from custom_components.sun_allocator.sensor.sensors.excess import (
    SunAllocatorExcessSensor,
)


def _sensor(last, new, cmax=1000.0):
    s = SunAllocatorExcessSensor.__new__(SunAllocatorExcessSensor)
    s._last_published_excess = last
    s._attr_extra_state_attributes = {"current_max_power": cmax}
    s._get_shared_snapshot = lambda: {
        "sensor_values": {}, "mppt_readings": [], "mppt_config": {},
        "temp_compensation": None,
    }
    s._calculate_value = lambda **_: new
    return s


def test_no_last_value_never_skips():
    assert _sensor(None, 100.0)._should_skip_update() is False


def test_subthreshold_change_is_skipped():
    # band = max(10, 0.015*1000=15) = 15W; delta 5W < 15 → skip.
    assert _sensor(100.0, 105.0)._should_skip_update() is True


def test_threshold_crossing_publishes():
    # delta 20W > 15W band → publish (no skip).
    assert _sensor(100.0, 120.0)._should_skip_update() is False


def test_zero_crossing_always_publishes():
    assert _sensor(0.0, 8.0)._should_skip_update() is False   # 0 → 8 (<band) still publishes
    assert _sensor(8.0, 0.0)._should_skip_update() is False   # 8 → 0 publishes


def test_absolute_floor_band_when_cmax_zero():
    # cmax=0 → band falls back to absolute 10W floor.
    assert _sensor(50.0, 56.0, cmax=0.0)._should_skip_update() is True   # 6 < 10
    assert _sensor(50.0, 65.0, cmax=0.0)._should_skip_update() is False  # 15 > 10


def test_calc_error_does_not_skip():
    s = _sensor(100.0, 100.0)
    def boom(**_):
        raise ValueError("x")
    s._calculate_value = boom
    assert s._should_skip_update() is False
