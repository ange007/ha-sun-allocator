"""Unit tests for battery-SOC gating, actual-power accounting and idle status.

Covers the per-device features layered on top of the allocator:
- ``_apply_battery_soc_gate``  — fail-open / fail-safe / hysteresis semantics
- ``_startup_reserve_active``  — startup-grace budget reservation window
- ``_resolve_standard_power_used`` — measured vs estimated vs idle accounting
- ``_resolve_device_status``   — the ``idle`` ENUM state
"""

from datetime import datetime, timedelta, timezone

from custom_components.sun_allocator.const import (
    CONF_DEVICE_ACTUAL_POWER_SENSOR,
    CONF_DEVICE_ACTUAL_POWER_THRESHOLD_W,
    CONF_DEVICE_MAX_ON_TIME_PER_DAY,
    CONF_DEVICE_MIN_BATTERY_SOC,
    CONF_DEVICE_NAME,
    DEFAULT_BATTERY_SOC_HYSTERESIS,
)
from custom_components.sun_allocator.core import power_processor as pp
from custom_components.sun_allocator.sensor.utils import (
    DEVICE_STATUS_ACTIVE,
    DEVICE_STATUS_DEBOUNCING_OFF,
    DEVICE_STATUS_IDLE,
    DEVICE_STATUS_INSUFFICIENT_POWER,
    _resolve_device_status,
)


# --- Battery SOC gate -------------------------------------------------------

def _gate(min_soc, soc, configured, *, is_active=True, prev_on=False, gate_state=None):
    device = {CONF_DEVICE_MIN_BATTERY_SOC: min_soc, CONF_DEVICE_NAME: "x"}
    status = {"refusal_reasons": []}
    gs = gate_state if gate_state is not None else {}
    res = pp._apply_battery_soc_gate(
        device, "d", is_active, prev_on, soc, configured, gs, status
    )
    return res, status, gs


def test_soc_gate_running_device_never_blocked_and_clears_sticky():
    # prev_on=True → never gated, and a prior block is cleared.
    res, _, gs = _gate(80, 10.0, True, prev_on=True, gate_state={"d": True})
    assert res is True
    assert "d" not in gs


def test_soc_gate_no_requirement_passthrough():
    res, _, _ = _gate(0, 5.0, True)
    assert res is True


def test_soc_gate_no_sensor_configured_fail_open():
    # min set but hub sensor missing → requirement meaningless → allow start.
    res, status, _ = _gate(80, None, False)
    assert res is True
    assert status["refusal_reasons"] == []


def test_soc_gate_sensor_unavailable_fail_safe_and_sticky():
    # sensor configured but unavailable → block, and mark sticky.
    res, status, gs = _gate(80, None, True)
    assert res is False
    assert gs["d"] is True
    assert any("unavailable" in r for r in status["refusal_reasons"])


def test_soc_gate_never_blocked_allows_at_min():
    # Key hysteresis behaviour: a device that has never been blocked may start at
    # exactly ``min`` — even within the [min, min+hysteresis] band.
    res, _, gs = _gate(80, 80.0, True)
    assert res is True
    assert "d" not in gs


def test_soc_gate_never_blocked_allows_within_band():
    res, _, _ = _gate(80, 80 + DEFAULT_BATTERY_SOC_HYSTERESIS - 1, True)
    assert res is True


def test_soc_gate_below_min_blocks_and_sets_sticky():
    res, status, gs = _gate(80, 79.0, True)
    assert res is False
    assert gs["d"] is True
    assert status["refusal_reasons"]


def test_soc_gate_blocked_stays_until_recovery():
    # Once blocked, SOC within the band is NOT enough — needs min+hysteresis.
    res, status, gs = _gate(
        80, 80 + DEFAULT_BATTERY_SOC_HYSTERESIS - 1, True, gate_state={"d": True}
    )
    assert res is False
    assert gs["d"] is True
    assert any("recovery" in r for r in status["refusal_reasons"])


def test_soc_gate_blocked_clears_at_recovery():
    res, _, gs = _gate(
        80, 80 + DEFAULT_BATTERY_SOC_HYSTERESIS, True, gate_state={"d": True}
    )
    assert res is True
    assert "d" not in gs


def test_soc_gate_inactive_candidate_unchanged():
    # not is_active → returned unchanged (gate only blocks would-be starts).
    res, _, _ = _gate(80, 10.0, True, is_active=False)
    assert res is False


# --- Startup reserve window -------------------------------------------------

def test_startup_reserve_none_now_is_false():
    assert pp._startup_reserve_active({"d": {"startup_until": object()}}, "d", None) is False


def test_startup_reserve_future_deadline_true():
    now = datetime.now(tz=timezone.utc)
    state = {"d": {"startup_until": now + timedelta(seconds=30)}}
    assert pp._startup_reserve_active(state, "d", now) is True


def test_startup_reserve_past_deadline_false():
    now = datetime.now(tz=timezone.utc)
    state = {"d": {"startup_until": now - timedelta(seconds=1)}}
    assert pp._startup_reserve_active(state, "d", now) is False


def test_startup_reserve_absent_false():
    assert pp._startup_reserve_active({"d": {}}, "d", datetime.now(tz=timezone.utc)) is False


# --- Standard-device power accounting ---------------------------------------

def _power(device, status, *, cache, now=None, on_time_state=None):
    return pp._resolve_standard_power_used(
        hass=None,
        device=device,
        status_entry=status,
        device_on_time_state=on_time_state or {},
        device_id="d",
        now=now,
        device_sensor_cache=cache,
    )


def test_power_no_actual_sensor_uses_min_expected():
    status = {"min_expected_w": 300.0, "is_idle": True}
    used = _power({}, status, cache={})
    assert used == 300.0
    assert "is_idle" not in status  # cleared when no feedback sensor


def test_power_actual_above_threshold_is_measured():
    device = {
        CONF_DEVICE_ACTUAL_POWER_SENSOR: "sensor.p",
        CONF_DEVICE_ACTUAL_POWER_THRESHOLD_W: 10,
    }
    status = {"min_expected_w": 300.0}
    used = _power(device, status, cache={"sensor.p": (250.0, True)})
    assert used == 250.0
    assert status["is_idle"] is False


def test_power_below_threshold_during_grace_reserves_min():
    now = datetime.now(tz=timezone.utc)
    device = {
        CONF_DEVICE_ACTUAL_POWER_SENSOR: "sensor.p",
        CONF_DEVICE_ACTUAL_POWER_THRESHOLD_W: 10,
    }
    status = {"min_expected_w": 300.0}
    on_time = {"d": {"startup_until": now + timedelta(seconds=30)}}
    used = _power(device, status, cache={"sensor.p": (2.0, True)}, now=now, on_time_state=on_time)
    assert used == 300.0  # reserved, not freed — load not ramped yet
    assert status["is_idle"] is False
    assert status["reserved_w"] == 300.0


def test_power_below_threshold_after_grace_is_idle():
    now = datetime.now(tz=timezone.utc)
    device = {
        CONF_DEVICE_ACTUAL_POWER_SENSOR: "sensor.p",
        CONF_DEVICE_ACTUAL_POWER_THRESHOLD_W: 10,
    }
    status = {"min_expected_w": 300.0}
    used = _power(device, status, cache={"sensor.p": (2.0, True)}, now=now, on_time_state={})
    assert used == 0.0  # genuinely idle → free the budget
    assert status["is_idle"] is True


def test_power_sensor_unavailable_falls_back_to_min():
    device = {CONF_DEVICE_ACTUAL_POWER_SENSOR: "sensor.p"}
    status = {"min_expected_w": 300.0, "is_idle": True}
    used = _power(device, status, cache={"sensor.p": (0.0, False)})
    assert used == 300.0
    assert "is_idle" not in status


# --- Idle device status -----------------------------------------------------

def _status(**st):
    return _resolve_device_status("d", {"d": st}, st.get("_alloc", 0.0), True)


def test_status_idle_when_enabled_and_idle_flag():
    key, _ = _status(is_enabled=True, is_idle=True, is_active_candidate=True)
    assert key == DEVICE_STATUS_IDLE


def test_status_active_when_enabled_not_idle():
    key, _ = _status(is_enabled=True, is_idle=False, is_active_candidate=True)
    assert key == DEVICE_STATUS_ACTIVE


def test_status_debouncing_off_when_candidate_false():
    key, _ = _status(is_enabled=True, is_active_candidate=False)
    assert key == DEVICE_STATUS_DEBOUNCING_OFF


def test_status_not_enabled_is_insufficient():
    key, _ = _status(is_enabled=False, is_active_candidate=False)
    assert key == DEVICE_STATUS_INSUFFICIENT_POWER


def test_status_fallback_to_allocated_power_when_no_is_enabled():
    # Devices that don't set is_enabled (custom/proportional) fall back to
    # allocated_power > 0 → ACTIVE, preserving prior behaviour.
    key, _ = _resolve_device_status(
        "d", {"d": {"is_active_candidate": True}}, 150.0, True
    )
    assert key == DEVICE_STATUS_ACTIVE


# --- Daily on-time accounting + max-on-time gate ----------------------------

_DAY = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)


def test_daily_on_time_accum_only_when_off():
    state = {"d": {"on_time_day": _DAY.date(), "on_time_accum_sec": 600.0}}
    assert pp._daily_on_time_sec(state, "d", _DAY, currently_on=False) == 600.0


def test_daily_on_time_adds_current_session_when_on():
    state = {
        "d": {
            "on_time_day": _DAY.date(),
            "on_time_accum_sec": 600.0,
            "last_on_time": _DAY - timedelta(seconds=120),
        }
    }
    assert pp._daily_on_time_sec(state, "d", _DAY, currently_on=True) == 720.0


def test_daily_on_time_resets_on_day_rollover():
    state = {"d": {"on_time_day": (_DAY - timedelta(days=1)).date(), "on_time_accum_sec": 9999.0}}
    assert pp._daily_on_time_sec(state, "d", _DAY, currently_on=False) == 0.0


def test_accumulate_folds_session():
    state = {"d": {"on_time_day": _DAY.date(), "on_time_accum_sec": 100.0,
                   "last_on_time": _DAY - timedelta(seconds=60)}}
    pp._accumulate_daily_on_time(state, "d", _DAY)
    assert state["d"]["on_time_accum_sec"] == 160.0


def test_accumulate_resets_then_folds_on_new_day():
    state = {"d": {"on_time_day": (_DAY - timedelta(days=1)).date(), "on_time_accum_sec": 9999.0,
                   "last_on_time": _DAY - timedelta(seconds=30)}}
    pp._accumulate_daily_on_time(state, "d", _DAY)
    assert state["d"]["on_time_day"] == _DAY.date()
    assert state["d"]["on_time_accum_sec"] == 30.0


def test_accumulate_no_entry_is_noop():
    state = {}
    pp._accumulate_daily_on_time(state, "d", _DAY)
    assert state == {}


def _maxgate(max_min, *, prev_on, state):
    device = {CONF_DEVICE_MAX_ON_TIME_PER_DAY: max_min, CONF_DEVICE_NAME: "x"}
    status = {"refusal_reasons": []}
    res = pp._apply_max_on_time_gate(device, "d", True, prev_on, state, _DAY, status)
    return res, status


def test_max_on_time_zero_passthrough():
    res, _ = _maxgate(0, prev_on=False, state={})
    assert res is True


def test_max_on_time_under_limit_allows():
    state = {"d": {"on_time_day": _DAY.date(), "on_time_accum_sec": 60.0}}
    res, _ = _maxgate(10, prev_on=False, state=state)  # 1min used < 10min
    assert res is True


def test_max_on_time_at_limit_blocks_new_start():
    state = {"d": {"on_time_day": _DAY.date(), "on_time_accum_sec": 600.0}}
    res, status = _maxgate(10, prev_on=False, state=state)  # 10min >= 10min
    assert res is False
    assert any("Daily on-time limit" in r for r in status["refusal_reasons"])


def test_max_on_time_blocks_running_and_folds_session():
    # Running device over limit: gate folds the live session and clears last_on_time
    # so it can't immediately restart.
    state = {
        "d": {
            "on_time_day": _DAY.date(),
            "on_time_accum_sec": 540.0,  # 9 min done
            "last_on_time": _DAY - timedelta(seconds=120),  # +2 min live → 11 min
        }
    }
    res, _ = _maxgate(10, prev_on=True, state=state)
    assert res is False
    assert "last_on_time" not in state["d"]
    assert state["d"]["on_time_accum_sec"] == 660.0  # 540 + 120
