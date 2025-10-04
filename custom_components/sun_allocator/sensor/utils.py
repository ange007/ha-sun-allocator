"""Sensor utilities for Sun Allocator integration."""

from typing import Optional, Dict, Any, Tuple

from homeassistant.const import STATE_UNKNOWN, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from ..core.logger import log_debug, log_error, journal_event

from ..const import (
    CONF_TEMPERATURE_COMPENSATION_ENABLED,
    CONF_TEMPERATURE_SENSOR,
    CONF_TEMP_COEFFICIENT_VOC,
    CONF_TEMP_COEFFICIENT_PMAX,
    CONF_CURVE_FACTOR_K,
    CONF_EFFICIENCY_CORRECTION_FACTOR,
    CONF_MIN_INVERTER_VOLTAGE,
    DEFAULT_STANDARD_TEMPERATURE,
    DEFAULT_VOC_COEFFICIENT,
    DEFAULT_PMAX_COEFFICIENT,
    PASSIVE_CHARGING_THRESHOLD_W,
)


def get_sensor_state_safely(
    hass: HomeAssistant, entity_id: Optional[str], sensor_name: str
) -> Tuple[float, bool]:
    """
    Safely get sensor state with proper error handling.

    Args:
        hass: Home Assistant instance
        entity_id: Entity ID of the sensor
        sensor_name: Human-readable name for logging

    Returns:
        Tuple of (value, success) where success indicates if the value was retrieved
    """
    if not entity_id:
        log_debug(f"{sensor_name} entity ID not configured")
        journal_event("sensor_missing_entity_id", {"sensor": sensor_name})
        return 0.0, False

    state = hass.states.get(entity_id)
    if state is None:
        log_debug(
            f"{sensor_name} sensor '{entity_id}' not found - normal during startup"
        )
        journal_event(
            "sensor_not_found", {"sensor": sensor_name, "entity_id": entity_id}
        )
        return 0.0, False

    if state.state in (None, STATE_UNKNOWN, STATE_UNAVAILABLE):
        log_debug(
            f"{sensor_name} sensor '{entity_id}' is {state.state} - waiting for it"
        )
        journal_event(
            "sensor_unavailable",
            {"sensor": sensor_name, "entity_id": entity_id, "state": state.state},
        )
        return 0.0, False

    try:
        value = float(state.state)
        log_debug(f"{sensor_name}: {value}")
        journal_event(
            "sensor_value",
            {"sensor": sensor_name, "entity_id": entity_id, "value": value},
        )
        return value, True
    except (ValueError, TypeError):
        log_error(f"Could not convert {sensor_name} state '{state.state}' to float")
        journal_event(
            "sensor_value_error",
            {"sensor": sensor_name, "entity_id": entity_id, "state": state.state},
        )
        return 0.0, False


def get_temperature_compensation_data(
    hass: HomeAssistant, config: Dict[str, Any]
) -> Optional[Dict[str, float]]:
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

    temp_diff = (
        temp_value - DEFAULT_STANDARD_TEMPERATURE
    )  # Difference from standard conditions (25°C)

    # Coefficients in % per degree, convert to decimal
    voc_coef = config.get(CONF_TEMP_COEFFICIENT_VOC, DEFAULT_VOC_COEFFICIENT) / 100
    pmax_coef = config.get(CONF_TEMP_COEFFICIENT_PMAX, DEFAULT_PMAX_COEFFICIENT) / 100

    log_debug(f"Temperature compensation: {temp_value}°C, diff: {temp_diff}°C")
    journal_event(
        "temperature_compensation", {"temp_value": temp_value, "temp_diff": temp_diff}
    )

    return {
        "temp_diff": temp_diff,
        "voc_coef": voc_coef,
        "pmax_coef": pmax_coef,
    }


def create_sensor_attributes(**kwargs) -> Dict[str, Any]:
    """
    Create a dictionary of sensor attributes from provided keyword arguments.
    Only non-None values are included.
    """
    return {key: value for key, value in kwargs.items() if value is not None}


def setup_sensor_listeners(
    hass: HomeAssistant,
    entity_ids: list,
    update_callback: callback,
    unsub_listeners: list,
) -> None:
    """Set up state change listeners for multiple entities."""
    for entity_id in entity_ids:
        if entity_id:
            unsub_listeners.append(
                async_track_state_change_event(hass, entity_id, update_callback)
            )


def cleanup_sensor_listeners(unsub_listeners: list) -> None:
    """Clean up state change listeners."""
    for unsub in unsub_listeners:
        unsub()
    unsub_listeners.clear()


def calculate_excess_power_parallel(
    pv_power: float,
    consumption: float,
    battery_power: float,
    battery_power_reversed: bool,
    configured_reserve: float,
    inverter_self_consumption: float = 0.0,
) -> float:
    """Calculate excess power using the simple parallel distribution method."""

    # Adjust battery power direction (positive = charging)
    if battery_power_reversed:
        battery_power = -battery_power

    if configured_reserve > 0:
        # --- Budgeting Mode ---
        effective_reserve = configured_reserve
        # Check for passive charging
        if 0 < battery_power < PASSIVE_CHARGING_THRESHOLD_W:
            effective_reserve = min(configured_reserve, battery_power)
            log_debug(
                f"Passive charging detected ({battery_power}W < {PASSIVE_CHARGING_THRESHOLD_W}W). "
                f"Effective reserve adjusted from {configured_reserve}W to {effective_reserve}W."
            )

        excess = float(pv_power) - float(consumption) - float(effective_reserve) - float(inverter_self_consumption)
        log_debug(
            f"Parallel Distribution (Budgeting): PV={pv_power}W, Consumption={consumption}W, "
            f"Effective Reserve={effective_reserve}W, Inverter Self-Consumption={inverter_self_consumption}W -> Excess={excess}W"
        )

    else:
        # --- Battery Priority Mode (reserve = 0) ---
        battery_charge_w = max(0, battery_power)
        excess = float(pv_power) - float(consumption) - float(battery_charge_w) - float(inverter_self_consumption)
        log_debug(
            f"Parallel Distribution (Priority): PV={pv_power}W, Consumption={consumption}W, "
            f"Battery Charge={battery_charge_w}W, Inverter Self-Consumption={inverter_self_consumption}W -> Excess={excess}W"
        )

    return max(0, excess)


def calculate_excess_power_mppt(
    current_max_power: float,
    pv_power: float = 0.0,
    battery_power: float = 0.0,
    battery_power_reversed: bool = False,
    consumption: float | None = None,
    configured_reserve: float = 0.0,
    inverter_self_consumption: float = 0.0,
    *_,  # Keep wildcard for future compatibility
    relative_voltage: float | None = None,
    energy_harvesting_possible: bool | None = None,
) -> float:
    """
    Calculate excess power with proper accounting for battery charge and consumption.
    This function uses a unified MPPT approach, leveraging consumption data if available
    to provide a more accurate calculation of available excess power.
    """
    # 1. Discharge Guard: If the battery is discharging, there's no excess power.
    is_discharging = (battery_power > 0) if battery_power_reversed else (battery_power < 0)
    if is_discharging:
        return 0.0

    # 2. Topology Guard: No excess if voltage is below MPP or harvesting isn't possible.
    if relative_voltage is not None and relative_voltage <= 1.0:
        return 0.0
    if energy_harvesting_possible is not None and not energy_harvesting_possible:
        return 0.0

    # 3. Normalize battery power (positive for charging, 0 otherwise).
    battery_charge_w = max(-battery_power if battery_power_reversed else battery_power, 0.0)

    # 4. Unified MPPT Calculation
    # Start with the theoretical untapped power from the panels.
    untapped_power = max(0, current_max_power - pv_power)

    # If consumption is known, we can refine the calculation.
    # We calculate the "real" excess based on total potential power minus known loads.
    # This allows us to account for home consumption that isn't met by current pv_power.
    if consumption is not None:
        # In priority mode, battery charging is a load. In budget mode, it's a source (up to the reserve).
        battery_load = battery_charge_w if configured_reserve == 0 else 0
        real_excess = current_max_power - consumption - battery_load
        # We take the minimum of untapped potential and real excess to be safe.
        excess = min(untapped_power, real_excess)
        print(f"MPPT (with consumption): CurrentMax={current_max_power}W, PV={pv_power}W, Consumption={consumption}W, Battery={battery_charge_w}W")
        print(f"MPPT (with consumption): Untapped={untapped_power}W, RealExcess={real_excess}W -> Using {excess}W")
    else:
        # Without consumption, we can only rely on untapped power.
        excess = untapped_power
        print(f"MPPT (no consumption): CurrentMax={current_max_power}W, Untapped={untapped_power}W")

    # 5. Adjust for battery reserve in "Budgeting" mode.
    if configured_reserve > 0:
        excess_from_battery = max(0, battery_charge_w - configured_reserve)
        excess += excess_from_battery
        log_debug(f"Budgeting adjustment: Added {excess_from_battery}W from battery -> Total Excess={excess}W")

    # 6. Subtract inverter self-consumption and ensure result is not negative.
    return max(0, excess - inverter_self_consumption)


def calculate_usage_percentage(actual_power: float, max_power: float) -> float:
    """Calculate usage percentage."""
    if max_power > 0:
        return round((actual_power / max_power) * 100, 1)
    return 0.0


def is_excess_possible(pv_voltage: float, vmp: float) -> bool:
    """Check if excess power is possible based on voltage."""
    return pv_voltage > vmp if pv_voltage > 0 else False


def get_mppt_algorithm_config(config: Dict[str, Any]) -> Dict[str, float]:
    """Get MPPT algorithm configuration parameters."""
    return {
        CONF_CURVE_FACTOR_K: config.get(CONF_CURVE_FACTOR_K, 0.2),
        CONF_EFFICIENCY_CORRECTION_FACTOR: config.get(
            CONF_EFFICIENCY_CORRECTION_FACTOR, 1.05
        ),
        CONF_MIN_INVERTER_VOLTAGE: config.get(CONF_MIN_INVERTER_VOLTAGE, 100.0),
    }
