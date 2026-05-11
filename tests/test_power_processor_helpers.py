"""Unit tests for the small helpers extracted from process_excess_power."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from custom_components.sun_allocator.const import (
    CONF_DEVICE_ACTIVE_FEEDBACK_SENSOR,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
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


@pytest.mark.asyncio
async def test_control_standard_device_reports_live_feedback_while_target_is_off(monkeypatch):
    hass = MagicMock()
    hass.states.get.side_effect = lambda entity_id: {
        "switch.heater": _state("off"),
        "binary_sensor.heater_active": _state("on"),
    }.get(entity_id)

    async def _turn_off_entity(*_args, **_kwargs):
        return None

    monkeypatch.setattr(pp, "parse_relay_entity", lambda entity_id: (entity_id, None))
    monkeypatch.setattr(pp, "is_entity_on", lambda _domain, state: state.state == "on")
    monkeypatch.setattr(pp, "turn_off_entity", _turn_off_entity)

    device = {
        CONF_DEVICE_ID: "heater_1",
        CONF_DEVICE_NAME: "Heater 1",
        CONF_DEVICE_ENTITY: "switch.heater",
        CONF_DEVICE_ACTIVE_FEEDBACK_SENSOR: "binary_sensor.heater_active",
    }
    status_entry = {
        "min_expected_w": 900.0,
        "max_expected_w": 990.0,
        "actual_power_threshold_w": 50.0,
        "refusal_reasons": [],
    }

    power_used, updated = await pp._control_standard_device(
        hass,
        device,
        False,
        False,
        0.0,
        {},
        status_entry,
        {},
        {},
        datetime.now(tz=timezone.utc),
    )

    assert power_used == 900.0
    assert updated["allocated_w"] == 900.0
    assert updated["percent_actual"] == 100.0
    assert updated["is_enabled"] is False
    assert updated["is_consuming"] is True
