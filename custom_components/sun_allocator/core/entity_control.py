"""Entity control helpers for Sun Allocator."""

from homeassistant.core import HomeAssistant
from homeassistant.const import (
    STATE_UNKNOWN,
    STATE_UNAVAILABLE,
    SERVICE_SELECT_OPTION,
    ATTR_ENTITY_ID,
    SERVICE_TURN_ON,
    SERVICE_TURN_OFF,
)

from .logger import log_debug, log_warning

from ..const import (
    DOMAIN_SELECT,
    DOMAIN_LIGHT,
    DOMAIN_SWITCH,
    DOMAIN_INPUT_BOOLEAN,
    DOMAIN_AUTOMATION,
    DOMAIN_SCRIPT,
    DOMAIN_CLIMATE,
    MAX_BRIGHTNESS,
    MAX_PERCENTAGE,
)


async def set_mode_for_entity(hass: HomeAssistant, entity_id, mode):
    """Set the mode for a select entity."""
    state = hass.states.get(entity_id)
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        log_debug(f"Entity {entity_id} not found or unavailable, skipping set_relay_mode({mode})")
        return

    log_debug(f"Setting relay mode to {mode} for entity {entity_id}")

    await hass.services.async_call(
        DOMAIN_SELECT,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: entity_id, "option": mode},
        blocking=False,
    )
    await hass.async_block_till_done()


async def set_power_for_entity(hass, entity_id, power_percent):
    """Set the power for a light or switch entity."""
    hvac_mode = None
    if "|" in entity_id:
        entity_id, hvac_mode = entity_id.split("|", 1)
        entity_id = entity_id.strip()
        hvac_mode = hvac_mode.strip()

    state = hass.states.get(entity_id)
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        log_debug(
            f"Entity {entity_id} not found or unavailable, "
            f"skipping set_relay_power({power_percent}%)"
        )
        return
    domain = entity_id.split(".")[0]
    brightness = int((power_percent / MAX_PERCENTAGE) * MAX_BRIGHTNESS)

    if power_percent <= 0:
        log_debug(f"Turning off entity {entity_id}")

        if domain == DOMAIN_LIGHT:
            await hass.services.async_call(
                DOMAIN_LIGHT,
                SERVICE_TURN_OFF,
                {ATTR_ENTITY_ID: entity_id},
                blocking=False,
            )
        elif domain in [
            DOMAIN_SWITCH,
            DOMAIN_INPUT_BOOLEAN,
            DOMAIN_AUTOMATION,
            DOMAIN_SCRIPT,
        ]:
            await hass.services.async_call(
                domain, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id}, blocking=False
            )
        elif domain == DOMAIN_CLIMATE:
            await hass.services.async_call(
                DOMAIN_CLIMATE,
                "set_hvac_mode",
                {ATTR_ENTITY_ID: entity_id, "hvac_mode": "off"},
                blocking=False,
            )
        else:
            log_warning(f"Unsupported entity domain: {domain}. Cannot turn off {entity_id}")
        await hass.async_block_till_done()
    else:
        log_debug(f"Turning on entity {entity_id} with power {power_percent}%")
        if domain == DOMAIN_LIGHT:
            await hass.services.async_call(
                DOMAIN_LIGHT,
                SERVICE_TURN_ON,
                {ATTR_ENTITY_ID: entity_id, "brightness": brightness},
                blocking=False,
            )
        elif domain in [
            DOMAIN_SWITCH,
            DOMAIN_INPUT_BOOLEAN,
            DOMAIN_AUTOMATION,
            DOMAIN_SCRIPT,
        ]:
            await hass.services.async_call(
                domain, SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=False
            )
        elif domain == DOMAIN_CLIMATE:
            await hass.services.async_call(
                DOMAIN_CLIMATE,
                "set_hvac_mode",
                {ATTR_ENTITY_ID: entity_id, "hvac_mode": hvac_mode or "heat"},
                blocking=False,
            )
        else:
            log_warning(f"Unsupported entity domain: {domain}. Cannot turn on {entity_id}")
        await hass.async_block_till_done()
