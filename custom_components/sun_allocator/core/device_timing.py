"""Per-device on-time accounting for Sun Allocator.

Tracks how long each device has run today (the runtime sensor + the
``max_on_time_per_day`` gate). Pure helpers with a single ``last_on_time`` /
``on_time_accum_sec`` / ``on_time_day`` state dict per device. Extracted from
``power_processor`` (re-exported there for import back-compat, and imported by the
manual switch / runtime sensor).
"""

from __future__ import annotations

from datetime import timedelta, time

from .logger import log_warning
from ..const import DEFAULT_DAILY_RESET_TIME


def _reset_offset_seconds(reset_time) -> int:
    """Parse a daily-reset time into a seconds-from-midnight offset. Accepts an
    ``"HH:MM[:SS]"`` string (HA TimeSelector), a ``datetime.time``, or a number of hours
    (legacy). Falls back to 06:00 on anything unparsable so a bad value can't disable rollover.
    """
    if isinstance(reset_time, bool):  # guard: bool is an int subclass
        reset_time = DEFAULT_DAILY_RESET_TIME
    if isinstance(reset_time, (int, float)):
        return int(reset_time) * 3600
    if isinstance(reset_time, time):
        return reset_time.hour * 3600 + reset_time.minute * 60 + reset_time.second
    try:
        parts = str(reset_time).split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        s = int(parts[2]) if len(parts) > 2 else 0
        return h * 3600 + m * 60 + s
    except (ValueError, IndexError, TypeError):
        return 6 * 3600


def _logical_day(now, reset_time=DEFAULT_DAILY_RESET_TIME):
    """The date of the current "logical day", whose boundary is ``reset_time`` (local),
    not calendar midnight. Shifting ``now`` back by that time-of-day maps the hours before
    the reset onto the previous date, so a manual choice / on-time total made late at night
    rolls over in the morning instead of at 00:00. ``"00:00:00"`` == calendar day.
    """
    return (now - timedelta(seconds=_reset_offset_seconds(reset_time))).date()


def _accumulate_daily_on_time(device_on_time_state, device_id, now,
                              reset_time=DEFAULT_DAILY_RESET_TIME) -> None:
    """Fold the just-finished ON session into today's accumulated on-time.

    Called when a device transitions OFF. Resets the accumulator first if the (logical)
    day rolled over, then adds ``now - last_on_time`` for the session that just ended.
    """
    entry = device_on_time_state.get(device_id)
    if not entry:
        return
    today = _logical_day(now, reset_time)
    if entry.get("on_time_day") != today:
        entry["on_time_day"] = today
        entry["on_time_accum_sec"] = 0.0
    last_on = entry.get("last_on_time")
    if last_on is not None:
        session = (now - last_on).total_seconds()
        if session < 0:
            log_warning(
                f"[on_time] Device {device_id}: negative session {session:.0f}s "
                f"(clock moved backward?) — not accumulated"
            )
        entry["on_time_accum_sec"] = entry.get("on_time_accum_sec", 0.0) + max(0.0, session)


def _close_on_time_session(device_on_time_state, device_id, now,
                           reset_time=DEFAULT_DAILY_RESET_TIME) -> None:
    """Close an in-progress on-time session on ANY on→off transition.

    Folds the running session into today's accumulator, stamps ``last_off_time`` and
    clears ``last_on_time``. Idempotent — a no-op when no session is open. Call this on
    EVERY path that turns a running device off (schedule/usable filter, discharge
    stop-floor, max-on-time, min-on-time off, manual off, manual battery-stop) so the
    runtime sensor and the ``max_on_time_per_day`` gate see a consistent daily total
    regardless of which gate shed the load.
    """
    entry = device_on_time_state.get(device_id)
    if not entry or entry.get("last_on_time") is None:
        return
    _accumulate_daily_on_time(device_on_time_state, device_id, now, reset_time)
    entry["last_off_time"] = now
    entry.pop("last_on_time", None)


def _daily_on_time_sec(device_on_time_state, device_id, now, currently_on,
                       reset_time=DEFAULT_DAILY_RESET_TIME) -> float:
    """Return seconds the device has run today (completed sessions + current one).

    Resets the per-day accumulator when the (logical) day changes. ``currently_on``
    adds the in-progress session (``now - last_on_time``).
    """
    entry = device_on_time_state.get(device_id, {})
    today = _logical_day(now, reset_time)
    if entry.get("on_time_day") != today:
        # Stale/absent day → nothing counted yet today.
        accum = 0.0
    else:
        accum = entry.get("on_time_accum_sec", 0.0)
    if currently_on:
        last_on = entry.get("last_on_time")
        if last_on is not None:
            accum += max(0.0, (now - last_on).total_seconds())
    return accum
