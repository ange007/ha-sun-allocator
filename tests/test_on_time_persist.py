"""Tests for persisting the IN-PROGRESS on-time session across a restart.

The daily total already survived restart; the currently-running session (``last_on_time``)
did not, so a long unbroken run lost all its elapsed time on restart. These cover the
persist/load round-trip and the restart-time restore rules in ``_sync_initial_device_states``.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from custom_components.sun_allocator.const import CONF_DEVICE_ID, CONF_DEVICE_ENTITY
from custom_components.sun_allocator.core import device_restore as dr
from custom_components.sun_allocator.core.power_processor import _sync_initial_device_states

NOW = datetime(2026, 8, 3, 14, 0, 0, tzinfo=timezone.utc)


def _cfg():
    c = MagicMock()
    c.entry_id = "e1"
    return c


# --- persist ↔ load round-trip ---------------------------------------------

@pytest.mark.asyncio
async def test_last_on_time_round_trip():
    saved: dict = {}

    async def fake_load(_h, _c):
        return dict(saved)

    async def fake_save(_h, _c, data):
        saved.clear()
        saved.update(data)

    start = NOW - timedelta(hours=6)
    state = {"d1": {"on_time_day": NOW.date(), "on_time_accum_sec": 120.0, "last_on_time": start}}
    with patch.object(dr, "_load_restore_data", new=fake_load), \
         patch.object(dr, "_save_restore_data", new=fake_save):
        await dr.persist_on_time_state(MagicMock(), _cfg(), state)
        out = await dr.load_on_time_state(MagicMock(), _cfg())

    assert out["d1"]["on_time_accum_sec"] == 120.0
    assert out["d1"]["on_time_day"] == NOW.date()
    assert out["d1"]["last_on_time"] == start


@pytest.mark.asyncio
async def test_first_unclosed_session_is_persisted():
    # A device in its FIRST ever session has on_time_day=None (only stamped on close) but
    # an open last_on_time. It must still persist — day derived from the session start —
    # or the continuous run is lost on restart (the exact bug this feature targets).
    saved: dict = {}

    async def fake_load(_h, _c):
        return dict(saved)

    async def fake_save(_h, _c, data):
        saved.clear()
        saved.update(data)

    start = NOW - timedelta(hours=3)
    state = {"d1": {"on_time_day": None, "on_time_accum_sec": 0.0, "last_on_time": start}}
    with patch.object(dr, "_load_restore_data", new=fake_load), \
         patch.object(dr, "_save_restore_data", new=fake_save):
        await dr.persist_on_time_state(MagicMock(), _cfg(), state)
        out = await dr.load_on_time_state(MagicMock(), _cfg())

    assert out["d1"]["last_on_time"] == start
    assert out["d1"]["on_time_day"] == start.date()   # derived from the open session
    assert out["d1"]["on_time_accum_sec"] == 0.0


@pytest.mark.asyncio
async def test_load_backward_compat_no_last_on_time():
    # A pre-1.3.1 store has no last_on_time — must still load the daily total.
    saved = {dr._ON_TIME_STORAGE_KEY: {"d9": {"on_time_day": "2026-08-03", "on_time_accum_sec": 60.0}}}

    async def fake_load(_h, _c):
        return dict(saved)

    with patch.object(dr, "_load_restore_data", new=fake_load):
        out = await dr.load_on_time_state(MagicMock(), _cfg())

    assert out["d9"]["on_time_accum_sec"] == 60.0
    assert "last_on_time" not in out["d9"]


# --- restart-time restore rules (_sync_initial_device_states) ---------------

def _hass(entity_state):
    hass = MagicMock()
    hass.states.get.return_value = MagicMock(state=entity_state)
    return hass


DEVICES = [{CONF_DEVICE_ID: "d1", CONF_DEVICE_ENTITY: "switch.ac"}]


def test_on_device_continues_restored_session():
    start = NOW - timedelta(hours=6)
    ot = {"d1": {"on_time_day": NOW.date(), "on_time_accum_sec": 0.0, "last_on_time": start}}
    _sync_initial_device_states(_hass("on"), DEVICES, {}, {}, ot, NOW)
    # Session start preserved → runtime will reflect the full 6h.
    assert ot["d1"]["last_on_time"] == start


def test_on_device_reseeds_stale_previous_day():
    yesterday = NOW - timedelta(days=1)
    ot = {"d1": {"on_time_day": NOW.date(), "on_time_accum_sec": 0.0, "last_on_time": yesterday}}
    _sync_initial_device_states(_hass("on"), DEVICES, {}, {}, ot, NOW)
    # Previous-day start would count across midnight → reseed to now.
    assert ot["d1"]["last_on_time"] == NOW


def test_on_device_no_restored_seeds_now():
    ot = {"d1": {"on_time_day": NOW.date(), "on_time_accum_sec": 0.0}}
    _sync_initial_device_states(_hass("on"), DEVICES, {}, {}, ot, NOW)
    assert ot["d1"]["last_on_time"] == NOW


def test_off_device_drops_restored_session():
    start = NOW - timedelta(hours=6)
    ot = {"d1": {"on_time_day": NOW.date(), "on_time_accum_sec": 0.0, "last_on_time": start}}
    _sync_initial_device_states(_hass("off"), DEVICES, {}, {}, ot, NOW)
    # Off at restart → dangling start dropped (session ended during downtime).
    assert "last_on_time" not in ot["d1"]
