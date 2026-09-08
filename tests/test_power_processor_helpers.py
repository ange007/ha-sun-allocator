"""Unit tests for the small helpers extracted from process_excess_power."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from custom_components.sun_allocator.const import (
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_ID,
    CONF_DEVICE_TYPE,
    DEVICE_TYPE_CUSTOM,
    DEVICE_TYPE_STANDARD,
    RELAY_MODE_PROPORTIONAL,
)
from custom_components.sun_allocator.core import power_processor as pp


def _state(value):
    s = MagicMock()
    s.state = value
    return s


def test_sync_initial_skips_when_already_initialized():
    hass = MagicMock()
    hass.states.get.return_value = _state("on")
    devices = [{CONF_DEVICE_ID: "d1", CONF_DEVICE_ENTITY: "switch.x"}]
    state: dict = {}
    entry_data = {"_device_on_state_initialized": True}

    pp._sync_initial_device_states(hass, devices, state, entry_data)

    assert state == {}
    hass.states.get.assert_not_called()


def test_sync_initial_seeds_from_actual_states():
    hass = MagicMock()
    hass.states.get.return_value = _state("on")
    devices = [{CONF_DEVICE_ID: "d1", CONF_DEVICE_ENTITY: "switch.x"}]
    state: dict = {}
    entry_data: dict = {}

    pp._sync_initial_device_states(hass, devices, state, entry_data)

    assert state == {"d1": True}
    assert entry_data["_device_on_state_initialized"] is True


def test_sync_initial_strips_climate_hvac_suffix():
    hass = MagicMock()
    hass.states.get.return_value = _state("heat")
    devices = [{CONF_DEVICE_ID: "d1", CONF_DEVICE_ENTITY: "climate.heater|heat"}]
    state: dict = {}

    pp._sync_initial_device_states(hass, devices, state, {})

    # Climate state != "off" → considered ON.
    assert state == {"d1": True}
    hass.states.get.assert_called_once_with("climate.heater")


def test_sync_initial_skips_unavailable_entities():
    hass = MagicMock()
    hass.states.get.return_value = _state("unavailable")
    devices = [{CONF_DEVICE_ID: "d1", CONF_DEVICE_ENTITY: "switch.x"}]
    state: dict = {}

    pp._sync_initial_device_states(hass, devices, state, {})

    assert state == {}


def test_sync_initial_seeds_fresh_session_for_device_already_on():
    """A device found ON across a restart continues its on-time session from `now`,
    on top of whatever daily total was separately restored (load_on_time_state)."""
    now = datetime(2026, 7, 3, 18, 0, 0, tzinfo=timezone.utc)
    hass = MagicMock()
    hass.states.get.return_value = _state("on")
    devices = [{CONF_DEVICE_ID: "d1", CONF_DEVICE_ENTITY: "switch.x"}]
    state: dict = {}
    on_time_state = {"d1": {"on_time_day": now.date(), "on_time_accum_sec": 120.0}}

    pp._sync_initial_device_states(hass, devices, state, {}, on_time_state, now)

    assert state == {"d1": True}
    assert on_time_state["d1"]["last_on_time"] == now
    assert on_time_state["d1"]["on_time_accum_sec"] == 120.0  # restored total untouched


def test_sync_initial_does_not_seed_session_for_device_off():
    now = datetime(2026, 7, 3, 18, 0, 0, tzinfo=timezone.utc)
    hass = MagicMock()
    hass.states.get.return_value = _state("off")
    devices = [{CONF_DEVICE_ID: "d1", CONF_DEVICE_ENTITY: "switch.x"}]
    state: dict = {}
    on_time_state: dict = {}

    pp._sync_initial_device_states(hass, devices, state, {}, on_time_state, now)

    assert "d1" not in on_time_state


def test_compute_proportional_allocations_distributes_by_max_w(monkeypatch):
    """Two active proportional devices share remaining_power weighted by max_expected_w."""
    monkeypatch.setattr(pp, "_calculate_device_state", lambda *args, **kw: (True, True))
    devices = [
        {CONF_DEVICE_ID: "a", CONF_DEVICE_TYPE: DEVICE_TYPE_CUSTOM},
        {CONF_DEVICE_ID: "b", CONF_DEVICE_TYPE: DEVICE_TYPE_CUSTOM},
    ]
    device_status = {
        "a": {"mode": RELAY_MODE_PROPORTIONAL, "max_expected_w": 1000.0},
        "b": {"mode": RELAY_MODE_PROPORTIONAL, "max_expected_w": 3000.0},
    }
    out = pp._compute_proportional_allocations(
        devices, device_status, 800.0, {}, {}, {}, datetime.now(tz=timezone.utc)
    )
    # Total max_w = 4000W; a gets 25%, b gets 75% of 800W.
    assert out["a"] == pytest.approx(200.0)
    assert out["b"] == pytest.approx(600.0)


def test_compute_proportional_allocations_excludes_inactive(monkeypatch):
    """Inactive proportional devices are not in the pool."""
    seq = iter([(True, True), (False, False)])
    monkeypatch.setattr(pp, "_calculate_device_state", lambda *args, **kw: next(seq))

    devices = [
        {CONF_DEVICE_ID: "a", CONF_DEVICE_TYPE: DEVICE_TYPE_CUSTOM},
        {CONF_DEVICE_ID: "b", CONF_DEVICE_TYPE: DEVICE_TYPE_CUSTOM},
    ]
    device_status = {
        "a": {"mode": RELAY_MODE_PROPORTIONAL, "max_expected_w": 1000.0},
        "b": {"mode": RELAY_MODE_PROPORTIONAL, "max_expected_w": 1000.0},
    }
    out = pp._compute_proportional_allocations(
        devices, device_status, 500.0, {}, {}, {}, datetime.now(tz=timezone.utc)
    )
    assert out == {"a": pytest.approx(500.0)}


def test_compute_proportional_allocations_skips_non_custom():
    devices = [{CONF_DEVICE_ID: "a", CONF_DEVICE_TYPE: DEVICE_TYPE_STANDARD}]
    device_status = {"a": {"mode": RELAY_MODE_PROPORTIONAL, "max_expected_w": 1000.0}}
    out = pp._compute_proportional_allocations(
        devices, device_status, 500.0, {}, {}, {}, datetime.now(tz=timezone.utc)
    )
    assert out == {}


def test_compute_proportional_allocations_returns_empty_when_pool_empty():
    out = pp._compute_proportional_allocations([], {}, 500.0, {}, {}, {}, datetime.now(tz=timezone.utc))
    assert out == {}


# --- daily on-time accounting -----------------------------------------------

def test_daily_on_time_sec_zero_when_never_started():
    now = datetime(2026, 7, 3, 12, 0, 0, tzinfo=timezone.utc)
    assert pp._daily_on_time_sec({}, "d1", now, currently_on=True) == 0.0


def test_daily_on_time_sec_adds_in_progress_session():
    now = datetime(2026, 7, 3, 12, 5, 0, tzinfo=timezone.utc)
    state = {"d1": {"on_time_day": now.date(), "on_time_accum_sec": 60.0,
                     "last_on_time": now - timedelta(minutes=2)}}
    # 60s already accumulated today + a 2-minute session still running.
    assert pp._daily_on_time_sec(state, "d1", now, currently_on=True) == pytest.approx(180.0)


def test_daily_on_time_sec_excludes_in_progress_session_when_off():
    now = datetime(2026, 7, 3, 12, 5, 0, tzinfo=timezone.utc)
    state = {"d1": {"on_time_day": now.date(), "on_time_accum_sec": 60.0,
                     "last_on_time": now - timedelta(minutes=2)}}
    assert pp._daily_on_time_sec(state, "d1", now, currently_on=False) == 60.0


def test_logical_day_boundary_at_reset_time():
    from datetime import date
    # "06:00:00": 05:59 still belongs to the previous date; 06:00 flips to the new one.
    assert pp._logical_day(datetime(2026, 7, 3, 5, 59, tzinfo=timezone.utc), "06:00:00") == date(2026, 7, 2)
    assert pp._logical_day(datetime(2026, 7, 3, 6, 0, tzinfo=timezone.utc), "06:00:00") == date(2026, 7, 3)
    # Minute granularity from the time-picker: boundary at 06:30.
    assert pp._logical_day(datetime(2026, 7, 3, 6, 29, tzinfo=timezone.utc), "06:30:00") == date(2026, 7, 2)
    assert pp._logical_day(datetime(2026, 7, 3, 6, 30, tzinfo=timezone.utc), "06:30:00") == date(2026, 7, 3)
    # "00:00:00" == calendar day; legacy integer-hours still accepted.
    assert pp._logical_day(datetime(2026, 7, 3, 0, 1, tzinfo=timezone.utc), "00:00:00") == date(2026, 7, 3)
    assert pp._logical_day(datetime(2026, 7, 3, 5, 0, tzinfo=timezone.utc), 6) == date(2026, 7, 2)


def test_daily_on_time_sec_resets_on_new_logical_day():
    # 07:00 is past the default 06:00 reset boundary → yesterday's accum is dropped.
    now = datetime(2026, 7, 3, 7, 0, 0, tzinfo=timezone.utc)
    state = {"d1": {"on_time_day": (now - timedelta(days=1)).date(), "on_time_accum_sec": 500.0}}
    assert pp._daily_on_time_sec(state, "d1", now, currently_on=False) == 0.0


def test_daily_on_time_sec_holds_before_reset_time():
    # 00:05 is BEFORE the 06:00 reset → still the previous logical day, accum retained
    # (this is the whole point of the shifted boundary: a late-night total survives midnight).
    now = datetime(2026, 7, 3, 0, 5, 0, tzinfo=timezone.utc)
    state = {"d1": {"on_time_day": pp._logical_day(now, "06:00:00"), "on_time_accum_sec": 500.0}}
    assert pp._daily_on_time_sec(state, "d1", now, currently_on=False) == 500.0
    # With reset_time="00:00:00" (calendar day) the same instant IS a new day → reset.
    state2 = {"d1": {"on_time_day": now.date() - timedelta(days=1), "on_time_accum_sec": 500.0}}
    assert pp._daily_on_time_sec(state2, "d1", now, currently_on=False, reset_time="00:00:00") == 0.0


def test_accumulate_daily_on_time_folds_session_into_accumulator():
    now = datetime(2026, 7, 3, 12, 5, 0, tzinfo=timezone.utc)
    state = {"d1": {"last_on_time": now - timedelta(minutes=3)}}
    pp._accumulate_daily_on_time(state, "d1", now)
    assert state["d1"]["on_time_accum_sec"] == pytest.approx(180.0)


def test_accumulate_daily_on_time_noop_when_never_started():
    now = datetime(2026, 7, 3, 12, 5, 0, tzinfo=timezone.utc)
    state = {"d1": {}}
    pp._accumulate_daily_on_time(state, "d1", now)
    assert state["d1"].get("on_time_accum_sec") is None


# --- _close_on_time_session (R1.1: consistent on→off close) ------------------

def test_close_on_time_session_folds_and_clears():
    now = datetime(2026, 7, 3, 12, 5, 0, tzinfo=timezone.utc)
    state = {"d1": {"on_time_day": now.date(), "on_time_accum_sec": 60.0,
                     "last_on_time": now - timedelta(minutes=3)}}
    pp._close_on_time_session(state, "d1", now)
    assert state["d1"].get("last_on_time") is None          # session closed
    assert state["d1"]["last_off_time"] == now
    assert state["d1"]["on_time_accum_sec"] == pytest.approx(240.0)  # 60 + 180


def test_close_on_time_session_noop_when_no_open_session():
    now = datetime(2026, 7, 3, 12, 5, 0, tzinfo=timezone.utc)
    state = {"d1": {"on_time_day": now.date(), "on_time_accum_sec": 60.0}}  # no last_on_time
    pp._close_on_time_session(state, "d1", now)
    assert state["d1"]["on_time_accum_sec"] == 60.0     # untouched
    assert "last_off_time" not in state["d1"]


def test_close_on_time_session_noop_when_device_absent():
    now = datetime(2026, 7, 3, 12, 5, 0, tzinfo=timezone.utc)
    state: dict = {}
    pp._close_on_time_session(state, "d1", now)  # must not raise
    assert state == {}


def test_max_on_time_gate_closes_session_when_forcing_off():
    # A running device over its daily budget is forced off and its session closed here
    # (the gate bypasses _apply_min_on_time's off-branch).
    from custom_components.sun_allocator.const import (
        CONF_DEVICE_MAX_ON_TIME_PER_DAY, CONF_DEVICE_NAME,
    )
    now = datetime(2026, 7, 3, 12, 0, 0, tzinfo=timezone.utc)
    device = {CONF_DEVICE_NAME: "x", CONF_DEVICE_MAX_ON_TIME_PER_DAY: 60}  # 60 min/day
    # 55 min accumulated + a 10-min running session = 65 min > 60 → force off.
    state = {"d1": {"on_time_day": now.date(), "on_time_accum_sec": 55 * 60.0,
                     "last_on_time": now - timedelta(minutes=10)}}
    status = {"refusal_reasons": []}
    res = pp._apply_max_on_time_gate(device, "d1", True, True, state, now, status)
    assert res is False                                  # forced off
    assert state["d1"].get("last_on_time") is None       # session closed
    assert state["d1"]["on_time_accum_sec"] == pytest.approx(65 * 60.0)


# --- _detect_external_change: restart-safe last_controlled_at ---------------
# Regression: last_controlled_at is purely in-memory (never persisted). A HA restart
# mid-session wipes it while device_on_state/manual_overrides/grace deadlines resync
# or restore from storage. A missing timestamp must NOT default to "user toggled it" —
# that misattributed a stale post-restart mismatch as deliberate user action, sticking
# a phantom manual override (observed live: a device forced OFF seconds after its own
# startup-grace window began, right after a HA restart).

def _relay_state(value, last_changed):
    s = MagicMock()
    s.state = value
    s.last_changed = last_changed
    return s


def _hass_with_relay(state):
    hass = MagicMock()
    hass.states.get.return_value = state
    return hass


def test_no_last_controlled_at_is_not_user_initiated():
    now = datetime(2026, 7, 3, 17, 0, 0, tzinfo=timezone.utc)
    old_change = now - timedelta(hours=16)  # entity hasn't changed since way earlier
    hass = _hass_with_relay(_relay_state("off", old_change))
    device = {CONF_DEVICE_ENTITY: "light.x"}
    entry_data = {}  # fresh post-restart entry_data: no last_controlled_at at all
    device_on_state = {"d1": True}  # we believe it's on (e.g. restored/synced)
    status_entry = {}

    pp._detect_external_change(hass, device, "d1", entry_data, status_entry, device_on_state, now)

    assert "d1" not in entry_data.get("manual_overrides", {})


def test_stale_last_controlled_at_is_not_user_initiated():
    """We commanded it before the entity's last real change → still catching up, not user."""
    now = datetime(2026, 7, 3, 17, 0, 0, tzinfo=timezone.utc)
    old_change = now - timedelta(hours=16)
    hass = _hass_with_relay(_relay_state("off", old_change))
    device = {CONF_DEVICE_ENTITY: "light.x"}
    entry_data = {"last_controlled_at": {"d1": now - timedelta(seconds=5)}}
    device_on_state = {"d1": True}
    status_entry = {}

    pp._detect_external_change(hass, device, "d1", entry_data, status_entry, device_on_state, now)

    assert "d1" not in entry_data.get("manual_overrides", {})


def test_fresh_actual_change_after_our_command_is_user_initiated():
    """The entity changed AFTER we last commanded it → a genuine user toggle."""
    now = datetime(2026, 7, 3, 17, 0, 0, tzinfo=timezone.utc)
    hass = _hass_with_relay(_relay_state("off", now - timedelta(seconds=1)))
    device = {CONF_DEVICE_ENTITY: "light.x"}
    entry_data = {"last_controlled_at": {"d1": now - timedelta(seconds=30)}}
    device_on_state = {"d1": True}
    status_entry = {}

    pp._detect_external_change(hass, device, "d1", entry_data, status_entry, device_on_state, now)

    ov = entry_data["manual_overrides"]["d1"]
    assert ov["state"] is False


def test_stale_mismatch_after_long_dormant_gap_is_not_user_initiated():
    """Regression (confirmed live 2026-07-04): a device dormant for hours (near-zero
    excess overnight, so the control loop barely runs) can have BOTH last_controlled_at
    and the entity's last_changed frozen from the previous evening. Their mere relative
    order — one a few seconds "newer" than the other, both ancient — must not read as
    "the user just toggled it" the instant the loop wakes up hours later."""
    last_controlled = datetime(2026, 7, 3, 22, 54, 44, tzinfo=timezone.utc)
    actual_last_changed = last_controlled + timedelta(seconds=15)  # a same-value flicker
    now = datetime(2026, 7, 4, 10, 32, 19, tzinfo=timezone.utc)  # ~11.5h later
    hass = _hass_with_relay(_relay_state("off", actual_last_changed))
    device = {CONF_DEVICE_ENTITY: "light.x"}
    entry_data = {"last_controlled_at": {"d1": last_controlled}}
    device_on_state = {"d1": True}
    status_entry = {}

    pp._detect_external_change(hass, device, "d1", entry_data, status_entry, device_on_state, now)

    assert "d1" not in entry_data.get("manual_overrides", {})


def test_manual_on_external_off_logs_once_per_episode(monkeypatch):
    """A forced-ON device switched OFF from outside HA (Tuya cloud / socket overload /
    device schedule) keeps its override but is surfaced ONCE per episode — not every cycle,
    and not silently. Realigning (entity back ON) resets the edge so a later drop logs again."""
    warns = MagicMock()
    journals = MagicMock()
    monkeypatch.setattr(pp, "log_warning", warns)
    monkeypatch.setattr(pp, "journal_event", journals)
    now = datetime(2026, 8, 6, 19, 17, 0, tzinfo=timezone.utc)
    device = {CONF_DEVICE_ENTITY: "switch.konditsioner_switch"}
    entry_data = {  # forced ON, no last_controlled_at → the off is "unresponsive", not a user toggle
        "manual_overrides": {"d1": {"state": True, "since": now - timedelta(minutes=5)}},
    }
    device_on_state = {"d1": True}

    off = _hass_with_relay(_relay_state("off", now - timedelta(hours=3)))
    pp._detect_external_change(off, device, "d1", entry_data, {}, device_on_state, now)
    pp._detect_external_change(off, device, "d1", entry_data, {}, device_on_state, now)

    assert warns.call_count == 1               # edge-logged once, not every cycle
    assert journals.call_count == 1
    assert "d1" in entry_data["_external_off_logged"]
    assert entry_data["manual_overrides"]["d1"]["state"] is True  # override kept, not cleared

    # Entity comes back ON (aligned) → flag resets so a future drop logs again.
    on = _hass_with_relay(_relay_state("on", now))
    pp._detect_external_change(on, device, "d1", entry_data, {}, device_on_state, now)
    assert "d1" not in entry_data["_external_off_logged"]


def test_cleared_expected_state_cannot_create_phantom_override():
    """Clean slate on auto-control re-enable: with device_on_state cleared the detector has
    nothing to compare against and must NOT invent a manual override — even for an entity
    that changed on its own (e.g. a climate cycling) while auto-control was disabled.
    Without the clearing, that same reading is misread as a user toggle and sticks a phantom
    override that leaves the device permanently in manual_override, never auto-controlled."""
    now = datetime(2026, 9, 8, 19, 12, 0, tzinfo=timezone.utc)
    hass = _hass_with_relay(_relay_state("heat_cool", now - timedelta(seconds=30)))
    device = {CONF_DEVICE_ENTITY: "climate.x"}

    # Cleared expected state (what the auto-control switch now does on re-enable).
    entry_data = {"last_controlled_at": {"d1": now - timedelta(minutes=5)}}
    pp._detect_external_change(hass, device, "d1", entry_data, {}, {}, now)
    assert "d1" not in entry_data.get("manual_overrides", {})

    # Contrast — the pre-fix path: a STALE expected state turns the same reading into a
    # phantom sticky manual override.
    entry_data_stale = {"last_controlled_at": {"d1": now - timedelta(minutes=5)}}
    pp._detect_external_change(hass, device, "d1", entry_data_stale, {}, {"d1": False}, now)
    assert entry_data_stale["manual_overrides"]["d1"]["state"] is True
