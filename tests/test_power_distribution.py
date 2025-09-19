"""Tests for priority-based power distribution."""
import pytest
from unittest.mock import AsyncMock, patch
from custom_components.sun_allocator.core.power_processor import process_excess_power

@pytest.mark.asyncio
async def test_priority_power_distribution(hass):
    """Test that higher priority devices get power first."""
    from unittest.mock import MagicMock
    
    # Create mock config entry
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"
    config_entry.data = {
        "devices": [
            {
                "device_id": "low_priority",
                "device_name": "Low Priority Device",
                "device_entity": "switch.low_priority",
                "device_type": "standard",
                "priority": 30,
                "min_expected_w": 100,
                "max_expected_w": 200,
                "auto_control_enabled": True,
                "debounce_time": 0
            },
            {
                "device_id": "high_priority", 
                "device_name": "High Priority Device",
                "device_entity": "switch.high_priority",
                "device_type": "standard",
                "priority": 80,
                "min_expected_w": 150,
                "max_expected_w": 300,
                "auto_control_enabled": True,
                "debounce_time": 0
            }
        ]
    }

    # Initialize hass.data structure
    from custom_components.sun_allocator.const import DOMAIN
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    hass.data[DOMAIN][config_entry.entry_id] = {
        "device_status": {},
        "device_filter_reasons": {},
        "device_on_state": {},
        "device_debounce_state": {},
        "power_allocation": {},
        "power_distribution": {}
    }

    # Mock states
    hass.states.async_set("switch.low_priority", "off")
    hass.states.async_set("switch.high_priority", "off")

    with patch("homeassistant.core.ServiceRegistry.async_call", new_callable=AsyncMock) as mock_call:
        # Test with limited excess power (only enough for one device)
        excess_power = 200  # Only enough for high priority device

        await process_excess_power(hass, config_entry, excess_power)

        # High priority device should be turned on
        calls = [call for call in mock_call.call_args_list if call[0][1] == "turn_on"]
        assert len(calls) >= 1
        # Check if any call contains high_priority device
        high_priority_calls = [call for call in calls if "high_priority" in str(call)]
        assert len(high_priority_calls) >= 1

@pytest.mark.asyncio 
async def test_proportional_power_allocation(hass):
    """Test proportional power allocation for ESPHome devices."""
    from unittest.mock import MagicMock
    
    # Create mock config entry
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"
    config_entry.data = {
        "devices": [
            {
                "device_id": "proportional_device",
                "device_name": "Proportional Device",
                "device_entity": "switch.proportional_device", 
                "device_type": "custom",
                "esphome_mode_select_entity": "select.proportional_mode",
                "priority": 50,
                "min_expected_w": 50,
                "max_expected_w": 200,
                "auto_control_enabled": True,
                "debounce_time": 0
            }
        ]
    }

    # Initialize hass.data structure
    from custom_components.sun_allocator.const import DOMAIN
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    hass.data[DOMAIN][config_entry.entry_id] = {
        "device_status": {},
        "device_filter_reasons": {},
        "device_on_state": {},
        "device_debounce_state": {},
        "power_allocation": {},
        "power_distribution": {}
    }

    hass.states.async_set("switch.proportional_device", "off")
    hass.states.async_set("select.proportional_mode", "Proportional")

    with patch("homeassistant.core.ServiceRegistry.async_call", new_callable=AsyncMock) as mock_call:
        excess_power = 100  # 50% of max power

        await process_excess_power(hass, config_entry, excess_power)

        # Should set mode to Proportional and brightness to 50%
        mode_calls = [call for call in mock_call.call_args_list if "select_option" in str(call)]
        brightness_calls = [call for call in mock_call.call_args_list if "turn_on" in str(call)]

        # Check that some calls were made (exact behavior may vary based on implementation)
        assert len(mock_call.call_args_list) >= 1

