"""Schedule handling for Sun Allocator."""

import homeassistant.util.dt as dt_util

from ..const import (
    CONF_DEVICE_SCHEDULE_ENABLED,
    CONF_START_TIME,
    CONF_END_TIME,
    CONF_DAYS_OF_WEEK,
    DAYS_OF_WEEK,
)


def is_device_in_schedule(device, now=None):
    """Check if the device is within its scheduled time."""
    # If scheduling is not enabled, device is always active
    if not device.get(CONF_DEVICE_SCHEDULE_ENABLED, False):
        return True

    # Get current time and day if not provided
    if now is None:
        now = dt_util.now()

    # Get schedule settings
    start_time = device.get(CONF_START_TIME)
    end_time = device.get(CONF_END_TIME)
    days_of_week = device.get(CONF_DAYS_OF_WEEK, DAYS_OF_WEEK)

    # If no schedule settings, device is always active
    if not start_time or not end_time or not days_of_week:
        return True

    # Check if current day is in schedule (locale-independent)
    day_index_to_name = DAYS_OF_WEEK  # ["monday", ..., "sunday"]
    current_day = day_index_to_name[now.weekday()]
    if current_day not in days_of_week:
        return False

    # Convert datetime to time for comparison
    current_time = now.time()

    # Handle overnight schedules (end_time < start_time)
    if end_time < start_time:
        # Active from start_time to midnight or from midnight to end_time
        return current_time >= start_time or current_time <= end_time

    # Active from start_time to end_time
    return start_time <= current_time <= end_time
