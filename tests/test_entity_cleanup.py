"""Tests for orphaned per-device entity cleanup (`_cleanup_orphan_device_entities`)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.sun_allocator import _cleanup_orphan_device_entities
from custom_components.sun_allocator.const import CONF_DEVICES, CONF_DEVICE_ID

ENTRY = "01KK4VDJ7NJ1NHJZMEJY939AKE"
DEV_A = "c30acc89-c56b-44dd-b63a-7e992d1ba9c9"  # current
DEV_OLD = "abd694c5-699a-4f8a-a5b7-9284a6e915ef"  # removed/orphan


def _entity(uid, entity_id):
    return SimpleNamespace(unique_id=uid, entity_id=entity_id)


def _run(entities, current_device_ids):
    config_entry = MagicMock()
    config_entry.entry_id = ENTRY
    config_entry.data = {CONF_DEVICES: [{CONF_DEVICE_ID: d} for d in current_device_ids]}
    registry = MagicMock()
    removed = []
    registry.async_remove.side_effect = removed.append
    with patch("custom_components.sun_allocator.er.async_get", return_value=registry), \
         patch("custom_components.sun_allocator.er.async_entries_for_config_entry",
               return_value=entities):
        _cleanup_orphan_device_entities(MagicMock(), config_entry)
    return removed


def test_removes_only_orphan_device_entities():
    entities = [
        # hub sensors — must NEVER be removed
        _entity(f"{ENTRY}_excess", "sensor.sun_allocator_excess_power"),
        _entity(f"{ENTRY}_max_power", "sensor.sun_allocator_max_power"),
        _entity(f"{ENTRY}_current_max_power", "sensor.sun_allocator_current_max_power"),
        # current device A — keep all four
        _entity(f"{ENTRY}_{DEV_A}_power", "sensor.a_power"),
        _entity(f"{ENTRY}_{DEV_A}_power_percent", "sensor.a_pp"),
        _entity(f"{ENTRY}_{DEV_A}_status", "sensor.a_status"),
        _entity(f"{ENTRY}_{DEV_A}_auto_control", "switch.a_auto"),
        # orphaned device OLD — remove all four
        _entity(f"{ENTRY}_{DEV_OLD}_power", "sensor.old_power"),
        _entity(f"{ENTRY}_{DEV_OLD}_power_percent", "sensor.old_pp"),
        _entity(f"{ENTRY}_{DEV_OLD}_status", "sensor.old_status"),
        _entity(f"{ENTRY}_{DEV_OLD}_auto_control", "switch.old_auto"),
    ]
    removed = _run(entities, current_device_ids={DEV_A})
    assert set(removed) == {
        "sensor.old_power", "sensor.old_pp", "sensor.old_status", "switch.old_auto",
    }


def test_no_removal_when_all_current():
    entities = [
        _entity(f"{ENTRY}_excess", "sensor.sun_allocator_excess_power"),
        _entity(f"{ENTRY}_{DEV_A}_power", "sensor.a_power"),
        _entity(f"{ENTRY}_{DEV_A}_power_percent", "sensor.a_pp"),
    ]
    assert _run(entities, current_device_ids={DEV_A}) == []


def test_ignores_foreign_unique_ids():
    # An entity from a different prefix must be ignored entirely.
    entities = [_entity(f"OTHERENTRY_{DEV_OLD}_power", "sensor.foreign")]
    assert _run(entities, current_device_ids={DEV_A}) == []
