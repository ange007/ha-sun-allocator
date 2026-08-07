"""Watchdog liveness: a live excess sensor holding a steady value (0 W all night with the
PV dark) must NOT be treated as stale. Only a genuinely unavailable/unknown sensor may trip
the fail-safe OFF. Regression for a real incident: the nightly flat 0 W froze the change-
driven `watchdog_last_seen` and the fail-safe forced a manually-run device off every 3 min.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.util import dt as dt_util

from custom_components.sun_allocator.core import watchdog as wd


def _cfg():
    c = MagicMock()
    c.domain = "sun_allocator"
    c.entry_id = "e1"
    c.data = {"devices": [{"device_entity": "switch.ac"}]}
    return c


def _hass(entry_data, excess_state):
    hass = MagicMock()
    hass.data = {"sun_allocator": {"e1": entry_data}}
    st = None if excess_state is None else MagicMock(state=excess_state)
    hass.states.get.return_value = st
    hass.services.async_call = AsyncMock()
    return hass


def _entry_data():
    return {
        "excess_sensor_id": "sensor.sun_allocator_excess_power",
        "watchdog_last_seen": dt_util.utcnow() - timedelta(minutes=10),  # long "stale"
        "watchdog_alerted": False,
        "device_on_state": {"ac": True},
        "manual_overrides": {"ac": {"state": True}},
    }


@pytest.mark.asyncio
async def test_live_flat_numeric_is_not_stale():
    ed = _entry_data()
    hass = _hass(ed, "0.0")  # PV dark → excess a steady 0 W, but the sensor is ALIVE
    cfg = _cfg()

    await wd.watchdog_check(hass, cfg)

    # No fail-safe: state + override untouched, and last_seen refreshed from liveness.
    assert ed["device_on_state"]["ac"] is True
    assert "ac" in ed["manual_overrides"]
    hass.services.async_call.assert_not_awaited()
    assert (dt_util.utcnow() - ed["watchdog_last_seen"]).total_seconds() < 5


@pytest.mark.asyncio
async def test_live_again_clears_alert():
    ed = _entry_data()
    ed["watchdog_alerted"] = True  # was in fail-safe
    hass = _hass(ed, "150")

    await wd.watchdog_check(hass, _cfg())

    assert ed["watchdog_alerted"] is False
    hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_unavailable_excess_fires_failsafe():
    ed = _entry_data()
    hass = _hass(ed, "unavailable")  # genuine death (inverter comms lost)

    await wd.watchdog_check(hass, _cfg())

    # Fail-safe OFF: relays commanded off, state reset, overrides cleared.
    hass.services.async_call.assert_awaited()
    assert ed["device_on_state"]["ac"] is False
    assert "manual_overrides" not in ed or "ac" not in ed.get("manual_overrides", {})
    assert ed["watchdog_alerted"] is True


@pytest.mark.asyncio
async def test_non_numeric_excess_falls_through_to_staleness():
    ed = _entry_data()
    hass = _hass(ed, "not_a_number")

    await wd.watchdog_check(hass, _cfg())

    # Unparsable reading is not "alive" → staleness applies → fail-safe.
    hass.services.async_call.assert_awaited()
    assert ed["watchdog_alerted"] is True
