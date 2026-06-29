"""Tests for detect_curtailment.

Curtailment = the inverter is throttling PV (so the MPPT untapped estimate is a
known underestimate): meaningful headroom between current_max_power and pv_power,
the battery not discharging beyond tolerance, and the battery at its charge limit
(charge power ≤ idle band). The charge-power signal is used instead of SOC because
many inverters cap charging below 100% (SOC/voltage/preserve limits).
"""

from custom_components.sun_allocator.sensor.utils import detect_curtailment
from custom_components.sun_allocator.const import (
    CURTAILMENT_UNTAPPED_MARGIN_W,
    BATTERY_CHARGE_IDLE_W,
)


def test_idle_battery_with_headroom_is_curtailment():
    # battery idle (net 0) + headroom 200 → curtailing.
    assert detect_curtailment(
        pv_power=1000.0, current_max_power=1200.0,
        battery_power=0.0, battery_power_reversed=True,
    ) is True


def test_no_headroom_is_not_curtailment():
    # headroom 20W <= margin (50W) → False even with idle battery.
    assert detect_curtailment(
        pv_power=1180.0, current_max_power=1200.0,
        battery_power=0.0, battery_power_reversed=True,
    ) is False


def test_discharging_beyond_tolerance_is_not_curtailment():
    # reversed=True → +50 = discharging; tolerance 0 → guard fails.
    assert detect_curtailment(
        pv_power=1000.0, current_max_power=1200.0,
        battery_power=50.0, battery_power_reversed=True, discharge_tolerance_w=0.0,
    ) is False


def test_battery_actively_charging_is_not_curtailment():
    # reversed=True → -200 = charging 200W (> idle band) → battery still absorbing.
    assert detect_curtailment(
        pv_power=1000.0, current_max_power=1200.0,
        battery_power=-200.0, battery_power_reversed=True,
    ) is False


def test_charge_within_idle_band_is_curtailment():
    # charging 30W (<= 50W idle) → at limit / trickle → curtailing.
    assert detect_curtailment(
        pv_power=1000.0, current_max_power=1200.0,
        battery_power=-30.0, battery_power_reversed=True,
    ) is True


def test_charge_just_above_idle_band_is_not_curtailment():
    # charging 80W (> 50W idle) → still hungry → not curtailment.
    assert detect_curtailment(
        pv_power=1000.0, current_max_power=1200.0,
        battery_power=-80.0, battery_power_reversed=True,
    ) is False


def test_discharge_within_tolerance_still_curtailment():
    # -10W with 20W tolerance → not discharging, idle → curtailing.
    assert detect_curtailment(
        pv_power=1000.0, current_max_power=1200.0,
        battery_power=10.0, battery_power_reversed=True, discharge_tolerance_w=20.0,
    ) is True


def test_headroom_exactly_at_margin_is_not_curtailment():
    # headroom == margin → strict greater-than required → False.
    assert detect_curtailment(
        pv_power=1000.0, current_max_power=1000.0 + CURTAILMENT_UNTAPPED_MARGIN_W,
        battery_power=0.0, battery_power_reversed=True,
    ) is False


def test_charge_idle_boundary_inclusive():
    # charging exactly at the idle band (50W) → inclusive → curtailing.
    assert detect_curtailment(
        pv_power=1000.0, current_max_power=1200.0,
        battery_power=-BATTERY_CHARGE_IDLE_W, battery_power_reversed=True,
    ) is True


def test_reversed_false_charging_not_curtailment():
    # reversed=False → +200 = charging → not curtailment.
    assert detect_curtailment(
        pv_power=1000.0, current_max_power=1200.0,
        battery_power=200.0, battery_power_reversed=False,
    ) is False
