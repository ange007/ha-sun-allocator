"""Excess-power math for Sun Allocator — the heart of the integration.

Pure functions that turn the raw PV / battery / consumption readings into the
available-surplus number the allocator budgets against, plus curtailment detection
and the MPPT algorithm config. Extracted from ``sensor/utils.py`` (which had grown
into a grab-bag) so the core calculation lives in one focused, unit-testable module.

Kept import-compatible: ``sensor/utils.py`` re-exports every public name here, so
existing ``from ..sensor.utils import calculate_excess_power_mppt`` imports (in the
sensors and the test suite) keep working unchanged.
"""

from typing import Any, Dict

from ..core.logger import log_debug
from ..core.probe import battery_net_charge_w as _battery_net_charge_w

from ..const import (
    CONF_CURVE_FACTOR_K,
    CONF_EFFICIENCY_CORRECTION_FACTOR,
    CONF_MIN_INVERTER_VOLTAGE,
    INTERNAL_CURVE_FACTOR_K,
    INTERNAL_EFFICIENCY_CORRECTION_FACTOR,
    BATTERY_CHARGE_IDLE_W,
    CURTAILMENT_UNTAPPED_MARGIN_W,
)


def _effective_reserve(
    configured_reserve: float, battery_soc: float | None, sharing_soc: float
) -> float:
    """SOC-modulated reserve: below ``sharing_soc`` the battery takes absolute
    charge priority (reserve forced to 0 → all charge protected). At/above it, or
    when ``sharing_soc`` is disabled (0) or SOC unknown, the configured reserve
    applies as-is."""
    if sharing_soc > 0 and battery_soc is not None and battery_soc < sharing_soc:
        return 0.0
    return configured_reserve


def detect_curtailment(
    pv_power: float,
    current_max_power: float,
    battery_power: float,
    battery_power_reversed: bool = False,
    discharge_tolerance_w: float = 0.0,
    charge_idle_w: float = BATTERY_CHARGE_IDLE_W,
) -> bool:
    """Return True when the inverter is curtailing PV — i.e. the MPPT untapped
    estimate is a known underestimate.

    Curtailment is inferred when there is meaningful headroom between the estimated
    max and the actual output, the battery is not discharging beyond tolerance, and
    the battery is at its charge limit (charge power ≤ ``charge_idle_w``). The
    charge-power signal is used instead of SOC because many inverters cap charging
    below 100% (SOC limit, stop-charging voltage, preserve mode), so an SOC test
    would never fire on those systems. A hybrid inverter in this state throttles
    the panels to match load, so a waiting device could be fed for free (see the
    ``mppt_probe`` method)."""
    if (float(current_max_power) - float(pv_power)) <= CURTAILMENT_UNTAPPED_MARGIN_W:
        return False
    net_charge_w = _battery_net_charge_w(battery_power, battery_power_reversed)
    if net_charge_w < -discharge_tolerance_w:
        return False  # discharging
    # Battery still actively absorbing charge → it is not "done"; not curtailment.
    return net_charge_w <= charge_idle_w


def calculate_excess_power_export(
    pv_power: float,
    consumption: float | None,
    battery_power: float,
    battery_power_reversed: bool,
    configured_reserve: float = 0.0,
    inverter_self_consumption: float = 0.0,
    battery_soc: float | None = None,
    sharing_soc: float = 0.0,
    battery_discharge_tolerance_w: float = 0.0,
) -> float:
    """Energy-balance excess for grid-export inverters where ``pv_power`` reflects
    true generation (not load-following curtailed output).

    ``excess = pv − consumption − inverter_self − battery_load`` where
    ``battery_load`` is the reserve-modulated charge (``min(charge, reserve)``).
    Battery charge above the reserve is divertible surplus, so it is NOT
    subtracted — it falls through into the available excess. Shares the discharge
    guard + tolerance and SOC-modulated reserve with the MPPT method.
    """
    net_charge_w = _battery_net_charge_w(battery_power, battery_power_reversed)
    if net_charge_w < -battery_discharge_tolerance_w:
        return 0.0
    battery_charge_w = max(0.0, net_charge_w)
    effective_reserve = _effective_reserve(configured_reserve, battery_soc, sharing_soc)
    battery_load = min(battery_charge_w, effective_reserve)

    excess = (
        float(pv_power)
        - float(consumption or 0.0)
        - float(inverter_self_consumption)
        - float(battery_load)
    )
    log_debug(
        "Export: PV=%sW, Consumption=%sW, Self=%sW, BatteryLoad=%sW -> Excess=%sW",
        pv_power, consumption, inverter_self_consumption, battery_load, excess,
    )
    return max(0.0, excess)


def calculate_excess_power_mppt(
    current_max_power: float,
    pv_power: float = 0.0,
    battery_power: float = 0.0,
    battery_power_reversed: bool = False,
    consumption: float | None = None,
    configured_reserve: float = 0.0,
    inverter_self_consumption: float = 0.0,
    relative_voltage: float | None = None,
    energy_harvesting_possible: bool | None = None,
    untapped_power_override: float | None = None,
    battery_soc: float | None = None,
    sharing_soc: float = 0.0,
    battery_discharge_tolerance_w: float = 0.0,
    **kwargs,  # Catch-all for future compatibility
) -> float:
    """
    Calculate excess power with proper accounting for battery charge and consumption.
    This function uses a unified MPPT approach, leveraging consumption data if available
    to provide a more accurate calculation of available excess power.

    For multi-MPPT setups, ``untapped_power_override`` can supply a pre-computed
    sum of per-tracker untapped power (with each tracker's own relative_voltage
    gating already applied). When provided, ``relative_voltage`` is bypassed for
    the untapped calculation but still used as a guard.

    SOC-modulated reserve: when ``sharing_soc`` > 0 and the battery SOC is below it,
    the configured reserve is forced to 0 (priority mode → the battery keeps all
    charge, devices get only untapped surplus). At or above ``sharing_soc`` the
    configured reserve applies normally (battery keeps the reserve, releases the
    rest). ``sharing_soc`` = 0 (default) or unknown SOC → configured reserve as-is.
    """
    # 1. Discharge Guard with tolerance.
    # net_charge_w: positive = charging, negative = discharging (sign-convention-independent).
    net_charge_w = _battery_net_charge_w(battery_power, battery_power_reversed)
    if net_charge_w < -battery_discharge_tolerance_w:
        return 0.0

    # 2. Topology Guard: No excess if harvesting isn't possible.
    if energy_harvesting_possible is not None and not energy_harvesting_possible:
        return 0.0

    # 3. Normalize: positive charging load; within-tolerance discharge counted as neutral (0).
    battery_charge_w = max(0.0, net_charge_w)

    # 4. Calculate untapped power based on voltage relative to MPP
    if untapped_power_override is not None:
        untapped_power = max(0.0, float(untapped_power_override))
    elif relative_voltage is not None and relative_voltage <= 1.0:
        # If voltage is at or below MPP, there is no untapped power from the panels.
        # Excess can only come from battery budget spillover in this state.
        untapped_power = 0.0
    else:
        # Voltage is above MPP, so there is potential untapped power.
        untapped_power = max(0, current_max_power - pv_power)

    # 5. Calculate base loads (consumption + inverter self-consumption)
    base_loads = inverter_self_consumption
    if consumption is not None:
        base_loads += consumption

    # 6. SOC-modulated reserve: below sharing_soc the battery gets absolute
    # priority (reserve forced to 0 → all charge protected); at/above it the
    # configured reserve applies. Disabled (sharing_soc=0) or unknown SOC → as-is.
    effective_reserve = _effective_reserve(configured_reserve, battery_soc, sharing_soc)

    # 7. Calculate battery load and battery_excess
    if effective_reserve > 0:
        # Budget mode: only battery charge above reserve is load, rest is excess
        battery_load = min(battery_charge_w, effective_reserve)
        battery_excess = max(0, battery_charge_w - effective_reserve)
    else:
        # Priority mode: all battery charge is load
        battery_load = battery_charge_w
        battery_excess = 0

    if consumption is None:
        # No consumption sensor: excess is untapped + battery_excess
        excess = untapped_power + battery_excess
        if inverter_self_consumption > 0:
            excess = max(0.0, excess - inverter_self_consumption)
    else:
        # With consumption sensor: self_consumption reduces effective untapped directly.
        # real_excess uses only consumption + battery (not self_consumption) to avoid
        # double-counting when untapped < real_excess.
        effective_untapped = max(0.0, untapped_power - inverter_self_consumption)
        real_excess = current_max_power - float(consumption) - battery_load
        if effective_reserve > 0:
            excess = min(effective_untapped, max(0, real_excess)) + battery_excess
        else:
            excess = min(effective_untapped, max(0, real_excess))

    log_debug(
        f"MPPT: PV={pv_power}W, Loads={base_loads}W, BatteryLoad={battery_load}W, "
        f"BatteryExcess={battery_excess}W, Untapped={untapped_power}W -> Excess={excess}W"
    )
    return excess


def get_mppt_algorithm_config(config: Dict[str, Any]) -> Dict[str, float]:
    """Get MPPT algorithm configuration parameters."""
    return {
        CONF_CURVE_FACTOR_K: INTERNAL_CURVE_FACTOR_K,
        CONF_EFFICIENCY_CORRECTION_FACTOR: INTERNAL_EFFICIENCY_CORRECTION_FACTOR,
        CONF_MIN_INVERTER_VOLTAGE: config.get(CONF_MIN_INVERTER_VOLTAGE, 100.0),
    }
