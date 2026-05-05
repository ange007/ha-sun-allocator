"""Tests for the per-device auto-control switch entity."""

from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from custom_components.sun_allocator.const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_AUTO_CONTROL_ENABLED,
)
from custom_components.sun_allocator.switch import async_setup_entry
from custom_components.sun_allocator.switch.auto_control_switch import (
    SunAllocatorDeviceAutoControlSwitch,
)


def _make_hass():
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    return hass


def _make_entry(devices, entry_id="entry_x"):
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {CONF_DEVICES: devices}
    return entry


@pytest.mark.asyncio
async def test_switch_created_for_every_device_regardless_of_auto_control_flag():
    """Regression: switch must be created for every device with a device_id even when auto-control is disabled."""
    hass = _make_hass()
    devices = [
        {CONF_DEVICE_ID: "dev1", CONF_AUTO_CONTROL_ENABLED: True},
        {CONF_DEVICE_ID: "dev2", CONF_AUTO_CONTROL_ENABLED: False},
        {CONF_DEVICE_ID: "dev3"},  # missing key — defaults to True
    ]
    entry = _make_entry(devices)
    added: list[SunAllocatorDeviceAutoControlSwitch] = []

    def add_entities(entities):
        added.extend(entities)

    await async_setup_entry(hass, entry, add_entities)

    assert len(added) == 3
    assert {sw._device_id for sw in added} == {"dev1", "dev2", "dev3"}
    # Initial state mirrors config (default True if absent).
    by_id = {sw._device_id: sw for sw in added}
    assert by_id["dev1"].is_on is True
    assert by_id["dev2"].is_on is False
    assert by_id["dev3"].is_on is True


@pytest.mark.asyncio
async def test_devices_without_device_id_skipped():
    hass = _make_hass()
    entry = _make_entry([{CONF_DEVICE_ID: "dev1"}, {"name": "no_id"}])
    added = []

    def add_entities(entities):
        added.extend(entities)

    await async_setup_entry(hass, entry, add_entities)

    assert [sw._device_id for sw in added] == ["dev1"]


@pytest.mark.asyncio
async def test_turn_off_persists_to_config_without_reload():
    """Toggling the switch off must update the config entry without triggering a reload."""
    hass = _make_hass()
    devices = [{CONF_DEVICE_ID: "dev1", CONF_AUTO_CONTROL_ENABLED: True}]
    hass.data[DOMAIN]["entry_x"] = {"manual_overrides": {}}
    hass.config_entries.async_get_entry.return_value = MagicMock(data={CONF_DEVICES: devices})

    sw = SunAllocatorDeviceAutoControlSwitch(hass, "entry_x", devices[0])
    sw.async_write_ha_state = MagicMock()

    await sw.async_turn_off()

    assert sw.is_on is False
    # _skip_reload guards against the listener triggering a full reload mid-toggle.
    assert hass.data[DOMAIN]["entry_x"]["_skip_reload"] is True
    hass.config_entries.async_update_entry.assert_called_once()
    new_data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert new_data[CONF_DEVICES][0][CONF_AUTO_CONTROL_ENABLED] is False


@pytest.mark.asyncio
async def test_turn_on_clears_pending_manual_override():
    hass = _make_hass()
    devices = [{CONF_DEVICE_ID: "dev1", CONF_AUTO_CONTROL_ENABLED: False}]
    entry_data = {"manual_overrides": {"dev1": {"since": 1, "state": False}}}
    hass.data[DOMAIN]["entry_x"] = entry_data
    hass.config_entries.async_get_entry.return_value = MagicMock(data={CONF_DEVICES: devices})

    sw = SunAllocatorDeviceAutoControlSwitch(hass, "entry_x", devices[0])
    sw.async_write_ha_state = MagicMock()

    await sw.async_turn_on()

    assert sw.is_on is True
    assert "dev1" not in entry_data["manual_overrides"]


@pytest.mark.asyncio
async def test_restore_state_overrides_config_value_on_startup():
    """RestoreEntity wins over the config value when both are available on startup."""
    hass = _make_hass()
    hass.data[DOMAIN]["entry_x"] = {}
    devices = [{CONF_DEVICE_ID: "dev1", CONF_AUTO_CONTROL_ENABLED: True}]
    sw = SunAllocatorDeviceAutoControlSwitch(hass, "entry_x", devices[0])

    last_state = MagicMock()
    last_state.state = "off"

    with patch.object(SunAllocatorDeviceAutoControlSwitch, "async_get_last_state",
                      new_callable=AsyncMock, return_value=last_state):
        with patch("homeassistant.helpers.restore_state.RestoreEntity.async_added_to_hass",
                   new_callable=AsyncMock):
            await sw.async_added_to_hass()

    assert sw.is_on is False


@pytest.mark.asyncio
async def test_sync_state_does_not_persist_to_config():
    """sync_state is the inbound channel from the config form; it must not write back to config."""
    hass = _make_hass()
    devices = [{CONF_DEVICE_ID: "dev1", CONF_AUTO_CONTROL_ENABLED: True}]
    sw = SunAllocatorDeviceAutoControlSwitch(hass, "entry_x", devices[0])
    sw.async_write_ha_state = MagicMock()

    sw.sync_state(False)

    assert sw.is_on is False
    hass.config_entries.async_update_entry.assert_not_called()
