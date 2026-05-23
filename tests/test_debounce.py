"""Simplified debounce tests."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from homeassistant.util import dt as dt_util

from custom_components.sun_allocator import _schedule_debounce_recheck
from custom_components.sun_allocator.core.power_processor import _calculate_device_state
from custom_components.sun_allocator.const import (
    CONF_AUTO_CONTROL_ENABLED,
    CONF_DEVICE_ID,
    CONF_DEVICE_MIN_EXPECTED_W,
    CONF_DEVICE_DEBOUNCE_TIME,
    CONF_HYSTERESIS_W,
)


@pytest.mark.asyncio
async def test_debounce_logic(freezer):
    """Test the debounce logic in isolation."""
    device = {
        CONF_DEVICE_ID: "test_device",
        CONF_DEVICE_MIN_EXPECTED_W: 100,
        CONF_DEVICE_DEBOUNCE_TIME: 5,
    }
    cfg = {
        CONF_HYSTERESIS_W: 20,
    }
    device_on_state = {}
    device_debounce_state = {}

    # Initial state: power is low
    now = datetime(2024, 1, 1, 0, 0, 0, tzinfo=dt_util.UTC)
    freezer.move_to(now)
    is_active, _ = _calculate_device_state(
        device, 0, device_on_state, device_debounce_state, cfg, now
    )
    assert not is_active

    # Power becomes available
    now = datetime(2024, 1, 1, 0, 0, 1, tzinfo=dt_util.UTC)
    freezer.move_to(now)
    is_active, _ = _calculate_device_state(
        device, 200, device_on_state, device_debounce_state, cfg, now
    )
    assert not is_active  # Still off due to debounce

    # Time moves forward, but not enough to clear debounce
    now = datetime(2024, 1, 1, 0, 0, 5, tzinfo=dt_util.UTC)
    freezer.move_to(now)
    is_active, _ = _calculate_device_state(
        device, 200, device_on_state, device_debounce_state, cfg, now
    )
    assert not is_active  # Still off

    # Time moves forward enough to clear debounce
    now = datetime(2024, 1, 1, 0, 0, 6, tzinfo=dt_util.UTC)
    freezer.move_to(now)
    is_active, _ = _calculate_device_state(
        device, 200, device_on_state, device_debounce_state, cfg, now
    )
    assert is_active  # Should be on now

    # Power drops
    device_on_state[device["device_id"]] = True # Update prev_on state
    now = datetime(2024, 1, 1, 0, 0, 7, tzinfo=dt_util.UTC)
    freezer.move_to(now)
    is_active, _ = _calculate_device_state(
        device, 50, device_on_state, device_debounce_state, cfg, now
    )
    assert is_active  # Still on due to debounce

    # Time moves forward enough to clear debounce
    now = datetime(2024, 1, 1, 0, 0, 12, tzinfo=dt_util.UTC)
    freezer.move_to(now)
    is_active, _ = _calculate_device_state(
        device, 50, device_on_state, device_debounce_state, cfg, now
    )
    assert not is_active  # Should be off now


@pytest.mark.asyncio
async def test_overdue_debounce_recheck_is_deferred_to_next_loop_tick(freezer):
    """Overdue debounce rechecks should not eagerly recurse into the allocator."""
    now = datetime(2024, 1, 1, 0, 0, 10, tzinfo=dt_util.UTC)
    freezer.move_to(now)

    hass = MagicMock()
    hass.loop = MagicMock()
    hass.async_create_task = MagicMock()
    hass.states.get.return_value = MagicMock(state="123.0")

    config_entry = MagicMock()
    config_entry.data = {
        "devices": [
            {
                CONF_DEVICE_ID: "test_device",
                    CONF_AUTO_CONTROL_ENABLED: True,
                CONF_DEVICE_DEBOUNCE_TIME: 5,
            }
        ]
    }

    entry_data = {
        "tracked_excess_sensor_id": "sensor.test_excess",
        "device_debounce_state": {
            "test_device": {
                "state_change_time": now - timedelta(seconds=6),
                "candidate_state": True,
                "counter_debounce_start": None,
            }
        },
    }
    processor = AsyncMock()

    _schedule_debounce_recheck(
        hass,
        config_entry,
        entry_data,
        processor=processor,
    )

    hass.async_create_task.assert_not_called()
    hass.loop.call_soon.assert_called_once()

    scheduled_create_task = hass.loop.call_soon.call_args.args[0]
    scheduled_coro = hass.loop.call_soon.call_args.args[1]

    scheduled_create_task(scheduled_coro)
    hass.async_create_task.assert_called_once_with(scheduled_coro)
    scheduled_coro.close()
