"""Entity control helpers for Sun Allocator."""

from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    STATE_ON,
    STATE_UNKNOWN,
    STATE_UNAVAILABLE,
    SERVICE_SELECT_OPTION,
    ATTR_ENTITY_ID,
    SERVICE_TURN_ON,
    SERVICE_TURN_OFF,
)

from .logger import log_debug, log_warning, log_error

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

try:
    from homeassistant.exceptions import HomeAssistantError
except ImportError:
    HomeAssistantError = Exception


def parse_relay_entity(entity: str | None) -> tuple[str | None, str | None]:
    """Split a stored relay entity reference into (entity_id, hvac_mode).

    Climate entities are stored as ``climate.x|hvac_mode``; everything else is a
    plain entity_id with no suffix. Returns ``(None, None)`` if input is empty.
    """
    if not entity:
        return None, None
    if "|" in entity:
        entity_id, hvac_mode = entity.split("|", 1)
        return entity_id.strip() or None, hvac_mode.strip() or None
    return entity.strip() or None, None


async def _async_call_service(
    hass: HomeAssistant, domain: str, service: str, service_data: dict, label: str
) -> None:
    """Invoke a HA service non-blockingly and surface errors uniformly."""
    try:
        await hass.services.async_call(domain, service, service_data, blocking=False)
        await hass.async_block_till_done()
    except HomeAssistantError as exc:
        log_error(f"Service {domain}.{service} failed for {label}: {exc}")


def is_entity_on(domain: str, state) -> bool:
    """Return True if entity is considered ON (handles climate vs standard domains)."""
    return state.state != "off" if domain == DOMAIN_CLIMATE else state.state == STATE_ON


async def turn_on_entity(
    hass: HomeAssistant,
    entity_id: str,
    hvac_mode: str | None = None,
    device_name: str = "",
) -> None:
    """Turn on entity (handles climate, light, and standard switch domains)."""
    domain = entity_id.split(".")[0]
    service_data = {ATTR_ENTITY_ID: entity_id}
    if domain == DOMAIN_LIGHT:
        service_name = SERVICE_TURN_ON
        service_data[ATTR_BRIGHTNESS] = MAX_BRIGHTNESS  # type: ignore[assignment]
    elif domain == DOMAIN_CLIMATE:
        service_name = "set_hvac_mode"
        service_data["hvac_mode"] = _resolve_hvac_mode(hass, entity_id, hvac_mode)
    elif domain in (DOMAIN_SWITCH, DOMAIN_INPUT_BOOLEAN, DOMAIN_AUTOMATION, DOMAIN_SCRIPT):
        service_name = SERVICE_TURN_ON
    else:
        log_warning(f"turn_on_entity: unsupported domain '{domain}' for {entity_id}")
        return
    await _async_call_service(hass, domain, service_name, service_data, device_name or entity_id)


async def turn_off_entity(hass: HomeAssistant, entity_id: str, device_name: str = "") -> None:
    """Turn off entity (handles climate and standard switch domains)."""
    domain = entity_id.split(".")[0]
    if domain == DOMAIN_CLIMATE:
        service_name = "set_hvac_mode"
        service_data = {ATTR_ENTITY_ID: entity_id, "hvac_mode": "off"}
    else:
        service_name = SERVICE_TURN_OFF
        service_data = {ATTR_ENTITY_ID: entity_id}
    await _async_call_service(hass, domain, service_name, service_data, device_name or entity_id)


_PREFERRED_HVAC_MODES = ("heat", "heat_cool", "auto")


def _resolve_hvac_mode(hass: HomeAssistant, entity_id: str, hvac_mode: str | None) -> str:
    """Return hvac_mode; auto-detect from supported modes if not set."""
    if hvac_mode:
        return hvac_mode
    state = hass.states.get(entity_id)
    supported = (state.attributes.get("hvac_modes") or []) if state else []
    for preferred in _PREFERRED_HVAC_MODES:
        if preferred in supported:
            return preferred
    non_off = [m for m in supported if m != "off"]
    if non_off:
        log_warning(
            f"Climate {entity_id} has no preferred mode {_PREFERRED_HVAC_MODES}; "
            f"falling back to '{non_off[0]}' from supported {supported}"
        )
        return non_off[0]
    return "heat"


async def set_mode_for_entity(hass: HomeAssistant, entity_id: str, mode: str) -> None:
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


async def set_power_for_entity(hass: HomeAssistant, entity_id: str, power_percent: float) -> None:
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
                {ATTR_ENTITY_ID: entity_id, "hvac_mode": _resolve_hvac_mode(hass, entity_id, hvac_mode)},
                blocking=False,
            )
        else:
            log_warning(f"Unsupported entity domain: {domain}. Cannot turn on {entity_id}")
        await hass.async_block_till_done()
