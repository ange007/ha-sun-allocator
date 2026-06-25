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


# --- Pmax clamp + near-Voc damping (real-data audit fixes) ------------------

_PANEL = dict(vmp=44.3, imp=10.05, voc=52.6, isc=10.71)


def _cmax(pv_voltage, pv_power, panel_count=10,
          panel_configuration=PANEL_CONFIG_SERIES):
    return calculate_current_max_power(
        pv_voltage=pv_voltage, pv_power=pv_power, panel_count=panel_count,
        panel_configuration=panel_configuration, **_PANEL,
    )


def test_current_max_power_never_exceeds_pmax():
    """current_max_power must never exceed the nameplate Pmax (no >Pmax overshoot)."""
    from custom_components.sun_allocator.core.solar_optimizer import calculate_pmax
    pmax = calculate_pmax(_PANEL["vmp"], _PANEL["imp"], 10, PANEL_CONFIG_SERIES)
    vmp_arr = _PANEL["vmp"] * 10
    voc_arr = _PANEL["voc"] * 10
    for frac in (1.02, 1.05, 1.1, 1.13, 1.16):
        v = vmp_arr * frac
        if v >= voc_arr:
            continue
        cmax, _ = _cmax(v, 200.0)
        assert cmax <= pmax + 0.5, f"overshoot at v={v:.0f}: {cmax} > pmax {pmax}"


def test_near_voc_small_voltage_delta_is_damped():
    """A few volts in the high-voltage/low-power regime must not swing
    current_max_power by a large factor (real data showed ~2.6x)."""
    vmp_arr = _PANEL["vmp"] * 10  # 443V
    # Two close operating points with similar tiny power (curtailed panel).
    c1, _ = _cmax(vmp_arr * 1.12, 240.0)
    c2, _ = _cmax(vmp_arr * 1.14, 238.0)
    hi, lo = max(c1, c2), max(1.0, min(c1, c2))
    assert hi / lo < 2.0, f"high-V jump too large: {c1} vs {c2}"


def test_below_mpp_unchanged_regression():
    """Below/at MPP path keeps the floor invariant (cmax >= pv_power)."""
    cmax, info = _cmax(_PANEL["vmp"] * 10 * 0.9, 1500.0)
    assert cmax >= 1500.0
    assert "MPP" in info["calculation_reason"]
