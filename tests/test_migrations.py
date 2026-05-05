"""Tests for ConfigEntryMigrator."""

from unittest.mock import MagicMock

import pytest

from custom_components.sun_allocator.const import (
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_SCHEDULE_MODE,
    SCHEDULE_MODE_DISABLED,
    SCHEDULE_MODE_STANDARD,
    SCHEDULE_MODE_HELPER,
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
    """Migrator must not touch the entry when no device has the legacy key."""
    hass = _hass()
    entry = _entry({
        CONF_DEVICES: [
            {CONF_DEVICE_ID: "a", CONF_DEVICE_SCHEDULE_MODE: SCHEDULE_MODE_HELPER},
        ]
    })
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
