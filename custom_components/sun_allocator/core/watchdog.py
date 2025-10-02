"""Watchdog for Sun Allocator."""

from datetime import timedelta
import homeassistant.util.dt as dt_util
from homeassistant.exceptions import HomeAssistantError
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
)
from ..const import (
    CONF_DEVICE_ENTITY,
    DOMAIN_LIGHT,
    DOMAIN_SWITCH,
    DOMAIN_INPUT_BOOLEAN,
    DOMAIN_AUTOMATION,
    DOMAIN_SCRIPT,
)

from .logger import log_error, log_info, log_warning


async def _enforce_all_off(hass, config_entry, reason: str):
    """Enforce all devices are turned off."""
    devices_cfg = config_entry.data.get("devices", [])
    for dev in devices_cfg:
        entity_id = dev.get(CONF_DEVICE_ENTITY)
        if not entity_id:
            continue
        if "|" in entity_id:
            entity_id = entity_id.split("|")[0]

        # Validate entity_id format
        if "." not in entity_id:
            log_warning(f"Invalid entity_id format: {entity_id}")
            continue

        domain = entity_id.split(".")[0]
        if not domain:
            log_warning(f"Empty domain in entity_id: {entity_id}")
            continue

        try:
            service_domain = (
                domain
                if domain
                in [
                    DOMAIN_LIGHT,
                    DOMAIN_SWITCH,
                    DOMAIN_INPUT_BOOLEAN,
                    DOMAIN_AUTOMATION,
                    DOMAIN_SCRIPT,
                ]
                else DOMAIN_LIGHT
            )
            await hass.services.async_call(
                service_domain,
                SERVICE_TURN_OFF,
                {ATTR_ENTITY_ID: entity_id},
                blocking=True,
            )
        except HomeAssistantError as exc:
            log_warning(f"Watchdog OFF failed for {entity_id}: {exc}")

    log_error(f"SunAllocator watchdog: fail-safe OFF enforced ({reason})")


async def watchdog_check(hass, config_entry):
    """Check if the excess power sensor is stale."""
    entry_data = hass.data[config_entry.domain][config_entry.entry_id]
    last_seen = entry_data.get("watchdog_last_seen")
    alerted = entry_data.get("watchdog_alerted", False)
    watchdog_stale_after = timedelta(minutes=3)

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
