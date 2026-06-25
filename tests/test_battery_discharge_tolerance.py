"""Tests for battery_discharge_tolerance_w in calculate_excess_power_mppt."""

import pytest
from custom_components.sun_allocator.sensor.utils import calculate_excess_power_mppt


# ---------------------------------------------------------------------------
# Helpers: call with reversed=True (signed sensor, positive=discharging)
# ---------------------------------------------------------------------------

def _excess(battery_w, tolerance=0.0, cmax=1000.0, consumption=500.0, reversed_=True):
    return calculate_excess_power_mppt(
        current_max_power=cmax,
        pv_power=cmax,
        battery_power=battery_w,
        battery_power_reversed=reversed_,
        consumption=consumption,
        configured_reserve=0.0,
        energy_harvesting_possible=True,
        relative_voltage=2.0,  # above MPP
        untapped_power_override=cmax - 800.0,  # 200W untapped
        battery_discharge_tolerance_w=tolerance,
    )


# ---------------------------------------------------------------------------
# Default tolerance = 0  (backward-compatible strict behaviour)
# ---------------------------------------------------------------------------

def test_zero_tolerance_blocks_any_discharge():
    """Any discharge (1W) blocks excess with default tolerance=0."""
    assert _excess(battery_w=1.0, tolerance=0.0) == 0.0


def test_zero_tolerance_allows_charging():
    """Charging never blocked (reversed=True, negative = charging)."""
    result = _excess(battery_w=-200.0, tolerance=0.0)
    assert result > 0


# ---------------------------------------------------------------------------
# Non-zero tolerance
# ---------------------------------------------------------------------------

def test_discharge_within_tolerance_allows_excess():
    """Discharge ≤ tolerance → excess calculated (not zero)."""
    result = _excess(battery_w=50.0, tolerance=100.0)
    assert result > 0


def test_discharge_at_tolerance_boundary_allows_excess():
    """Discharge exactly equal to tolerance → allowed (boundary inclusive)."""
    result = _excess(battery_w=100.0, tolerance=100.0)
    assert result > 0


def test_discharge_above_tolerance_blocks():
    """Discharge > tolerance → excess = 0."""
    assert _excess(battery_w=150.0, tolerance=100.0) == 0.0


def test_tolerance_neutral_battery_discharge_not_subtracted():
    """Within tolerance: discharging battery is treated as neutral (charge_w=0).

    cmax=1000, consumption=500, 200W untapped, battery discharging 50W (within 100W tol).
    excess = min(untapped=200, max(0, cmax-consumption-0)) = min(200, 500) = 200.
    (Battery load is NOT added — it's neutral, not load.)
    """
    result = _excess(battery_w=50.0, tolerance=100.0, cmax=1000.0, consumption=500.0)
    assert result == pytest.approx(200.0, abs=1.0)


# ---------------------------------------------------------------------------
# Sign-convention parity (reversed=False)
# ---------------------------------------------------------------------------

def test_reversed_false_discharge_check():
    """reversed=False: negative battery_power = discharging."""
    # -50W = discharging 50W; tolerance 0 → block
    result = calculate_excess_power_mppt(
        current_max_power=1000.0,
        pv_power=1000.0,
        battery_power=-50.0,
        battery_power_reversed=False,
        consumption=500.0,
        energy_harvesting_possible=True,
        relative_voltage=2.0,
        untapped_power_override=200.0,
        battery_discharge_tolerance_w=0.0,
    )
    assert result == 0.0


def test_reversed_false_within_tolerance():
    """reversed=False, tolerance 100W: -50W discharge allowed."""
    result = calculate_excess_power_mppt(
        current_max_power=1000.0,
        pv_power=1000.0,
        battery_power=-50.0,
        battery_power_reversed=False,
        consumption=500.0,
        energy_harvesting_possible=True,
        relative_voltage=2.0,
        untapped_power_override=200.0,
        battery_discharge_tolerance_w=100.0,
    )
    assert result > 0
