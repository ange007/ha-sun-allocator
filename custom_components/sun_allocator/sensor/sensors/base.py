"""Base sensor class for Sun Allocator sensors."""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Tuple

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.typing import StateType

from ...core.logger import log_error, journal_event
from ...core.solar_optimizer import get_panel_parameters_with_fallbacks
from ..utils import (
    get_sensor_state_safely,
    get_temperature_compensation_data,
    create_sensor_attributes,
    setup_sensor_listeners,
    cleanup_sensor_listeners,
    get_mppt_algorithm_config,
)

from ...const import (
    DOMAIN,
    CONF_MPPT_INPUTS,
    CONF_PV_POWER,
    CONF_PV_VOLTAGE,
    CONF_CONSUMPTION,
    CONF_BATTERY_POWER,
    CONF_PANEL_VMP,
    CONF_PANEL_IMP,
    CONF_PANEL_VOC,
    CONF_PANEL_ISC,
    CONF_PANEL_COUNT,
    CONF_PANEL_CONFIGURATION,
    PANEL_CONFIG_SERIES,
    CONF_TEMPERATURE_COMPENSATION_ENABLED,
    CONF_TEMPERATURE_SENSOR,
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
        )


    @property
    def should_poll(self) -> bool:
        """Return False as entity pushes updates."""
        return False


    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        entity_ids = self._get_entity_ids_to_listen()

        @callback
        def _update_sensor(*_):
            """Update the sensor when underlying data changes."""
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

        if self._config.get(CONF_TEMPERATURE_COMPENSATION_ENABLED, False):
            temp_sensor = self._config.get(CONF_TEMPERATURE_SENSOR)
            if temp_sensor:
                entity_ids.append(temp_sensor)

        return entity_ids


    def _get_sensor_values(self) -> Dict[str, Any]:
        """Read shared sensor values (consumption, battery_power)."""
        consumption = 0.0
        if self._consumption:
            consumption, _ = get_sensor_state_safely(
                self._hass, self._consumption, "Consumption"
            )

        battery_power = 0.0
        if self._battery_power:
            battery_power, _ = get_sensor_state_safely(
                self._hass, self._battery_power, "Battery Power"
            )

        return {
            CONF_CONSUMPTION: consumption,
            CONF_BATTERY_POWER: battery_power,
        }


    def _get_mppt_readings(self) -> List[Dict[str, Any]]:
        """Read per-MPPT pv_power, pv_voltage and panel parameters."""
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


    def _update_attributes(self, **kwargs) -> None:
        """Update sensor attributes."""
        self._attr_extra_state_attributes.update(kwargs)


    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        try:
            sensor_values = self._get_sensor_values()
            mppt_readings = self._get_mppt_readings()
            mppt_config = self._get_mppt_config()
            temp_compensation = self._get_temperature_compensation()

            value = self._calculate_value(
                sensor_values=sensor_values,
                mppt_readings=mppt_readings,
                mppt_config=mppt_config,
                temp_compensation=temp_compensation,
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
