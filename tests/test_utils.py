from custom_components.sun_allocator.sensor.utils import (
    calculate_excess_power_mppt,
    calculate_excess_power_parallel,
)


def test_calculate_excess_power_mppt_with_consumption():
    """Test excess power calculation with consumption sensor."""
    # This test remains valid for the fallback logic inside mppt calc

    # Scenario 1: Basic case, no battery, priority mode
    excess = calculate_excess_power_mppt(
        current_max_power=1500, consumption=500, configured_reserve=0
    )
    assert excess == 1000  # 1500 - 500 - 0

    # Scenario 2: With battery charging, priority mode
    excess = calculate_excess_power_mppt(
        current_max_power=1500,
        consumption=500,
        battery_power=200,  # Charging
        configured_reserve=0,
    )
    assert excess == 800  # 1500 - 500 - 200

    # Scenario 3: With battery charging, budget mode
    excess = calculate_excess_power_mppt(
        current_max_power=1500,
        consumption=500,
        battery_power=200,  # Charging
        configured_reserve=100,
    )
    assert excess == 900  # 1500 - 500 - 100


def test_calculate_excess_power_mppt_without_consumption():
    """Test MPPT excess power calculation without consumption sensor."""

    # --- Priority Mode (reserve = 0) ---
    # Excess should only be the untapped panel power
    excess = calculate_excess_power_mppt(
        current_max_power=1500,
        pv_power=1000,
        battery_power=300,  # Charging
        consumption=None,
        configured_reserve=0,
    )
    assert excess == 500  # 1500 - 1000

    # --- Budget Mode (reserve > 0) ---
    # Excess is untapped + (charge - reserve)
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

    # --- Budget Mode (charging less than reserve) ---
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

    # --- Discharging ---
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
