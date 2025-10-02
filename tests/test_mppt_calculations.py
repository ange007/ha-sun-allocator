"""Tests for MPPT algorithm and power calculations."""

import pytest

from custom_components.sun_allocator.core.solar_optimizer import (
    calculate_current_max_power,
    calculate_pmax,
)
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
