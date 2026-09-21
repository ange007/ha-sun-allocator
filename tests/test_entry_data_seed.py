"""Regression: entry_data must be usable by the control loop from the very first cycle.

``setup_auto_control`` seeds ``entry_data[CONF_POWER_ALLOCATION]``, but it returns early
when NO device has auto-control enabled. The control loop nevertheless writes
``entry_data[CONF_POWER_ALLOCATION][device_id] = ...`` unconditionally (manual runs, timed
runs, the require_grid gate), so that early return used to leave a KeyError landmine.
Reachable in practice since the auto-control switch kicks an immediate re-eval on toggle.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sun_allocator import async_setup_entry
from custom_components.sun_allocator.const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_POWER_ALLOCATION,
)


class _StopSetup(Exception):
    """Sentinel: abort async_setup_entry once entry_data exists, before platform setup."""


def _hass():
    hass = MagicMock()
    hass.data = {}
    hass.bus.async_listen_once = MagicMock(return_value=lambda: None)
    hass.config_entries.async_forward_entry_setups = AsyncMock(side_effect=_StopSetup)
    return hass


@pytest.mark.asyncio
async def test_power_allocation_is_seeded_even_with_no_auto_control_devices():
    hass = _hass()
    entry = MagicMock()
    entry.entry_id = "entry_x"
    entry.data = {CONF_DEVICES: [
        {CONF_DEVICE_ID: "dev1", CONF_AUTO_CONTROL_ENABLED: False},
    ]}

    with patch("custom_components.sun_allocator.ConfigEntryMigrator") as migrator, patch(
        "custom_components.sun_allocator.rebuild_device_index"
    ), patch("custom_components.sun_allocator._cleanup_orphan_device_entities"), patch(
        "custom_components.sun_allocator._fix_power_percent_entity_ids"
    ), patch(
        "custom_components.sun_allocator._setup_entity_state_listeners",
        new_callable=AsyncMock,
    ):
        migrator.return_value.run = AsyncMock()
        with pytest.raises(_StopSetup):
            await async_setup_entry(hass, entry)

    entry_data = hass.data[DOMAIN]["entry_x"]
    # The loop indexes into this dict; absent key == KeyError on the first manual/timed run.
    assert entry_data[CONF_POWER_ALLOCATION] == {}
    entry_data[CONF_POWER_ALLOCATION]["dev1"] = 0.0
