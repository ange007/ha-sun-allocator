"""Integration-level tests for on-time session accounting across _control_one_device
exit paths (R1.1) and the deferred session/grace start recording (R1.2).

Drives the real `_control_one_device` with a fake hass + patched relay-command calls,
so the full gate pipeline runs. Verifies the two audit-confirmed bugs are fixed:
- a running device shed by the schedule/usable filter or the discharge stop-floor
  closes its on-time session (was silently dropped → runtime/max-on-time undercount);
- a start vetoed by the SOC gate records NO last_on_time and NO grace deadline (was a
  phantom session + per-cycle persist_grace_state flash churn).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sun_allocator.const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_NAME,
    CONF_DEVICE_MIN_EXPECTED_W,
    CONF_DEVICE_MAX_EXPECTED_W,
    CONF_DEVICE_MIN_ON_TIME,
    CONF_DEVICE_DEBOUNCE_TIME,
    CONF_DEVICE_START_BATTERY_SOC,
    CONF_DEVICE_SCHEDULE_MODE,
    SCHEDULE_MODE_DISABLED,
    CONF_POWER_ALLOCATION,
    KEY_STARTUP_GRACE_PERIOD,
)
from custom_components.sun_allocator.core import power_processor as pp

NOW = datetime(2026, 7, 3, 12, 0, 0, tzinfo=timezone.utc)


class _State:
    def __init__(self, state):
        self.state = state
        self.last_changed = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _Hass:
    def __init__(self, relay_state):
        self._relay = _State(relay_state)
        self.services = MagicMock()

    class _States:
        def __init__(self, outer):
            self._outer = outer

        def get(self, _eid):
            return self._outer._relay
    @property
    def states(self):
        return _Hass._States(self)

    def async_create_task(self, coro):
        # persist_grace_state is patched to a recorder (non-coro); tolerate both.
        try:
            coro.close()
        except (AttributeError, TypeError):
            pass


def _device(**extra):
    d = {
        CONF_DEVICE_ID: "d1",
        CONF_DEVICE_NAME: "Dev",
        CONF_DEVICE_ENTITY: "switch.x",
        CONF_DEVICE_MIN_EXPECTED_W: 100.0,
        CONF_DEVICE_MAX_EXPECTED_W: 110.0,
        CONF_DEVICE_MIN_ON_TIME: 0,
        CONF_DEVICE_DEBOUNCE_TIME: 0,
        CONF_DEVICE_SCHEDULE_MODE: SCHEDULE_MODE_DISABLED,
        KEY_STARTUP_GRACE_PERIOD: 90,
    }
    d.update(extra)
    return d


def _entry_data(device, *, device_on, on_time=None):
    return {
        "device_status": {"d1": {
            "refusal_reasons": [], "min_expected_w": 100.0, "max_expected_w": 110.0,
            CONF_DEVICE_MIN_ON_TIME: 0, "allow_probe": True,
        }},
        "device_on_state": {"d1": device_on},
        "device_debounce_state": {},
        "device_on_time_state": on_time or {},
        "manual_overrides": {},
        "command_retries": {},
        "last_controlled_at": {},
        "battery_stop_gate_state": {},
        "battery_soc_gate_state": {},
        "device_filter_reasons": {},
        CONF_POWER_ALLOCATION: {},
    }


def _patch(monkeypatch):
    monkeypatch.setattr(pp, "turn_on_entity", AsyncMock())
    monkeypatch.setattr(pp, "turn_off_entity", AsyncMock())
    grace = MagicMock()
    monkeypatch.setattr(pp, "persist_grace_state", grace)
    return grace


async def _run(hass, device, entry_data, **kw):
    return await pp._control_one_device(
        hass, MagicMock(), device,
        cfg={}, entry_data=entry_data, now=NOW, strategy="fill_one_by_one",
        proportional_allocations={}, remaining_power=kw.pop("remaining_power", 500.0),
        battery_soc=kw.pop("battery_soc", None),
        battery_soc_configured=kw.pop("battery_soc_configured", False),
        **kw,
    )


@pytest.mark.asyncio
async def test_soc_blocked_start_records_no_session_and_no_grace(monkeypatch):
    grace = _patch(monkeypatch)
    device = _device(**{CONF_DEVICE_START_BATTERY_SOC: 80.0})
    entry_data = _entry_data(device, device_on=False)   # off, wants on (excess 500)
    hass = _Hass("off")

    await _run(hass, device, entry_data, battery_soc=50.0, battery_soc_configured=True)

    # SOC 50 < start 80 → gate blocks the start. No phantom session / no grace persist.
    assert entry_data["device_on_time_state"].get("d1", {}).get("last_on_time") is None
    assert "startup_until" not in entry_data["device_on_time_state"].get("d1", {})
    grace.assert_not_called()


@pytest.mark.asyncio
async def test_surviving_start_records_session_and_grace(monkeypatch):
    grace = _patch(monkeypatch)
    device = _device()  # no SOC gate
    entry_data = _entry_data(device, device_on=False)
    hass = _Hass("off")

    await _run(hass, device, entry_data, battery_soc=None, battery_soc_configured=False)

    # Start survived every gate → session + grace ARE recorded (post-gate, pre-dispatch).
    assert entry_data["device_on_time_state"]["d1"]["last_on_time"] == NOW
    grace.assert_called_once()


@pytest.mark.asyncio
async def test_filter_off_closes_running_session(monkeypatch):
    _patch(monkeypatch)
    device = _device()
    on_time = {"d1": {"on_time_day": NOW.date(), "on_time_accum_sec": 0.0,
                       "last_on_time": NOW - timedelta(minutes=5)}}
    entry_data = _entry_data(device, device_on=True, on_time=on_time)
    hass = _Hass("unavailable")   # entity unavailable → filter sheds it

    await _run(hass, device, entry_data, battery_soc=None)

    st = entry_data["device_on_time_state"]["d1"]
    assert st.get("last_on_time") is None                 # session closed
    assert st["on_time_accum_sec"] == pytest.approx(300.0)  # 5 min folded in


@pytest.mark.asyncio
async def test_auto_stop_floor_closes_running_session(monkeypatch):
    _patch(monkeypatch)
    device = _device()
    on_time = {"d1": {"on_time_day": NOW.date(), "on_time_accum_sec": 0.0,
                       "last_on_time": NOW - timedelta(minutes=4)}}
    entry_data = _entry_data(device, device_on=True, on_time=on_time)
    hass = _Hass("on")

    # Discharging + SOC below the protection floor → stop-floor forces the running device
    # off. This path previously left the session open (auto vs manual inconsistency).
    await _run(hass, device, entry_data, battery_soc=50.0, battery_soc_configured=True,
               discharging=True, protection_soc=80.0)

    st = entry_data["device_on_time_state"]["d1"]
    assert st.get("last_on_time") is None
    assert st["on_time_accum_sec"] == pytest.approx(240.0)
