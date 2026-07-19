"""Tests for the timed-run feature (force ON for N minutes, ignoring battery + schedule).

Covers the core helper (``core/timed_run.py``), the manual-override serialization
round-trip (``core/device_restore.py``) and the ``manual_timer`` status resolution.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sun_allocator.const import (
    DOMAIN,
    CONF_DEVICE_ID,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_NAME,
)
from custom_components.sun_allocator.core import timed_run as tr
from custom_components.sun_allocator.core import device_restore as dr
from custom_components.sun_allocator.sensor.utils import (
    DEVICE_STATUS_MANUAL_TIMER,
    DEVICE_STATUS_MANUAL_ACTIVE,
    _resolve_device_status,
)

NOW = datetime(2026, 7, 3, 12, 0, 0, tzinfo=timezone.utc)


def _hass(entry_data, entity_state="off"):
    hass = MagicMock()
    hass.data = {DOMAIN: {"e1": entry_data}}
    st = MagicMock()
    st.state = entity_state
    hass.states.get.return_value = st
    return hass


def _cfg():
    cfg = MagicMock()
    cfg.entry_id = "e1"
    return cfg


# --- pure helpers -----------------------------------------------------------

def test_is_timed_override():
    assert tr.is_timed_override(None) is False
    assert tr.is_timed_override({"state": True}) is False
    assert tr.is_timed_override({"state": True, "until": NOW}) is True


def test_timed_run_remaining_min():
    assert tr.timed_run_remaining_min(None, NOW) == 0
    assert tr.timed_run_remaining_min({"state": True}, NOW) == 0
    # 45 min ahead → 45; a partial minute rounds up.
    ov = {"state": True, "until": NOW + timedelta(minutes=45)}
    assert tr.timed_run_remaining_min(ov, NOW) == 45
    ov2 = {"state": True, "until": NOW + timedelta(seconds=61)}
    assert tr.timed_run_remaining_min(ov2, NOW) == 2
    # already elapsed → 0
    assert tr.timed_run_remaining_min({"state": True, "until": NOW - timedelta(minutes=1)}, NOW) == 0


def test_is_expired():
    assert tr.is_expired(None, NOW) is False
    assert tr.is_expired({"state": True}, NOW) is False  # not timed
    assert tr.is_expired({"state": True, "until": NOW + timedelta(minutes=1)}, NOW) is False
    assert tr.is_expired({"state": True, "until": NOW - timedelta(seconds=1)}, NOW) is True
    assert tr.is_expired({"state": True, "until": NOW}, NOW) is True  # now >= until


# --- start_timed_run --------------------------------------------------------

@pytest.mark.asyncio
async def test_start_timed_run_writes_timed_override():
    entry_data = {}
    hass = _hass(entry_data, entity_state="off")
    device = {CONF_DEVICE_ID: "d1", CONF_DEVICE_ENTITY: "switch.x", CONF_DEVICE_NAME: "X"}

    with patch.object(tr, "turn_on_entity", new=AsyncMock()) as on, \
         patch.object(tr, "_trigger_reeval", new=AsyncMock()):
        ok = await tr.start_timed_run(hass, _cfg(), device, 30)

    assert ok is True
    on.assert_awaited_once()
    ov = entry_data["manual_overrides"]["d1"]
    assert ov["state"] is True
    assert ov["ignore_battery"] is True
    assert ov["timer_minutes"] == 30
    assert ov["until"] > ov["since"]
    # device_on_state aligned so _detect_external_change won't clobber the timed fields.
    assert entry_data["device_on_state"]["d1"] is True
    # Regression: must STAMP last_controlled_at (not clear it) — otherwise a
    # slow-to-confirm relay (cloud/Tuya lag) is misread as a user toggle on the very
    # next reconciliation, clobbering the timed override (until/ignore_battery) early.
    assert entry_data["last_controlled_at"]["d1"] == ov["since"]


@pytest.mark.asyncio
async def test_start_timed_run_refuses_unavailable_entity():
    entry_data = {}
    hass = _hass(entry_data, entity_state="unavailable")
    device = {CONF_DEVICE_ID: "d1", CONF_DEVICE_ENTITY: "switch.x", CONF_DEVICE_NAME: "X"}

    with patch.object(tr, "turn_on_entity", new=AsyncMock()) as on, \
         patch.object(tr, "_trigger_reeval", new=AsyncMock()):
        ok = await tr.start_timed_run(hass, _cfg(), device, 30)

    assert ok is False
    on.assert_not_awaited()
    assert "manual_overrides" not in entry_data or "d1" not in entry_data.get("manual_overrides", {})


@pytest.mark.asyncio
async def test_start_timed_run_zero_minutes_no_op():
    entry_data = {}
    hass = _hass(entry_data)
    device = {CONF_DEVICE_ID: "d1", CONF_DEVICE_ENTITY: "switch.x"}
    with patch.object(tr, "turn_on_entity", new=AsyncMock()), \
         patch.object(tr, "_trigger_reeval", new=AsyncMock()):
        ok = await tr.start_timed_run(hass, _cfg(), device, 0)
    assert ok is False


# --- cancel_timed_run -------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_timed_run_releases_to_auto():
    entry_data = {
        "manual_overrides": {
            "d1": {"since": NOW, "state": True, "until": NOW + timedelta(minutes=10),
                   "ignore_battery": True, "timer_minutes": 10}
        }
    }
    hass = _hass(entry_data)
    with patch.object(tr, "_trigger_reeval", new=AsyncMock()):
        await tr.cancel_timed_run(hass, _cfg(), "d1")
    assert "d1" not in entry_data["manual_overrides"]  # released, not downgraded


@pytest.mark.asyncio
async def test_cancel_timed_run_noop_when_not_timed():
    entry_data = {"manual_overrides": {"d1": {"since": NOW, "state": True}}}
    hass = _hass(entry_data)
    with patch.object(tr, "_trigger_reeval", new=AsyncMock()) as reeval:
        await tr.cancel_timed_run(hass, _cfg(), "d1")
    reeval.assert_not_awaited()
    assert entry_data["manual_overrides"]["d1"] == {"since": NOW, "state": True}


# --- serialization round-trip (persist ↔ load) ------------------------------

@pytest.mark.asyncio
async def test_manual_override_serialization_round_trip():
    saved: dict = {}

    async def fake_load(_h, _c):
        return dict(saved)

    async def fake_save(_h, _c, data):
        saved.clear()
        saved.update(data)

    until = NOW + timedelta(minutes=20)
    overrides = {
        "d1": {"since": NOW, "state": True, "until": until,
               "ignore_battery": True, "timer_minutes": 20},
    }
    hass = MagicMock()
    cfg = _cfg()
    with patch.object(dr, "_load_restore_data", new=fake_load), \
         patch.object(dr, "_save_restore_data", new=fake_save):
        await dr.persist_manual_overrides(hass, cfg, overrides)
        out = await dr.load_manual_overrides(hass, cfg)

    assert out["d1"]["state"] is True
    assert out["d1"]["until"] == until
    assert out["d1"]["ignore_battery"] is True
    assert out["d1"]["timer_minutes"] == 20


@pytest.mark.asyncio
async def test_load_manual_override_backward_compat_no_timer_fields():
    # An override stored before the timed-run feature (only since+state) must still load.
    saved = {dr._MANUAL_STORAGE_KEY: {"d9": {"since": NOW.isoformat(), "state": True}}}

    async def fake_load(_h, _c):
        return dict(saved)

    hass = MagicMock()
    with patch.object(dr, "_load_restore_data", new=fake_load):
        out = await dr.load_manual_overrides(hass, _cfg())

    assert out["d9"]["state"] is True
    assert out["d9"]["since"] == NOW
    assert "until" not in out["d9"]


# --- status resolution ------------------------------------------------------

def test_manual_timer_status_wins_over_manual_active():
    device_status = {"d1": {"manual_timer": True, "manual_active": True, "refusal_reasons": []}}
    key, _ = _resolve_device_status("d1", device_status, 100.0, True)
    assert key == DEVICE_STATUS_MANUAL_TIMER


def test_plain_manual_active_without_timer():
    device_status = {"d1": {"manual_active": True, "refusal_reasons": []}}
    key, _ = _resolve_device_status("d1", device_status, 100.0, True)
    assert key == DEVICE_STATUS_MANUAL_ACTIVE
