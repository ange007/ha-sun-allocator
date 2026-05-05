"""Tests for device restore/persist logic."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sun_allocator.const import (
    CONF_DEVICES,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_ID,
    CONF_ESPHOME_MODE_SELECT_ENTITY,
)
from custom_components.sun_allocator.core import device_restore as dr


def _entry(devices):
    cfg = MagicMock()
    cfg.entry_id = "entry_x"
    cfg.data = {CONF_DEVICES: devices}
    return cfg


@pytest.mark.asyncio
async def test_persist_device_state_writes_only_when_changed():
    hass = MagicMock()
    cfg = _entry([])
    storage = {"switch.x": {"last_percent": 50, "_restore_on": True}}
    save_mock = AsyncMock()

    with patch.object(dr, "_load_restore_data", new_callable=AsyncMock, return_value=storage), \
         patch.object(dr, "_save_restore_data", new=save_mock):
        # Same values — no save.
        await dr.persist_device_state(hass, cfg, "switch.x", percent=50, is_on=True)
        save_mock.assert_not_awaited()
        # Different percent — save fires.
        await dr.persist_device_state(hass, cfg, "switch.x", percent=80, is_on=True)
        save_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_restore_entity_state_climate_round_trip():
    """A climate entity stored as `climate.x|heat` must be restored with the suffix attached."""
    hass = MagicMock()
    devices = [{CONF_DEVICE_ID: "d1", CONF_DEVICE_ENTITY: "climate.heater|heat_cool"}]
    cfg = _entry(devices)
    storage = {"climate.heater": {"_restore_on": True}}
    state = MagicMock()
    state.state = "off"
    hass.states.get.return_value = state

    set_power = AsyncMock()
    with patch.object(dr, "_load_restore_data", new_callable=AsyncMock, return_value=storage), \
         patch.object(dr, "set_power_for_entity", new=set_power):
        await dr.restore_entity_state(hass, cfg, "climate.heater")

    set_power.assert_awaited_once_with(hass, "climate.heater|heat_cool", 100)


@pytest.mark.asyncio
async def test_restore_entity_state_pipe_split_uses_max_split():
    """Pipe-only-once: a stray '|' inside hvac_mode must not break the base entity match."""
    hass = MagicMock()
    devices = [{CONF_DEVICE_ID: "d1", CONF_DEVICE_ENTITY: "switch.x|legacy|garbage"}]
    cfg = _entry(devices)
    storage = {"switch.x": {"_restore_on": True}}
    state = MagicMock()
    state.state = "off"
    hass.states.get.return_value = state

    set_power = AsyncMock()
    with patch.object(dr, "_load_restore_data", new_callable=AsyncMock, return_value=storage), \
         patch.object(dr, "set_power_for_entity", new=set_power):
        await dr.restore_entity_state(hass, cfg, "switch.x")

    # Single split → base "switch.x", suffix "legacy|garbage". Switch (non-climate) ignores suffix.
    set_power.assert_awaited_once_with(hass, "switch.x", 100)


@pytest.mark.asyncio
async def test_restore_all_skips_devices_already_in_target_state():
    hass = MagicMock()
    devices = [{CONF_DEVICE_ID: "d1", CONF_DEVICE_ENTITY: "switch.x"}]
    cfg = _entry(devices)
    storage = {"switch.x": {"_restore_on": True}}
    state = MagicMock()
    state.state = "on"
    hass.states.get.return_value = state

    set_power = AsyncMock()
    with patch.object(dr, "_load_restore_data", new_callable=AsyncMock, return_value=storage), \
         patch.object(dr, "set_power_for_entity", new=set_power):
        await dr.restore_all_devices(hass, cfg)

    set_power.assert_not_awaited()


@pytest.mark.asyncio
async def test_grace_state_round_trip():
    """Persist + load grace state preserves the deadline."""
    hass = MagicMock()
    cfg = _entry([])
    storage: dict = {}

    async def fake_load(_hass, _cfg):
        # Mirror Store.async_load which returns a freshly-deserialised dict each call.
        import copy
        return copy.deepcopy(storage)

    async def fake_save(_hass, _cfg, data):
        storage.clear()
        storage.update(data)

    deadline = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    with patch.object(dr, "_load_restore_data", new=fake_load), \
         patch.object(dr, "_save_restore_data", new=fake_save):
        await dr.persist_grace_state(hass, cfg, "dev1", deadline)
        loaded = await dr.load_grace_state(hass, cfg)

    assert loaded == {"dev1": deadline}


@pytest.mark.asyncio
async def test_grace_state_clear_on_none():
    hass = MagicMock()
    cfg = _entry([])
    storage = {dr._GRACE_STORAGE_KEY: {"dev1": "2026-01-01T12:00:00+00:00"}}

    async def fake_load(_hass, _cfg):
        return storage

    save_mock = AsyncMock()

    with patch.object(dr, "_load_restore_data", new=fake_load), \
         patch.object(dr, "_save_restore_data", new=save_mock):
        await dr.persist_grace_state(hass, cfg, "dev1", None)

    save_mock.assert_awaited_once()
    saved_data = save_mock.call_args.args[2]
    assert "dev1" not in saved_data[dr._GRACE_STORAGE_KEY]


@pytest.mark.asyncio
async def test_grace_state_idempotent_when_value_unchanged():
    """Re-persisting the same deadline must not write to storage again."""
    hass = MagicMock()
    cfg = _entry([])
    deadline = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    storage = {dr._GRACE_STORAGE_KEY: {"dev1": deadline.isoformat()}}

    async def fake_load(_hass, _cfg):
        return storage

    save_mock = AsyncMock()
    with patch.object(dr, "_load_restore_data", new=fake_load), \
         patch.object(dr, "_save_restore_data", new=save_mock):
        await dr.persist_grace_state(hass, cfg, "dev1", deadline)

    save_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_load_grace_state_drops_malformed_entries():
    hass = MagicMock()
    cfg = _entry([])
    storage = {
        dr._GRACE_STORAGE_KEY: {
            "ok": "2026-01-01T12:00:00+00:00",
            "bad": "not-a-date",
            "alsobad": 12345,
        }
    }

    async def fake_load(_hass, _cfg):
        return storage

    with patch.object(dr, "_load_restore_data", new=fake_load):
        loaded = await dr.load_grace_state(hass, cfg)

    assert list(loaded) == ["ok"]


@pytest.mark.asyncio
async def test_restore_all_restores_mode_select_first():
    """Restoring the mode_select before the relay matters for ESPHome devices in proportional mode."""
    hass = MagicMock()
    devices = [
        {
            CONF_DEVICE_ID: "d1",
            CONF_DEVICE_ENTITY: "light.bulb",
            CONF_ESPHOME_MODE_SELECT_ENTITY: "select.bulb_mode",
        }
    ]
    cfg = _entry(devices)
    storage = {
        "select.bulb_mode": {"last_mode": "Proportional"},
        "light.bulb": {"last_percent": 70},
    }

    state_select = MagicMock()
    state_select.state = "Off"

    def states_get(entity_id):
        return state_select if entity_id == "select.bulb_mode" else None

    hass.states.get.side_effect = states_get

    set_mode = AsyncMock()
    set_power = AsyncMock()
    with patch.object(dr, "_load_restore_data", new_callable=AsyncMock, return_value=storage), \
         patch.object(dr, "set_mode_for_entity", new=set_mode), \
         patch.object(dr, "set_power_for_entity", new=set_power):
        await dr.restore_all_devices(hass, cfg)

    # Order: mode first, then power.
    set_mode.assert_awaited_once_with(hass, "select.bulb_mode", "Proportional")
    set_power.assert_awaited_once_with(hass, "light.bulb", 70)
