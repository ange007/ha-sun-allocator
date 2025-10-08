"""MPPT (Maximum Power Point Tracking) algorithm utilities for Sun Allocator."""

from typing import Tuple, Optional

from .logger import log_debug, log_warning, log_error, log_info

from ..const import (
    PANEL_CONFIG_SERIES,
    PANEL_CONFIG_PARALLEL_SERIES,
)


def calculate_current_max_power(
    pv_voltage: float,
    pv_power: float,
    vmp: float,
    imp: float,
    voc: float,
    isc: float,
    panel_count: int,
    panel_configuration: str,
    curve_factor_k: float = 0.2,
    efficiency_correction_factor: float = 1.05,
    min_inverter_voltage: float = 100.0,
    temperature_compensation: Optional[dict] = None,
) -> Tuple[float, dict]:
    """
    Calculate current maximum power based on MPPT algorithm.

    Args:
        pv_voltage: Current PV voltage
        pv_power: Current PV power
        vmp: Voltage at maximum power point (single panel)
        imp: Current at maximum power point (single panel)
        voc: Open circuit voltage (single panel)
        isc: Short circuit current (single panel)
        panel_count: Number of panels
        panel_configuration: Panel configuration ("series", "parallel", "parallel-series")
        curve_factor_k: Curve fitting parameter for I-V model
        efficiency_correction_factor: Efficiency correction factor
        min_inverter_voltage: Minimum inverter voltage
        temperature_compensation: Temperature compensation parameters

    Returns:
        Tuple of (current_max_power, debug_info)
    """
    # pylint: disable=too-many-locals,too-many-branches,too-many-statements

    # Guard clause for zero or negative PV power
    if pv_power <= 0:
        return 0.0, {"pmax": 0, "light_factor": 0, "min_system_voltage": 0, "energy_harvesting_possible": False, "relative_voltage": 0, "voc_ratio": 0, "calculation_reason": "PV power is zero or negative"}

    # Apply temperature compensation if provided
    if temperature_compensation:
        temp_diff = temperature_compensation.get("temp_diff", 0)
        voc_coef = temperature_compensation.get("voc_coef", -0.003)
        pmax_coef = temperature_compensation.get("pmax_coef", -0.004)

        # Adjust values
        voc = round(voc * (1 + voc_coef * temp_diff), 3)
        vmp = round(vmp * (1 + voc_coef * temp_diff), 3)
        imp = round(imp * (1 + pmax_coef * temp_diff + voc_coef * temp_diff), 3)

        log_debug(f"Applied temperature compensation: temp_diff={temp_diff}°C")

    # Calculate maximum power based on panel configuration
    pmax = calculate_pmax(vmp, imp, panel_count, panel_configuration)

    # Calculate light factor based on actual power vs max power
    if pmax > 0 and pv_power > 0:
        light_factor = max(0.1, min(1.0, pv_power / pmax))
    else:
        light_factor = 0.1

    # Calculate if energy harvesting is possible
    min_system_voltage = calculate_min_system_voltage(
        min_inverter_voltage, panel_count, panel_configuration
    )
    energy_harvesting_possible = pv_voltage >= min_system_voltage

    # Calculate relative voltage
    relative_voltage = calculate_relative_voltage(
        pv_voltage, vmp, panel_count, panel_configuration
    )

    # Calculate voc_ratio with protection against 1.0
    voc_ratio = voc / vmp if vmp > 0 else 1.2
    if voc_ratio == 1.0:
        voc_ratio = 1.01  # Add a small buffer
        log_debug(f"Fix applied: Adjusted voc_ratio from 1.0 to {voc_ratio:.2f}")

    # Calculate current max power using enhanced I-V model
    current_max_power = 0.0
    calculation_reason = ""

    if pv_voltage <= 0 or vmp <= 0:
        current_max_power = 0.0
        calculation_reason = "Invalid voltage or Vmp"
    elif relative_voltage >= voc_ratio:
        current_max_power = 0.0
        calculation_reason = "Voltage at or above Voc"
    elif not energy_harvesting_possible:
        current_max_power = 0.0
        calculation_reason = "Energy harvesting not possible"
    elif relative_voltage <= 1.0:
        # Below or at MPP: Use improved I-V model
        current_ratio = 1.0 - (1.0 - (imp / isc)) * (relative_voltage**curve_factor_k)
        current_max_power = (
            pmax
            * light_factor
            * relative_voltage
            * current_ratio
            * efficiency_correction_factor
        )
        calculation_reason = "Below or at MPP"
    else:
        # Between Vmp and Voc: Back-estimate irradiance from current operating point and project to MPP
        # Calculate position between Vmp and Voc (0 at Vmp, 1 at Voc)
        if abs(voc_ratio - 1.0) < 0.001:
            position = (relative_voltage - 1.0) * 10
        else:
            position = (
                (relative_voltage - 1.0) / (voc_ratio - 1.0)
                if (voc_ratio - 1.0) > 0
                else 0.0
            )

        # Use a softer dependence on light level and cap the drop rate to avoid over-penalizing at low light
        base_drop_rate = 1.5
        adjusted_drop_rate = base_drop_rate / (light_factor**0.5)
        adjusted_drop_rate = min(adjusted_drop_rate, 3.0)

        # For very high voltage ratios (above 90% of Voc), increase drop rate further
        if position > 0.9:
            high_voltage_penalty = ((position - 0.9) / 0.1) ** 2
            adjusted_drop_rate += high_voltage_penalty * 2

        # Calculate power factor with adjusted drop rate and apply a small floor away from Voc
        power_factor = 1 - (adjusted_drop_rate * position**2)
        floor = 0.05 if position <= 0.98 else 0.0
        power_factor = max(floor, power_factor)

        # Back-estimate light level from current operating point: pv_power ≈ pmax * lf * power_factor * efficiency
        if pmax > 0 and power_factor > 0.1:
            light_est = pv_power / (pmax * power_factor * efficiency_correction_factor)
            light_est = max(0.1, min(1.0, light_est))
        else:
            light_est = light_factor  # fallback

        # Project to MPP at the same light level
        current_max_power = pmax * light_est * efficiency_correction_factor
        calculation_reason = "Between Vmp and Voc (back-estimated irradiance)"
        # Replace light_factor in debug info with the estimated irradiance
        light_factor = light_est

    current_max_power = max(current_max_power, pv_power)
    current_max_power = round(current_max_power, 1)

    # Prepare debug information
    debug_info = {
        "pmax": pmax,
        "light_factor": light_factor,
        "min_system_voltage": min_system_voltage,
        "energy_harvesting_possible": energy_harvesting_possible,
        "relative_voltage": relative_voltage,
        "voc_ratio": voc_ratio,
        "calculation_reason": calculation_reason,
    }

    return current_max_power, debug_info


def calculate_pmax(
    vmp: float, imp: float, panel_count: int, panel_configuration: str
) -> float:
    """Calculate maximum power based on panel configuration."""
    pmax = 0.0
    if panel_configuration == PANEL_CONFIG_SERIES:
        # For series: Vmp is multiplied by panel_count, Imp stays the same
        pmax = (vmp * panel_count) * imp
    elif panel_configuration == PANEL_CONFIG_PARALLEL_SERIES:
        # For parallel-series: Two strings of panels in series, connected in parallel
        string_count = 2  # Number of parallel strings
        panels_per_string = panel_count / string_count

        # Check if panel_count is even for equal strings
        if panel_count % string_count != 0:
            log_warning(
                f"Panel count {panel_count} is not evenly divisible by {string_count} "
                f"for parallel-series configuration. Using {int(panels_per_string)} panels per string."
            )

        pmax = (vmp * panels_per_string) * (imp * string_count)
    else:
        # For parallel: Vmp stays the same, Imp is multiplied by panel_count
        pmax = vmp * (imp * panel_count)
    
    return round(pmax, 2)


def calculate_min_system_voltage(
    min_inverter_voltage: float, panel_count: int, panel_configuration: str
) -> float:
    """Calculate minimum system voltage based on configuration."""
    if panel_configuration == PANEL_CONFIG_SERIES:
        return min_inverter_voltage
    
    if panel_configuration == PANEL_CONFIG_PARALLEL_SERIES:
        return min_inverter_voltage

    # parallel
    return min_inverter_voltage


def calculate_relative_voltage(
    pv_voltage: float, vmp: float, panel_count: int, panel_configuration: str
) -> float:
    """Calculate relative voltage based on panel configuration."""
    if panel_configuration == PANEL_CONFIG_SERIES:
        # For series: divide by (Vmp * panel_count)
        return pv_voltage / (vmp * panel_count) if vmp > 0 else 0

    if panel_configuration == PANEL_CONFIG_PARALLEL_SERIES:
        # For parallel-series: divide by (Vmp * panels_per_string)
        string_count = 2
        panels_per_string = panel_count / string_count
        return pv_voltage / (vmp * panels_per_string) if vmp > 0 else 0

    # For parallel: divide by Vmp (voltage is the same across all panels)
    return pv_voltage / vmp if vmp > 0 else 0


def get_panel_parameters_with_fallbacks(
    vmp: Optional[float],
    imp: Optional[float],
    voc: Optional[float],
    isc: Optional[float],
    panel_count: Optional[int],
) -> Tuple[float, float, float, float, int]:
    """
    Get panel parameters with proper fallbacks for missing values.

    Returns:
        Tuple of (vmp, imp, voc, isc, panel_count)
    """
    # Set defaults
    _vmp = 0.0
    _imp = 0.0
    _voc = 0.0
    _isc = 0.0
    _panel_count = 1

    try:
        if vmp is not None:
            _vmp = float(vmp)
        else:
            log_warning("Vmp is not configured, calculations will be inaccurate")

        if imp is not None:
            _imp = float(imp)
        else:
            log_warning("Imp is not configured, calculations will be inaccurate")

        if voc is not None:
            _voc = float(voc)
        else:
            log_info("Voc is not configured, using estimated value")
            _voc = round(_vmp * 1.2, 3)  # Estimate Voc as 20% higher than Vmp

        if isc is not None:
            _isc = float(isc)
        else:
            log_info("Isc is not configured, using estimated value")
            _isc = round(_imp * 1.1, 3)  # Estimate Isc as 10% higher than Imp

        if panel_count is not None:
            _panel_count = int(panel_count)

    except (ValueError, TypeError) as exc:
        log_error(f"Error converting panel parameters: {exc}")

    return _vmp, _imp, _voc, _isc, _panel_count
