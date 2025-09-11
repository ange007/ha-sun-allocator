"""Utilities for Sun Allocator integration."""

# Re-export MPPT utilities
from .mppt import (
    calculate_current_max_power,
    calculate_pmax,
    calculate_min_system_voltage,
    calculate_relative_voltage,
    calculate_power_above_mpp,
    get_panel_parameters_with_fallbacks,
)

# Re-export sensor utilities
from .sensor_utils import (
    get_sensor_state_safely,
    get_temperature_compensation_data,
    create_sensor_attributes,
    setup_sensor_listeners,
    cleanup_sensor_listeners,
    calculate_excess_power,
    calculate_usage_percentage,
    is_excess_possible,
    get_mppt_algorithm_config,
)

# Re-export journal utilities
from .journal import (
    journal_event,
    audit_action,
    log_exception,
)

from .logger import (
    get_logger,
    log_info,
    log_debug,
    log_warning,
    log_error,
)

__all__ = [
    # MPPT utilities
    "calculate_current_max_power",
    "calculate_pmax",
    "calculate_min_system_voltage",
    "calculate_relative_voltage",
    "calculate_power_above_mpp",
    "get_panel_parameters_with_fallbacks",
    # Sensor utilities
    "get_sensor_state_safely",
    "get_temperature_compensation_data",
    "create_sensor_attributes",
    "setup_sensor_listeners",
    "cleanup_sensor_listeners",
    "calculate_excess_power",
    "calculate_usage_percentage",
    "is_excess_possible",
    "get_mppt_algorithm_config",
    # Journal utilities
    "journal_event",
    "audit_action",
    "log_exception",
    # Logger utilities
    "get_logger",
    "log_info",
    "log_debug",
    "log_warning",
    "log_error",
]