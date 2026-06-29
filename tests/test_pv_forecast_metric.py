"""Tests that the optional PV forecast sensor surfaces as diagnostic attributes on
the excess sensor (forecast_potential_w / forecast_untapped_w), and is omitted
when unset. The forecast is metric-only — it must not change the excess value.
"""

from custom_components.sun_allocator.sensor.sensors import excess as excess_mod
from custom_components.sun_allocator.sensor.sensors.excess import (
    SunAllocatorExcessSensor,
)
from custom_components.sun_allocator.const import (
    CONF_CALCULATION_METHOD,
    CALC_METHOD_MPPT,
    CONF_CONSUMPTION,
    CONF_BATTERY_POWER,
    CONF_BATTERY_SOC_SENSOR,
    CONF_PV_FORECAST_SENSOR,
    CONF_PANEL_VMP,
    CONF_PANEL_IMP,
    CONF_PANEL_VOC,
    CONF_PANEL_ISC,
    CONF_PANEL_COUNT,
    CONF_PANEL_CONFIGURATION,
    KEY_ENERGY_HARVESTING_POSSIBLE,
    KEY_RELATIVE_VOLTAGE,
    KEY_LIGHT_FACTOR,
    KEY_VOC_RATIO,
    KEY_PMAX,
    KEY_MIN_SYSTEM_VOLTAGE,
    KEY_CALCULATION_REASON,
)

_DEBUG = {
    KEY_ENERGY_HARVESTING_POSSIBLE: True,
    KEY_RELATIVE_VOLTAGE: 2.0,
    KEY_LIGHT_FACTOR: 0.3,
    KEY_VOC_RATIO: 1.2,
    KEY_PMAX: 4000.0,
    KEY_MIN_SYSTEM_VOLTAGE: 100.0,
    KEY_CALCULATION_REASON: "test",
}

_READINGS = [{
    "pv_power": 1000.0,
    "pv_voltage": 320.0,
    "panel_params": {
        CONF_PANEL_VMP: 30.0, CONF_PANEL_IMP: 8.0, CONF_PANEL_VOC: 37.0,
        CONF_PANEL_ISC: 8.5, CONF_PANEL_COUNT: 10, CONF_PANEL_CONFIGURATION: "series",
    },
}]


def _run(monkeypatch, forecast):
    monkeypatch.setattr(
        excess_mod, "calculate_current_max_power", lambda **_: (1200.0, dict(_DEBUG))
    )
    monkeypatch.setattr(excess_mod, "calculate_excess_power_mppt", lambda **_: 200.0)
    monkeypatch.setattr(excess_mod, "calculate_excess_power_export", lambda **_: 0.0)
    monkeypatch.setattr(excess_mod, "detect_curtailment", lambda **_: False)

    s = SunAllocatorExcessSensor.__new__(SunAllocatorExcessSensor)
    s._config = {CONF_CALCULATION_METHOD: CALC_METHOD_MPPT}
    s._attr_extra_state_attributes = {}
    s.hass = None
    s._entry_id = None
    sensor_values = {
        CONF_CONSUMPTION: 0.0,
        CONF_BATTERY_POWER: 0.0,
        CONF_BATTERY_SOC_SENSOR: None,
        CONF_PV_FORECAST_SENSOR: forecast,
    }
    result = s._calculate_value(
        sensor_values=sensor_values, mppt_readings=_READINGS,
        mppt_config={}, temp_compensation=None,
    )
    return result, s._attr_extra_state_attributes


def test_forecast_attrs_present_when_configured(monkeypatch):
    # forecast 1500 W, total pv 1000 W → untapped 500 W.
    result, attrs = _run(monkeypatch, 1500.0)
    assert attrs["forecast_potential_w"] == 1500.0
    assert attrs["forecast_untapped_w"] == 500.0
    assert result == 200.0  # excess value unaffected by the forecast


def test_forecast_untapped_clamped_to_zero(monkeypatch):
    # forecast below current pv → untapped clamps to 0.
    _, attrs = _run(monkeypatch, 800.0)
    assert attrs["forecast_potential_w"] == 800.0
    assert attrs["forecast_untapped_w"] == 0.0


def test_forecast_attrs_omitted_when_unset(monkeypatch):
    _, attrs = _run(monkeypatch, None)
    assert "forecast_potential_w" not in attrs
    assert "forecast_untapped_w" not in attrs
