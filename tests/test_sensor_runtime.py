"""Focused runtime tests for shared sensor calculations."""

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.sun_allocator.const import DOMAIN
from custom_components.sun_allocator.sensor.sensors.base import BaseSunAllocatorSensor
from custom_components.sun_allocator.sensor.sensors.current_max_power import (
    SunAllocatorCurrentMaxPowerSensor,
)
from custom_components.sun_allocator.sensor.sensors.excess import SunAllocatorExcessSensor


def _build_sensor_config():
    return {
        "pv_power": "sensor.test_pv_power",
        "pv_voltage": "sensor.test_pv_voltage",
        "vmp": 36.0,
        "imp": 8.0,
        "voc": 44.0,
        "isc": 8.5,
        "panel_count": 1,
        "panel_configuration": "series",
        "curve_factor_k": 0.2,
        "efficiency_correction_factor": 1.05,
        "min_inverter_voltage": 100.0,
    }


def _build_sensor_values():
    return {
        "pv_power": 120.0,
        "pv_voltage": 35.0,
        "pv_current": 3.4,
        "pv2_power": 0.0,
        "pv2_voltage": 0.0,
        "pv2_current": None,
        "consumption": 0.0,
        "battery_power": 0.0,
    }


def _build_panel_params():
    return {
        "vmp": 36.0,
        "imp": 8.0,
        "voc": 44.0,
        "isc": 8.5,
        "panel_count": 1,
        "panel_configuration": "series",
    }


def _build_mppt_summary():
    return {
        "pv_power": 120.0,
        "current_max_power": 200.0,
        "untapped_power": 80.0,
        "mppt_count": 1,
        "mppt_inputs": [{"id": "mppt1", "name": "MPPT 1", "vmp": 36.0, "imp": 8.0}],
        "debug_info": {
            "pmax": 288.0,
            "energy_harvesting_possible": True,
            "min_system_voltage": 100.0,
            "light_factor": 1.0,
            "relative_voltage": 1.1,
            "voc_ratio": 1.0,
            "calculation_reason": "Test",
        },
    }


def test_sensor_cache_shares_source_snapshot_and_mppt_summary():
    """Excess and current-max sensors should reuse the same entry snapshot."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {DOMAIN: {"test_entry": {}}}
    config = _build_sensor_config()
    excess_sensor = SunAllocatorExcessSensor(hass, config, "test_entry", 1)
    current_sensor = SunAllocatorCurrentMaxPowerSensor(hass, config, "test_entry", 1)

    with (
        patch.object(BaseSunAllocatorSensor, "_get_sensor_values", return_value=_build_sensor_values()) as mock_sensor_values,
        patch.object(BaseSunAllocatorSensor, "_get_panel_parameters", return_value=_build_panel_params()),
        patch.object(BaseSunAllocatorSensor, "_get_mppt_config", return_value={"curve_factor_k": 0.2, "efficiency_correction_factor": 1.05, "min_inverter_voltage": 100.0}),
        patch.object(BaseSunAllocatorSensor, "_get_temperature_compensation", return_value=None),
        patch.object(BaseSunAllocatorSensor, "_calculate_mppt_summary", return_value=_build_mppt_summary()) as mock_mppt_summary,
        patch("custom_components.sun_allocator.sensor.sensors.excess.calculate_excess_power_mppt", return_value=80.0),
        patch("custom_components.sun_allocator.sensor.sensors.excess.calculate_usage_percentage", return_value=60.0),
    ):
        assert excess_sensor.native_value == 80.0
        assert current_sensor.native_value == 200.0

    assert mock_sensor_values.call_count == 1
    assert mock_mppt_summary.call_count == 1


def test_excess_sensor_journal_is_deduplicated_for_identical_payload():
    """Repeated identical excess reads should not spam the journal."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {DOMAIN: {"test_entry": {}}}
    config = _build_sensor_config()
    excess_sensor = SunAllocatorExcessSensor(hass, config, "test_entry", 1)

    with (
        patch.object(BaseSunAllocatorSensor, "_get_sensor_values", return_value=_build_sensor_values()),
        patch.object(BaseSunAllocatorSensor, "_get_panel_parameters", return_value=_build_panel_params()),
        patch.object(BaseSunAllocatorSensor, "_get_mppt_config", return_value={"curve_factor_k": 0.2, "efficiency_correction_factor": 1.05, "min_inverter_voltage": 100.0}),
        patch.object(BaseSunAllocatorSensor, "_get_temperature_compensation", return_value=None),
        patch.object(BaseSunAllocatorSensor, "_calculate_mppt_summary", return_value=_build_mppt_summary()),
        patch("custom_components.sun_allocator.sensor.sensors.excess.calculate_excess_power_mppt", return_value=80.0),
        patch("custom_components.sun_allocator.sensor.sensors.excess.calculate_usage_percentage", return_value=60.0),
        patch("custom_components.sun_allocator.sensor.sensors.excess.journal_event") as mock_journal_event,
    ):
        assert excess_sensor.native_value == 80.0
        assert excess_sensor.native_value == 80.0

    mock_journal_event.assert_called_once()