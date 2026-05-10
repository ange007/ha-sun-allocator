"""MPPT (Maximum Power Point Tracking) algorithm utilities for Sun Allocator."""

import math
from typing import Any, Dict, List, Tuple, Optional

from .logger import log_debug, log_warning, log_error, log_info

from ..const import (
    KEY_CALCULATION_REASON,
    KEY_ENERGY_HARVESTING_POSSIBLE,
    KEY_LIGHT_FACTOR,
    KEY_MIN_SYSTEM_VOLTAGE,
    KEY_PMAX,
    KEY_RELATIVE_VOLTAGE,
    KEY_VOC_RATIO,
    PANEL_CONFIG_SERIES,
    PANEL_CONFIG_PARALLEL_SERIES,
)

# Default voc/vmp ratio used when vmp is unknown. Real-world panels are typically
# 1.18-1.25; 1.2 is a safe centroid that keeps relative_voltage math stable.
_DEFAULT_VOC_RATIO_FALLBACK = 1.2


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
        imp = round(imp * (1 + (pmax_coef - voc_coef) * temp_diff), 3)

        log_debug(f"Applied temperature compensation: temp_diff={temp_diff}°C")

    # Calculate maximum power based on panel configuration
    pmax = calculate_pmax(vmp, imp, panel_count, panel_configuration)

    # Calculate light factor based on actual power vs max power
    if pmax > 0 and pv_power > 0:
        light_factor = max(0.01, min(1.0, pv_power / pmax))
    else:
        light_factor = 0.01

    # Calculate if energy harvesting is possible
    energy_harvesting_possible = pv_voltage >= min_inverter_voltage

    # Calculate relative voltage
    relative_voltage = calculate_relative_voltage(
        pv_voltage, vmp, panel_count, panel_configuration
    )

    # Calculate voc_ratio with protection against 1.0 and non-finite inputs.
    if vmp > 0:
        voc_ratio = voc / vmp
        if not math.isfinite(voc_ratio) or voc_ratio <= 0:
            log_warning(
                "voc/vmp produced non-finite ratio (voc=%s, vmp=%s); "
                "falling back to default %.2f",
                voc, vmp, _DEFAULT_VOC_RATIO_FALLBACK,
            )
            voc_ratio = _DEFAULT_VOC_RATIO_FALLBACK
    else:
        voc_ratio = _DEFAULT_VOC_RATIO_FALLBACK
    if abs(voc_ratio - 1.0) < 1e-6:
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
        fill_factor = imp / isc
        raw_ratio = 1.0 - (1.0 - fill_factor) * (relative_voltage ** curve_factor_k)
        current_ratio = raw_ratio / fill_factor if fill_factor > 0 else raw_ratio

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

        position = max(0.0, min(1.0, position))

        # Use a softer dependence on light level and cap the drop rate to avoid over-penalizing at low light
        adjusted_drop_rate = 1.5 + 1.5 * (1.0 - light_factor)

        # For very high voltage ratios (above 90% of Voc), increase drop rate further
        if position > 0.9:
            high_voltage_penalty = ((position - 0.9) / 0.1) ** 2
            adjusted_drop_rate += high_voltage_penalty * 2

        # Calculate power factor with adjusted drop rate and apply a small floor away from Voc
        power_factor = 1 - (adjusted_drop_rate * position**2)
        floor = 0.05 * max(0.0, min(1.0, (1.0 - position) / 0.05))
        power_factor = max(floor, power_factor)

        # Back-estimate light level from current operating point: pv_power ≈ pmax * lf * power_factor * efficiency
        if pmax > 0 and power_factor > 0.01:
            light_est = pv_power / (pmax * power_factor * efficiency_correction_factor)
            light_est = max(0.01, min(1.0, light_est))
        else:
            light_est = light_factor

        # Project to MPP at the same light level
        current_max_power = pmax * light_est * efficiency_correction_factor
        calculation_reason = "Between Vmp and Voc (back-estimated irradiance)"
        # Replace light_factor in debug info with the estimated irradiance
        light_factor = light_est

    if not math.isfinite(current_max_power):
        log_warning(
            "current_max_power computation produced non-finite value "
            "(reason=%s); falling back to pv_power=%s",
            calculation_reason, pv_power,
        )
        current_max_power = pv_power
    current_max_power = max(current_max_power, pv_power)
    current_max_power = round(current_max_power, 1)

    # Prepare debug information
    debug_info = {
        "pmax": round(pmax, 1),
        "light_factor": round(light_factor, 4),
        "min_system_voltage": round(min_inverter_voltage, 1),
        "energy_harvesting_possible": energy_harvesting_possible,
        "relative_voltage": round(relative_voltage, 4),
        "voc_ratio": round(voc_ratio, 4),
        "calculation_reason": calculation_reason,
    }

    return current_max_power, debug_info


def _calculate_voltage_position(relative_voltage: float, voc_ratio: float) -> float:
    """Return the normalized position between Vmp (0) and Voc (1)."""
    if abs(voc_ratio - 1.0) < 0.001:
        position = (relative_voltage - 1.0) * 10
    else:
        position = (
            (relative_voltage - 1.0) / (voc_ratio - 1.0)
            if (voc_ratio - 1.0) > 0
            else 0.0
        )

    return max(0.0, min(1.0, position))


def _maybe_apply_curtailment_floor(
    input_results: List[Dict[str, Any]],
    total_pv_power: float,
    total_current_max_power: float,
    total_untapped_power: float,
    total_pmax: float,
    relative_voltage: float,
    voc_ratio: float,
    consumption: Optional[float],
    battery_power: Optional[float],
    efficiency_correction_factor: float,
) -> tuple[float, float, float, str]:
    """Lift current_max when a load-limited inverter is likely curtailing PV output."""
    if len(input_results) != 1 or consumption is None or total_pmax <= 0 or total_pv_power <= 0:
        return (
            total_current_max_power,
            total_untapped_power,
            input_results[0][KEY_LIGHT_FACTOR] if input_results else 0.0,
            input_results[0][KEY_CALCULATION_REASON] if input_results else "",
        )

    input_result = input_results[0]
    if input_result[KEY_CALCULATION_REASON] != "Between Vmp and Voc (back-estimated irradiance)":
        return (
            total_current_max_power,
            total_untapped_power,
            input_result[KEY_LIGHT_FACTOR],
            input_result[KEY_CALCULATION_REASON],
        )

    try:
        consumption_value = float(consumption)
    except (TypeError, ValueError):
        return (
            total_current_max_power,
            total_untapped_power,
            input_result[KEY_LIGHT_FACTOR],
            input_result[KEY_CALCULATION_REASON],
        )

    try:
        battery_power_value = float(battery_power or 0.0)
    except (TypeError, ValueError):
        battery_power_value = 0.0

    if consumption_value <= 0 or abs(battery_power_value) > 20.0 or relative_voltage <= 1.0:
        return (
            total_current_max_power,
            total_untapped_power,
            input_result[KEY_LIGHT_FACTOR],
            input_result[KEY_CALCULATION_REASON],
        )

    if total_pv_power > consumption_value * 1.25:
        return (
            total_current_max_power,
            total_untapped_power,
            input_result[KEY_LIGHT_FACTOR],
            input_result[KEY_CALCULATION_REASON],
        )

    position = _calculate_voltage_position(relative_voltage, voc_ratio)
    if position <= 0.2:
        return (
            total_current_max_power,
            total_untapped_power,
            input_result[KEY_LIGHT_FACTOR],
            input_result[KEY_CALCULATION_REASON],
        )

    estimated_light_factor = max(0.01, min(1.0, float(input_result[KEY_LIGHT_FACTOR] or 0.0)))
    curtailment_floor_light = max(estimated_light_factor, math.sqrt(estimated_light_factor))
    curtailment_floor_power = round(
        total_pmax * curtailment_floor_light * efficiency_correction_factor,
        1,
    )

    if curtailment_floor_power <= total_current_max_power:
        return (
            total_current_max_power,
            total_untapped_power,
            input_result[KEY_LIGHT_FACTOR],
            input_result[KEY_CALCULATION_REASON],
        )

    untapped_power = round(max(0.0, curtailment_floor_power - total_pv_power), 1)
    calculation_reason = "Between Vmp and Voc (curtailment-aware floor)"
    input_result["current_max_power"] = curtailment_floor_power
    input_result["untapped_power"] = untapped_power
    input_result[KEY_LIGHT_FACTOR] = round(curtailment_floor_light, 4)
    input_result[KEY_CALCULATION_REASON] = calculation_reason

    return curtailment_floor_power, untapped_power, curtailment_floor_light, calculation_reason


def calculate_multi_mppt_power(
    mppt_inputs: List[Dict[str, Any]],
    curve_factor_k: float = 0.2,
    efficiency_correction_factor: float = 1.05,
    min_inverter_voltage: float = 100.0,
    temperature_compensation: Optional[dict] = None,
    consumption: Optional[float] = None,
    battery_power: Optional[float] = None,
) -> Dict[str, Any]:
    """Calculate aggregate PV power data across one or more independent MPPT inputs."""
    input_results = []

    for index, mppt_input in enumerate(mppt_inputs, start=1):
        pv_power = float(mppt_input.get("pv_power", 0.0) or 0.0)
        pv_voltage = float(mppt_input.get("pv_voltage", 0.0) or 0.0)
        pv_current = mppt_input.get("pv_current")
        pv_current_value = None if pv_current is None else float(pv_current or 0.0)

        current_max_power, debug_info = calculate_current_max_power(
            pv_voltage=pv_voltage,
            pv_power=pv_power,
            vmp=float(mppt_input.get("vmp", 0.0) or 0.0),
            imp=float(mppt_input.get("imp", 0.0) or 0.0),
            voc=float(mppt_input.get("voc", 0.0) or 0.0),
            isc=float(mppt_input.get("isc", 0.0) or 0.0),
            panel_count=int(mppt_input.get("panel_count", 1) or 1),
            panel_configuration=mppt_input.get("panel_configuration", PANEL_CONFIG_SERIES),
            curve_factor_k=curve_factor_k,
            efficiency_correction_factor=efficiency_correction_factor,
            min_inverter_voltage=min_inverter_voltage,
            temperature_compensation=temperature_compensation,
        )

        energy_harvesting_possible = debug_info[KEY_ENERGY_HARVESTING_POSSIBLE]
        relative_voltage = debug_info[KEY_RELATIVE_VOLTAGE]
        untapped_power = 0.0
        if energy_harvesting_possible and relative_voltage > 1.0:
            untapped_power = max(0.0, current_max_power - pv_power)

        input_results.append(
            {
                "id": mppt_input.get("id", f"mppt{index}"),
                "name": mppt_input.get("name", f"MPPT {index}"),
                "pv_power": round(pv_power, 1),
                "pv_voltage": round(pv_voltage, 2),
                "pv_current": None if pv_current_value is None else round(pv_current_value, 3),
                "current_max_power": round(current_max_power, 1),
                "untapped_power": round(untapped_power, 1),
                "vmp": round(float(mppt_input.get("vmp", 0.0) or 0.0), 3),
                "imp": round(float(mppt_input.get("imp", 0.0) or 0.0), 3),
                "voc": round(float(mppt_input.get("voc", 0.0) or 0.0), 3),
                "isc": round(float(mppt_input.get("isc", 0.0) or 0.0), 3),
                "panel_count": int(mppt_input.get("panel_count", 1) or 1),
                "panel_configuration": mppt_input.get("panel_configuration", PANEL_CONFIG_SERIES),
                **debug_info,
            }
        )

    total_pv_power = sum(item["pv_power"] for item in input_results)
    total_current_max_power = sum(item["current_max_power"] for item in input_results)
    total_untapped_power = sum(item["untapped_power"] for item in input_results)
    total_pmax = sum(item[KEY_PMAX] for item in input_results)
    energy_harvesting_possible = any(
        item[KEY_ENERGY_HARVESTING_POSSIBLE] for item in input_results
    )
    relative_voltage = max(
        (item[KEY_RELATIVE_VOLTAGE] for item in input_results), default=0.0
    )
    voc_ratio = max((item[KEY_VOC_RATIO] for item in input_results), default=0.0)
    min_system_voltage = max(
        (item[KEY_MIN_SYSTEM_VOLTAGE] for item in input_results), default=0.0
    )
    if total_pmax > 0:
        light_factor = sum(
            item[KEY_LIGHT_FACTOR] * item[KEY_PMAX] for item in input_results
        ) / total_pmax
    else:
        light_factor = 0.0

    (
        total_current_max_power,
        total_untapped_power,
        light_factor,
        _,
    ) = _maybe_apply_curtailment_floor(
        input_results=input_results,
        total_pv_power=total_pv_power,
        total_current_max_power=total_current_max_power,
        total_untapped_power=total_untapped_power,
        total_pmax=total_pmax,
        relative_voltage=relative_voltage,
        voc_ratio=voc_ratio,
        consumption=consumption,
        battery_power=battery_power,
        efficiency_correction_factor=efficiency_correction_factor,
    )

    calculation_reason = (
        input_results[0][KEY_CALCULATION_REASON]
        if len(input_results) == 1
        else f"Aggregated {len(input_results)} MPPT inputs"
    )

    debug_info = {
        KEY_PMAX: round(total_pmax, 1),
        KEY_LIGHT_FACTOR: round(light_factor, 4),
        KEY_MIN_SYSTEM_VOLTAGE: round(min_system_voltage, 1),
        KEY_ENERGY_HARVESTING_POSSIBLE: energy_harvesting_possible,
        KEY_RELATIVE_VOLTAGE: round(relative_voltage, 4),
        KEY_VOC_RATIO: round(voc_ratio, 4),
        KEY_CALCULATION_REASON: calculation_reason,
    }

    return {
        "pv_power": round(total_pv_power, 1),
        "consumption": None if consumption is None else round(float(consumption), 1),
        "battery_power": None if battery_power is None else round(float(battery_power), 1),
        "current_max_power": round(total_current_max_power, 1),
        "untapped_power": round(total_untapped_power, 1),
        "mppt_count": len(input_results),
        "mppt_inputs": input_results,
        "debug_info": debug_info,
    }


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
