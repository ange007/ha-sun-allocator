"""Tests for the grid-availability manual-bypass helper.

When a grid-voltage sensor is configured and reads at/above ``grid_min_voltage``, a
manually-forced (manual_on) device ignores the battery-protection force-off — the grid
carries the load. The helper fails CLOSED (returns False → protection stays in force)
whenever the sensor is unconfigured, unavailable, or unparsable.
"""

from unittest.mock import MagicMock

from custom_components.sun_allocator.const import (
    CONF_GRID_VOLTAGE_SENSOR,
    CONF_GRID_MIN_VOLTAGE,
    DEFAULT_GRID_MIN_VOLTAGE,
)
from custom_components.sun_allocator.core.power_processor import _grid_available


def _hass(state_value):
    hass = MagicMock()
    st = MagicMock()
    st.state = state_value
    hass.states.get.return_value = st
    return hass


def test_no_sensor_configured_fails_closed():
    # No grid sensor → protection must stand (auto behaviour unchanged).
    assert _grid_available(_hass("230"), {}) is False


def test_above_default_threshold_is_available():
    cfg = {CONF_GRID_VOLTAGE_SENSOR: "sensor.grid_v"}
    assert _grid_available(_hass("228.5"), cfg) is True


def test_below_default_threshold_not_available():
    cfg = {CONF_GRID_VOLTAGE_SENSOR: "sensor.grid_v"}
    # Default floor is 200 V; a brownout at 150 V is NOT a present grid.
    assert _grid_available(_hass("150"), cfg) is False


def test_exactly_at_threshold_is_available():
    cfg = {CONF_GRID_VOLTAGE_SENSOR: "sensor.grid_v", CONF_GRID_MIN_VOLTAGE: 210}
    assert _grid_available(_hass("210"), cfg) is True
    assert _grid_available(_hass("209.9"), cfg) is False


def test_custom_threshold_respected():
    cfg = {CONF_GRID_VOLTAGE_SENSOR: "sensor.grid_v", CONF_GRID_MIN_VOLTAGE: 50}
    assert _grid_available(_hass("60"), cfg) is True


def test_unavailable_state_fails_closed():
    cfg = {CONF_GRID_VOLTAGE_SENSOR: "sensor.grid_v"}
    assert _grid_available(_hass("unavailable"), cfg) is False
    assert _grid_available(_hass("unknown"), cfg) is False


def test_unparsable_state_fails_closed():
    cfg = {CONF_GRID_VOLTAGE_SENSOR: "sensor.grid_v"}
    assert _grid_available(_hass("not_a_number"), cfg) is False


def test_missing_state_object_fails_closed():
    cfg = {CONF_GRID_VOLTAGE_SENSOR: "sensor.grid_v"}
    hass = MagicMock()
    hass.states.get.return_value = None
    assert _grid_available(hass, cfg) is False


def test_default_threshold_value():
    # Guard the documented default so a silent const edit is caught.
    assert DEFAULT_GRID_MIN_VOLTAGE == 200.0
