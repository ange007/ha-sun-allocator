"""Tests for battery SOC reading.

The age-based staleness guard was removed (it fail-safe-blocked SOC-gated starts
whenever the battery rested at a flat value — e.g. 100% all afternoon — because a
report-on-change SOC sensor freezes its timestamps while the value holds). Genuine
sensor death is surfaced by HA as ``unavailable``/``unknown`` and still returns None;
a stale-but-valid numeric reading is now trusted (last known value).
"""

from datetime import timedelta
from unittest.mock import MagicMock

import homeassistant.util.dt as dt_util

from custom_components.sun_allocator.const import CONF_BATTERY_SOC_SENSOR
from custom_components.sun_allocator.core import power_processor as pp


def _hass_with(entity_id, state_val, age_s):
    hass = MagicMock()
    st = MagicMock()
    st.state = state_val
    st.last_updated = dt_util.utcnow() - timedelta(seconds=age_s)
    st.last_changed = st.last_updated
    hass.states.get.return_value = st
    return hass


def test_read_battery_soc_fresh_returns_value():
    hass = _hass_with("sensor.soc", "75", 120)
    assert pp._read_battery_soc(hass, {CONF_BATTERY_SOC_SENSOR: "sensor.soc"}) == 75.0


def test_read_battery_soc_stale_but_valid_is_trusted():
    # Battery resting at a flat value freezes the timestamp for hours — must NOT be
    # discarded (would fail-safe-block SOC-gated starts when the battery is fullest).
    hass = _hass_with("sensor.soc", "100", 6 * 3600)
    assert pp._read_battery_soc(hass, {CONF_BATTERY_SOC_SENSOR: "sensor.soc"}) == 100.0


def test_read_battery_soc_unavailable_returns_none():
    # Genuine sensor death (HA marks it unavailable) still returns None.
    hass = _hass_with("sensor.soc", "unavailable", 5)
    assert pp._read_battery_soc(hass, {CONF_BATTERY_SOC_SENSOR: "sensor.soc"}) is None


def test_read_battery_soc_unknown_returns_none():
    hass = _hass_with("sensor.soc", "unknown", 5)
    assert pp._read_battery_soc(hass, {CONF_BATTERY_SOC_SENSOR: "sensor.soc"}) is None


def test_read_battery_soc_no_sensor_configured_returns_none():
    assert pp._read_battery_soc(MagicMock(), {}) is None
