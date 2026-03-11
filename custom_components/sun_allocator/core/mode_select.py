"""Mode select logic for Sun Allocator."""

from homeassistant.const import STATE_UNKNOWN, STATE_UNAVAILABLE

from .logger import log_debug
from .entity_control import set_mode_for_entity
from .device_restore import persist_mode_state


VALID_MODES = {"off", "on", "proportional"}


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
        await persist_mode_state(hass, config_entry, entity_id, new_state.state)

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
