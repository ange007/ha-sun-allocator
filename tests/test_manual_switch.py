"""Tests for the per-device manual proxy switch's OFF-button semantics.

Turning the switch OFF is asymmetric by design (see manual_switch.py docstring):
- an active forced-ON override (manual_on or timed run) is released entirely, so
  auto-control decides from the next cycle;
- with no override present, it creates a fresh sticky ``manual_off``.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

import homeassistant.util.dt as dt_util

from custom_components.sun_allocator.const import (
    DOMAIN,
    CONF_DEVICE_ID,
    CONF_DEVICE_ENTITY,
)
from custom_components.sun_allocator.switch.manual_switch import SunAllocatorDeviceManualSwitch

NOW = datetime(2026, 7, 3, 12, 0, 0, tzinfo=timezone.utc)


def _make_switch(entry_data, entity_state="on"):
    hass = MagicMock()
    hass.data = {DOMAIN: {"e1": entry_data}}
    st = MagicMock()
    st.state = entity_state
    hass.states.get.return_value = st
    device = {CONF_DEVICE_ID: "d1", CONF_DEVICE_ENTITY: "switch.x"}
    sw = SunAllocatorDeviceManualSwitch(hass, "e1", device)
    sw.async_write_ha_state = MagicMock()
    return sw, hass


@pytest.mark.asyncio
async def test_turn_off_releases_active_manual_on_override():
    entry_data = {
        "manual_overrides": {"d1": {"since": NOW, "state": True}},
        "device_on_state": {"d1": True},
    }
    sw, hass = _make_switch(entry_data)
    hass.services.async_call = AsyncMock()

    await sw.async_turn_off()

    assert "d1" not in entry_data["manual_overrides"]  # released, not sticky-off
    assert entry_data["device_on_state"]["d1"] is False


@pytest.mark.asyncio
async def test_turn_off_releases_active_timed_run_entirely():
    entry_data = {
        "manual_overrides": {
            "d1": {"since": NOW, "state": True, "until": NOW + timedelta(minutes=10),
                   "ignore_battery": True, "timer_minutes": 10}
        },
        "device_on_state": {"d1": True},
    }
    sw, hass = _make_switch(entry_data)
    hass.services.async_call = AsyncMock()

    await sw.async_turn_off()

    assert "d1" not in entry_data["manual_overrides"]


@pytest.mark.asyncio
async def test_turn_off_with_no_override_creates_sticky_manual_off():
    entry_data = {}  # pure auto state, no override yet
    sw, hass = _make_switch(entry_data)
    hass.services.async_call = AsyncMock()

    await sw.async_turn_off()

    ov = entry_data["manual_overrides"]["d1"]
    assert ov["state"] is False
    assert "until" not in ov


@pytest.mark.asyncio
async def test_turn_off_already_manual_off_stays_sticky_off():
    entry_data = {"manual_overrides": {"d1": {"since": NOW, "state": False}}}
    sw, hass = _make_switch(entry_data, entity_state="off")
    hass.services.async_call = AsyncMock()

    await sw.async_turn_off()

    ov = entry_data["manual_overrides"]["d1"]
    assert ov["state"] is False


# --- race-condition fix: stamp (not clear) last_controlled_at ---------------

@pytest.mark.asyncio
async def test_turn_on_stamps_last_controlled_at():
    """Regression: clearing last_controlled_at let a slow-to-confirm relay (cloud/
    Tuya lag) be misread as a user toggle on the very next cycle, clobbering the
    override we just created."""
    entry_data = {}
    sw, hass = _make_switch(entry_data)
    hass.services.async_call = AsyncMock()

    await sw.async_turn_on()

    assert "d1" in entry_data["last_controlled_at"]


@pytest.mark.asyncio
async def test_turn_off_release_path_stamps_last_controlled_at():
    entry_data = {
        "manual_overrides": {"d1": {"since": NOW, "state": True}},
        "device_on_state": {"d1": True},
    }
    sw, hass = _make_switch(entry_data)
    hass.services.async_call = AsyncMock()

    await sw.async_turn_off()

    assert "d1" in entry_data["last_controlled_at"]


# --- on-time session accounting ---------------------------------------------

@pytest.mark.asyncio
async def test_sticky_manual_off_closes_in_progress_on_time_session():
    # _close_on_time_session uses the real dt_util.now() internally (not an injected
    # clock), so the fixture's last_on_time must be relative to that same clock.
    real_now = dt_util.now()
    entry_data = {
        "device_on_time_state": {"d1": {"last_on_time": real_now - timedelta(minutes=5)}},
    }
    sw, hass = _make_switch(entry_data)
    hass.states.get.return_value.last_changed = real_now
    hass.services.async_call = AsyncMock()

    await sw.async_turn_off()

    on_time = entry_data["device_on_time_state"]["d1"]
    assert on_time.get("last_on_time") is None
    assert on_time.get("on_time_accum_sec", 0.0) > 0.0


@pytest.mark.asyncio
async def test_release_override_closes_in_progress_on_time_session():
    real_now = dt_util.now()
    entry_data = {
        "manual_overrides": {"d1": {"since": NOW, "state": True}},
        "device_on_state": {"d1": True},
        "device_on_time_state": {"d1": {"last_on_time": real_now - timedelta(minutes=2)}},
    }
    sw, hass = _make_switch(entry_data)
    hass.services.async_call = AsyncMock()

    await sw.async_turn_off()

    on_time = entry_data["device_on_time_state"]["d1"]
    assert on_time.get("last_on_time") is None
    assert on_time.get("on_time_accum_sec", 0.0) > 0.0
