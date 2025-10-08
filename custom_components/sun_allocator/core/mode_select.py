"""Mode select logic for Sun Allocator."""

from homeassistant.const import STATE_UNKNOWN, STATE_UNAVAILABLE

from .logger import log_debug
from .entity_control import set_mode_for_entity

from ..const import (
    DOMAIN,
    CONF_ESPHOME_MODE_SELECT_ENTITY,
    CONF_DEVICES,
)

VALID_MODES = {"off", "on", "proportional"}


async def persist_last_mode(hass, config_entry, entity_id, mode):
    """Persist the last mode of the device."""
    # Defer persistence if a config flow is in progress to avoid race conditions
    active_flows = config_entry.async_get_active_flows(hass)
    if any(flow["handler"] == DOMAIN for flow in active_flows):
        log_debug(
            "Config flow in progress. Deferring persistence of last_mode for %s.",
            entity_id,
        )
        return

    if mode not in VALID_MODES:
        return

    data = dict(config_entry.data)
    devs = list(data.get(CONF_DEVICES, []))
    changed = False
    for i, dev in enumerate(devs):
        if dev.get(CONF_ESPHOME_MODE_SELECT_ENTITY) == entity_id:
            if dev.get("last_mode") != mode:
                nd = dict(dev)
                nd["last_mode"] = mode
                devs[i] = nd
                changed = True
            break

    if changed:
        data[CONF_DEVICES] = devs
        log_debug("--- MODE SELECT ---: Saving %d devices. Data: %s", len(devs), data)
        hass.config_entries.async_update_entry(config_entry, data=data)


async def mode_select_state_listener(
    hass, config_entry, event, desired_modes, select_entity_ids
):
    """Handle state changes for the mode select entity."""
    entity_id = event.data.get("entity_id")
    if entity_id not in select_entity_ids:
        return

    new_state = event.data.get("new_state")
    old_state = event.data.get("old_state")
    if not new_state:
        return

    if new_state.state in VALID_MODES:
        desired_modes[entity_id] = new_state.state
        await persist_last_mode(hass, config_entry, entity_id, new_state.state)

    was_unavailable = (old_state is None) or (
        old_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE)
    )
    now_available = new_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
    if was_unavailable and now_available:
        desired = desired_modes.get(entity_id)
        if desired and new_state.state != desired:
            log_debug(
                "Re-applying desired mode %s to %s after availability",
                desired,
                entity_id,
            )
            await set_mode_for_entity(hass, entity_id, desired)
