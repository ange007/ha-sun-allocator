"""Tests for power distribution strategies."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant, State

from custom_components.sun_allocator.core.power_processor import process_excess_power
from custom_components.sun_allocator.const import (
    DOMAIN,
    DEVICE_TYPE_STANDARD,
    DEVICE_TYPE_CUSTOM,
    CONF_DEVICE_ALLOCATION_STRATEGY,
    CONF_DEVICE_ACTUAL_POWER_SENSOR,
    CONF_DEVICE_ACTUAL_POWER_THRESHOLD_W,
    STRATEGY_FILL_ONE_BY_ONE,
    STRATEGY_DISTRIBUTE_EVENLY,
)


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {}
    
    states = {}

    def get_state(entity_id):
        return states.get(entity_id)

    def set_state(entity_id, state):
        states[entity_id] = State(entity_id, state)

    hass.states = MagicMock()
    hass.states.get = get_state
    hass.states.async_set = set_state
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    def create_task(coro, *_args, **_kwargs):
        coro.close()
        return None

    hass.async_create_task = create_task
    return hass


@pytest.mark.asyncio
async def test_priority_power_distribution(mock_hass):
    """Test that higher priority devices get power first."""
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"
    config_entry.data = {
        "devices": [
            {
                "device_id": "low_priority",
                "device_name": "Low Priority Device",
                "device_entity": "switch.low_priority",
                "device_type": DEVICE_TYPE_STANDARD,
                "priority": 30,
                "min_expected_w": 100,
                "auto_control_enabled": True,
                "debounce_time": 0,
            },
            {
                "device_id": "high_priority",
                "device_name": "High Priority Device",
                "device_entity": "switch.high_priority",
                "device_type": DEVICE_TYPE_STANDARD,
                "priority": 80,
                "min_expected_w": 150,
                "auto_control_enabled": True,
                "debounce_time": 0,
            },
        ]
    }

    mock_hass.data[DOMAIN] = {config_entry.entry_id: {"power_allocation": {}}}
    mock_hass.states.async_set("switch.low_priority", "off")
    mock_hass.states.async_set("switch.high_priority", "off")

    await process_excess_power(mock_hass, config_entry, 200)  # Only enough for high priority device

    power_dist = mock_hass.data[DOMAIN][config_entry.entry_id]["power_distribution"]
    assert power_dist["allocation"]["high_priority"] == 150
    assert power_dist["allocation"].get("low_priority", 0) == 0


@pytest.mark.asyncio
async def test_standard_device_allocation(mock_hass):
    """Test that standard devices only allocate their min_expected_w."""
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"
    config_entry.data = {
        "devices": [
            {
                "device_id": "standard_device",
                "device_name": "Standard Device",
                "device_entity": "switch.standard_device",
                "device_type": DEVICE_TYPE_STANDARD,
                "priority": 80,
                "min_expected_w": 150,
                "auto_control_enabled": True,
                "debounce_time": 0,
            }
        ]
    }

    mock_hass.data[DOMAIN] = {config_entry.entry_id: {"power_allocation": {}}}
    mock_hass.states.async_set("switch.standard_device", "off")

    await process_excess_power(mock_hass, config_entry, 1000)  # More than enough power

    power_dist = mock_hass.data[DOMAIN][config_entry.entry_id]["power_distribution"]
    assert power_dist["allocation"]["standard_device"] == 150


@pytest.mark.asyncio
async def test_proportional_100_percent(mock_hass):
    """Test that a proportional device can reach 100%."""
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"
    config_entry.data = {
        "devices": [
            {
                "device_id": "proportional_device",
                "device_name": "Proportional Device",
                "device_entity": "switch.proportional_device",
                "device_type": DEVICE_TYPE_CUSTOM,
                "esphome_mode_select_entity": "select.proportional_mode",
                "priority": 50,
                "min_expected_w": 50,
                "max_expected_w": 200,
                "auto_control_enabled": True,
                "debounce_time": 0,
            }
        ]
    }

    mock_hass.data[DOMAIN] = {config_entry.entry_id: {"power_allocation": {}}}
    mock_hass.states.async_set("switch.proportional_device", "off")
    mock_hass.states.async_set("select.proportional_mode", "Proportional")

    await process_excess_power(mock_hass, config_entry, 300)  # More than enough power

    status = mock_hass.data[DOMAIN][config_entry.entry_id]["device_status"]["proportional_device"]
    assert status["percent_target"] == 100.0


@pytest.mark.asyncio
async def test_proportional_fill_strategy(mock_hass):
    """Test the fill one by one proportional strategy."""
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"
    config_entry.data = {
        CONF_DEVICE_ALLOCATION_STRATEGY: STRATEGY_FILL_ONE_BY_ONE,
        "devices": [
            {
                "device_id": "heater_1",
                "device_name": "Heater 1",
                "device_entity": "switch.heater_1",
                "device_type": DEVICE_TYPE_CUSTOM,
                "esphome_mode_select_entity": "select.heater_1_mode",
                "priority": 80,
                "min_expected_w": 100,
                "max_expected_w": 1000,
                "auto_control_enabled": True,
                "debounce_time": 0,
            },
            {
                "device_id": "heater_2",
                "device_name": "Heater 2",
                "device_entity": "switch.heater_2",
                "device_type": DEVICE_TYPE_CUSTOM,
                "esphome_mode_select_entity": "select.heater_2_mode",
                "priority": 70,
                "min_expected_w": 100,
                "max_expected_w": 1000,
                "auto_control_enabled": True,
                "debounce_time": 0,
            },
        ]
    }

    mock_hass.data[DOMAIN] = {config_entry.entry_id: {"power_allocation": {}}}
    mock_hass.states.async_set("switch.heater_1", "off")
    mock_hass.states.async_set("select.heater_1_mode", "Proportional")
    mock_hass.states.async_set("switch.heater_2", "off")
    mock_hass.states.async_set("select.heater_2_mode", "Proportional")

    await process_excess_power(mock_hass, config_entry, 1200)  # 1200W to distribute

    status1 = mock_hass.data[DOMAIN][config_entry.entry_id]["device_status"]["heater_1"]
    status2 = mock_hass.data[DOMAIN][config_entry.entry_id]["device_status"]["heater_2"]

    # Heater 1 should get 100% (1000W), heater 2 should get the rest (200W)
    assert status1["percent_target"] == 100.0
    assert status2["percent_target"] == 20.0


@pytest.mark.asyncio
async def test_proportional_distribute_strategy(mock_hass):
    """Test the distribute evenly proportional strategy."""
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"
    config_entry.data = {
        CONF_DEVICE_ALLOCATION_STRATEGY: STRATEGY_DISTRIBUTE_EVENLY,
        "devices": [
            {
                "device_id": "heater_1",
                "device_name": "Heater 1",
                "device_entity": "switch.heater_1",
                "device_type": DEVICE_TYPE_CUSTOM,
                "esphome_mode_select_entity": "select.heater_1_mode",
                "priority": 80,
                "min_expected_w": 100,
                "max_expected_w": 1000,
                "auto_control_enabled": True,
                "debounce_time": 0,
            },
            {
                "device_id": "heater_2",
                "device_name": "Heater 2",
                "device_entity": "switch.heater_2",
                "device_type": DEVICE_TYPE_CUSTOM,
                "esphome_mode_select_entity": "select.heater_2_mode",
                "priority": 70,
                "min_expected_w": 100,
                "max_expected_w": 1000,
                "auto_control_enabled": True,
                "debounce_time": 0,
            },
        ]
    }

    mock_hass.data[DOMAIN] = {config_entry.entry_id: {"power_allocation": {}}}
    mock_hass.states.async_set("switch.heater_1", "off")
    mock_hass.states.async_set("select.heater_1_mode", "Proportional")
    mock_hass.states.async_set("switch.heater_2", "off")
    mock_hass.states.async_set("select.heater_2_mode", "Proportional")

    await process_excess_power(mock_hass, config_entry, 1000)  # 1000W to distribute

    status1 = mock_hass.data[DOMAIN][config_entry.entry_id]["device_status"]["heater_1"]
    status2 = mock_hass.data[DOMAIN][config_entry.entry_id]["device_status"]["heater_2"]

    # Each device has max 1000W, total 2000W. With 1000W available, each should get 50%.
    assert status1["percent_target"] == 50.0
    assert status2["percent_target"] == 50.0


@pytest.mark.asyncio
async def test_distribute_evenly_does_not_overspend_when_one_device_inactive(mock_hass):
    """Regression: under DISTRIBUTE_EVENLY, a non-proportional device must not consume the whole remaining budget."""
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"
    config_entry.data = {
        CONF_DEVICE_ALLOCATION_STRATEGY: STRATEGY_DISTRIBUTE_EVENLY,
        "devices": [
            {
                "device_id": "proportional",
                "device_name": "Proportional",
                "device_entity": "switch.proportional",
                "device_type": DEVICE_TYPE_CUSTOM,
                "esphome_mode_select_entity": "select.proportional_mode",
                "priority": 80,
                "min_expected_w": 100,
                "max_expected_w": 500,
                "auto_control_enabled": True,
                "debounce_time": 0,
            },
            {
                # Same custom type but in RELAY_MODE_ON — must not be treated as proportional.
                "device_id": "on_mode",
                "device_name": "Always On Mode",
                "device_entity": "switch.on_mode",
                "device_type": DEVICE_TYPE_CUSTOM,
                "esphome_mode_select_entity": "select.on_mode",
                "priority": 70,
                "min_expected_w": 50,
                "max_expected_w": 500,
                "auto_control_enabled": True,
                "debounce_time": 0,
            },
        ],
    }

    mock_hass.data[DOMAIN] = {config_entry.entry_id: {"power_allocation": {}}}
    mock_hass.states.async_set("switch.proportional", "off")
    mock_hass.states.async_set("select.proportional_mode", "Proportional")
    mock_hass.states.async_set("switch.on_mode", "off")
    mock_hass.states.async_set("select.on_mode", "On")

    await process_excess_power(mock_hass, config_entry, 600)

    allocation = mock_hass.data[DOMAIN][config_entry.entry_id]["power_distribution"]["allocation"]
    # Proportional gets the full 600W (only proportional in pool); the On device must not double-spend it.
    assert allocation["proportional"] > 0
    assert allocation.get("on_mode", 0) <= 50  # min_expected_w upper bound for standard-style ON
    # And the total allocated must not exceed the input budget.
    assert allocation["proportional"] + allocation.get("on_mode", 0) <= 600


@pytest.mark.asyncio
async def test_partial_recompute_updates_changed_device_and_downstream(mock_hass):
    """Feedback-triggered recompute should update the changed device and lower priorities."""
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"
    config_entry.data = {
        "devices": [
            {
                "device_id": "high_priority",
                "device_name": "High Priority",
                "device_entity": "switch.high_priority",
                "device_type": DEVICE_TYPE_STANDARD,
                "priority": 90,
                "min_expected_w": 100,
                "auto_control_enabled": True,
                "debounce_time": 0,
            },
            {
                "device_id": "measured_device",
                "device_name": "Measured Device",
                "device_entity": "switch.measured_device",
                "device_type": DEVICE_TYPE_STANDARD,
                "priority": 80,
                "min_expected_w": 150,
                "auto_control_enabled": True,
                "debounce_time": 0,
                CONF_DEVICE_ACTUAL_POWER_SENSOR: "sensor.measured_device_power",
                CONF_DEVICE_ACTUAL_POWER_THRESHOLD_W: 10,
            },
            {
                "device_id": "low_priority",
                "device_name": "Low Priority",
                "device_entity": "switch.low_priority",
                "device_type": DEVICE_TYPE_STANDARD,
                "priority": 70,
                "min_expected_w": 100,
                "auto_control_enabled": True,
                "debounce_time": 0,
            },
        ]
    }

    mock_hass.data[DOMAIN] = {config_entry.entry_id: {"power_allocation": {}}}
    mock_hass.states.async_set("switch.high_priority", "off")
    mock_hass.states.async_set("switch.measured_device", "off")
    mock_hass.states.async_set("switch.low_priority", "off")
    mock_hass.states.async_set("sensor.measured_device_power", "150")

    await process_excess_power(mock_hass, config_entry, 250)

    entry_data = mock_hass.data[DOMAIN][config_entry.entry_id]
    entry_data["device_on_time_state"]["measured_device"].pop("startup_until", None)

    mock_hass.states.async_set("switch.high_priority", "on")
    mock_hass.states.async_set("switch.measured_device", "on")
    mock_hass.states.async_set("sensor.measured_device_power", "0")

    await process_excess_power(
        mock_hass,
        config_entry,
        250,
        start_from_device_id="measured_device",
    )

    power_dist = mock_hass.data[DOMAIN][config_entry.entry_id]["power_distribution"]

    assert power_dist["allocation"]["high_priority"] == 100
    assert power_dist["allocation"]["measured_device"] == 0.0
    assert power_dist["allocation"]["low_priority"] == 100


@pytest.mark.asyncio
async def test_outside_schedule_off_is_not_repeated_without_state_change(mock_hass):
    """Outside-schedule enforcement should not spam repeated off commands."""
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"
    config_entry.data = {
        "devices": [
            {
                "device_id": "scheduled_device",
                "device_name": "Scheduled Device",
                "device_entity": "switch.scheduled_device",
                "device_type": DEVICE_TYPE_STANDARD,
                "priority": 80,
                "min_expected_w": 150,
                "auto_control_enabled": True,
                "debounce_time": 0,
            }
        ]
    }

    mock_hass.data[DOMAIN] = {config_entry.entry_id: {"power_allocation": {}}}
    mock_hass.states.async_set("switch.scheduled_device", "on")

    with (
        patch(
            "custom_components.sun_allocator.core.power_processor.is_device_in_schedule",
            return_value=False,
        ),
        patch(
            "custom_components.sun_allocator.core.power_processor.async_turn_off_entity",
            new_callable=AsyncMock,
        ) as mock_turn_off_entity,
    ):
        await process_excess_power(mock_hass, config_entry, 200)
        await process_excess_power(mock_hass, config_entry, 200)

        assert mock_turn_off_entity.await_count == 1

        mock_hass.states.async_set("switch.scheduled_device", "off")
        await process_excess_power(mock_hass, config_entry, 200)

        mock_hass.states.async_set("switch.scheduled_device", "on")
        await process_excess_power(mock_hass, config_entry, 200)

        assert mock_turn_off_entity.await_count == 2
