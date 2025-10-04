from custom_components.sun_allocator.sensor.utils import (
    calculate_excess_power_mppt,
    calculate_excess_power_parallel,
)


def test_calculate_excess_power_mppt_with_consumption_unified():
    """Test unified MPPT excess power calculation with a consumption sensor."""

    # --- Priority Mode (reserve = 0) ---

    # Scenario 1: Untapped power is the limiting factor.
    # Real excess is high, but we can only use the untapped potential.
    excess = calculate_excess_power_mppt(
        current_max_power=2000,
        pv_power=1800,          # -> untapped = 200
        consumption=500,
        battery_power=100,      # -> battery_load = 100
        configured_reserve=0,
    )
    # real_excess = 2000 - 500 - 100 = 1400
    # excess = min(untapped, real_excess) = min(200, 1400) = 200
    assert excess == 200

    # Scenario 2: Real excess is the limiting factor.
    # High home consumption limits the available excess, even with high untapped potential.
    excess = calculate_excess_power_mppt(
        current_max_power=2000,
        pv_power=1000,          # -> untapped = 1000
        consumption=1600,
        battery_power=100,      # -> battery_load = 100
        configured_reserve=0,
    )
    # real_excess = 2000 - 1600 - 100 = 300
    # excess = min(untapped, real_excess) = min(1000, 300) = 300
    assert excess == 300

    # --- Budget Mode (reserve > 0) ---

    # Scenario 3: Budgeting adds power from the battery.
    excess = calculate_excess_power_mppt(
        current_max_power=2000,
        pv_power=1800,          # -> untapped = 200
        consumption=500,
        battery_power=300,      # -> battery_charge_w = 300
        configured_reserve=100,
    )
    # In budget mode, battery_load is 0 for real_excess calculation.
    # real_excess = 2000 - 500 - 0 = 1500
    # excess = min(untapped, real_excess) = min(200, 1500) = 200
    # excess_from_battery = 300 - 100 = 200
    # total_excess = 200 + 200 = 400
    assert excess == 400


def test_calculate_excess_power_mppt_without_consumption():
    """Test MPPT excess power calculation without consumption sensor."""

    # --- Priority Mode (reserve = 0) ---
    # Excess is just the untapped panel power.
    excess = calculate_excess_power_mppt(
        current_max_power=1500,
        pv_power=1000,
        battery_power=300,  # Charging
        consumption=None,
        configured_reserve=0,
    )
    assert excess == 500  # 1500 - 1000

    # --- Budget Mode (reserve > 0) ---
    # Excess is untapped + (battery_charge - reserve).
    excess = calculate_excess_power_mppt(
        current_max_power=1500,
        pv_power=1000,
        battery_power=300,  # Charging
        consumption=None,
        configured_reserve=100,
    )
    # Untapped = 1500 - 1000 = 500
    # From Battery = 300 - 100 = 200
    # Total = 700
    assert excess == 700

    # --- Budget Mode (charging is less than reserve) ---
    excess = calculate_excess_power_mppt(
        current_max_power=1500,
        pv_power=1000,
        battery_power=50,  # Charging
        consumption=None,
        configured_reserve=100,
    )
    # Untapped = 1500 - 1000 = 500
    # From Battery = max(0, 50 - 100) = 0
    # Total = 500
    assert excess == 500

    # --- Discharging Guard ---
    # Should always be 0
    excess = calculate_excess_power_mppt(
        current_max_power=1500,
        pv_power=1000,
        battery_power=-100,  # Discharging
        consumption=None,
        configured_reserve=100,
    )
    assert excess == 0


def test_calculate_excess_power_parallel():
    """Test the parallel excess power calculation for both sub-modes."""

    # --- Priority Mode (reserve = 0) ---
    # Excess = PV - Consumption - Battery Charge
    excess = calculate_excess_power_parallel(
        pv_power=3000,
        consumption=500,
        battery_power=200,  # Charging
        battery_power_reversed=False,
        configured_reserve=0,
    )
    assert excess == 2300  # 3000 - 500 - 200

    # --- Budgeting Mode (reserve > 0) ---
    # Excess = PV - Consumption - Reserve
    excess = calculate_excess_power_parallel(
        pv_power=3000,
        consumption=500,
        battery_power=200,  # Charging
        battery_power_reversed=False,
        configured_reserve=100,
    )
    assert excess == 2400  # 3000 - 500 - 100

    # --- Budgeting Mode with Passive Charging ---
    # Effective reserve becomes the battery charge rate
    excess = calculate_excess_power_parallel(
        pv_power=3000,
        consumption=500,
        battery_power=40,  # Passive charging
        battery_power_reversed=False,
        configured_reserve=100,
    )
    assert excess == 2460  # 3000 - 500 - 40
