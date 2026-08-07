"""Watchdog for Sun Allocator."""

from datetime import timedelta

import homeassistant.util.dt as dt_util
from homeassistant.exceptions import HomeAssistantError
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    STATE_UNKNOWN,
    STATE_UNAVAILABLE,
)

from .logger import log_error, log_info, log_warning
from .settings import WATCHDOG_STALE_AFTER_MINUTES
from .entity_control import parse_relay_entity
from .constants_internal import SUPPORTED_DOMAINS

from ..const import (
    CONF_DEVICE_ENTITY,
    DOMAIN_CLIMATE,
)

# Backward-compatible alias for the watchdog's own usage.
SUPPORTED_OFF_DOMAINS = SUPPORTED_DOMAINS


async def _enforce_all_off(hass, config_entry, reason: str):
    """Enforce all devices are turned off."""
    # Reset internal state tracking so hysteresis thresholds recalculate correctly on recovery
    entry_data = hass.data.get(config_entry.domain, {}).get(config_entry.entry_id, {})
    device_on_state = entry_data.get("device_on_state", {})
    for _device_id in device_on_state:
        device_on_state[_device_id] = False
    # Also clear manual overrides — watchdog takes priority over everything
    entry_data.pop("manual_overrides", None)
    # Stand the probe down: drop any discovered headroom so it cannot re-inflate
    # the budget and re-enable devices while the fail-safe OFF is in force.
    entry_data["probe_headroom_w"] = 0.0
    entry_data.pop("probe_state", None)

    devices_cfg = config_entry.data.get("devices", [])
    for dev in devices_cfg:
        entity_id, _ = parse_relay_entity(dev.get(CONF_DEVICE_ENTITY))
        if not entity_id:
            continue

        # Validate entity_id format
        if "." not in entity_id:
            log_warning(f"Invalid entity_id format: {entity_id}")
            continue

        domain = entity_id.split(".")[0]
        if not domain:
            log_warning(f"Empty domain in entity_id: {entity_id}")
            continue

        if domain not in SUPPORTED_OFF_DOMAINS:
            log_warning(f"Watchdog: unsupported domain '{domain}' for {entity_id}, skipping")
            continue

        try:
            if domain == DOMAIN_CLIMATE:
                await hass.services.async_call(
                    domain, "set_hvac_mode",
                    {ATTR_ENTITY_ID: entity_id, "hvac_mode": "off"},
                    blocking=True,
                )
            else:
                await hass.services.async_call(
                    domain, SERVICE_TURN_OFF,
                    {ATTR_ENTITY_ID: entity_id},
                    blocking=True,
                )
        except HomeAssistantError as exc:
            log_warning(f"Watchdog OFF failed for {entity_id}: {exc}")

    log_error(f"SunAllocator watchdog: fail-safe OFF enforced ({reason})")


async def watchdog_check(hass, config_entry):
    """Fail-safe OFF when the excess-power pipeline has genuinely DIED.

    ``watchdog_last_seen`` is refreshed by the excess sensor's state-change handler, which
    HA fires only when the value MOVES. A live sensor holding a steady value — 0 W all
    night with the PV dark, or a deadbanded flat reading during curtailment — would freeze
    that timestamp and trip a false fail-safe (forcing every device, including manual ones,
    OFF) exactly when nothing is wrong. So first re-derive liveness from the sensor's ACTUAL
    state: a readable numeric value means the pipeline is alive → refresh and return. Only a
    genuinely ``unavailable``/``unknown``/missing sensor (the real "inverter/integration
    died" signal — the MUST inverter marks its sensors unavailable on comms loss, which
    propagates to the excess sensor) is allowed to accrue staleness toward the fail-safe.
    """
    entry_data = hass.data[config_entry.domain][config_entry.entry_id]

    excess_sensor_id = entry_data.get("excess_sensor_id")
    if excess_sensor_id:
        st = hass.states.get(excess_sensor_id)
        if st is not None and st.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                float(st.state)
            except (ValueError, TypeError):
                pass  # non-numeric → not a healthy reading; fall through to staleness
            else:
                entry_data["watchdog_last_seen"] = dt_util.utcnow()
                if entry_data.get("watchdog_alerted"):
                    entry_data["watchdog_alerted"] = False
                    log_info(
                        "SunAllocator watchdog: excess sensor live again; normal operation resumed"
                    )
                return

    last_seen = entry_data.get("watchdog_last_seen")
    alerted = entry_data.get("watchdog_alerted", False)
    watchdog_stale_after = timedelta(minutes=WATCHDOG_STALE_AFTER_MINUTES)

    if not last_seen:
        return
    stale_for = dt_util.utcnow() - last_seen
    if stale_for > watchdog_stale_after:
        if not alerted:
            entry_data["watchdog_alerted"] = True
            await _enforce_all_off(
                hass,
                config_entry,
                f"excess sensor stale for {int(stale_for.total_seconds())}s",
            )
    elif alerted:
        entry_data["watchdog_alerted"] = False
        log_info("SunAllocator watchdog: data fresh again; normal operation resumed")
