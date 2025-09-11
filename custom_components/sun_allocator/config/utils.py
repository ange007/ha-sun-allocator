"""Utility functions for Sun Allocator config flow."""
from typing import Dict, Any, List, Optional

from homeassistant.core import HomeAssistant

from ..utils.logger import log_error
from ..utils.journal import log_exception

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


def convert_none_strings_to_none(data: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    """Convert 'None' strings to actual None values for specified keys."""
    for key in keys:
        if data.get(key) == NONE_OPTION:
            data[key] = None
    return data


def filter_entities_by_domain(hass: HomeAssistant, domain: str) -> List[str]:
    """Filter entities by domain prefix."""
    return [e.entity_id for e in hass.states.async_all() if e.entity_id.startswith(f"{domain}.")]


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


def get_boolean_entities(hass: HomeAssistant, exclude_keywords: Optional[List[str]] = None) -> List[str]:
    """Get entities that have boolean states (on/off)."""
    if exclude_keywords is None:
        exclude_keywords = ["sun_allocator", "sunallocator", "sun_allocator", "sunallocator"]
    
    boolean_domains = [DOMAIN_LIGHT, DOMAIN_SWITCH, DOMAIN_INPUT_BOOLEAN, DOMAIN_AUTOMATION, DOMAIN_SCRIPT]
    boolean_entities = []
    
    for domain in boolean_domains:
        domain_entities = filter_entities_by_domain(hass, domain)
        for entity_id in domain_entities:
            entity = hass.states.get(entity_id)
            if entity and entity.state in [STATE_ON, STATE_OFF]:
                # Exclude entities with specified keywords
                if not any(keyword.lower() in entity_id.lower() for keyword in exclude_keywords):
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
            if ("temp" in entity_id.lower() or 
                "temperature" in entity_id.lower() or 
                (entity.attributes.get("unit_of_measurement") in ["°C", "°F", "K"])):
                temperature_entities.append(entity_id)
    
    return sorted(temperature_entities)


def validate_float_range(value: Any, min_val: float, max_val: float, field_name: str) -> Optional[str]:
    """Validate that a value is a float within the specified range."""
    try:
        float_val = float(value)
        if float_val < min_val or float_val > max_val:
            return f"invalid_{field_name}_range"
        return None
    except (ValueError, TypeError) as e:
        log_error("[utils] Invalid float for %s: %s", field_name, value)
        log_exception(f"validate_float_range_{field_name}", e)
        return f"invalid_{field_name}_format"


def validate_int_range(value: Any, min_val: int, max_val: int, field_name: str) -> Optional[str]:
    """Validate that a value is an integer within the specified range."""
    try:
        int_val = int(value)
        if int_val < min_val or int_val > max_val:
            return f"invalid_{field_name}_range"
        return None
    except (ValueError, TypeError) as e:
        log_error("[utils] Invalid int for %s: %s", field_name, value)
        log_exception(f"validate_int_range_{field_name}", e)
        return f"invalid_{field_name}_format"


def validate_time_format(time_str: str) -> Optional[str]:
    """Validate time format (HH:MM)."""
    try:
        hour, minute = map(int, time_str.split(':'))
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return "invalid_time_format"
        return None
    except (ValueError, AttributeError) as e:
        log_error("[utils] Invalid time format: %s", time_str)
        log_exception("validate_time_format", e)
        return "invalid_time_format"


def create_device_options_dict(devices: List[Dict[str, Any]], action_prefix: str) -> Dict[str, str]:
    """Create options dictionary for device management."""
    options = {}
    
    for device in devices:
        device_id = device.get("id", "")
        device_name = device.get("name", "Unknown")
        if device_id:
            options[f"{action_prefix}_{device_id}"] = f"{action_prefix.title()} {device_name}"
    
    return options


def get_default_value_for_dropdown(value: Any, none_string: str = NONE_OPTION) -> str:
    """Convert None values to string for dropdown display."""
    return none_string if value is None else str(value)


def merge_config_data(base_config: Dict[str, Any], new_data: Dict[str, Any]) -> Dict[str, Any]:
    """Merge new configuration data into base configuration."""
    merged = base_config.copy()
    merged.update(new_data)
    return merged