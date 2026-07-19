"""Tests for ConfigEntryMigrator."""

from unittest.mock import MagicMock

import pytest

from custom_components.sun_allocator.const import (
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_SCHEDULE_MODE,
    CONF_CALCULATION_METHOD,
    DEFAULT_CALCULATION_METHOD,
    CALC_METHOD_EXPORT,
    SCHEDULE_MODE_DISABLED,
    SCHEDULE_MODE_STANDARD,
    SCHEDULE_MODE_HELPER,
    CONF_ESPHOME_MODE_SELECT_ENTITY,
    CONF_DEVICE_CONTROL_MODE,
    CONTROL_MODE_ON_OFF,
    CONTROL_MODE_PROPORTIONAL,
    CONF_DEVICE_START_BATTERY_SOC,
    CONF_DEVICE_STOP_BATTERY_SOC,
    DEFAULT_DEVICE_STOP_BATTERY_SOC,
)
from custom_components.sun_allocator.core.migrations import ConfigEntryMigrator


def _entry(data):
    e = MagicMock()
    e.data = data
    return e


def _hass():
    h = MagicMock()
    h.config_entries = MagicMock()
    h.config_entries.async_update_entry = MagicMock()
    return h


@pytest.mark.asyncio
async def test_no_op_when_no_devices_have_old_key():
    """Migrator must not touch a fully-migrated entry (legacy key absent AND
    calculation_method already present)."""
    hass = _hass()
    entry = _entry({
        CONF_CALCULATION_METHOD: DEFAULT_CALCULATION_METHOD,
        CONF_DEVICES: [
            {
                CONF_DEVICE_ID: "a",
                CONF_DEVICE_SCHEDULE_MODE: SCHEDULE_MODE_HELPER,
                CONF_DEVICE_CONTROL_MODE: CONTROL_MODE_ON_OFF,
                CONF_DEVICE_STOP_BATTERY_SOC: DEFAULT_DEVICE_STOP_BATTERY_SOC,
            },
        ],
    })
    changed = await ConfigEntryMigrator(hass, entry).run()
    assert changed is False
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_calculation_method_backfilled_when_missing():
    """An entry without calculation_method gets the default backfilled."""
    hass = _hass()
    # Pre-Phase-B entry: no calculation_method key.
    entry = _entry({"x": 1})
    changed = await ConfigEntryMigrator(hass, entry).run()
    assert changed is True
    new_data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert new_data[CONF_CALCULATION_METHOD] == DEFAULT_CALCULATION_METHOD
    assert new_data["x"] == 1


@pytest.mark.asyncio
async def test_calculation_method_preserved_when_set():
    """An explicit calculation_method is never overwritten by the backfill."""
    hass = _hass()
    entry = _entry({CONF_CALCULATION_METHOD: CALC_METHOD_EXPORT})
    changed = await ConfigEntryMigrator(hass, entry).run()
    assert changed is False
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_enabled_true_becomes_standard():
    """Legacy `schedule_enabled: True` migrates to `schedule_mode: standard`."""
    hass = _hass()
    entry = _entry({
        CONF_DEVICES: [
            {CONF_DEVICE_ID: "a", "schedule_enabled": True, "start_time": "08:00"},
        ]
    })
    changed = await ConfigEntryMigrator(hass, entry).run()
    assert changed is True
    hass.config_entries.async_update_entry.assert_called_once()
    new_data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
    migrated = new_data[CONF_DEVICES][0]
    assert migrated[CONF_DEVICE_SCHEDULE_MODE] == SCHEDULE_MODE_STANDARD
    assert "schedule_enabled" not in migrated
    # Other fields preserved.
    assert migrated["start_time"] == "08:00"


@pytest.mark.asyncio
async def test_schedule_enabled_false_becomes_disabled():
    hass = _hass()
    entry = _entry({CONF_DEVICES: [{CONF_DEVICE_ID: "a", "schedule_enabled": False}]})
    changed = await ConfigEntryMigrator(hass, entry).run()
    assert changed is True
    new_data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert new_data[CONF_DEVICES][0][CONF_DEVICE_SCHEDULE_MODE] == SCHEDULE_MODE_DISABLED


@pytest.mark.asyncio
async def test_explicit_new_key_wins_over_legacy():
    """Defensive: if both old and new keys are present, the new one is preserved."""
    hass = _hass()
    entry = _entry({
        CONF_DEVICES: [
            {
                CONF_DEVICE_ID: "a",
                "schedule_enabled": False,  # would imply DISABLED
                CONF_DEVICE_SCHEDULE_MODE: SCHEDULE_MODE_HELPER,
            }
        ]
    })
    changed = await ConfigEntryMigrator(hass, entry).run()
    assert changed is True
    new_data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
    migrated = new_data[CONF_DEVICES][0]
    assert migrated[CONF_DEVICE_SCHEDULE_MODE] == SCHEDULE_MODE_HELPER
    assert "schedule_enabled" not in migrated


@pytest.mark.asyncio
async def test_mixed_devices_only_legacy_ones_change():
    hass = _hass()
    entry = _entry({
        CONF_DEVICES: [
            {CONF_DEVICE_ID: "old", "schedule_enabled": True},
            {CONF_DEVICE_ID: "new", CONF_DEVICE_SCHEDULE_MODE: SCHEDULE_MODE_DISABLED},
        ]
    })
    changed = await ConfigEntryMigrator(hass, entry).run()
    assert changed is True
    new_data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
    by_id = {d[CONF_DEVICE_ID]: d for d in new_data[CONF_DEVICES]}
    assert by_id["old"][CONF_DEVICE_SCHEDULE_MODE] == SCHEDULE_MODE_STANDARD
    assert "schedule_enabled" not in by_id["old"]
    assert by_id["new"][CONF_DEVICE_SCHEDULE_MODE] == SCHEDULE_MODE_DISABLED


@pytest.mark.asyncio
async def test_control_mode_backfill_esphome_proportional_else_on_off():
    """ESPHome devices (paired mode select) migrate to proportional; the rest to on/off."""
    hass = _hass()
    entry = _entry({
        CONF_CALCULATION_METHOD: DEFAULT_CALCULATION_METHOD,
        CONF_DEVICES: [
            {CONF_DEVICE_ID: "esp", CONF_ESPHOME_MODE_SELECT_ENTITY: "select.x"},
            {CONF_DEVICE_ID: "plain"},
        ],
    })
    changed = await ConfigEntryMigrator(hass, entry).run()
    assert changed is True
    new_data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
    by_id = {d[CONF_DEVICE_ID]: d for d in new_data[CONF_DEVICES]}
    assert by_id["esp"][CONF_DEVICE_CONTROL_MODE] == CONTROL_MODE_PROPORTIONAL
    assert by_id["plain"][CONF_DEVICE_CONTROL_MODE] == CONTROL_MODE_ON_OFF


@pytest.mark.asyncio
async def test_control_mode_preserved_when_set():
    """An explicit control_mode is never overwritten by the backfill."""
    hass = _hass()
    entry = _entry({
        CONF_CALCULATION_METHOD: DEFAULT_CALCULATION_METHOD,
        CONF_DEVICES: [
            {
                CONF_DEVICE_ID: "esp",
                CONF_ESPHOME_MODE_SELECT_ENTITY: "select.x",
                CONF_DEVICE_CONTROL_MODE: CONTROL_MODE_ON_OFF,
                CONF_DEVICE_STOP_BATTERY_SOC: DEFAULT_DEVICE_STOP_BATTERY_SOC,
            },
        ],
    })
    changed = await ConfigEntryMigrator(hass, entry).run()
    assert changed is False
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_soc_start_stop_rename_and_backfill():
    """min_battery_soc → start_battery_soc; stop_battery_soc backfilled to 100."""
    hass = _hass()
    entry = _entry({
        CONF_CALCULATION_METHOD: DEFAULT_CALCULATION_METHOD,
        CONF_DEVICES: [
            {CONF_DEVICE_ID: "a", "min_battery_soc": 80, CONF_DEVICE_CONTROL_MODE: CONTROL_MODE_ON_OFF},
        ],
    })
    changed = await ConfigEntryMigrator(hass, entry).run()
    assert changed is True
    dev = hass.config_entries.async_update_entry.call_args.kwargs["data"][CONF_DEVICES][0]
    assert dev[CONF_DEVICE_START_BATTERY_SOC] == 80
    assert "min_battery_soc" not in dev
    assert dev[CONF_DEVICE_STOP_BATTERY_SOC] == DEFAULT_DEVICE_STOP_BATTERY_SOC


@pytest.mark.asyncio
async def test_soc_start_stop_idempotent():
    """No-op once stop_battery_soc is present on every device."""
    hass = _hass()
    entry = _entry({
        CONF_CALCULATION_METHOD: DEFAULT_CALCULATION_METHOD,
        CONF_DEVICES: [
            {
                CONF_DEVICE_ID: "a",
                CONF_DEVICE_CONTROL_MODE: CONTROL_MODE_ON_OFF,
                CONF_DEVICE_START_BATTERY_SOC: 80,
                CONF_DEVICE_STOP_BATTERY_SOC: 60,
            },
        ],
    })
    changed = await ConfigEntryMigrator(hass, entry).run()
    assert changed is False
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_prune_dead_options():
    """Dead ramp_* (top-level) + min_excess_power (per-device) are removed."""
    hass = _hass()
    entry = _entry({
        CONF_CALCULATION_METHOD: DEFAULT_CALCULATION_METHOD,
        "ramp_up_step": 10,
        "ramp_down_step": 20,
        "ramp_deadband": 1,
        CONF_DEVICES: [
            {
                CONF_DEVICE_ID: "a",
                "min_excess_power": 50,
                CONF_DEVICE_CONTROL_MODE: CONTROL_MODE_ON_OFF,
                CONF_DEVICE_STOP_BATTERY_SOC: DEFAULT_DEVICE_STOP_BATTERY_SOC,
            },
        ],
    })
    changed = await ConfigEntryMigrator(hass, entry).run()
    assert changed is True
    new_data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert "ramp_up_step" not in new_data
    assert "ramp_down_step" not in new_data
    assert "ramp_deadband" not in new_data
    assert "min_excess_power" not in new_data[CONF_DEVICES][0]


@pytest.mark.asyncio
async def test_idempotent_when_run_twice():
    hass = _hass()
    entry_data = {CONF_DEVICES: [{CONF_DEVICE_ID: "a", "schedule_enabled": True}]}
    entry = _entry(entry_data)

    await ConfigEntryMigrator(hass, entry).run()
    # Simulate the entry now reflecting the migrated state.
    entry.data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
    hass.config_entries.async_update_entry.reset_mock()

    changed = await ConfigEntryMigrator(hass, entry).run()
    assert changed is False
    hass.config_entries.async_update_entry.assert_not_called()
