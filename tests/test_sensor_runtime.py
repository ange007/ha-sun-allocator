"""Focused runtime tests for shared sensor calculations."""

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.sun_allocator.const import DOMAIN
from custom_components.sun_allocator.sensor.sensors.base import BaseSunAllocatorSensor
from custom_components.sun_allocator.sensor.sensors.current_max_power import (
    SunAllocatorCurrentMaxPowerSensor,
)
from custom_components.sun_allocator.sensor.sensors.excess import SunAllocatorExcessSensor
from custom_components.sun_allocator.sensor.sensors.power_distribution import (
    SunAllocatorPowerDistributionSensor,
)


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


def test_current_max_sensor_exposes_flat_legacy_mppt_aliases():
    """Flat PV1/PV2 attributes should remain available for Lovelace templates."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {DOMAIN: {"test_entry": {}}}
    config = _build_sensor_config() | {
        "mppt2_enabled": True,
        "panel2_count": 2,
        "panel2_configuration": "parallel",
    }
    current_sensor = SunAllocatorCurrentMaxPowerSensor(hass, config, "test_entry", 1)

    mppt_summary = _build_mppt_summary() | {
        "mppt_count": 2,
        "mppt_inputs": [
            {
                "id": "mppt1",
                "name": "MPPT 1",
                "pv_power": 120.0,
                "pv_voltage": 35.0,
                "pv_current": 3.4,
                "current_max_power": 200.0,
                "untapped_power": 80.0,
                "vmp": 36.0,
                "imp": 8.0,
                "voc": 44.0,
                "isc": 8.5,
                "panel_count": 1,
                "panel_configuration": "series",
                "light_factor": 1.0,
                "relative_voltage": 1.1,
                "voc_ratio": 1.0,
                "calculation_reason": "Test",
                "energy_harvesting_possible": True,
            },
            {
                "id": "mppt2",
                "name": "MPPT 2",
                "pv_power": 240.0,
                "pv_voltage": 37.5,
                "pv_current": 6.4,
                "current_max_power": 310.0,
                "untapped_power": 70.0,
                "vmp": 36.2,
                "imp": 8.4,
                "voc": 44.5,
                "isc": 8.9,
                "panel_count": 2,
                "panel_configuration": "parallel",
                "light_factor": 0.95,
                "relative_voltage": 1.03,
                "voc_ratio": 0.98,
                "calculation_reason": "Test MPPT 2",
                "energy_harvesting_possible": True,
            },
        ],
    }
    with (
        patch.object(BaseSunAllocatorSensor, "_get_sensor_values", return_value=_build_sensor_values()),
        patch.object(BaseSunAllocatorSensor, "_get_panel_parameters", return_value=_build_panel_params()),
        patch.object(BaseSunAllocatorSensor, "_get_mppt_config", return_value={"curve_factor_k": 0.2, "efficiency_correction_factor": 1.05, "min_inverter_voltage": 100.0}),
        patch.object(BaseSunAllocatorSensor, "_get_temperature_compensation", return_value=None),
        patch.object(BaseSunAllocatorSensor, "_calculate_mppt_summary", return_value=mppt_summary),
    ):
        assert current_sensor.native_value == 200.0

    attrs = current_sensor.extra_state_attributes
    assert attrs["pv1_power"] == 120.0
    assert attrs["pv1_voltage"] == 35.0
    assert attrs["pv1_current"] == 3.4
    assert attrs["pv2_power"] == 240.0
    assert attrs["pv2_voltage"] == 37.5
    assert attrs["pv2_current"] == 6.4
    assert attrs["pv2_current_max_power"] == 310.0


def test_power_distribution_dispatch_updates_cached_state_without_force_refresh():
    """Dispatcher updates should defer writes to the next loop tick."""
    hass = MagicMock(spec=HomeAssistant)
    hass.loop = MagicMock()
    hass.data = {
        DOMAIN: {
            "test_entry": {
                "config": {"devices": []},
                "device_status": {},
                "device_filter_reasons": {},
                "power_distribution": {
                    "total_power": 500.0,
                    "remaining_power": 150.0,
                    "allocated_power": 350.0,
                    "allocation": {},
                },
            }
        }
    }
    sensor = SunAllocatorPowerDistributionSensor(hass, "test_entry", 1)
    sensor.async_write_ha_state = MagicMock()
    sensor.async_schedule_update_ha_state = MagicMock()

    sensor._handle_dispatch_update()

    assert sensor.native_value == 350.0
    assert sensor.extra_state_attributes["allocated_power"] == 350.0
    sensor.async_write_ha_state.assert_not_called()
    sensor.async_schedule_update_ha_state.assert_not_called()
    hass.loop.call_soon.assert_called_once()

    flush_callback = hass.loop.call_soon.call_args.args[0]
    flush_callback()

    sensor.async_write_ha_state.assert_called_once_with()


def test_power_distribution_dispatch_coalesces_multiple_updates_until_flush():
    """Repeated dispatcher signals before the scheduled flush should collapse into one write."""
    hass = MagicMock(spec=HomeAssistant)
    hass.loop = MagicMock()
    hass.data = {
        DOMAIN: {
            "test_entry": {
                "config": {"devices": []},
                "device_status": {},
                "device_filter_reasons": {},
                "power_distribution": {
                    "total_power": 500.0,
                    "remaining_power": 150.0,
                    "allocated_power": 350.0,
                    "allocation": {},
                },
            }
        }
    }
    sensor = SunAllocatorPowerDistributionSensor(hass, "test_entry", 1)
    sensor.async_write_ha_state = MagicMock()

    sensor._handle_dispatch_update()
    sensor._handle_dispatch_update()

    hass.loop.call_soon.assert_called_once()
    flush_callback = hass.loop.call_soon.call_args.args[0]
    flush_callback()

    sensor.async_write_ha_state.assert_called_once_with()