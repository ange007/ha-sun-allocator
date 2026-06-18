"""Deterministic unit tests for the minimum-on-time guard.

The previous version drove this through the full allocator with real
``asyncio.sleep`` calls, which raced the debounce + min-on-time windows and was
flaky. The guard lives in the pure helper ``_apply_min_on_time`` (it takes ``now``
as a parameter), so we test it directly with controlled timestamps. End-to-end
on/off behaviour is covered by ``test_device.py``.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from custom_components.sun_allocator.const import KEY_STARTUP_GRACE_PERIOD
from custom_components.sun_allocator.core import power_processor as pp


def _now():
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _no_persist(monkeypatch):
    # Avoid creating the persist coroutine (and its "never awaited" warning).
    monkeypatch.setattr(pp, "persist_grace_state", lambda *a, **k: None)


def _apply(state, status, *, is_active, prev_on, now, min_on_time, device=None):
    return pp._apply_min_on_time(
        MagicMock(), MagicMock(), device or {KEY_STARTUP_GRACE_PERIOD: 0},
        "d", state, status, is_active, prev_on, now, min_on_time,
    )


def test_records_last_on_time_on_turn_on():
    state, status, now = {}, {"refusal_reasons": []}, _now()
    res = _apply(state, status, is_active=True, prev_on=False, now=now, min_on_time=2)
    assert res is True
    assert state["d"]["last_on_time"] == now
    assert status["last_on_time"] == now


def test_blocks_turn_off_before_min_elapsed():
    now = _now()
    state = {"d": {"last_on_time": now - timedelta(seconds=1)}}  # on for 1s
    status = {"refusal_reasons": []}
    # wants off (prev_on True, is_active False) but only 1s < 2s min → keep on.
    res = _apply(state, status, is_active=False, prev_on=True, now=now, min_on_time=2)
    assert res is True
    assert any("Minimum on-time" in r for r in status["refusal_reasons"])
    assert "last_on_time" in state["d"]  # not cleared — still on


def test_allows_turn_off_after_min_elapsed():
    now = _now()
    state = {"d": {"last_on_time": now - timedelta(seconds=5)}}  # on for 5s > 2s
    status = {"refusal_reasons": []}
    res = _apply(state, status, is_active=False, prev_on=True, now=now, min_on_time=2)
    assert res is False  # allowed to turn off
    assert status["refusal_reasons"] == []
    assert state["d"]["last_off_time"] == now
    assert "last_on_time" not in state["d"]


def test_min_on_time_zero_allows_immediate_off():
    now = _now()
    state = {"d": {"last_on_time": now}}
    status = {"refusal_reasons": []}
    res = _apply(state, status, is_active=False, prev_on=True, now=now, min_on_time=0)
    assert res is False


def test_passthrough_when_staying_on():
    now = _now()
    res = _apply({}, {"refusal_reasons": []}, is_active=True, prev_on=True, now=now, min_on_time=2)
    assert res is True


def test_passthrough_when_staying_off():
    now = _now()
    res = _apply({}, {"refusal_reasons": []}, is_active=False, prev_on=False, now=now, min_on_time=2)
    assert res is False
