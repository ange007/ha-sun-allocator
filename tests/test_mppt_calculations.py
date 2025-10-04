"""Tests for MPPT algorithm and power calculations."""

import pytest

from custom_components.sun_allocator.core.solar_optimizer import (
    calculate_current_max_power,
    calculate_pmax,
)
from custom_components.sun_allocator.sensor.utils import calculate_excess_power_mppt
from custom_components.sun_allocator.const import (
    PANEL_CONFIG_SERIES,
    PANEL_CONFIG_PARALLEL,
    PANEL_CONFIG_PARALLEL_SERIES,
)


@pytest.mark.parametrize(
    "pv_voltage,pv_power,vmp,imp,expected_range",
    [
        (30.0, 250, 30.0, 8.0, (240, 260)),  # At MPP
        (35.0, 200, 30.0, 8.0, (180, 220)),  # Above MPP
        (25.0, 180, 30.0, 8.0, (170, 190)),  # Below MPP
        (0.0, 0, 30.0, 8.0, (0, 0)),  # No power
    ],
)
async def test_mppt_power_calculation(pv_voltage, pv_power, vmp, imp, expected_range):
    """Test MPPT power calculation accuracy."""
    current_max_power, debug_info = calculate_current_max_power(
        pv_voltage=pv_voltage,
        pv_power=pv_power,
        vmp=vmp,
        imp=imp,
        voc=36.0,
        isc=8.5,
        panel_count=1,
        panel_configuration=PANEL_CONFIG_SERIES,
    )

    assert expected_range[0] <= current_max_power <= expected_range[1]
    assert "calculation_reason" in debug_info


@pytest.mark.parametrize(
    "panel_config,panel_count,expected_multiplier",
    [
        (PANEL_CONFIG_SERIES, 2, 2.0),  # Series: voltage doubles
        (PANEL_CONFIG_PARALLEL, 2, 2.0),  # Parallel: current doubles
        (PANEL_CONFIG_PARALLEL_SERIES, 4, 4.0),  # Both: power quadruples
    ],
)
async def test_panel_configuration_calculations(
    panel_config, panel_count, expected_multiplier
):
    """Test different panel configurations."""
    vmp, imp = 30.0, 8.0
    pmax = calculate_pmax(vmp, imp, panel_count, panel_config)
    expected_pmax = vmp * imp * expected_multiplier
    assert abs(pmax - expected_pmax) < 0.1

@pytest.mark.parametrize(
    "scenario, inputs, expected_excess",
    [
        (
            "Scenario 1: Standard operation, no reserve",
            {
                "current_max_power": 2500,
                "pv_power": 1500,
                "consumption": 900,
                "battery_power": 500,
                "configured_reserve": 0,
            },
            1000,
        ),
        (
            "Scenario 2: Battery charging exceeds reserve",
            {
                "current_max_power": 2500,
                "pv_power": 1500,
                "consumption": 900,
                "battery_power": 700,
                "configured_reserve": 500,
            },
            1200,
        ),
        (
            "Scenario 3a: Battery charging equals reserve",
            {
                "current_max_power": 2500,
                "pv_power": 1500,
                "consumption": 900,
                "battery_power": 500,
                "configured_reserve": 500,
            },
            1000,
        ),
        (
            "Scenario 3b: Battery is full (not charging)",
            {
                "current_max_power": 2500,
                "pv_power": 1500,
                "consumption": 900,
                "battery_power": 0,
                "configured_reserve": 500,
            },
            1000,
        ),
        (
            "No Consumption Sensor: Excess is just untapped power",
            {
                "current_max_power": 2500,
                "pv_power": 1500,
                "consumption": None,  # No sensor
                "battery_power": 500,
                "configured_reserve": 0,
            },
            1000,
        ),
        (
            "Battery Discharging: No excess power available",
            {
                "current_max_power": 2500,
                "pv_power": 500,
                "consumption": 1000,
                "battery_power": -500,  # Discharging
                "configured_reserve": 0,
            },
            0,
        ),
        (
            "High PV, Low Consumption: Untapped is the limit",
            {
                "current_max_power": 2500,
                "pv_power": 2400, # Near max
                "consumption": 100,
                "battery_power": 100,
                "configured_reserve": 0,
            },
            100, # min(untapped=100, real_excess=2300)
        ),
    ],
)
async def test_excess_power_scenarios(scenario, inputs, expected_excess):
    """Test calculate_excess_power_mppt with various real-world scenarios."""
    excess = calculate_excess_power_mppt(**inputs)
    assert excess == pytest.approx(
        expected_excess
    ), f"Failed scenario: {scenario}"