
"""Sensor utilities for Sun Allocator integration."""
from typing import Optional, Dict, Any, Tuple

from homeassistant.const import STATE_UNKNOWN, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .logger import log_debug, log_error
from .journal import journal_event

from ..const import (
    CONF_TEMPERATURE_COMPENSATION_ENABLED,
    CONF_TEMPERATURE_SENSOR,
    CONF_TEMP_COEFFICIENT_VOC,
    CONF_TEMP_COEFFICIENT_PMAX,
    PANEL_CONFIG_SERIES,
    CONF_CURVE_FACTOR_K,
    CONF_EFFICIENCY_CORRECTION_FACTOR,
    CONF_MIN_INVERTER_VOLTAGE,
    DEFAULT_STANDARD_TEMPERATURE,
    DEFAULT_VOC_COEFFICIENT,
    DEFAULT_PMAX_COEFFICIENT,
)


def get_sensor_state_safely(hass: HomeAssistant, entity_id: Optional[str], sensor_name: str) -> Tuple[float, bool]:
    """
    Safely get sensor state with proper error handling.

    Args:
        hass: Home Assistant instance
        entity_id: Entity ID of the sensor
        sensor_name: Human-readable name for logging

    Returns:
        Tuple of (value, success) where success indicates if the value was retrieved successfully
    """
    if not entity_id:
        log_debug(f"{sensor_name} entity ID not configured")
        journal_event("sensor_missing_entity_id", {"sensor": sensor_name})
        return 0.0, False

    state = hass.states.get(entity_id)
    if state is None:
        log_debug(f"{sensor_name} sensor '{entity_id}' not found - this is normal during startup")
        journal_event("sensor_not_found", {"sensor": sensor_name, "entity_id": entity_id})
        return 0.0, False

    if state.state in (None, STATE_UNKNOWN, STATE_UNAVAILABLE):
        log_debug(f"{sensor_name} sensor '{entity_id}' is {state.state} - waiting for sensor to become available")
        journal_event("sensor_unavailable", {"sensor": sensor_name, "entity_id": entity_id, "state": state.state})
        return 0.0, False

    try:
        value = float(state.state)
        log_debug(f"{sensor_name}: {value}")
        journal_event("sensor_value", {"sensor": sensor_name, "entity_id": entity_id, "value": value})
        return value, True
    except (ValueError, TypeError):
        log_error(f"Could not convert {sensor_name} state '{state.state}' to float")
        journal_event("sensor_value_error", {"sensor": sensor_name, "entity_id": entity_id, "state": state.state})
        return 0.0, False


def get_temperature_compensation_data(hass: HomeAssistant, config: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """
    Get temperature compensation data if enabled.

    Args:
        hass: Home Assistant instance
        config: Configuration dictionary

    Returns:
        Temperature compensation data or None if not enabled/available
    """
    if not config.get(CONF_TEMPERATURE_COMPENSATION_ENABLED, False):
        return None

    temp_sensor = config.get(CONF_TEMPERATURE_SENSOR)
    if not temp_sensor:
        return None

    temp_value, success = get_sensor_state_safely(hass, temp_sensor, "Temperature")
    if not success:
        return None

    temp_diff = temp_value - DEFAULT_STANDARD_TEMPERATURE  # Difference from standard conditions (25°C)

    # Coefficients in % per degree, convert to decimal
    voc_coef = config.get(CONF_TEMP_COEFFICIENT_VOC, DEFAULT_VOC_COEFFICIENT) / 100
    pmax_coef = config.get(CONF_TEMP_COEFFICIENT_PMAX, DEFAULT_PMAX_COEFFICIENT) / 100

    log_debug(f"Temperature compensation: {temp_value}°C, diff: {temp_diff}°C")
    journal_event("temperature_compensation", {"temp_value": temp_value, "temp_diff": temp_diff})

    return {
        "temp_diff": temp_diff,
        "voc_coef": voc_coef,
        "pmax_coef": pmax_coef
    }


def create_sensor_attributes(
    pv_power: float = 0.0,
    pv_voltage: float = 0.0,
    consumption: float = 0.0,
    battery_power: float = 0.0,
    excess_possible: bool = False,
    energy_harvesting_possible: bool = False,
    min_system_voltage: float = 0.0,
    vmp: float = 0.0,
    imp: float = 0.0,
    voc: float = 0.0,
    isc: float = 0.0,
    panel_count: int = 1,
    panel_configuration: str = PANEL_CONFIG_SERIES,
    pmax: float = 0.0,
    current_max_power: float = 0.0,
    usage_percent: float = 0.0,
    **kwargs
) -> Dict[str, Any]:
    """
    Create standardized sensor attributes dictionary.

    Args:
        Various sensor values and parameters
        **kwargs: Additional attributes to include

    Returns:
        Dictionary of sensor attributes
    """
    attributes = {
        "pv_power": pv_power,
        "pv_voltage": pv_voltage,
        "consumption": consumption,
        "battery_power": battery_power,
        "excess_possible": excess_possible,
        "energy_harvesting_possible": energy_harvesting_possible,
        "min_system_voltage": min_system_voltage,
        "vmp": vmp,
        "imp": imp,
        "voc": voc,
        "isc": isc,
        "panel_count": panel_count,
        "panel_configuration": panel_configuration,
        "pmax": pmax,
        "current_max_power": current_max_power,
        "usage_percent": usage_percent
    }

    # Add any additional attributes
    attributes.update(kwargs)

    return attributes


def setup_sensor_listeners(
    hass: HomeAssistant,
    entity_ids: list,
    update_callback: callback,
    unsub_listeners: list
) -> None:
    """
    Set up state change listeners for multiple entities.

    Args:
        hass: Home Assistant instance
        entity_ids: List of entity IDs to listen to
        update_callback: Callback function to call on state change
        unsub_listeners: List to store unsubscribe functions
    """
    for entity_id in entity_ids:
        if entity_id:
            unsub_listeners.append(
                async_track_state_change_event(hass, entity_id, update_callback)
            )


def cleanup_sensor_listeners(unsub_listeners: list) -> None:
    """
    Clean up state change listeners.

    Args:
        unsub_listeners: List of unsubscribe functions
    """
    for unsub in unsub_listeners:
        unsub()
    unsub_listeners.clear()


def calculate_excess_power(
    current_max_power: float,
    pv_power: float,
    battery_power: float = 0.0,
    battery_power_reversed: bool = False,
    *,
    relative_voltage: float | None = None,
    energy_harvesting_possible: bool | None = None,
) -> float:
    """
    Calculate excess (untapped potential) with internal accounting for battery charge
    and topology constraints.

    Rules:
    - If battery is discharging → return 0
    - If topology disallows harvesting (relative_voltage <= 1.0 or EHP is False) → return 0
    - Else excess = max(current_max_power - (pv_power + battery_charge_w), 0)
    """
    # 1) Discharge guard
    if battery_power_reversed:
        # reversed polarity: positive means discharging
        is_discharging = battery_power > 0
    else:
        # normal polarity: negative means discharging
        is_discharging = battery_power < 0

    if is_discharging:
        return 0.0

    # 2) Topology guard (if provided)
    if relative_voltage is not None and relative_voltage <= 1.0:
        return 0.0
    if energy_harvesting_possible is not None and not energy_harvesting_possible:
        return 0.0

    # 3) Account battery charging as already used PV power
    if battery_power_reversed:
        # reversed polarity: negative means charging
        battery_charge_w = max(-battery_power, 0.0)
    else:
        # normal polarity: positive means charging
        battery_charge_w = max(battery_power, 0.0)

    actual_harvested = pv_power + battery_charge_w
    return max(current_max_power - actual_harvested, 0.0)


def calculate_usage_percentage(actual_power: float, max_power: float) -> float:
    """
    Calculate usage percentage.

    Args:
        actual_power: Actual power being generated
        max_power: Maximum theoretical power

    Returns:
        Usage percentage (0-100)
    """
    if max_power > 0:
        return round((actual_power / max_power) * 100, 1)
    return 0.0


def is_excess_possible(pv_voltage: float, vmp: float) -> bool:
    """
    Check if excess power is possible based on voltage.

    Args:
        pv_voltage: Current PV voltage
        vmp: Voltage at maximum power point

    Returns:
        True if excess power is possible
    """
    return pv_voltage > vmp if pv_voltage > 0 else False


def get_mppt_algorithm_config(config: Dict[str, Any]) -> Dict[str, float]:
    """
    Get MPPT algorithm configuration parameters.

    Args:
        config: Configuration dictionary

    Returns:
        Dictionary with MPPT algorithm parameters
    """
    return {
        CONF_CURVE_FACTOR_K: config.get(CONF_CURVE_FACTOR_K, 0.2),
        CONF_EFFICIENCY_CORRECTION_FACTOR: config.get(CONF_EFFICIENCY_CORRECTION_FACTOR, 1.05),
        CONF_MIN_INVERTER_VOLTAGE: config.get(CONF_MIN_INVERTER_VOLTAGE, 100.0)
    }


def clean_entity_id_and_mode(entity_id_raw):
    """Normalize entity_id and extract hvac_mode if present."""
    import re
    if not entity_id_raw or not isinstance(entity_id_raw, str):
        return entity_id_raw, None
    entity_id = entity_id_raw.strip()
    entity_id = re.sub(r"^[^a-zA-Z0-9]*", "", entity_id)
    # Extract mode if present in parentheses (e.g., (Heat) or (Cool))
    mode_match = re.search(r"\((.*?)\)", entity_id)
    hvac_mode = mode_match.group(1).strip().lower() if mode_match else None
    entity_id = re.sub(r"\s*\(.*?\)", "", entity_id)
    entity_id = re.sub(r"\s*\[.*?\]", "", entity_id)
    entity_id = entity_id.strip()
    return entity_id, hvac_mode