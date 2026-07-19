"""Timed-run control: force a device ON for N minutes, ignoring battery + schedule.

Extends the sticky ``manual_overrides`` mechanism with two optional fields:
``until`` (an aware deadline) and ``ignore_battery`` (full SOC bypass). While a timed
run is active the device is treated as ``manual_on`` (so it already bypasses the
schedule/usable filter) plus the battery-protection force-off is skipped. Ending the
run — deadline reached, or cancelled early via the number field — releases the
override entirely and hands control back to auto (same as the manual switch's OFF
release semantics); see ``_control_one_device`` in ``power_processor.py``.
"""

from __future__ import annotations

from datetime import timedelta

import homeassistant.util.dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNKNOWN, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from .logger import log_debug, log_info
from .entity_control import turn_on_entity, parse_relay_entity

from ..const import (
    DOMAIN,
    CONF_DEVICE_ID,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_NAME,
    CONF_POWER_DISTRIBUTION,
)


def is_timed_override(override) -> bool:
    """True when a manual override carries a timed-run deadline."""
    return bool(override) and override.get("until") is not None


def is_expired(override, now) -> bool:
    """True when a timed override's deadline has passed (→ release to auto)."""
    return is_timed_override(override) and now >= override["until"]


def timed_run_remaining_min(override, now) -> int:
    """Whole minutes left on an active timed run (ceil), else 0."""
    if not is_timed_override(override):
        return 0
    remaining = (override["until"] - now).total_seconds()
    if remaining <= 0:
        return 0
    return int(-(-remaining // 60))  # ceil division


async def _trigger_reeval(hass: HomeAssistant, config_entry: ConfigEntry, entry_data: dict) -> None:
    """Kick an immediate allocation run so budget/status/sensors update at once.

    Deferred import breaks the ``__init__`` ↔ ``core`` import cycle; the queue helper
    serializes against the periodic run via the shared lock.
    """
    try:
        from .. import _queue_process_excess_power

        last_excess = float(
            (entry_data.get(CONF_POWER_DISTRIBUTION, {}) or {}).get("total_power", 0.0) or 0.0
        )
        await _queue_process_excess_power(hass, config_entry, entry_data, last_excess)
    except Exception as exc:  # noqa: BLE001 - never let a UI action fail on re-eval
        log_debug("[timed] re-eval trigger failed: %s", exc)


async def start_timed_run(
    hass: HomeAssistant, config_entry: ConfigEntry, device: dict, minutes: int
) -> bool:
    """Force ``device`` ON for ``minutes``, ignoring battery + schedule limits.

    Returns True if the run was armed. Mirrors ``manual_switch`` bookkeeping so the
    override is honored on the next cycle without racing ``_detect_external_change``.
    """
    entry_data = hass.data.get(DOMAIN, {}).get(config_entry.entry_id)
    device_id = device.get(CONF_DEVICE_ID)
    if entry_data is None or not device_id or minutes <= 0:
        return False

    relay_entity, hvac_mode = parse_relay_entity(device.get(CONF_DEVICE_ENTITY))
    if not relay_entity:
        return False
    st = hass.states.get(relay_entity)
    if st is None or st.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        log_debug("[timed] %s: entity %s unavailable, not arming", device_id, relay_entity)
        return False

    now = dt_util.now()
    entry_data.setdefault("manual_overrides", {})[device_id] = {
        "since": now,
        "state": True,
        "until": now + timedelta(minutes=int(minutes)),
        "ignore_battery": True,
        "timer_minutes": int(minutes),
    }
    # Align device_on_state so the entity's resulting ON is NOT misread as a user
    # toggle by _detect_external_change. Stamp (not clear) last_controlled_at — while
    # a slow-to-confirm relay (cloud/Tuya lag) hasn't caught up, this reads as "still
    # catching up to our own command", not a user toggle; clearing it instead let a
    # stale "off" reading immediately clobber the timed fields (until/ignore_battery),
    # cutting the run short well before its deadline.
    entry_data.setdefault("device_on_state", {})[device_id] = True
    entry_data.setdefault("last_controlled_at", {})[device_id] = now

    await turn_on_entity(hass, relay_entity, hvac_mode, device.get(CONF_DEVICE_NAME, ""))
    log_info("[timed] %s: run armed for %d min (battery+schedule bypassed)", device_id, int(minutes))
    await _trigger_reeval(hass, config_entry, entry_data)
    return True


async def cancel_timed_run(hass: HomeAssistant, config_entry: ConfigEntry, device_id: str) -> None:
    """Cancel an active timed run → release fully to auto-control (matches natural
    expiry and the manual-switch OFF release semantics).

    No-op when the device has no timed override.
    """
    entry_data = hass.data.get(DOMAIN, {}).get(config_entry.entry_id)
    if entry_data is None or not device_id:
        return
    overrides = entry_data.setdefault("manual_overrides", {})
    override = overrides.get(device_id)
    if not is_timed_override(override):
        return
    overrides.pop(device_id, None)
    log_info("[timed] %s: timer cancelled → released to auto", device_id)
    await _trigger_reeval(hass, config_entry, entry_data)
