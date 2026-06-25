"""Tests for the SOC staleness guard (`is_reading_stale` + `_read_battery_soc`)."""

from datetime import timedelta
from unittest.mock import MagicMock

import homeassistant.util.dt as dt_util

from custom_components.sun_allocator.const import (
    CONF_BATTERY_SOC_SENSOR,
    DEFAULT_SOC_MAX_AGE_S,
)
from custom_components.sun_allocator.core import power_processor as pp
from custom_components.sun_allocator.sensor.utils import is_reading_stale


def _hass_with(entity_id, state_val, age_s):
    hass = MagicMock()
    st = MagicMock()
    st.state = state_val
    st.last_updated = dt_util.utcnow() - timedelta(seconds=age_s)
    st.last_changed = st.last_updated
    hass.states.get.return_value = st
    return hass


def test_is_reading_stale_fresh_vs_old():
    fresh = _hass_with("sensor.soc", "80", 60)
    old = _hass_with("sensor.soc", "80", DEFAULT_SOC_MAX_AGE_S + 60)
    assert is_reading_stale(fresh, "sensor.soc", DEFAULT_SOC_MAX_AGE_S) is False
    assert is_reading_stale(old, "sensor.soc", DEFAULT_SOC_MAX_AGE_S) is True


def test_is_reading_stale_noops():
    hass = _hass_with("sensor.soc", "80", 99999)
    assert is_reading_stale(hass, None, DEFAULT_SOC_MAX_AGE_S) is False  # no entity
    assert is_reading_stale(hass, "sensor.soc", 0) is False              # disabled


def test_read_battery_soc_fresh_returns_value():
    hass = _hass_with("sensor.soc", "75", 120)
    assert pp._read_battery_soc(hass, {CONF_BATTERY_SOC_SENSOR: "sensor.soc"}) == 75.0


def test_read_battery_soc_stale_returns_none():
    hass = _hass_with("sensor.soc", "75", DEFAULT_SOC_MAX_AGE_S + 600)
    assert pp._read_battery_soc(hass, {CONF_BATTERY_SOC_SENSOR: "sensor.soc"}) is None
