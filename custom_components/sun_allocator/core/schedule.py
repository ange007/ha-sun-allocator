"""Schedule handling for Sun Allocator."""

from datetime import time

import homeassistant.util.dt as dt_util

from ..const import (
    CONF_DEVICE_SCHEDULE_MODE,
    SCHEDULE_MODE_DISABLED,
    SCHEDULE_MODE_HELPER,
    CONF_DEVICE_SCHEDULE_HELPER_ENTITY,
    CONF_START_TIME,
    CONF_END_TIME,
    CONF_DAYS_OF_WEEK,
    DAYS_OF_WEEK,
)


def _ensure_time(value):
    """Convert a string or time object to datetime.time safely."""
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        try:
            parts = value.split(":")
            return time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            return None
    return None


def is_device_in_schedule(device, now=None, hass=None):
    """Check if the device is within its scheduled time."""
    schedule_mode = device.get(CONF_DEVICE_SCHEDULE_MODE, SCHEDULE_MODE_DISABLED)

    if schedule_mode == SCHEDULE_MODE_DISABLED:
        return True

    if schedule_mode == SCHEDULE_MODE_HELPER:
        if hass is None:
            return True
        helper_entity = device.get(CONF_DEVICE_SCHEDULE_HELPER_ENTITY)
        if not helper_entity:
            return True
        state = hass.states.get(helper_entity)
        return state is not None and state.state == "on"

    # SCHEDULE_MODE_STANDARD — time-based schedule
    # Get current time and day if not provided
    if now is None:
        now = dt_util.now()

    # Get schedule settings and ensure they are time objects
    start_time = _ensure_time(device.get(CONF_START_TIME))
    end_time = _ensure_time(device.get(CONF_END_TIME))
    days_of_week = device.get(CONF_DAYS_OF_WEEK, DAYS_OF_WEEK)

    # If no schedule settings, device is always active
    if start_time is None or end_time is None:
        return True
    # No days selected = never active within schedule
    if not days_of_week:
        return False

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
