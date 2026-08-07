"""Tests for flap protection: a transient ``unavailable`` blip on a controlled entity
must NOT wipe the device's on-state / manual override. Only a SUSTAINED outage (longer
than ``UNAVAILABLE_CLEAR_GRACE_S``) clears the held state so it starts fresh on return.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from custom_components.sun_allocator.const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_ENTITY,
    UNAVAILABLE_CLEAR_GRACE_S,
)
from custom_components.sun_allocator.core.power_processor import _clear_stale_unavailable

NOW = datetime(2026, 8, 2, 20, 0, 0, tzinfo=timezone.utc)
DEVICES = [{CONF_DEVICE_ID: "d1", CONF_DEVICE_ENTITY: "switch.ac"}]


def _hass(state_value):
    hass = MagicMock()
    st = None if state_value is None else MagicMock(state=state_value)
    hass.states.get.return_value = st
    return hass


def _entry_data():
    return {
        "device_on_state": {"d1": True},
        "manual_overrides": {"d1": {"since": NOW, "state": True}},
        "unavailable_since": {},
    }


def test_available_drops_stamp_keeps_state():
    ed = _entry_data()
    ed["unavailable_since"]["d1"] = NOW - timedelta(seconds=999)  # stale stamp
    _clear_stale_unavailable(_hass("on"), ed, DEVICES, NOW)
    assert "d1" not in ed["unavailable_since"]          # recovered → stamp cleared
    assert ed["device_on_state"]["d1"] is True          # state untouched
    assert "d1" in ed["manual_overrides"]               # override survives


def test_transient_blip_holds_state():
    ed = _entry_data()
    # First cycle sees it unavailable → stamps now, holds everything.
    _clear_stale_unavailable(_hass("unavailable"), ed, DEVICES, NOW)
    assert ed["unavailable_since"]["d1"] == NOW
    assert ed["device_on_state"]["d1"] is True
    assert ed["manual_overrides"]["d1"]["state"] is True


def test_blip_shorter_than_grace_holds():
    ed = _entry_data()
    ed["unavailable_since"]["d1"] = NOW
    later = NOW + timedelta(seconds=UNAVAILABLE_CLEAR_GRACE_S - 1)
    _clear_stale_unavailable(_hass("unavailable"), ed, DEVICES, later)
    assert ed["device_on_state"]["d1"] is True          # still held
    assert "d1" in ed["manual_overrides"]
    assert ed["unavailable_since"]["d1"] == NOW          # stamp preserved


def test_sustained_outage_clears_state():
    ed = _entry_data()
    ed["unavailable_since"]["d1"] = NOW
    later = NOW + timedelta(seconds=UNAVAILABLE_CLEAR_GRACE_S + 1)
    _clear_stale_unavailable(_hass("unavailable"), ed, DEVICES, later)
    assert "d1" not in ed["device_on_state"]            # genuinely gone → cleared
    assert "d1" not in ed["manual_overrides"]
    assert "d1" not in ed["unavailable_since"]


def test_exactly_at_grace_clears():
    ed = _entry_data()
    ed["unavailable_since"]["d1"] = NOW
    at = NOW + timedelta(seconds=UNAVAILABLE_CLEAR_GRACE_S)
    _clear_stale_unavailable(_hass("unavailable"), ed, DEVICES, at)
    assert "d1" not in ed["manual_overrides"]           # >= grace boundary clears


def test_missing_state_object_treated_unavailable():
    ed = _entry_data()
    _clear_stale_unavailable(_hass(None), ed, DEVICES, NOW)
    assert ed["unavailable_since"]["d1"] == NOW          # None state → stamped, held
    assert ed["device_on_state"]["d1"] is True
