"""Tests for power distribution strategies."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant, State

from custom_components.sun_allocator.core.power_processor import process_excess_power
from custom_components.sun_allocator.const import (
    DOMAIN,
    DEVICE_TYPE_STANDARD,
    DEVICE_TYPE_CUSTOM,
    CONF_DEVICE_ALLOCATION_STRATEGY,
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
