"""Device restore and persist logic for Sun Allocator."""

from __future__ import annotations

from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .logger import log_info, log_debug
from .entity_control import set_power_for_entity, set_mode_for_entity, parse_relay_entity

from ..const import (
    DOMAIN,
    DOMAIN_CLIMATE,
    CONF_DEVICES,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_ID,
    CONF_ESPHOME_MODE_SELECT_ENTITY,
)

STORAGE_VERSION = 1

# Reserved (non-entity-id) key inside the per-entry restore dict for cross-entity state
# such as device_id-keyed startup grace deadlines.
_GRACE_STORAGE_KEY = "_grace_state"


def _get_store(hass, config_entry) -> Store:
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}_{config_entry.entry_id}_restore")


async def _load_restore_data(hass, config_entry) -> dict:
    store = _get_store(hass, config_entry)
    data = await store.async_load()
    return data or {}


async def _save_restore_data(hass, config_entry, data: dict):
    store = _get_store(hass, config_entry)
    await store.async_save(data)


async def persist_device_state(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    entity_id: str,
    percent: float | None = None,
    is_on: bool | None = None,
) -> None:
    """Persist the device state to storage (NOT config_entry.data)."""
    restore_data = await _load_restore_data(hass, config_entry)
    device_data = restore_data.get(entity_id, {})
    changed = False

    if percent is not None and device_data.get("last_percent") != percent:
        device_data["last_percent"] = percent
        changed = True

    if is_on is not None and device_data.get("_restore_on") != is_on:
        device_data["_restore_on"] = is_on
        changed = True

    if changed:
        restore_data[entity_id] = device_data
        log_debug("--- DEVICE RESTORE ---: Saving state for %s: %s", entity_id, device_data)
        await _save_restore_data(hass, config_entry, restore_data)


async def persist_grace_state(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    device_id: str,
    startup_until: datetime | None,
) -> None:
    """Persist the startup-grace deadline for a device so it survives a HA restart.

    ``startup_until`` accepts a ``datetime`` (preferred) or ``None`` to clear.
    Idempotent — a no-op when the stored value already matches.
    """
    if not device_id:
        return
    iso = startup_until.isoformat() if isinstance(startup_until, datetime) else None
    restore_data = await _load_restore_data(hass, config_entry)
    grace = dict(restore_data.get(_GRACE_STORAGE_KEY, {}))
    if iso is None:
        if device_id not in grace:
            return
        grace.pop(device_id, None)
    else:
        if grace.get(device_id) == iso:
            return
        grace[device_id] = iso
    restore_data[_GRACE_STORAGE_KEY] = grace
    log_debug("--- GRACE RESTORE ---: device=%s until=%s", device_id, iso)
    await _save_restore_data(hass, config_entry, restore_data)


async def load_grace_state(hass: HomeAssistant, config_entry: ConfigEntry) -> dict[str, datetime]:
    """Return ``{device_id: datetime}`` for all persisted grace deadlines.

    Malformed or expired-by-format entries are silently dropped; callers should
    additionally check ``deadline > now`` before applying.
    """
    restore_data = await _load_restore_data(hass, config_entry)
    raw = restore_data.get(_GRACE_STORAGE_KEY, {}) or {}
    out: dict[str, datetime] = {}
    for device_id, iso in raw.items():
        try:
            out[device_id] = datetime.fromisoformat(iso)
        except (TypeError, ValueError):
            log_debug("[grace] dropping malformed entry %s=%r", device_id, iso)
    return out


async def persist_mode_state(
    hass: HomeAssistant, config_entry: ConfigEntry, entity_id: str, mode: str
) -> None:
    """Persist the mode state to storage (NOT config_entry.data)."""
    restore_data = await _load_restore_data(hass, config_entry)
    device_data = restore_data.get(entity_id, {})

    if device_data.get("last_mode") != mode:
        device_data["last_mode"] = mode
        restore_data[entity_id] = device_data
        log_debug("--- MODE RESTORE ---: Saving mode for %s: %s", entity_id, mode)
        await _save_restore_data(hass, config_entry, restore_data)


def _build_climate_target(base_entity: str, hvac_suffix: str | None) -> str:
    """Append the hvac mode suffix back to a climate entity for set_power_for_entity."""
    if hvac_suffix and base_entity.startswith(DOMAIN_CLIMATE + "."):
        return f"{base_entity}|{hvac_suffix}"
    return base_entity


async def _restore_relay(hass, device, restore_data, *, force: bool):
    """Apply the persisted state for a single device's relay entity.

    ``force`` skips the "already at desired state" check (used when an entity
    just came back from unavailable and we always want to assert the target).
    """
    base_entity, hvac_suffix = parse_relay_entity(device.get(CONF_DEVICE_ENTITY))
    if not base_entity:
        return False

    entity_data = restore_data.get(base_entity, {})
    percent = entity_data.get("last_percent")
    is_on = entity_data.get("_restore_on")
    target = _build_climate_target(base_entity, hvac_suffix)
    domain = base_entity.split(".")[0]
    state = hass.states.get(base_entity)

    if percent is not None:
        log_info(f"[Restore] Setting percent {percent} for {target}")
        await set_power_for_entity(hass, target, percent)
        return True

    if is_on is None:
        if force:
            log_info(f"[Restore] No saved state for {base_entity}")
        return False

    currently_on = False
    if state is not None:
        currently_on = (
            state.state != "off" if domain == DOMAIN_CLIMATE else state.state == STATE_ON
        )

    if force or is_on != currently_on:
        log_info(f"[Restore] Setting {'ON' if is_on else 'OFF'} for {target}")
        await set_power_for_entity(hass, target, 100 if is_on else 0)
        return True

    return False


async def _restore_mode(hass, device, restore_data, *, force: bool):
    """Apply the persisted ESPHome mode for a single device's mode_select entity."""
    mode_select_entity = device.get(CONF_ESPHOME_MODE_SELECT_ENTITY)
    if not mode_select_entity:
        return False

    last_mode = restore_data.get(mode_select_entity, {}).get("last_mode")
    if not last_mode:
        return False

    state = hass.states.get(mode_select_entity)
    if not force and state and state.state == last_mode:
        return False

    log_info(f"[Restore] Setting mode {last_mode} for {mode_select_entity}")
    await set_mode_for_entity(hass, mode_select_entity, last_mode)
    return True


async def restore_entity_state(
    hass: HomeAssistant, config_entry: ConfigEntry, entity_id: str
) -> None:
    """Restore the persisted state for a single entity that just became available."""
    restore_data = await _load_restore_data(hass, config_entry)
    for device in config_entry.data.get(CONF_DEVICES, []):
        base_entity, _ = parse_relay_entity(device.get(CONF_DEVICE_ENTITY))
        if base_entity == entity_id:
            await _restore_relay(hass, device, restore_data, force=True)
        if device.get(CONF_ESPHOME_MODE_SELECT_ENTITY) == entity_id:
            await _restore_mode(hass, device, restore_data, force=True)


async def restore_all_devices(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Restore all devices after Home Assistant restart."""
    restore_data = await _load_restore_data(hass, config_entry)
    devices = config_entry.data.get(CONF_DEVICES, [])
    log_info("Found %d devices to check for restore state", len(devices))
    restored_any = False

    for device in devices:
        device_id = device.get(CONF_DEVICE_ID)
        log_info(f"Checking restore state for device_id: {device_id}")

        if await _restore_mode(hass, device, restore_data, force=False):
            restored_any = True
        if await _restore_relay(hass, device, restore_data, force=False):
            restored_any = True

    if not restored_any:
        log_info("No device states needed to be restored after restart.")
