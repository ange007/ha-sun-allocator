"""Sensor utilities for Sun Allocator integration."""

from typing import Optional, Dict, Any, Tuple

from homeassistant.const import STATE_UNKNOWN, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event

from ..core.logger import log_debug, log_error, journal_event
# Excess-power math lives in its own module; re-exported here for import back-compat.
from .excess_math import (  # noqa: F401
    detect_curtailment,
    calculate_excess_power_export,
    calculate_excess_power_mppt,
    get_mppt_algorithm_config,
)

from ..const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_ENTITY_FRIENDLY_NAME,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_TEMPERATURE_COMPENSATION_ENABLED,
    CONF_TEMPERATURE_SENSOR,
    CONF_TEMP_COEFFICIENT_VOC,
    CONF_TEMP_COEFFICIENT_PMAX,
    DEFAULT_STANDARD_TEMPERATURE,
    DEFAULT_VOC_COEFFICIENT,
    DEFAULT_PMAX_COEFFICIENT,
)


def get_device_entity_friendly_name(hass: HomeAssistant, device_config: Dict[str, Any]) -> str | None:
    """Return the real HA entity friendly name (for device model field)."""
    stored = device_config.get(CONF_DEVICE_ENTITY_FRIENDLY_NAME)
    if stored:
        return stored
    entity_id = device_config.get(CONF_DEVICE_ENTITY)
    if entity_id:
        clean_id = entity_id.split("|")[0] if "|" in entity_id else entity_id
        state = hass.states.get(clean_id)
        if state:
            fn = state.attributes.get("friendly_name")
            if fn:
                return fn
        return clean_id
    return None


def is_device_auto_control_enabled(config_data: Dict[str, Any], device_id: str | None) -> bool:
    """Return True if a device has auto-control enabled in the config entry data."""
    if not device_id:
        return False
    for dev in config_data.get(CONF_DEVICES, []) or []:
        if dev.get(CONF_DEVICE_ID) == device_id:
            return bool(dev.get(CONF_AUTO_CONTROL_ENABLED, False))
    return False


def get_device_info(hass: HomeAssistant, device_config: Dict[str, Any], entry_id: str) -> DeviceInfo:
    """Shared DeviceInfo for all per-device entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, device_config.get(CONF_DEVICE_ID))},
        name=device_config.get(CONF_DEVICE_NAME) or "Unknown Device",
        manufacturer="Sun Allocator",
        model=get_device_entity_friendly_name(hass, device_config),
        via_device=(DOMAIN, entry_id),
    )


# Machine-readable status keys for SensorDeviceClass.ENUM
DEVICE_STATUS_ACTIVE = "active"
DEVICE_STATUS_INSUFFICIENT_POWER = "insufficient_power"
DEVICE_STATUS_DEBOUNCING_ON = "debouncing_on"
DEVICE_STATUS_DEBOUNCING_OFF = "debouncing_off"
DEVICE_STATUS_AUTO_CONTROL_OFF = "auto_control_off"
DEVICE_STATUS_MANUAL_OVERRIDE = "manual_override"
DEVICE_STATUS_MANUAL_ACTIVE = "manual_active"
DEVICE_STATUS_MANUAL_TIMER = "manual_timer"
DEVICE_STATUS_FILTERED = "filtered"
DEVICE_STATUS_TRYING_ON = "trying_on"
DEVICE_STATUS_TRYING_OFF = "trying_off"
DEVICE_STATUS_UNREACHABLE = "unreachable"
DEVICE_STATUS_IDLE = "idle"

DEVICE_STATUS_OPTIONS = [
    DEVICE_STATUS_ACTIVE,
    DEVICE_STATUS_IDLE,
    DEVICE_STATUS_INSUFFICIENT_POWER,
    DEVICE_STATUS_DEBOUNCING_ON,
    DEVICE_STATUS_DEBOUNCING_OFF,
    DEVICE_STATUS_AUTO_CONTROL_OFF,
    DEVICE_STATUS_MANUAL_OVERRIDE,
    DEVICE_STATUS_MANUAL_ACTIVE,
    DEVICE_STATUS_MANUAL_TIMER,
    DEVICE_STATUS_FILTERED,
    DEVICE_STATUS_TRYING_ON,
    DEVICE_STATUS_TRYING_OFF,
    DEVICE_STATUS_UNREACHABLE,
]


def _resolve_device_status(
    device_id: str | None,
    device_status: Dict[str, Any],
    allocated_power: float,
    auto_control_on: bool,
) -> tuple[str, list[str]]:
    """Core logic: return (status_key, refusal_reasons) for a device.

    Single source of truth used by both build_device_status (ENUM sensor)
    and build_device_reason (structured payload).
    """
    if not auto_control_on:
        return DEVICE_STATUS_AUTO_CONTROL_OFF, []

    if device_id not in device_status:
        return DEVICE_STATUS_FILTERED, []

    st = device_status[device_id]

    if st.get("manual_timer"):
        return DEVICE_STATUS_MANUAL_TIMER, []

    if st.get("manual_active"):
        return DEVICE_STATUS_MANUAL_ACTIVE, []

    if st.get("manual_override"):
        return DEVICE_STATUS_MANUAL_OVERRIDE, []

    # Retry states take priority over normal status
    retry_count = st.get("retry_count", 0)
    retry_expected_on = st.get("retry_expected_on")

    # Device has ignored several throttled re-sends → surface it as clearly
    # unreachable (not "insufficient power" / "failed") so the cause is obvious.
    if st.get("unreachable"):
        return DEVICE_STATUS_UNREACHABLE, []
    if retry_count > 0 and retry_expected_on is not None:
        key = DEVICE_STATUS_TRYING_ON if retry_expected_on else DEVICE_STATUS_TRYING_OFF
        return key, []

    is_candidate = st.get("is_active_candidate")
    refusals: list[str] = st.get("refusal_reasons") or []

    # "Enabled" = relay commanded ON this cycle. Standard devices set this flag
    # explicitly; for device types that don't (e.g. custom/proportional), fall back
    # to the allocated-power signal so behaviour is unchanged for them.
    is_enabled = st.get("is_enabled")
    if is_enabled is None:
        is_enabled = allocated_power > 0

    if is_enabled:
        if is_candidate is False:
            return DEVICE_STATUS_DEBOUNCING_OFF, refusals
        # Relay on but the actual-power sensor confirms draw below threshold →
        # idle (e.g. boiler reached target temp, element cycled off).
        if st.get("is_idle"):
            return DEVICE_STATUS_IDLE, []
        return DEVICE_STATUS_ACTIVE, []

    if refusals:
        return DEVICE_STATUS_FILTERED, refusals

    if is_candidate is None or not is_candidate:
        return DEVICE_STATUS_INSUFFICIENT_POWER, []
    return DEVICE_STATUS_DEBOUNCING_ON, []


def build_device_status(
    device_id: str | None,
    device_status: Dict[str, Any],
    allocated_power: float,
    auto_control_on: bool,
) -> str:
    """Return a machine-readable status key (used with SensorDeviceClass.ENUM)."""
    key, _ = _resolve_device_status(device_id, device_status, allocated_power, auto_control_on)
    return key


def build_device_reason(
    device_id: str | None,
    device_status: Dict[str, Any],
    allocated_power: float,
    auto_control_on: bool,
) -> Dict[str, Any]:
    """Return a structured reason payload for display in Lovelace cards.

    Shape: ``{"status": "<enum_key>", "refusals": ["..."]}``. The ENUM key
    matches ``device_status`` sensor's native value, so Lovelace templates
    can call ``state_translated`` for an i18n label and format ``refusals``
    however they want.
    """
    key, refusals = _resolve_device_status(device_id, device_status, allocated_power, auto_control_on)
    return {"status": key, "refusals": list(refusals)}


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
        return 0.0, False

    state = hass.states.get(entity_id)
    if state is None:
        log_debug(
            f"{sensor_name} sensor '{entity_id}' not found - normal during startup"
        )
        return 0.0, False

    if state.state in (None, STATE_UNKNOWN, STATE_UNAVAILABLE):
        log_debug(
            f"{sensor_name} sensor '{entity_id}' is {state.state} - waiting for it"
        )
        return 0.0, False

    try:
        value = float(state.state)
        log_debug(f"{sensor_name}: {value}")
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


def calculate_usage_percentage(actual_power: float, max_power: float) -> float:  # noqa: D401
    """Calculate usage percentage."""
    if max_power > 0:
        return round((actual_power / max_power) * 100, 1)

    return 0.0
