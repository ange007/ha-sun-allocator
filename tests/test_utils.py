import pytest
from custom_components.sun_allocator.sensor.utils import calculate_excess_power_mppt, calculate_excess_power_parallel

def test_calculate_excess_power_mppt_with_consumption():
    """Test excess power calculation with consumption sensor."""
    # excess = current_max_power - consumption - battery_charge_w
    
    # Scenario 1: Basic case, no battery
    excess = calculate_excess_power_mppt(
        pv_power=1000,
        current_max_power=1500,
        consumption=500
    )
    assert excess == 1000 # 1500 - 500 - 0

    # Scenario 2: With battery charging
    excess = calculate_excess_power_mppt(
        pv_power=1000,
        current_max_power=1500,
        consumption=500,
        battery_power=200 # Charging
    )
    assert excess == 800 # 1500 - 500 - 200

    # Scenario 3: With battery charging (reversed polarity)
    excess = calculate_excess_power_mppt(
        pv_power=1000,
        current_max_power=1500,
        consumption=500,
        battery_power=-200, # Charging
        battery_power_reversed=True
    )
    assert excess == 800 # 1500 - 500 - 200

    # Scenario 4: With battery discharging
    excess = calculate_excess_power_mppt(
        pv_power=1000,
        current_max_power=1500,
        consumption=500,
        battery_power=-200 # Discharging
    )
    assert excess == 0

    # Scenario 5: With battery discharging (reversed polarity)
    excess = calculate_excess_power_mppt(
        pv_power=1000,
        current_max_power=1500,
        consumption=500,
        battery_power=200, # Discharging
        battery_power_reversed=True
    )
    assert excess == 0

    # Scenario 6: High consumption case
    excess = calculate_excess_power_mppt(
        pv_power=1000,
        current_max_power=1500,
        consumption=1400
    )
    assert excess == 100 # 1500 - 1400 - 0

    # Scenario 7: Consumption exceeds max power
    excess = calculate_excess_power_mppt(
        pv_power=1000,
        current_max_power=1500,
        consumption=1600
    )
    assert excess == 0 # max(1500 - 1600 - 0, 0) = 0


def test_calculate_excess_power_mppt_without_consumption():
    """Test excess power calculation without consumption sensor."""
    # When consumption is None, the function uses:
    # excess = current_max_power - actual_harvested
    # actual_harvested = pv_power + battery_charge_w
    
    # Scenario 1: Basic case with PV power, no battery
    excess = calculate_excess_power_mppt(
        pv_power=1000,
        current_max_power=1500,
        consumption=None
    )
    assert excess == 500 # 1500 - (1000 + 0) = 500

    # Scenario 2: With PV power and battery charging
    excess = calculate_excess_power_mppt(
        pv_power=1000,
        current_max_power=1500,
        consumption=None,
        battery_power=200 # Charging
    )
    assert excess == 300 # 1500 - (1000 + 200) = 300

    # Scenario 3: With battery discharging
    excess = calculate_excess_power_mppt(
        pv_power=1000,
        current_max_power=1500,
        consumption=None,
        battery_power=-200 # Discharging
    )
    assert excess == 0 # Discharging guard returns 0

    # Scenario 4: PV power equals max power
    excess = calculate_excess_power_mppt(
        pv_power=1500,
        current_max_power=1500,
        consumption=None
    )
    assert excess == 0 # 1500 - (1500 + 0) = 0

    # Scenario 5: PV power exceeds max power (shouldn't happen in reality)
    excess = calculate_excess_power_mppt(
        pv_power=1600,
        current_max_power=1500,
        consumption=None
    )
    assert excess == 0 # max(1500 - (1600 + 0), 0) = 0


def test_calculate_excess_power_mppt_consistency():
    """Test that both calculation methods give consistent results in similar scenarios."""
    # When consumption equals PV power, both methods should give similar results
    
    # With consumption sensor
    excess_with_consumption = calculate_excess_power_mppt(
        pv_power=1000,
        current_max_power=1500,
        consumption=1000,
        battery_power=200
    )
    
    # Without consumption sensor
    excess_without_consumption = calculate_excess_power_mppt(
        pv_power=1000,
        current_max_power=1500,
        consumption=None,
        battery_power=200
    )
    
    # Both should give the same result when consumption = pv_power
    assert excess_with_consumption == excess_without_consumption == 300 # 1500 - 1000 - 200

def test_calculate_excess_power_parallel():
    """Test the parallel excess power calculation."""

    # Scenario 1: Basic, no passive charging
    excess = calculate_excess_power_parallel(
        pv_power=3000,
        consumption=200,
        battery_power=200,  # Charging, but > 50W
        battery_power_reversed=False,
        configured_reserve=500
    )
    assert excess == 2300  # 3000 - 500 - 200

    # Scenario 2: Passive charging detected
    excess = calculate_excess_power_parallel(
        pv_power=3000,
        consumption=200,
        battery_power=40,  # Charging, < 50W
        battery_power_reversed=False,
        configured_reserve=500
    )
    assert excess == 2760  # 3000 - 40 - 200

    # Scenario 3: Passive charging, but reserve is lower
    excess = calculate_excess_power_parallel(
        pv_power=3000,
        consumption=200,
        battery_power=40,  # Charging, < 50W
        battery_power_reversed=False,
        configured_reserve=30
    )
    assert excess == 2770  # 3000 - 30 - 200

    # Scenario 4: Discharging battery
    excess = calculate_excess_power_parallel(
        pv_power=3000,
        consumption=200,
        battery_power=-1000,  # Discharging
        battery_power_reversed=False,
        configured_reserve=500
    )
    assert excess == 2300  # 3000 - 500 - 200 (passive charging rule doesn't apply)

    # Scenario 5: Reversed polarity
    excess = calculate_excess_power_parallel(
        pv_power=3000,
        consumption=200,
        battery_power=-40,  # Charging, < 50W
        battery_power_reversed=True,
        configured_reserve=500
    )
    assert excess == 2760  # 3000 - 40 - 200