"""Tests for device scheduling functionality."""

import pytest
from datetime import time, datetime

from custom_components.sun_allocator.core.schedule import is_device_in_schedule
from custom_components.sun_allocator.const import (
    CONF_DEVICE_SCHEDULE_ENABLED,
    CONF_START_TIME,
    CONF_END_TIME,
    CONF_DAYS_OF_WEEK,
    DAY_MONDAY,
)


@pytest.mark.parametrize(
    "current_time,start_time,end_time,days,expected",
    [
        (time(12, 0), time(10, 0), time(14, 0), [DAY_MONDAY], True),  # Within schedule
        (time(9, 0), time(10, 0), time(14, 0), [DAY_MONDAY], False),  # Before schedule
        (time(15, 0), time(10, 0), time(14, 0), [DAY_MONDAY], False),  # After schedule
        (
            time(23, 0),
            time(22, 0),
            time(2, 0),
            [DAY_MONDAY],
            True,
        ),  # Overnight schedule
        (
            time(1, 0),
            time(22, 0),
            time(2, 0),
            [DAY_MONDAY],
            True,
        ),  # Overnight schedule (early morning)
    ],
)
async def test_schedule_time_ranges(current_time, start_time, end_time, days, expected):
    """Test various time range scenarios."""
    device = {
        CONF_DEVICE_SCHEDULE_ENABLED: True,
        CONF_START_TIME: start_time,
        CONF_END_TIME: end_time,
        CONF_DAYS_OF_WEEK: days,
    }

    # Mock datetime to Monday
    mock_now = datetime(2024, 1, 1, current_time.hour, current_time.minute)  # Monday
    result = is_device_in_schedule(device, mock_now)
    assert result == expected


async def test_schedule_disabled():
    """Test that disabled schedule always returns True."""
    device = {CONF_DEVICE_SCHEDULE_ENABLED: False}
    result = is_device_in_schedule(device)
    assert result is True
