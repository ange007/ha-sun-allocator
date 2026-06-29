"""Tests for calculate_excess_power_export (the 'export' calculation method).

Energy balance: excess = max(0, pv − consumption − inverter_self − battery_load),
where battery_load is the reserve-modulated charge. Charge above the reserve falls
through into the available excess. Shares the discharge guard + tolerance and the
SOC-modulated reserve with the MPPT method.
"""

import pytest
from custom_components.sun_allocator.sensor.utils import calculate_excess_power_export


def test_basic_balance():
    """pv − consumption with no battery / reserve / self."""
    result = calculate_excess_power_export(
        pv_power=1000.0, consumption=600.0,
        battery_power=0.0, battery_power_reversed=True,
    )
    assert result == pytest.approx(400.0)


def test_inverter_self_consumption_subtracted():
    result = calculate_excess_power_export(
        pv_power=1000.0, consumption=600.0,
        battery_power=0.0, battery_power_reversed=True,
        inverter_self_consumption=50.0,
    )
    assert result == pytest.approx(350.0)


def test_charge_within_reserve_is_load():
    """Charging 100W within a 200W reserve → fully subtracted as battery_load."""
    # reversed=True → negative battery_power means charging.
    result = calculate_excess_power_export(
        pv_power=1000.0, consumption=600.0,
        battery_power=-100.0, battery_power_reversed=True,
        configured_reserve=200.0,
    )
    assert result == pytest.approx(300.0)  # 1000 - 600 - min(100,200)=100


def test_charge_above_reserve_falls_through():
    """Charging 300W with a 100W reserve → only 100W reserved; the surplus 200W
    of charge is divertible and is NOT subtracted."""
    result = calculate_excess_power_export(
        pv_power=1000.0, consumption=600.0,
        battery_power=-300.0, battery_power_reversed=True,
        configured_reserve=100.0,
    )
    assert result == pytest.approx(300.0)  # 1000 - 600 - 100


def test_discharge_beyond_tolerance_blocks():
    """Battery discharging beyond tolerance → excess forced to 0."""
    result = calculate_excess_power_export(
        pv_power=1000.0, consumption=600.0,
        battery_power=50.0, battery_power_reversed=True,  # +50 = discharging
        battery_discharge_tolerance_w=0.0,
    )
    assert result == 0.0


def test_discharge_within_tolerance_neutral():
    """Discharge ≤ tolerance → treated as neutral (battery_load=0)."""
    result = calculate_excess_power_export(
        pv_power=1000.0, consumption=600.0,
        battery_power=50.0, battery_power_reversed=True,
        battery_discharge_tolerance_w=100.0,
    )
    assert result == pytest.approx(400.0)


def test_soc_below_sharing_forces_priority():
    """Below sharing_soc the reserve is forced to 0 → all charge is divertible."""
    result = calculate_excess_power_export(
        pv_power=1000.0, consumption=600.0,
        battery_power=-300.0, battery_power_reversed=True,
        configured_reserve=200.0, sharing_soc=50.0, battery_soc=40.0,
    )
    # effective_reserve=0 → battery_load=0 → 1000-600-0 = 400
    assert result == pytest.approx(400.0)


def test_soc_at_or_above_sharing_applies_reserve():
    result = calculate_excess_power_export(
        pv_power=1000.0, consumption=600.0,
        battery_power=-300.0, battery_power_reversed=True,
        configured_reserve=200.0, sharing_soc=50.0, battery_soc=60.0,
    )
    # effective_reserve=200 → battery_load=min(300,200)=200 → 1000-600-200 = 200
    assert result == pytest.approx(200.0)


def test_consumption_none_treated_as_zero():
    result = calculate_excess_power_export(
        pv_power=1000.0, consumption=None,
        battery_power=0.0, battery_power_reversed=True,
    )
    assert result == pytest.approx(1000.0)


def test_negative_result_clamped_to_zero():
    result = calculate_excess_power_export(
        pv_power=100.0, consumption=600.0,
        battery_power=0.0, battery_power_reversed=True,
    )
    assert result == 0.0


def test_reversed_false_parity():
    """reversed=False: positive battery_power = charging."""
    result = calculate_excess_power_export(
        pv_power=1000.0, consumption=600.0,
        battery_power=100.0, battery_power_reversed=False,  # +100 charging
        configured_reserve=200.0,
    )
    assert result == pytest.approx(300.0)  # 1000-600-min(100,200)
