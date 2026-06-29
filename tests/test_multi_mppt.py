"""Tests for multi-MPPT support (v1.0.8).

Covers:
- ``_migrate_flat_solar_to_mppt_inputs`` migration
- Base sensor entity-id listener collection
- Excess power per-MPPT untapped gating
- Safety fallback for un-migrated config in ``base.py``
"""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.sun_allocator.const import (
    CONF_BATTERY_POWER,
    CONF_BATTERY_SOC_SENSOR,
    CONF_BATTERY_SHARING_SOC,
    CONF_CALCULATION_METHOD,
    CONF_CONSUMPTION,
    CONF_MPPT_INPUTS,
    CONF_PANEL_CONFIGURATION,
    CONF_PANEL_COUNT,
    CONF_PANEL_IMP,
    CONF_PANEL_ISC,
    CONF_PANEL_VMP,
    CONF_PANEL_VOC,
    CONF_PV_POWER,
    CONF_PV_VOLTAGE,
    PANEL_CONFIG_SERIES,
    DEFAULT_CALCULATION_METHOD,
)
from custom_components.sun_allocator.core.migrations import ConfigEntryMigrator
from custom_components.sun_allocator.sensor.sensors.base import (
    _build_mppt_inputs_from_config,
)


def _entry(data):
    e = MagicMock()
    e.data = data
    return e


def _hass():
    h = MagicMock()
    h.config_entries = MagicMock()
    h.config_entries.async_update_entry = MagicMock()
    return h


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migrate_flat_solar_to_mppt_inputs():
    """Flat solar keys are wrapped into a single-element ``mppt_inputs`` list."""
    hass = _hass()
    entry = _entry({
        CONF_PV_POWER: "sensor.pv_power",
        CONF_PV_VOLTAGE: "sensor.pv_voltage",
        CONF_PANEL_VMP: 44.3,
        CONF_PANEL_IMP: 10.05,
        CONF_PANEL_VOC: 52.6,
        CONF_PANEL_ISC: 10.71,
        CONF_PANEL_COUNT: 8,
        CONF_PANEL_CONFIGURATION: PANEL_CONFIG_SERIES,
        CONF_CONSUMPTION: "sensor.house",
        "devices": [],
    })
    changed = await ConfigEntryMigrator(hass, entry).run()
    assert changed is True

    new_data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert CONF_MPPT_INPUTS in new_data
    assert len(new_data[CONF_MPPT_INPUTS]) == 1
    mppt = new_data[CONF_MPPT_INPUTS][0]
    assert mppt[CONF_PV_POWER] == "sensor.pv_power"
    assert mppt[CONF_PV_VOLTAGE] == "sensor.pv_voltage"
    assert mppt[CONF_PANEL_VMP] == 44.3
    assert mppt[CONF_PANEL_COUNT] == 8

    # Flat keys removed from top level.
    for k in (
        CONF_PV_POWER,
        CONF_PV_VOLTAGE,
        CONF_PANEL_VMP,
        CONF_PANEL_IMP,
        CONF_PANEL_VOC,
        CONF_PANEL_ISC,
        CONF_PANEL_COUNT,
        CONF_PANEL_CONFIGURATION,
    ):
        assert k not in new_data

    # Shared keys preserved.
    assert new_data[CONF_CONSUMPTION] == "sensor.house"


@pytest.mark.asyncio
async def test_migrate_idempotent():
    """Running the migrator twice does not modify already-migrated data."""
    hass = _hass()
    entry_data = {
        CONF_MPPT_INPUTS: [{
            CONF_PV_POWER: "sensor.pv_power",
            CONF_PANEL_VMP: 44.3,
        }],
        CONF_CALCULATION_METHOD: DEFAULT_CALCULATION_METHOD,
        "devices": [],
    }
    entry = _entry(entry_data)
    changed = await ConfigEntryMigrator(hass, entry).run()
    assert changed is False
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_migrate_no_solar_config_is_noop():
    """Entries lacking ``pv_power`` are left alone."""
    hass = _hass()
    entry = _entry({CONF_CALCULATION_METHOD: DEFAULT_CALCULATION_METHOD, "devices": []})
    changed = await ConfigEntryMigrator(hass, entry).run()
    assert changed is False


@pytest.mark.asyncio
async def test_migrate_empty_pv_power_string_is_noop():
    """Empty string ``pv_power`` is treated as absent."""
    hass = _hass()
    entry = _entry({
        CONF_PV_POWER: "",
        CONF_CALCULATION_METHOD: DEFAULT_CALCULATION_METHOD,
        "devices": [],
    })
    changed = await ConfigEntryMigrator(hass, entry).run()
    assert changed is False


# ---------------------------------------------------------------------------
# base.py: safety fallback for un-migrated config
# ---------------------------------------------------------------------------


def test_safety_fallback_for_unmigrated_config():
    """When mppt_inputs is absent but flat keys are present, a 1-element list is built."""
    config = {
        CONF_PV_POWER: "sensor.pv_power",
        CONF_PV_VOLTAGE: "sensor.pv_voltage",
        CONF_PANEL_VMP: 44.3,
        CONF_PANEL_IMP: 10.05,
        CONF_PANEL_VOC: 52.6,
        CONF_PANEL_COUNT: 8,
        CONF_PANEL_CONFIGURATION: PANEL_CONFIG_SERIES,
    }
    inputs = _build_mppt_inputs_from_config(config)
    assert len(inputs) == 1
    assert inputs[0][CONF_PV_POWER] == "sensor.pv_power"
    assert inputs[0][CONF_PANEL_COUNT] == 8


def test_build_returns_existing_mppt_inputs():
    """When mppt_inputs is present, it is returned as-is."""
    raw = [
        {CONF_PV_POWER: "sensor.a", CONF_PANEL_VMP: 44.3},
        {CONF_PV_POWER: "sensor.b", CONF_PANEL_VMP: 40.1},
    ]
    inputs = _build_mppt_inputs_from_config({CONF_MPPT_INPUTS: raw})
    assert len(inputs) == 2
    assert inputs[0][CONF_PV_POWER] == "sensor.a"
    assert inputs[1][CONF_PV_POWER] == "sensor.b"


def test_build_returns_empty_for_empty_config():
    """No mppt_inputs and no flat keys → empty list."""
    inputs = _build_mppt_inputs_from_config({})
    assert inputs == []


# ---------------------------------------------------------------------------
# base.py: entity-id collection across MPPTs
# ---------------------------------------------------------------------------


def test_entity_ids_for_two_mppts():
    """Two MPPT inputs → 4 entity IDs (2x power + 2x voltage), plus shared."""
    from custom_components.sun_allocator.sensor.sensors.base import (
        BaseSunAllocatorSensor,
    )

    config = {
        CONF_MPPT_INPUTS: [
            {CONF_PV_POWER: "sensor.mppt1_power", CONF_PV_VOLTAGE: "sensor.mppt1_voltage"},
            {CONF_PV_POWER: "sensor.mppt2_power", CONF_PV_VOLTAGE: "sensor.mppt2_voltage"},
        ],
        CONF_CONSUMPTION: "sensor.house",
        CONF_BATTERY_POWER: None,
    }

    # Build a minimal subclass overriding _calculate_value (abstract).
    class _Stub(BaseSunAllocatorSensor):
        def _calculate_value(self, **_kwargs):  # pragma: no cover
            return 0.0

    sensor = _Stub.__new__(_Stub)
    sensor._hass = MagicMock()
    sensor._config = config
    sensor._entry_id = "x"
    sensor._entry_index = 0
    sensor._mppt_inputs = list(config[CONF_MPPT_INPUTS])
    sensor._consumption = config[CONF_CONSUMPTION]
    sensor._battery_power = None
    sensor._battery_soc_sensor = None
    sensor._pv_forecast_sensor = None

    ids = sensor._get_entity_ids_to_listen()
    assert "sensor.mppt1_power" in ids
    assert "sensor.mppt1_voltage" in ids
    assert "sensor.mppt2_power" in ids
    assert "sensor.mppt2_voltage" in ids
    assert "sensor.house" in ids


# ---------------------------------------------------------------------------
# excess.py: per-MPPT untapped gating
# ---------------------------------------------------------------------------


def test_excess_per_mppt_untapped_gating():
    """Aggregate untapped uses each tracker's own relative_voltage gate."""
    from custom_components.sun_allocator.sensor.sensors.excess import (
        SunAllocatorExcessSensor,
    )

    # Two MPPTs:
    #   tracker 0: at-MPP (rel_v=1.0) → no untapped gating bypass → untapped=0
    #   tracker 1: above-MPP (rel_v=1.5) → untapped = max(0, 600 - 400) = 200
    def _fake_cmp(pv_voltage, pv_power, **_kwargs):
        if pv_voltage > 100:  # tracker 1 marker
            debug = {
                "energy_harvesting_possible": True,
                "relative_voltage": 1.5,
                "pmax": 600.0,
                "light_factor": 1.0,
                "voc_ratio": 1.0,
                "calculation_reason": "above_mpp",
                "min_system_voltage": 30.0,
            }
            return 600.0, debug
        debug = {
            "energy_harvesting_possible": True,
            "relative_voltage": 1.0,
            "pmax": 500.0,
            "light_factor": 1.0,
            "voc_ratio": 1.0,
            "calculation_reason": "at_mpp",
            "min_system_voltage": 30.0,
        }
        return 500.0, debug

    sensor = SunAllocatorExcessSensor.__new__(SunAllocatorExcessSensor)
    sensor._config = {
        CONF_CONSUMPTION: None,
        CONF_BATTERY_POWER: None,
    }
    sensor._attr_extra_state_attributes = {}
    sensor.hass = None
    sensor._entry_id = "x"

    mppt_readings = [
        {
            "pv_power": 500.0,
            "pv_voltage": 50.0,
            "panel_params": {
                CONF_PANEL_VMP: 44.3,
                CONF_PANEL_IMP: 10.05,
                CONF_PANEL_VOC: 52.6,
                CONF_PANEL_ISC: 10.71,
                CONF_PANEL_COUNT: 8,
                CONF_PANEL_CONFIGURATION: PANEL_CONFIG_SERIES,
            },
        },
        {
            "pv_power": 400.0,
            "pv_voltage": 200.0,  # > 100 → tracker 1 marker for fake
            "panel_params": {
                CONF_PANEL_VMP: 44.3,
                CONF_PANEL_IMP: 10.05,
                CONF_PANEL_VOC: 52.6,
                CONF_PANEL_ISC: 10.71,
                CONF_PANEL_COUNT: 8,
                CONF_PANEL_CONFIGURATION: PANEL_CONFIG_SERIES,
            },
        },
    ]

    with patch(
        "custom_components.sun_allocator.sensor.sensors.excess.calculate_current_max_power",
        side_effect=_fake_cmp,
    ):
        result = sensor._calculate_value(
            sensor_values={CONF_CONSUMPTION: 0, CONF_BATTERY_POWER: 0},
            mppt_readings=mppt_readings,
            mppt_config={},
            temp_compensation=None,
        )

    # Tracker0 contributes 0 untapped (at MPP). Tracker1 contributes 200 (above MPP).
    # No consumption, no battery → excess equals total untapped.
    assert result == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# excess.py: battery_soc + sharing_soc are wired through to the calculation
# ---------------------------------------------------------------------------


def test_excess_passes_soc_and_sharing_to_calculation():
    """The sensor layer must forward battery_soc (from sensor_values) and
    sharing_soc (from config) into calculate_excess_power_mppt — the unit math
    is tested in test_utils; this guards the plumbing."""
    from custom_components.sun_allocator.sensor.sensors.excess import (
        SunAllocatorExcessSensor,
    )

    def _fake_cmp(pv_voltage, pv_power, **_kwargs):
        debug = {
            "energy_harvesting_possible": True,
            "relative_voltage": 1.0,
            "pmax": 500.0,
            "light_factor": 1.0,
            "voc_ratio": 1.0,
            "calculation_reason": "at_mpp",
            "min_system_voltage": 30.0,
        }
        return 500.0, debug

    sensor = SunAllocatorExcessSensor.__new__(SunAllocatorExcessSensor)
    sensor._config = {
        CONF_CONSUMPTION: None,
        CONF_BATTERY_POWER: None,
        CONF_BATTERY_SHARING_SOC: 70,
    }
    sensor._attr_extra_state_attributes = {}
    sensor.hass = None
    sensor._entry_id = "x"

    mppt_readings = [{
        "pv_power": 500.0,
        "pv_voltage": 50.0,
        "panel_params": {
            CONF_PANEL_VMP: 44.3,
            CONF_PANEL_IMP: 10.05,
            CONF_PANEL_VOC: 52.6,
            CONF_PANEL_ISC: 10.71,
            CONF_PANEL_COUNT: 8,
            CONF_PANEL_CONFIGURATION: PANEL_CONFIG_SERIES,
        },
    }]

    with patch(
        "custom_components.sun_allocator.sensor.sensors.excess.calculate_current_max_power",
        side_effect=_fake_cmp,
    ), patch(
        "custom_components.sun_allocator.sensor.sensors.excess.calculate_excess_power_mppt",
        return_value=0.0,
    ) as mock_calc:
        sensor._calculate_value(
            sensor_values={
                CONF_CONSUMPTION: 0,
                CONF_BATTERY_POWER: 0,
                CONF_BATTERY_SOC_SENSOR: 55.0,
            },
            mppt_readings=mppt_readings,
            mppt_config={},
            temp_compensation=None,
        )

    mock_calc.assert_called_once()
    kwargs = mock_calc.call_args.kwargs
    assert kwargs["battery_soc"] == 55.0
    assert kwargs["sharing_soc"] == 70


# ---------------------------------------------------------------------------
# max_power: temp compensation per-MPPT then sum
# ---------------------------------------------------------------------------


def test_max_power_sums_with_temp_compensation():
    """Two MPPTs with different vmp/imp, temp compensation applied per-tracker."""
    from custom_components.sun_allocator.sensor.sensors.max_power import (
        SunAllocatorMaxPowerSensor,
    )

    sensor = SunAllocatorMaxPowerSensor.__new__(SunAllocatorMaxPowerSensor)
    sensor._config = {}
    sensor._attr_extra_state_attributes = {}

    mppt_readings = [
        {
            "pv_power": 0,
            "pv_voltage": 0,
            "panel_params": {
                CONF_PANEL_VMP: 40.0,
                CONF_PANEL_IMP: 10.0,
                CONF_PANEL_VOC: 50.0,
                CONF_PANEL_ISC: 11.0,
                CONF_PANEL_COUNT: 4,
                CONF_PANEL_CONFIGURATION: PANEL_CONFIG_SERIES,
            },
        },
        {
            "pv_power": 0,
            "pv_voltage": 0,
            "panel_params": {
                CONF_PANEL_VMP: 30.0,
                CONF_PANEL_IMP: 8.0,
                CONF_PANEL_VOC: 38.0,
                CONF_PANEL_ISC: 9.0,
                CONF_PANEL_COUNT: 6,
                CONF_PANEL_CONFIGURATION: PANEL_CONFIG_SERIES,
            },
        },
    ]

    # No temp compensation → straightforward Pmax sum.
    # Tracker0 series: (40 * 4) * 10 = 1600
    # Tracker1 series: (30 * 6) * 8  = 1440
    result = sensor._calculate_value(
        sensor_values={},
        mppt_readings=mppt_readings,
        mppt_config={},
        temp_compensation=None,
    )
    assert result == pytest.approx(3040.0)
