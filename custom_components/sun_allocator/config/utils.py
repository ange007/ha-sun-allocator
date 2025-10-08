"""Utility functions for Sun Allocator config flow."""

from typing import Dict, Any, List, Optional

from homeassistant.core import HomeAssistant

from ..core.logger import log_error, log_exception
from ..const import (
    NONE_OPTION,
    STATE_ON,
    STATE_OFF,
    DOMAIN_LIGHT,
    DOMAIN_SWITCH,
    DOMAIN_INPUT_BOOLEAN,
    DOMAIN_AUTOMATION,
    DOMAIN_SCRIPT,
)


def get_entity_options_with_none(entities: List[str]) -> List[str]:
    """Add 'None' option to entity list for optional selections."""
    return [NONE_OPTION] + entities


def convert_none_strings_to_none(
    data: Dict[str, Any], keys: List[str]
) -> Dict[str, Any]:
    """Convert 'None' strings to actual None values for specified keys."""
    for key in keys:
        if data.get(key) == NONE_OPTION:
            data[key] = None

    return data


def filter_entities_by_domain(hass: HomeAssistant, domain: str) -> List[str]:
    """Filter entities by domain prefix."""
    return [
        entity.entity_id
        for entity in hass.states.async_all()
        if entity.entity_id.startswith(f"{domain}.")
    ]


def filter_entities_by_keywords(entities: List[str], keywords: List[str]) -> List[str]:
    """Filter entities that contain any of the specified keywords."""
    filtered = []
    for entity in entities:
        if any(keyword.lower() in entity.lower() for keyword in keywords):
            filtered.append(entity)

    return filtered


def exclude_entities_by_keywords(entities: List[str], keywords: List[str]) -> List[str]:
    """Exclude entities that contain any of the specified keywords."""
    filtered = []
    for entity in entities:
        if not any(keyword.lower() in entity.lower() for keyword in keywords):
            filtered.append(entity)

    return filtered


def get_boolean_entities(
    hass: HomeAssistant, exclude_keywords: Optional[List[str]] = None
) -> List[str]:
    """Get entities that have boolean states (on/off)."""
    if exclude_keywords is None:
        exclude_keywords = ["sun_allocator", "sunallocator"]

    boolean_domains = [
        DOMAIN_LIGHT,
        DOMAIN_SWITCH,
        DOMAIN_INPUT_BOOLEAN,
        DOMAIN_AUTOMATION,
        DOMAIN_SCRIPT,
    ]
    boolean_entities = []

    for domain in boolean_domains:
        domain_entities = filter_entities_by_domain(hass, domain)
        for entity_id in domain_entities:
            entity = hass.states.get(entity_id)
            if entity and entity.state in [STATE_ON, STATE_OFF]:
                # Exclude entities with specified keywords
                if not any(
                    keyword.lower() in entity_id.lower() for keyword in exclude_keywords
                ):
                    boolean_entities.append(entity_id)

    return sorted(boolean_entities)


def get_temperature_entities(hass: HomeAssistant) -> List[str]:
    """Get entities that appear to be temperature sensors."""
    temperature_entities = []
    sensor_entities = filter_entities_by_domain(hass, "sensor")

    for entity_id in sensor_entities:
        entity = hass.states.get(entity_id)
        if entity:
            # Check if entity has temperature in its name or attributes
            if (
                "temp" in entity_id.lower()
                or "temperature" in entity_id.lower()
                or (entity.attributes.get("unit_of_measurement") in ["°C", "°F", "K"])
            ):
                temperature_entities.append(entity_id)

    return sorted(temperature_entities)


def validate_float_range(
    value: Any, min_val: float, max_val: float, field_name: str
) -> Optional[str]:
    """Validate that a value is a float within the specified range."""
    try:
        float_val = float(value)
        if not min_val <= float_val <= max_val:
            return f"invalid_{field_name}_range"

        return None
    except (ValueError, TypeError) as exc:
        log_error("[utils] Invalid float for %s: %s", field_name, value)
        log_exception(f"validate_float_range_{field_name}", exc)

        return f"invalid_{field_name}_format"


def validate_int_range(
    value: Any, min_val: int, max_val: int, field_name: str
) -> Optional[str]:
    """Validate that a value is an integer within the specified range."""
    try:
        int_val = int(value)
        if not min_val <= int_val <= max_val:
            return f"invalid_{field_name}_range"

        return None
    except (ValueError, TypeError) as exc:
        log_error("[utils] Invalid int for %s: %s", field_name, value)
        log_exception(f"validate_int_range_{field_name}", exc)

        return f"invalid_{field_name}_format"


def validate_time_format(time_str: str) -> Optional[str]:
    """Validate time format (HH:MM)."""
    try:
        hour, minute = map(int, time_str.split(":"))
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            return "invalid_time_format"
        return None
    except (ValueError, AttributeError) as exc:
        log_error("[utils] Invalid time format: %s", time_str)
        log_exception("validate_time_format", exc)

        return "invalid_time_format"


def create_device_options_dict(
    devices: List[Dict[str, Any]], action_prefix: str
) -> Dict[str, str]:
    """Create options dictionary for device management."""
    options = {}

    for device in devices:
        device_id = device.get("id", "")
        device_name = device.get("name", "Unknown")
        if device_id:
            options[f"{action_prefix}_{device_id}"] = (
                f"{action_prefix.title()} {device_name}"
            )

    return options


def get_default_value_for_dropdown(value: Any, none_string: str = NONE_OPTION) -> str:
    """Convert None values to string for dropdown display."""

    return none_string if value is None else str(value)


def merge_config_data(
    base_config: Dict[str, Any], new_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Merge new configuration data into base configuration."""
    merged = base_config.copy()
    merged.update(new_data)

    return merged


def validate_solar_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate solar panel configuration parameters.

    Args:
        config: Dictionary containing solar panel configuration

    Returns:
        Dictionary with 'valid' boolean and optional 'errors' list
    """
    errors = []

    # Validate required parameters
    vmp = config.get("vmp", 0)
    imp = config.get("imp", 0)
    voc = config.get("voc")
    isc = config.get("isc")
    panel_count = config.get("panel_count", 1)

    # Validate Vmp (Voltage at Maximum Power)
    if not isinstance(vmp, (int, float)) or vmp <= 0:
        errors.append("vmp_invalid")

    # Validate Imp (Current at Maximum Power)
    if not isinstance(imp, (int, float)) or imp <= 0:
        errors.append("imp_invalid")

    # Validate panel count
    if not isinstance(panel_count, int) or panel_count <= 0:
        errors.append("panel_count_invalid")

    # Validate Voc if provided (should be greater than Vmp)
    if voc is not None:
        if not isinstance(voc, (int, float)) or voc <= vmp:
            errors.append("voc_invalid")

    # Validate Isc if provided (should be greater than Imp)
    if isc is not None:
        if not isinstance(isc, (int, float)) or isc <= imp:
            errors.append("isc_invalid")

    return {"valid": len(errors) == 0, "errors": errors}


def validate_device_entity(entity_id: str) -> bool:
    """Validate that an entity ID is in a supported domain.

    Args:
        entity_id: The entity ID to validate

    Returns:
        True if entity is valid, False otherwise
    """
    if not entity_id or not isinstance(entity_id, str):
        return False

    # Check if entity ID has proper format (domain.entity_name)
    if "." not in entity_id:
        return False

    domain = entity_id.split(".")[0]
    supported_domains = [DOMAIN_SWITCH, DOMAIN_LIGHT, DOMAIN_INPUT_BOOLEAN]

    return domain in supported_domains
