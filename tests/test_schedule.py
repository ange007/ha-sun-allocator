"""Tests for device scheduling functionality."""
import pytest
from datetime import time, datetime
from custom_components.sun_allocator.core.schedule import is_device_in_schedule

@pytest.mark.parametrize("current_time,start_time,end_time,days,expected", [
    (time(12, 0), time(10, 0), time(14, 0), ["monday"], True),   # Within schedule
    (time(9, 0), time(10, 0), time(14, 0), ["monday"], False),   # Before schedule
    (time(15, 0), time(10, 0), time(14, 0), ["monday"], False),  # After schedule
    (time(23, 0), time(22, 0), time(2, 0), ["monday"], True),    # Overnight schedule
    (time(1, 0), time(22, 0), time(2, 0), ["monday"], True),     # Overnight schedule (early morning)
])
async def test_schedule_time_ranges(current_time, start_time, end_time, days, expected):
    """Test various time range scenarios."""
    device = {
        "schedule_enabled": True,
        "start_time": start_time,
        "end_time": end_time,
        "days_of_week": days
    }

    # Mock datetime to Monday
    mock_now = datetime(2024, 1, 1, current_time.hour, current_time.minute)  # Monday
    result = is_device_in_schedule(device, mock_now)
    assert result == expected

async def test_schedule_disabled():
    """Test that disabled schedule always returns True."""
    device = {"schedule_enabled": False}
    result = is_device_in_schedule(device)
    assert result is True

