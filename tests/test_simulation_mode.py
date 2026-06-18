"""Tests for debug simulation mode in the base sensor.

Simulation replaces the live PV readings wholesale, and replaces the
consumption / battery-power / SOC readings only when their individual override
toggle is on — so each real sensor can be kept or overridden independently.
"""

from unittest.mock import MagicMock

from custom_components.sun_allocator.const import (
    CONF_CONSUMPTION,
    CONF_BATTERY_POWER,
    CONF_BATTERY_SOC_SENSOR,
    CONF_MPPT_INPUTS,
    CONF_SIM_ENABLED,
    CONF_SIM_PV_POWER,
    CONF_SIM_PV_VOLTAGE,
    CONF_SIM_CONSUMPTION,
    CONF_SIM_BATTERY_POWER,
    CONF_SIM_BATTERY_SOC,
    CONF_SIM_OVERRIDE_CONSUMPTION,
    CONF_SIM_OVERRIDE_BATTERY_POWER,
    CONF_SIM_OVERRIDE_BATTERY_SOC,
)
from custom_components.sun_allocator.sensor.sensors.base import (
    BaseSunAllocatorSensor,
)


def _sensor(config):
    """Build a minimal base-sensor instance with no real shared sensors wired."""
    class _Stub(BaseSunAllocatorSensor):
        def _calculate_value(self, **_kwargs):  # pragma: no cover
            return 0.0

    sensor = _Stub.__new__(_Stub)
    sensor._hass = MagicMock()
    sensor._config = config
    # No real shared sensors → real reads short-circuit to defaults (0/0/None).
    sensor._consumption = None
    sensor._battery_power = None
    sensor._battery_soc_sensor = None
    sensor._mppt_inputs = list(config.get(CONF_MPPT_INPUTS, []))
    return sensor


def test_sim_disabled_returns_real_defaults():
    vals = _sensor({})._get_sensor_values()
    assert vals[CONF_CONSUMPTION] == 0.0
    assert vals[CONF_BATTERY_POWER] == 0.0
    assert vals[CONF_BATTERY_SOC_SENSOR] is None


def test_sim_enabled_but_no_overrides_keeps_real_values():
    """sim_enabled alone must not touch consumption/battery/SOC — only PV."""
    vals = _sensor({
        CONF_SIM_ENABLED: True,
        CONF_SIM_CONSUMPTION: 999,
        CONF_SIM_BATTERY_POWER: 888,
        CONF_SIM_BATTERY_SOC: 77,
    })._get_sensor_values()
    assert vals[CONF_CONSUMPTION] == 0.0
    assert vals[CONF_BATTERY_POWER] == 0.0
    assert vals[CONF_BATTERY_SOC_SENSOR] is None


def test_sim_override_consumption_only():
    vals = _sensor({
        CONF_SIM_ENABLED: True,
        CONF_SIM_OVERRIDE_CONSUMPTION: True,
        CONF_SIM_CONSUMPTION: 250,
    })._get_sensor_values()
    assert vals[CONF_CONSUMPTION] == 250.0
    assert vals[CONF_BATTERY_POWER] == 0.0  # not overridden
    assert vals[CONF_BATTERY_SOC_SENSOR] is None  # not overridden


def test_sim_override_all_fields():
    vals = _sensor({
        CONF_SIM_ENABLED: True,
        CONF_SIM_OVERRIDE_CONSUMPTION: True,
        CONF_SIM_CONSUMPTION: 200,
        CONF_SIM_OVERRIDE_BATTERY_POWER: True,
        CONF_SIM_BATTERY_POWER: -150,  # discharging
        CONF_SIM_OVERRIDE_BATTERY_SOC: True,
        CONF_SIM_BATTERY_SOC: 65,
    })._get_sensor_values()
    assert vals[CONF_CONSUMPTION] == 200.0
    assert vals[CONF_BATTERY_POWER] == -150.0  # negative passes through (discharge)
    assert vals[CONF_BATTERY_SOC_SENSOR] == 65.0


def test_sim_mppt_readings_split_power_evenly():
    """sim_pv_power is the total; it is divided evenly across configured trackers."""
    sensor = _sensor({
        CONF_SIM_ENABLED: True,
        CONF_SIM_PV_POWER: 1000,
        CONF_SIM_PV_VOLTAGE: 120,
        CONF_MPPT_INPUTS: [{}, {}],  # two trackers
    })
    readings = sensor._get_mppt_readings()
    assert len(readings) == 2
    assert readings[0]["pv_power"] == 500.0
    assert readings[1]["pv_power"] == 500.0
    assert readings[0]["pv_voltage"] == 120.0
