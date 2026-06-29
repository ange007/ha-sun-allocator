"""Tests that the excess sensor dispatches to the right calculation function
based on the configured ``calculation_method`` and publishes the method +
curtailment attributes.

The two excess functions and the MPPT-curve function are monkeypatched with
sentinels so the test isolates the branch logic from the (separately tested)
formulas.
"""

from custom_components.sun_allocator.sensor.sensors import excess as excess_mod
from custom_components.sun_allocator.sensor.sensors.excess import (
    SunAllocatorExcessSensor,
)
from custom_components.sun_allocator.const import (
    CONF_CALCULATION_METHOD,
    DEFAULT_CALCULATION_METHOD,
    CALC_METHOD_MPPT,
    CALC_METHOD_EXPORT,
    CONF_CONSUMPTION,
    CONF_BATTERY_POWER,
    CONF_BATTERY_SOC_SENSOR,
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

_MPPT_SENTINEL = 200.0
_EXPORT_SENTINEL = 0.0

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
        CONF_PANEL_VMP: 30.0,
        CONF_PANEL_IMP: 8.0,
        CONF_PANEL_VOC: 37.0,
        CONF_PANEL_ISC: 8.5,
        CONF_PANEL_COUNT: 10,
        CONF_PANEL_CONFIGURATION: "series",
    },
}]

_SENSOR_VALUES = {
    CONF_CONSUMPTION: 0.0,
    CONF_BATTERY_POWER: 0.0,
    CONF_BATTERY_SOC_SENSOR: None,
}


def _run(monkeypatch, method):
    monkeypatch.setattr(
        excess_mod, "calculate_current_max_power", lambda **_: (1200.0, dict(_DEBUG))
    )
    monkeypatch.setattr(
        excess_mod, "calculate_excess_power_mppt", lambda **_: _MPPT_SENTINEL
    )
    monkeypatch.setattr(
        excess_mod, "calculate_excess_power_export", lambda **_: _EXPORT_SENTINEL
    )
    monkeypatch.setattr(excess_mod, "detect_curtailment", lambda **_: True)

    s = SunAllocatorExcessSensor.__new__(SunAllocatorExcessSensor)
    s._config = {} if method is None else {CONF_CALCULATION_METHOD: method}
    s._attr_extra_state_attributes = {}
    s.hass = None
    s._entry_id = None
    result = s._calculate_value(
        sensor_values=dict(_SENSOR_VALUES),
        mppt_readings=_READINGS,
        mppt_config={},
        temp_compensation=None,
    )
    return result, s._attr_extra_state_attributes


def test_export_method_uses_export_formula(monkeypatch):
    result, attrs = _run(monkeypatch, CALC_METHOD_EXPORT)
    assert result == _EXPORT_SENTINEL
    assert attrs["calculation_method"] == CALC_METHOD_EXPORT
    assert attrs["curtailment_detected"] is True


def test_mppt_method_uses_mppt_formula(monkeypatch):
    result, attrs = _run(monkeypatch, CALC_METHOD_MPPT)
    assert result == _MPPT_SENTINEL
    assert attrs["calculation_method"] == CALC_METHOD_MPPT


def test_mppt_probe_uses_mppt_formula(monkeypatch):
    # probe publishes the same cautious MPPT value; it acts only in the controller.
    result, attrs = _run(monkeypatch, "mppt_probe")
    assert result == _MPPT_SENTINEL
    assert attrs["calculation_method"] == "mppt_probe"


def test_default_method_is_mppt(monkeypatch):
    result, attrs = _run(monkeypatch, None)
    assert result == _MPPT_SENTINEL
    assert attrs["calculation_method"] == DEFAULT_CALCULATION_METHOD
