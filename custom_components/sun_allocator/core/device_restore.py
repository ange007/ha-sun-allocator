"""Device restore and persist logic for Sun Allocator."""

from homeassistant.const import STATE_ON, STATE_OFF

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


async def persist_device_state(hass, config_entry, entity_id, percent=None, is_on=None):
    """Persist the device state to the config entry."""
    # Defer persistence if a config flow is in progress to avoid race conditions
    active_flows = config_entry.async_get_active_flows(hass)
    if any(flow.get("handler") == DOMAIN for flow in active_flows):
        log_debug(
            "Config flow in progress. Deferring persistence of device state for %s.",
            entity_id,
        )
        return

    data = dict(config_entry.data)
    devs = list(data.get(CONF_DEVICES, []))
    changed = False
    for i, dev in enumerate(devs):
        relay_entity = dev.get(CONF_DEVICE_ENTITY)
        if relay_entity == entity_id:
            nd = dict(dev)
            if percent is not None:
                if nd.get("last_percent") != percent:
                    nd["last_percent"] = percent
                    changed = True
            if is_on is not None:
                if nd.get("_restore_on") != is_on:
                    nd["_restore_on"] = is_on
                    changed = True
            devs[i] = nd
            break
    if changed:
        data[CONF_DEVICES] = devs
        log_debug(
            "--- DEVICE RESTORE ---: Saving %d devices. Data: %s", len(devs), data
        )
        hass.config_entries.async_update_entry(config_entry, data=data)


async def restore_entity_state(hass, config_entry, entity_id):
    """Restore the entity state after Home Assistant restart."""
    devices = config_entry.data.get(CONF_DEVICES, [])
    for device in devices:
        relay_entity = device.get(CONF_DEVICE_ENTITY)
        mode_select_entity = device.get(CONF_ESPHOME_MODE_SELECT_ENTITY)
        if relay_entity == entity_id:
            percent = device.get("last_percent")
            is_on = device.get("_restore_on")
            if percent is not None:
                log_info(f"[Restore] Setting percent {percent} for {entity_id}")
                await set_power_for_entity(hass, entity_id, percent)
            elif is_on is not None:
                log_info(f"[Restore] Setting ON/OFF {is_on} for {entity_id}")
                await set_power_for_entity(hass, entity_id, 100 if is_on else 0)
            else:
                log_info(f"[Restore] No saved state for {entity_id}")
        if mode_select_entity == entity_id:
            last_mode = device.get("last_mode")
            if last_mode:
                log_info(f"[Restore] Setting mode {last_mode} for {entity_id}")
                await set_mode_for_entity(hass, entity_id, last_mode)


async def restore_all_devices(hass, config_entry):
    """Restore all devices after Home Assistant restart."""
    devices = config_entry.data.get(CONF_DEVICES, [])
    log_info("Found %d devices to check for restore state", len(devices))
    restored = set()
    for device in devices:
        device_id = device.get(CONF_DEVICE_ID)
        hvac_mode = device.get("_hvac_mode")
        log_info(f"Checking restore state for device_id: {device_id}")

        relay_entity = device.get(CONF_DEVICE_ENTITY)
        mode_select_entity = device.get(CONF_ESPHOME_MODE_SELECT_ENTITY)

        if mode_select_entity:
            last_mode = device.get("last_mode")
            if last_mode:
                state = hass.states.get(mode_select_entity)
                if state and state.state != last_mode:
                    log_info(f"Restoring mode '{last_mode}' for {mode_select_entity}")
                    await set_mode_for_entity(hass, mode_select_entity, last_mode)
                    restored.add(mode_select_entity)

        if relay_entity:
            entity_to_restore = relay_entity
            domain = relay_entity.split(".")[0]
            if domain == DOMAIN_CLIMATE and hvac_mode:
                entity_to_restore = f"{relay_entity}|{hvac_mode}"

            state = hass.states.get(relay_entity)
            if state and state.state in (STATE_ON, STATE_OFF):
                if device.get("_restore_on", False) and state.state != STATE_ON:
                    log_info(f"Restoring ON state for {entity_to_restore}")
                    await set_power_for_entity(hass, entity_to_restore, 100)
                    restored.add(relay_entity)
                elif not device.get("_restore_on", False) and state.state != STATE_OFF:
                    log_info(f"Restoring OFF state for {entity_to_restore}")
                    await set_power_for_entity(hass, entity_to_restore, 0)
                    restored.add(relay_entity)

            percent = device.get("last_percent")
            if percent is not None:
                log_info(f"Restoring percent {percent} for {entity_to_restore}")
                await set_power_for_entity(hass, entity_to_restore, percent)
                restored.add(relay_entity)

    if not restored:
        log_info("No device states needed to be restored after restart.")
