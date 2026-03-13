"""Device restore and persist logic for Sun Allocator."""

from homeassistant.const import STATE_ON, STATE_OFF
from homeassistant.helpers.storage import Store

from .logger import log_info, log_debug
from .entity_control import set_power_for_entity, set_mode_for_entity

from ..const import (
    DOMAIN,
    DOMAIN_CLIMATE,
    CONF_DEVICES,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_ID,
    CONF_ESPHOME_MODE_SELECT_ENTITY,
)

STORAGE_VERSION = 1


def _get_store(hass, config_entry) -> Store:
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}_{config_entry.entry_id}_restore")


async def _load_restore_data(hass, config_entry) -> dict:
    store = _get_store(hass, config_entry)
    data = await store.async_load()
    return data or {}


async def _save_restore_data(hass, config_entry, data: dict):
    store = _get_store(hass, config_entry)
    await store.async_save(data)


async def persist_device_state(hass, config_entry, entity_id, percent=None, is_on=None):
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


async def persist_mode_state(hass, config_entry, entity_id, mode: str):
    """Persist the mode state to storage (NOT config_entry.data)."""
    restore_data = await _load_restore_data(hass, config_entry)
    device_data = restore_data.get(entity_id, {})

    if device_data.get("last_mode") != mode:
        device_data["last_mode"] = mode
        restore_data[entity_id] = device_data
        log_debug("--- MODE RESTORE ---: Saving mode for %s: %s", entity_id, mode)
        await _save_restore_data(hass, config_entry, restore_data)


async def restore_entity_state(hass, config_entry, entity_id):
    """Restore the entity state after Home Assistant restart."""
    restore_data = await _load_restore_data(hass, config_entry)
    devices = config_entry.data.get(CONF_DEVICES, [])

    for device in devices:
        relay_entity = device.get(CONF_DEVICE_ENTITY)
        mode_select_entity = device.get(CONF_ESPHOME_MODE_SELECT_ENTITY)

        if relay_entity and relay_entity.split("|")[0] == entity_id:
            entity_restore = restore_data.get(entity_id, {})
            percent = entity_restore.get("last_percent")
            is_on = entity_restore.get("_restore_on")

            if percent is not None:
                log_info(f"[Restore] Setting percent {percent} for {entity_id}")
                await set_power_for_entity(hass, entity_id, percent)
            elif is_on is not None:
                log_info(f"[Restore] Setting ON/OFF {is_on} for {entity_id}")
                await set_power_for_entity(hass, entity_id, 100 if is_on else 0)
            else:
                log_info(f"[Restore] No saved state for {entity_id}")

        if mode_select_entity == entity_id:
            mode_restore = restore_data.get(entity_id, {})
            last_mode = mode_restore.get("last_mode")
            if last_mode:
                log_info(f"[Restore] Setting mode {last_mode} for {entity_id}")
                await set_mode_for_entity(hass, entity_id, last_mode)


async def restore_all_devices(hass, config_entry):
    """Restore all devices after Home Assistant restart."""
    restore_data = await _load_restore_data(hass, config_entry)
    devices = config_entry.data.get(CONF_DEVICES, [])
    log_info("Found %d devices to check for restore state", len(devices))
    restored = set()

    for device in devices:
        device_id = device.get(CONF_DEVICE_ID)
        hvac_mode = device.get("hvac_mode")
        log_info(f"Checking restore state for device_id: {device_id}")

        relay_entity = device.get(CONF_DEVICE_ENTITY)
        mode_select_entity = device.get(CONF_ESPHOME_MODE_SELECT_ENTITY)

        if mode_select_entity:
            mode_data = restore_data.get(mode_select_entity, {})
            last_mode = mode_data.get("last_mode")
            if last_mode:
                state = hass.states.get(mode_select_entity)
                if state and state.state != last_mode:
                    log_info(f"Restoring mode '{last_mode}' for {mode_select_entity}")
                    await set_mode_for_entity(hass, mode_select_entity, last_mode)
                    restored.add(mode_select_entity)

        if relay_entity:
            # Strip |hvac_mode suffix to get the bare HA entity id
            base_entity = relay_entity.split("|")[0] if "|" in relay_entity else relay_entity
            domain = base_entity.split(".")[0]

            # Build the entity_to_restore with hvac_mode suffix if needed
            hvac_suffix = relay_entity.split("|")[1] if "|" in relay_entity else hvac_mode
            if domain == DOMAIN_CLIMATE and hvac_suffix:
                entity_to_restore = f"{base_entity}|{hvac_suffix}"
            else:
                entity_to_restore = base_entity

            state = hass.states.get(base_entity)
            entity_data = restore_data.get(base_entity, {})
            percent = entity_data.get("last_percent")

            if percent is not None:
                log_info(f"Restoring percent {percent} for {entity_to_restore}")
                await set_power_for_entity(hass, entity_to_restore, percent)
                restored.add(relay_entity)
            elif state:
                is_on = entity_data.get("_restore_on", False)
                # Climate entities use non-binary states ("heat", "cool", "off") — check != "off"
                currently_on = (
                    state.state != "off" if domain == DOMAIN_CLIMATE else state.state == STATE_ON
                )
                if is_on and not currently_on:
                    log_info(f"Restoring ON state for {entity_to_restore}")
                    await set_power_for_entity(hass, entity_to_restore, 100)
                    restored.add(relay_entity)
                elif not is_on and currently_on:
                    log_info(f"Restoring OFF state for {entity_to_restore}")
                    await set_power_for_entity(hass, entity_to_restore, 0)
                    restored.add(relay_entity)

    if not restored:
        log_info("No device states needed to be restored after restart.")
