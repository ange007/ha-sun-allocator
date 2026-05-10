"""Focused runtime tests for auto-control orchestration."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import State

from custom_components.sun_allocator import (
    _handle_auto_control_state_change,
    _queue_process_excess_power,
    setup_auto_control,
)
from custom_components.sun_allocator.const import (
    CONF_AUTO_CONTROL_ENABLED,
    CONF_DEVICE_ACTIVE_FEEDBACK_SENSOR,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_ID,
    CONF_DEVICE_PRIORITY,
    CONF_DEVICES,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_handle_state_change_refreshes_watchdog_only_for_excess_sensor():
    """Auxiliary sensors should not keep the watchdog alive."""
    hass = MagicMock()
    excess_sensor_id = "sensor.test_excess"
    hass.states = MagicMock()
    hass.states.get = lambda entity_id: {
        excess_sensor_id: State(excess_sensor_id, "125")
    }.get(entity_id)

    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"

    old_seen = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    new_seen = datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc)
    entry_data = {
        "watchdog_last_seen": old_seen,
        "watchdog_alerted": True,
    }
    processor = AsyncMock()

    await _handle_auto_control_state_change(
        hass,
        config_entry,
        entry_data,
        excess_sensor_id,
        "sensor.auxiliary",
        State("sensor.auxiliary", "1"),
        processor=processor,
    )

    processor.assert_awaited_once_with(
        hass,
        config_entry,
        125.0,
        start_from_device_id=None,
    )
    assert entry_data["watchdog_last_seen"] == old_seen
    assert entry_data["watchdog_alerted"] is True

    processor.reset_mock()

    with patch("custom_components.sun_allocator.dt_util.utcnow", return_value=new_seen):
        await _handle_auto_control_state_change(
            hass,
            config_entry,
            entry_data,
            excess_sensor_id,
            excess_sensor_id,
            State(excess_sensor_id, "130"),
            processor=processor,
        )

    processor.assert_awaited_once_with(
        hass,
        config_entry,
        130.0,
        start_from_device_id=None,
    )
    assert entry_data["watchdog_last_seen"] == new_seen
    assert entry_data["watchdog_alerted"] is False


@pytest.mark.asyncio
async def test_handle_state_change_uses_partial_recompute_for_device_feedback():
    """Per-device feedback updates should recompute that device and downstream only."""
    hass = MagicMock()
    excess_sensor_id = "sensor.test_excess"
    hass.states = MagicMock()
    hass.states.get = lambda entity_id: {
        excess_sensor_id: State(excess_sensor_id, "125")
    }.get(entity_id)

    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"
    entry_data = {
        "tracked_device_sensor_map": {"sensor.heater_2_power": "heater_2"},
        "tracked_battery_soc_sensor": "sensor.battery_soc",
    }
    processor = AsyncMock()

    await _handle_auto_control_state_change(
        hass,
        config_entry,
        entry_data,
        excess_sensor_id,
        "sensor.heater_2_power",
        State("sensor.heater_2_power", "0"),
        processor=processor,
    )

    processor.assert_awaited_once_with(
        hass,
        config_entry,
        125.0,
        start_from_device_id="heater_2",
    )


@pytest.mark.asyncio
async def test_setup_auto_control_tracks_relay_entities_for_partial_recompute():
    """External relay on/off changes should trigger recompute for that device."""
    hass = MagicMock()
    hass.data = {DOMAIN: {"test_entry": {}}}
    spawned_tasks = []

    def _spawn_task(coro, *_args, **_kwargs):
        task = asyncio.create_task(coro)
        spawned_tasks.append(task)
        return task

    hass.async_create_task = _spawn_task

    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"
    config_entry.data = {
        CONF_DEVICES: [
            {
                CONF_DEVICE_ID: "heater_1",
                CONF_DEVICE_ENTITY: "input_boolean.heater_1",
                CONF_DEVICE_ACTIVE_FEEDBACK_SENSOR: "binary_sensor.heater_1_feedback",
                CONF_DEVICE_PRIORITY: 50,
                CONF_AUTO_CONTROL_ENABLED: True,
            },
            {
                CONF_DEVICE_ID: "climate_1",
                CONF_DEVICE_ENTITY: "climate.room|heat",
                CONF_DEVICE_PRIORITY: 25,
                CONF_AUTO_CONTROL_ENABLED: True,
            },
        ]
    }

    registry = MagicMock()
    registry.async_get_entity_id.return_value = "sensor.test_excess"

    with (
        patch("custom_components.sun_allocator.er.async_get", return_value=registry),
        patch(
            "custom_components.sun_allocator.async_track_time_interval",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.sun_allocator.async_track_state_change_event",
            return_value=MagicMock(),
        ) as mock_track_state,
        patch(
            "custom_components.sun_allocator._initial_pass_with_retry",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.sun_allocator.load_grace_state",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        await setup_auto_control(hass, config_entry)

    await asyncio.gather(*spawned_tasks)

    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    assert entry_data["tracked_device_sensor_map"]["input_boolean.heater_1"] == "heater_1"
    assert entry_data["tracked_device_sensor_map"]["binary_sensor.heater_1_feedback"] == "heater_1"
    assert entry_data["tracked_device_sensor_map"]["climate.room"] == "climate_1"
    assert entry_data["tracked_auto_control_entities"] == [
        "binary_sensor.heater_1_feedback",
        "climate.room",
        "input_boolean.heater_1",
        "sensor.test_excess",
    ]
    mock_track_state.assert_called_once()


@pytest.mark.asyncio
async def test_queue_process_excess_power_coalesces_overlapping_triggers():
    """Overlapping triggers should collapse to one trailing rerun."""
    hass = MagicMock()
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"
    entry_data = {}

    calls = []
    first_run_started = asyncio.Event()
    allow_first_run_to_finish = asyncio.Event()

    async def processor(_hass, _config_entry, excess_power, start_from_device_id=None):
        calls.append((excess_power, start_from_device_id))
        if len(calls) == 1:
            first_run_started.set()
            await allow_first_run_to_finish.wait()

    first_task = asyncio.create_task(
        _queue_process_excess_power(
            hass,
            config_entry,
            entry_data,
            100.0,
            start_from_device_id=None,
            processor=processor,
        )
    )

    await first_run_started.wait()

    await _queue_process_excess_power(
        hass,
        config_entry,
        entry_data,
        200.0,
        start_from_device_id=None,
        processor=processor,
    )
    await _queue_process_excess_power(
        hass,
        config_entry,
        entry_data,
        300.0,
        start_from_device_id=None,
        processor=processor,
    )

    allow_first_run_to_finish.set()
    await first_task

    assert calls == [(100.0, None), (300.0, None)]
    assert not entry_data["process_excess_power_lock"].locked()
    assert "pending_process_request" not in entry_data