"""Tests for the throttled ON-command retry + ``unreachable`` escalation.

Covers ``_control_standard_device``'s retry policy (see A13):
- first command on a fresh ON decision fires immediately;
- while the relay stays OFF, re-sends are throttled to one per
  ``COMMAND_RETRY_INTERVAL_SECONDS`` and never permanently give up;
- after ``UNREACHABLE_AFTER_RETRIES`` unanswered re-sends the device is
  surfaced as ``unreachable`` (suppressed for climate);
- a relay that finally confirms ON clears the retry bookkeeping.
"""

from datetime import datetime, timedelta, timezone

from custom_components.sun_allocator.const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_ENTITY,
)
from custom_components.sun_allocator.core import power_processor as pp
from custom_components.sun_allocator.sensor.utils import (
    DEVICE_STATUS_TRYING_ON,
    DEVICE_STATUS_UNREACHABLE,
    _resolve_device_status,
)

T0 = datetime(2026, 7, 2, 10, 0, 0, tzinfo=timezone.utc)


class _State:
    def __init__(self, state):
        self.state = state
        self.last_changed = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _Services:
    def async_call(self, *a, **k):
        async def _noop():
            return None
        return _noop()


class _Hass:
    def __init__(self, entity_state):
        self._entity_state = entity_state
        self.services = _Services()

    class _States:
        def __init__(self, outer):
            self._outer = outer

        def get(self, _eid):
            return self._outer._entity_state
    @property
    def states(self):
        return _Hass._States(self)

    def async_create_task(self, coro):
        try:
            coro.close()
        except Exception:
            pass
        return None


def _install_patches():
    """Patch the service-call helpers; return (calls list, restore fn)."""
    calls = []
    orig_on = pp.turn_on_entity
    orig_off = pp.turn_off_entity
    orig_power = pp._resolve_standard_power_used

    async def _fake_on(hass, entity, hvac, name):
        calls.append(("on", entity))

    async def _fake_off(hass, entity, name):
        calls.append(("off", entity))

    def _fake_power(*a, **k):
        return 100.0

    pp.turn_on_entity = _fake_on
    pp.turn_off_entity = _fake_off
    pp._resolve_standard_power_used = _fake_power

    def restore():
        pp.turn_on_entity = orig_on
        pp.turn_off_entity = orig_off
        pp._resolve_standard_power_used = orig_power

    return calls, restore


async def _cycle(hass, device, entry_data, *, is_active, prev_on, now):
    status_entry = {"refusal_reasons": [], "max_expected_w": 100.0}
    await pp._control_standard_device(
        hass, device, is_active, prev_on, 500.0, {}, status_entry,
        entry_data["device_on_state"], device_sensor_cache={},
        device_on_time_state={}, now=now, entry_data=entry_data,
    )
    return status_entry


def _status(status_entry, device_id, entry_data):
    entry_data["device_status"] = {device_id: status_entry}
    key, _ = _resolve_device_status(device_id, entry_data["device_status"], 100.0, True)
    return key


async def test_fresh_command_sends_immediately_then_throttles():
    calls, restore = _install_patches()
    try:
        hass = _Hass(_State("off"))  # relay never confirms ON (unresponsive)
        device = {CONF_DEVICE_ID: "d", CONF_DEVICE_NAME: "AC", CONF_DEVICE_ENTITY: "switch.ac"}
        entry_data = {"command_retries": {}, "device_on_state": {}, "device_status": {}}

        # Fresh ON decision → immediate command, no re-send yet, not unreachable.
        st = await _cycle(hass, device, entry_data, is_active=True, prev_on=False, now=T0)
        assert len(calls) == 1
        assert "unreachable" not in st
        assert entry_data["command_retries"]["d"]["count"] == 0

        # +60s: below the interval → NO re-send.
        st = await _cycle(hass, device, entry_data, is_active=True, prev_on=True,
                          now=T0 + timedelta(seconds=60))
        assert len(calls) == 1

        # +120s: interval elapsed → 1st re-send, count 1 → trying_on, not yet unreachable.
        st = await _cycle(hass, device, entry_data, is_active=True, prev_on=True,
                          now=T0 + timedelta(seconds=120))
        assert len(calls) == 2
        assert entry_data["command_retries"]["d"]["count"] == 1
        assert "unreachable" not in st
        assert _status(st, "d", entry_data) == DEVICE_STATUS_TRYING_ON

        # +240s: 2nd re-send, count 2 → unreachable.
        st = await _cycle(hass, device, entry_data, is_active=True, prev_on=True,
                          now=T0 + timedelta(seconds=240))
        assert len(calls) == 3
        assert entry_data["command_retries"]["d"]["count"] == 2
        assert st.get("unreachable") is True
        assert _status(st, "d", entry_data) == DEVICE_STATUS_UNREACHABLE
    finally:
        restore()


async def test_relay_confirms_on_clears_retry():
    calls, restore = _install_patches()
    try:
        hass = _Hass(_State("off"))
        device = {CONF_DEVICE_ID: "d", CONF_DEVICE_NAME: "AC", CONF_DEVICE_ENTITY: "switch.ac"}
        entry_data = {"command_retries": {}, "device_on_state": {}, "device_status": {}}

        await _cycle(hass, device, entry_data, is_active=True, prev_on=False, now=T0)
        assert "d" in entry_data["command_retries"]

        # Relay now reports ON → bookkeeping cleared.
        hass._entity_state = _State("on")
        await _cycle(hass, device, entry_data, is_active=True, prev_on=True,
                    now=T0 + timedelta(seconds=200))
        assert "d" not in entry_data["command_retries"]
    finally:
        restore()


async def test_climate_never_marked_unreachable():
    calls, restore = _install_patches()
    try:
        hass = _Hass(_State("off"))  # climate reports off (thermostat satisfied)
        device = {CONF_DEVICE_ID: "c", CONF_DEVICE_NAME: "Floor", CONF_DEVICE_ENTITY: "climate.floor"}
        entry_data = {"command_retries": {}, "device_on_state": {}, "device_status": {}}

        await _cycle(hass, device, entry_data, is_active=True, prev_on=False, now=T0)
        await _cycle(hass, device, entry_data, is_active=True, prev_on=True,
                    now=T0 + timedelta(seconds=120))
        st = await _cycle(hass, device, entry_data, is_active=True, prev_on=True,
                         now=T0 + timedelta(seconds=240))
        # Reached count 2 but climate is exempt from the unreachable escalation.
        assert entry_data["command_retries"]["c"]["count"] == 2
        assert "unreachable" not in st
    finally:
        restore()
