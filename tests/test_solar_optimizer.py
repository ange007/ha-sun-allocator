"""Tests for solar_optimizer guards against degenerate inputs."""

import logging
import math

from custom_components.sun_allocator.const import PANEL_CONFIG_SERIES
from custom_components.sun_allocator.core import solar_optimizer
from custom_components.sun_allocator.core.solar_optimizer import (
    calculate_current_max_power,
    calculate_relative_voltage,
)


def test_zero_pv_power_returns_zero():
    result, info = calculate_current_max_power(
        pv_voltage=200.0, pv_power=0.0, vmp=30.0, imp=8.0, voc=36.0, isc=8.5,
        panel_count=1, panel_configuration=PANEL_CONFIG_SERIES,
    )
    assert result == 0.0
    assert info["calculation_reason"] == "PV power is zero or negative"


def test_zero_vmp_uses_fallback_voc_ratio(caplog):
    """vmp=0 must not crash; voc_ratio should fall back instead of div-by-zero."""
    with caplog.at_level(logging.WARNING):
        result, info = calculate_current_max_power(
            pv_voltage=200.0, pv_power=100.0, vmp=0.0, imp=8.0, voc=36.0, isc=8.5,
            panel_count=1, panel_configuration=PANEL_CONFIG_SERIES,
        )
    # Result is finite; integration shouldn't blow up.
    assert math.isfinite(result)
    # Reason captures the invalid-vmp branch.
    assert info["calculation_reason"] == "Invalid voltage or Vmp"


def test_negative_voc_falls_back(caplog):
    """A negative voc/vmp ratio (sensor glitch) must trigger the fallback warning."""
    with caplog.at_level(logging.WARNING):
        _, info = calculate_current_max_power(
            pv_voltage=20.0, pv_power=50.0, vmp=30.0, imp=8.0, voc=-1.0, isc=8.5,
            panel_count=1, panel_configuration=PANEL_CONFIG_SERIES,
        )
    # voc_ratio gets recalculated from negative voc, falls back to default 1.2.
    assert info["voc_ratio"] == solar_optimizer._DEFAULT_VOC_RATIO_FALLBACK
    assert any("non-finite" in rec.message or "fall" in rec.message.lower() for rec in caplog.records)


def test_calculate_relative_voltage_zero_vmp():
    """Division-by-zero guard: vmp <= 0 must return 0 instead of raising."""
    assert calculate_relative_voltage(100.0, 0.0, 1, PANEL_CONFIG_SERIES) == 0
    assert calculate_relative_voltage(100.0, -5.0, 1, PANEL_CONFIG_SERIES) == 0
