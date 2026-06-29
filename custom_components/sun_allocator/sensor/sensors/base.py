"""Base sensor class for Sun Allocator sensors."""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Tuple

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.typing import StateType

from ...core.logger import log_error, log_warning, journal_event
from ...core.solar_optimizer import get_panel_parameters_with_fallbacks
from ..utils import (
    get_sensor_state_safely,
    is_reading_stale,
    get_temperature_compensation_data,
    create_sensor_attributes,
    setup_sensor_listeners,
    cleanup_sensor_listeners,
    get_mppt_algorithm_config,
)

from ...const import (
    DOMAIN,
    VERSION,
    CONF_MPPT_INPUTS,
    CONF_PV_POWER,
    CONF_PV_VOLTAGE,
    CONF_CONSUMPTION,
    CONF_BATTERY_POWER,
    CONF_BATTERY_POWER_REVERSED,
    CONF_PV_FORECAST_SENSOR,
    CONF_PANEL_VMP,
    CONF_PANEL_IMP,
    CONF_PANEL_VOC,
    CONF_PANEL_ISC,
    CONF_PANEL_COUNT,
    CONF_PANEL_CONFIGURATION,
    PANEL_CONFIG_SERIES,
    CONF_TEMPERATURE_COMPENSATION_ENABLED,
    CONF_TEMPERATURE_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    DEFAULT_SOC_MAX_AGE_S,
    CONF_SIM_ENABLED,
    CONF_SIM_PV_POWER,
    CONF_SIM_PV_VOLTAGE,
    CONF_SIM_CONSUMPTION,
    CONF_SIM_BATTERY_POWER,
    CONF_SIM_BATTERY_SOC,
    CONF_SIM_OVERRIDE_CONSUMPTION,
    CONF_SIM_OVERRIDE_BATTERY_POWER,
    CONF_SIM_OVERRIDE_BATTERY_SOC,
    DEFAULT_SIM_CONSUMPTION,
    DEFAULT_SIM_BATTERY_POWER,
    DEFAULT_SIM_BATTERY_SOC,
)


def _build_mppt_inputs_from_config(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return ``mppt_inputs`` from config with safety fallback for un-migrated data."""
    raw = config.get(CONF_MPPT_INPUTS)
    if raw:
        return list(raw)
    if config.get(CONF_PV_POWER):
        # Pre-1.0.8 entry that has not been through ConfigEntryMigrator yet.
        return [{
            CONF_PV_POWER: config.get(CONF_PV_POWER),
            CONF_PV_VOLTAGE: config.get(CONF_PV_VOLTAGE),
            CONF_PANEL_VMP: config.get(CONF_PANEL_VMP),
            CONF_PANEL_IMP: config.get(CONF_PANEL_IMP),
            CONF_PANEL_VOC: config.get(CONF_PANEL_VOC),
            CONF_PANEL_ISC: config.get(CONF_PANEL_ISC),
            CONF_PANEL_COUNT: config.get(CONF_PANEL_COUNT, 1),
            CONF_PANEL_CONFIGURATION: config.get(
                CONF_PANEL_CONFIGURATION, PANEL_CONFIG_SERIES
            ),
        }]
    return []


class BaseSunAllocatorSensor(SensorEntity, ABC):
    """Base class for all SunAllocator hub sensors (multi-MPPT aware)."""

    _attr_has_entity_name = True

    # pylint: disable=too-many-instance-attributes
    def __init__(
        self,
        hass: HomeAssistant,
        config: Dict[str, Any],
        entry_id: str,
        entry_index: int,
        name: str,
        unique_id_suffix: str,
        unit_of_measurement: str = "W",
    ):
        """Initialize the base sensor."""
        self._hass = hass
        self._config = config
        self._entry_id = entry_id
        self._entry_index = entry_index

        self._attr_translation_key = name
        self._attr_unique_id = f"{entry_id}_{unique_id_suffix}"
        self._attr_native_unit_of_measurement = unit_of_measurement
        self.entity_id = f"sensor.{DOMAIN}_{entry_id}_{unique_id_suffix}".lower()

        self._mppt_inputs: List[Dict[str, Any]] = _build_mppt_inputs_from_config(config)
        self._consumption = config.get(CONF_CONSUMPTION)
        self._battery_power = config.get(CONF_BATTERY_POWER)
        self._battery_soc_sensor = config.get(CONF_BATTERY_SOC_SENSOR)
        self._pv_forecast_sensor = config.get(CONF_PV_FORECAST_SENSOR)

        self._state = 0.0
        self._attr_extra_state_attributes = self._get_default_attributes()

        self._unsub_listeners = []


    def _get_default_attributes(self) -> Dict[str, Any]:
        """Get default attributes for the sensor."""
        return create_sensor_attributes(
            pv_power=0.0,
            pv_voltage=0.0,
            consumption=0.0,
            battery_power=0.0,
            excess_possible=False,
            energy_harvesting_possible=False,
            current_max_power=0.0,
            usage_percent=0.0,
        )


    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        entry = self._hass.config_entries.async_get_entry(self._entry_id)
        name = entry.title if entry else "SunAllocator"
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=name,
            manufacturer="Sun Allocator",
            model="Solar Excess Controller",
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
        )


    @property
    def should_poll(self) -> bool:
        """Return False as entity pushes updates."""
        return False


    def _should_skip_update(self) -> bool:
        """Hook: return True to suppress this state update (deadband).

        Default never skips. Subclasses (e.g. the excess sensor) may override to
        coalesce sub-threshold fluctuations and cut recorder/listener churn.
        """
        return False


    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        entity_ids = self._get_entity_ids_to_listen()

        @callback
        def _update_sensor(*_):
            """Update the sensor when underlying data changes."""
            # Invalidate the shared snapshot so the next computation re-reads inputs.
            # All hub sensors listen to the same entities; when one input changes,
            # every sensor's listener fires and clears the cache before any of them
            # recompute, so the first to recompute rebuilds the snapshot and the rest
            # reuse it within the same event-loop burst.
            self._invalidate_shared_snapshot()
            # Optional per-sensor deadband: skip the state write (and therefore the
            # recorder row + downstream listeners) when the value has not moved
            # enough to matter. Default hook never skips.
            if self._should_skip_update():
                return
            self.async_schedule_update_ha_state(True)

        setup_sensor_listeners(
            self._hass, entity_ids, _update_sensor, self._unsub_listeners
        )

        self.async_schedule_update_ha_state(True)


    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        cleanup_sensor_listeners(self._unsub_listeners)


    def _get_entity_ids_to_listen(self) -> list:
        """Get list of entity IDs to listen for state changes."""
        entity_ids = []

        for mppt in self._mppt_inputs:
            pv_power = mppt.get(CONF_PV_POWER)
            if pv_power:
                entity_ids.append(pv_power)
            pv_voltage = mppt.get(CONF_PV_VOLTAGE)
            if pv_voltage:
                entity_ids.append(pv_voltage)

        if self._consumption:
            entity_ids.append(self._consumption)

        if self._battery_power:
            entity_ids.append(self._battery_power)

        if self._battery_soc_sensor:
            entity_ids.append(self._battery_soc_sensor)

        if self._pv_forecast_sensor:
            entity_ids.append(self._pv_forecast_sensor)

        if self._config.get(CONF_TEMPERATURE_COMPENSATION_ENABLED, False):
            temp_sensor = self._config.get(CONF_TEMPERATURE_SENSOR)
            if temp_sensor:
                entity_ids.append(temp_sensor)

        return entity_ids


    _BATTERY_SIGN_MIN_SAMPLES = 300

    def _check_battery_sign(self, battery_power: float) -> None:
        """Warn once if the battery power sensor never goes negative while reversal
        is off — a sign that a charge/discharge-magnitude (non-signed) sensor was
        chosen, which skews the excess calculation (the discharge guard can't fire)."""
        if self._config.get(CONF_BATTERY_POWER_REVERSED):
            return
        entry_data = self._hass.data.get(DOMAIN, {}).get(self._entry_id)
        if entry_data is None:
            return
        st = entry_data.setdefault(
            "_battery_sign_check",
            {"samples": 0, "saw_negative": False, "saw_positive": False, "warned": False},
        )
        if st["warned"]:
            return
        if battery_power < 0:
            st["saw_negative"] = True
        elif battery_power > 0:
            st["saw_positive"] = True
        st["samples"] += 1
        if (
            st["samples"] >= self._BATTERY_SIGN_MIN_SAMPLES
            and st["saw_positive"]
            and not st["saw_negative"]
        ):
            st["warned"] = True
            log_warning(
                "Battery power sensor '%s' has only reported values >= 0 over %d "
                "samples. SunAllocator expects a SIGNED bidirectional sensor "
                "(negative = discharging, with 'Reverse Battery Power Values' off). "
                "A charge/discharge-magnitude sensor breaks the discharge guard and "
                "skews excess. Choose a signed sensor or toggle 'Reverse Battery "
                "Power Values'.",
                self._battery_power, st["samples"],
            )

    def _get_sensor_values(self) -> Dict[str, Any]:
        """Read shared sensor values (consumption, battery_power, battery_soc)."""
        consumption = 0.0
        if self._consumption:
            consumption, _ = get_sensor_state_safely(
                self._hass, self._consumption, "Consumption"
            )

        battery_power = 0.0
        if self._battery_power:
            battery_power, battery_ok = get_sensor_state_safely(
                self._hass, self._battery_power, "Battery Power"
            )
            if battery_ok and not self._config.get(CONF_SIM_ENABLED):
                self._check_battery_sign(battery_power)

        # SOC stays None when unconfigured, unavailable or STALE so the reserve
        # modulation fails open (configured reserve as-is) rather than to 0%.
        battery_soc = None
        if self._battery_soc_sensor:
            soc_value, soc_ok = get_sensor_state_safely(
                self._hass, self._battery_soc_sensor, "Battery SOC"
            )
            if soc_ok and not is_reading_stale(
                self._hass, self._battery_soc_sensor, DEFAULT_SOC_MAX_AGE_S
            ):
                battery_soc = soc_value

        # Optional external PV-production forecast (W). Diagnostic only — stays
        # None when unconfigured or unavailable.
        pv_forecast = None
        if self._pv_forecast_sensor:
            fc_value, fc_ok = get_sensor_state_safely(
                self._hass, self._pv_forecast_sensor, "PV Forecast"
            )
            if fc_ok:
                pv_forecast = fc_value

        if self._config.get(CONF_SIM_ENABLED):
            if self._config.get(CONF_SIM_OVERRIDE_CONSUMPTION):
                consumption = float(
                    self._config.get(CONF_SIM_CONSUMPTION, DEFAULT_SIM_CONSUMPTION)
                )
            if self._config.get(CONF_SIM_OVERRIDE_BATTERY_POWER):
                battery_power = float(
                    self._config.get(CONF_SIM_BATTERY_POWER, DEFAULT_SIM_BATTERY_POWER)
                )
            if self._config.get(CONF_SIM_OVERRIDE_BATTERY_SOC):
                battery_soc = float(
                    self._config.get(CONF_SIM_BATTERY_SOC, DEFAULT_SIM_BATTERY_SOC)
                )

        return {
            CONF_CONSUMPTION: consumption,
            CONF_BATTERY_POWER: battery_power,
            CONF_BATTERY_SOC_SENSOR: battery_soc,
            CONF_PV_FORECAST_SENSOR: pv_forecast,
        }


    def _get_mppt_readings(self) -> List[Dict[str, Any]]:
        """Read per-MPPT pv_power, pv_voltage and panel parameters."""
        if self._config.get(CONF_SIM_ENABLED):
            return self._get_simulated_mppt_readings()
        readings: List[Dict[str, Any]] = []
        for mppt in self._mppt_inputs:
            pv_power = 0.0
            if mppt.get(CONF_PV_POWER):
                pv_power, _ = get_sensor_state_safely(
                    self._hass, mppt.get(CONF_PV_POWER), "PV Power"
                )
            pv_voltage = 0.0
            if mppt.get(CONF_PV_VOLTAGE):
                pv_voltage, _ = get_sensor_state_safely(
                    self._hass, mppt.get(CONF_PV_VOLTAGE), "PV Voltage"
                )
            vmp, imp, voc, isc, panel_count = get_panel_parameters_with_fallbacks(
                mppt.get(CONF_PANEL_VMP),
                mppt.get(CONF_PANEL_IMP),
                mppt.get(CONF_PANEL_VOC),
                mppt.get(CONF_PANEL_ISC),
                mppt.get(CONF_PANEL_COUNT, 1),
            )
            readings.append({
                "pv_power": pv_power,
                "pv_voltage": pv_voltage,
                "panel_params": {
                    CONF_PANEL_VMP: vmp,
                    CONF_PANEL_IMP: imp,
                    CONF_PANEL_VOC: voc,
                    CONF_PANEL_ISC: isc,
                    CONF_PANEL_COUNT: panel_count,
                    CONF_PANEL_CONFIGURATION: mppt.get(
                        CONF_PANEL_CONFIGURATION, PANEL_CONFIG_SERIES
                    ),
                },
            })
        return readings


    def _get_simulated_mppt_readings(self) -> List[Dict[str, Any]]:
        """Build synthetic MPPT readings from simulation config.

        sim_pv_power is total across all MPPTs; split evenly.
        Panel parameters come from real config so MPPT math stays correct.
        """
        total_power = float(self._config.get(CONF_SIM_PV_POWER, 0.0))
        voltage = float(self._config.get(CONF_SIM_PV_VOLTAGE, 0.0))
        inputs = self._mppt_inputs or [{}]
        per_mppt_power = total_power / len(inputs)
        readings: List[Dict[str, Any]] = []
        for mppt in inputs:
            vmp, imp, voc, isc, panel_count = get_panel_parameters_with_fallbacks(
                mppt.get(CONF_PANEL_VMP),
                mppt.get(CONF_PANEL_IMP),
                mppt.get(CONF_PANEL_VOC),
                mppt.get(CONF_PANEL_ISC),
                mppt.get(CONF_PANEL_COUNT, 1),
            )
            readings.append({
                "pv_power": per_mppt_power,
                "pv_voltage": voltage,
                "panel_params": {
                    CONF_PANEL_VMP: vmp,
                    CONF_PANEL_IMP: imp,
                    CONF_PANEL_VOC: voc,
                    CONF_PANEL_ISC: isc,
                    CONF_PANEL_COUNT: panel_count,
                    CONF_PANEL_CONFIGURATION: mppt.get(
                        CONF_PANEL_CONFIGURATION, PANEL_CONFIG_SERIES
                    ),
                },
            })
        return readings


    def _apply_temp_compensation_to_panel(
        self,
        panel_params: Dict[str, Any],
        temp_compensation: Optional[Dict[str, float]],
    ) -> Tuple[float, float]:
        """Apply temperature compensation to a single MPPT's vmp/imp.

        Pmax = Vmp * Imp, so Imp_coef = Pmax_coef - Vmp_coef.
        """
        vmp = float(panel_params[CONF_PANEL_VMP])
        imp = float(panel_params[CONF_PANEL_IMP])
        if temp_compensation:
            temp_diff = temp_compensation["temp_diff"]
            voc_coef = temp_compensation["voc_coef"]
            pmax_coef = temp_compensation["pmax_coef"]
            vmp = vmp * (1 + voc_coef * temp_diff)
            imp = imp * (1 + (pmax_coef - voc_coef) * temp_diff)
        return vmp, imp


    def _get_mppt_config(self) -> Dict[str, float]:
        """Get MPPT algorithm configuration."""
        return get_mppt_algorithm_config(self._config)


    def _get_temperature_compensation(self) -> Optional[Dict[str, float]]:
        """Get temperature compensation data if enabled."""
        return get_temperature_compensation_data(self._hass, self._config)


    def _invalidate_shared_snapshot(self) -> None:
        """Drop the cached input snapshot for this config entry, if present."""
        entry_data = self._hass.data.get(DOMAIN, {}).get(self._entry_id)
        if entry_data is not None:
            entry_data.pop("_sensor_snapshot", None)


    def _get_shared_snapshot(self) -> Dict[str, Any]:
        """Return per-cycle shared input snapshot, building it once per change.

        The four hub sensors (excess, max_power, current_max_power, usage_percent)
        all derive from the same inputs (per-MPPT readings, consumption, battery,
        algorithm config, temperature compensation). Reading and assembling those is
        identical across the four; caching the snapshot means it is built once per
        input change instead of four times. The cache is invalidated event-driven
        (see ``_update_sensor``), so it never serves data older than the latest
        state change — no time-based staleness.
        """
        entry_data = self._hass.data.get(DOMAIN, {}).get(self._entry_id)
        if entry_data is None:
            # No entry storage (e.g. during teardown) — build a throwaway snapshot.
            return {
                "sensor_values": self._get_sensor_values(),
                "mppt_readings": self._get_mppt_readings(),
                "mppt_config": self._get_mppt_config(),
                "temp_compensation": self._get_temperature_compensation(),
            }

        snapshot = entry_data.get("_sensor_snapshot")
        if snapshot is None:
            snapshot = {
                "sensor_values": self._get_sensor_values(),
                "mppt_readings": self._get_mppt_readings(),
                "mppt_config": self._get_mppt_config(),
                "temp_compensation": self._get_temperature_compensation(),
            }
            entry_data["_sensor_snapshot"] = snapshot
        return snapshot


    def _update_attributes(self, **kwargs) -> None:
        """Update sensor attributes."""
        self._attr_extra_state_attributes.update(kwargs)


    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        try:
            snapshot = self._get_shared_snapshot()

            value = self._calculate_value(
                sensor_values=snapshot["sensor_values"],
                mppt_readings=snapshot["mppt_readings"],
                mppt_config=snapshot["mppt_config"],
                temp_compensation=snapshot["temp_compensation"],
            )

            self._state = value
            return value

        except (
            ValueError,
            TypeError,
            ZeroDivisionError,
            KeyError,
            AttributeError,
        ) as exc:
            log_error(f"Error calculating {self.entity_id}: {exc}")
            journal_event(
                "sensor_calc_error", {"sensor": self.entity_id, "error": str(exc)}
            )

            return self._state or 0.0


    @abstractmethod
    def _calculate_value(
        self,
        sensor_values: Dict[str, Any],
        mppt_readings: List[Dict[str, Any]],
        mppt_config: Dict[str, float],
        temp_compensation: Optional[Dict[str, float]],
    ) -> float:
        """Calculate sensor-specific value.

        Args:
            sensor_values: shared sensor values (consumption, battery_power).
            mppt_readings: list of per-MPPT dicts with pv_power, pv_voltage,
                panel_params.
            mppt_config: MPPT algorithm configuration.
            temp_compensation: optional temperature compensation data.

        Returns:
            Calculated sensor value.
        """
