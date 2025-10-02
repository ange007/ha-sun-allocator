"""Base sensor class for Sun Allocator sensors."""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

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
    CONF_PV_POWER,
    CONF_PV_VOLTAGE,
    CONF_CONSUMPTION,
    CONF_BATTERY_POWER,
    CONF_VMP,
    CONF_IMP,
    CONF_VOC,
    CONF_ISC,
    CONF_PANEL_COUNT,
    CONF_PANEL_CONFIGURATION,
    PANEL_CONFIG_SERIES,
    CONF_TEMPERATURE_COMPENSATION_ENABLED,
    CONF_TEMPERATURE_SENSOR,
    KEY_PMAX,
    KEY_ENERGY_HARVESTING_POSSIBLE,
    KEY_MIN_SYSTEM_VOLTAGE,
    KEY_LIGHT_FACTOR,
    KEY_RELATIVE_VOLTAGE,
    KEY_VOC_RATIO,
    KEY_CALCULATION_REASON,
)


class BaseSunAllocatorSensor(SensorEntity, ABC):
    """Base class for all SunAllocator sensors."""

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

        # Sensor identification
        self._attr_translation_key = name
        self._attr_unique_id = f"{entry_id}_{unique_id_suffix}"
        self._attr_native_unit_of_measurement = unit_of_measurement

        # Configuration values
        self._pv_power = config.get(CONF_PV_POWER)
        self._pv_voltage = config.get(CONF_PV_VOLTAGE)
        self._consumption = config.get(CONF_CONSUMPTION)
        self._battery_power = config.get(CONF_BATTERY_POWER)
        self._vmp = config.get(CONF_VMP)
        self._imp = config.get(CONF_IMP)
        self._voc = config.get(CONF_VOC)
        self._isc = config.get(CONF_ISC)
        self._panel_count = config.get(CONF_PANEL_COUNT, 1)
        self._panel_configuration = config.get(
            CONF_PANEL_CONFIGURATION, PANEL_CONFIG_SERIES
        )

        # Initialize state and attributes
        self._state = 0.0
        self._attr_extra_state_attributes = self._get_default_attributes()

        # Initialize update listeners
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
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            manufacturer="Sun Allocator",
        )

    @property
    def should_poll(self) -> bool:
        """Return False as entity pushes updates."""
        return False

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        # Set up state change listeners
        entity_ids = self._get_entity_ids_to_listen()

        @callback
        def _update_sensor(*_):
            """Update the sensor when underlying data changes."""
            self.async_schedule_update_ha_state(True)

        setup_sensor_listeners(
            self._hass, entity_ids, _update_sensor, self._unsub_listeners
        )

        # Initial update
        self.async_schedule_update_ha_state(True)

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        cleanup_sensor_listeners(self._unsub_listeners)

    def _get_entity_ids_to_listen(self) -> list:
        """Get list of entity IDs to listen for state changes."""
        entity_ids = []

        # Always listen to PV power if configured
        if self._pv_power:
            entity_ids.append(self._pv_power)

        # Listen to PV voltage if configured
        if self._pv_voltage:
            entity_ids.append(self._pv_voltage)

        # Listen to consumption if configured
        if self._consumption:
            entity_ids.append(self._consumption)

        # Listen to battery power if configured
        if self._battery_power:
            entity_ids.append(self._battery_power)

        # Listen to temperature sensor if temperature compensation is enabled
        if self._config.get(CONF_TEMPERATURE_COMPENSATION_ENABLED, False):
            temp_sensor = self._config.get(CONF_TEMPERATURE_SENSOR)
            if temp_sensor:
                entity_ids.append(temp_sensor)

        return entity_ids

    def _get_sensor_values(self) -> Dict[str, Any]:
        """Get current sensor values with error handling."""
        # Get PV power
        pv_power, _ = get_sensor_state_safely(self._hass, self._pv_power, "PV Power")

        # Get PV voltage (optional)
        pv_voltage = 0.0
        if self._pv_voltage:
            pv_voltage, _ = get_sensor_state_safely(
                self._hass, self._pv_voltage, "PV Voltage"
            )

        # Get consumption (optional)
        consumption = 0.0
        if self._consumption:
            consumption, _ = get_sensor_state_safely(
                self._hass, self._consumption, "Consumption"
            )

        # Get battery power (optional)
        battery_power = 0.0
        if self._battery_power:
            battery_power, _ = get_sensor_state_safely(
                self._hass, self._battery_power, "Battery Power"
            )

        return {
            "pv_power": pv_power,
            "pv_voltage": pv_voltage,
            "consumption": consumption,
            "battery_power": battery_power,
        }

    def _get_panel_parameters(self) -> Dict[str, Any]:
        """Get panel parameters with proper fallbacks."""
        vmp, imp, voc, isc, panel_count = get_panel_parameters_with_fallbacks(
            self._vmp, self._imp, self._voc, self._isc, self._panel_count
        )

        return {
            "vmp": vmp,
            "imp": imp,
            "voc": voc,
            "isc": isc,
            "panel_count": panel_count,
            "panel_configuration": self._panel_configuration,
        }

    def _get_mppt_config(self) -> Dict[str, float]:
        """Get MPPT algorithm configuration."""
        return get_mppt_algorithm_config(self._config)

    def _get_temperature_compensation(self) -> Optional[Dict[str, float]]:
        """Get temperature compensation data if enabled."""
        return get_temperature_compensation_data(self._hass, self._config)

    def _update_attributes(self, **kwargs) -> None:
        """Update sensor attributes."""
        self._attr_extra_state_attributes.update(kwargs)

    def _get_common_attributes(
        self,
        debug_info: Dict[str, Any],
        panel_params: Dict[str, Any],
        pv_power: float,
        pv_voltage: float,
        current_max_power: float,
    ) -> Dict[str, Any]:
        """Get common attributes for sensor updates."""
        return {
            "pv_power": pv_power,
            "pv_voltage": pv_voltage,
            "energy_harvesting_possible": debug_info[KEY_ENERGY_HARVESTING_POSSIBLE],
            "min_system_voltage": debug_info[KEY_MIN_SYSTEM_VOLTAGE],
            "vmp": panel_params[CONF_VMP],
            "imp": panel_params[CONF_IMP],
            "voc": panel_params[CONF_VOC],
            "isc": panel_params[CONF_ISC],
            "panel_count": panel_params[CONF_PANEL_COUNT],
            "panel_configuration": panel_params[CONF_PANEL_CONFIGURATION],
            "pmax": debug_info[KEY_PMAX],
            "current_max_power": current_max_power,
            "light_factor": debug_info[KEY_LIGHT_FACTOR],
            "relative_voltage": debug_info[KEY_RELATIVE_VOLTAGE],
            "voc_ratio": debug_info[KEY_VOC_RATIO],
            "calculation_reason": debug_info[KEY_CALCULATION_REASON],
        }

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        try:
            # Get current sensor values
            sensor_values = self._get_sensor_values()

            # Get panel parameters
            panel_params = self._get_panel_parameters()

            # Get MPPT configuration
            mppt_config = self._get_mppt_config()

            # Get temperature compensation
            temp_compensation = self._get_temperature_compensation()

            # Calculate sensor-specific value
            value = self._calculate_value(
                sensor_values=sensor_values,
                panel_params=panel_params,
                mppt_config=mppt_config,
                temp_compensation=temp_compensation,
            )

            # Update state and attributes
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
        panel_params: Dict[str, Any],
        mppt_config: Dict[str, float],
        temp_compensation: Optional[Dict[str, float]],
    ) -> float:
        """
        Calculate the sensor-specific value.

        This method must be implemented by each sensor subclass.

        Args:
            sensor_values: Current sensor values (pv_power, pv_voltage, consumption)
            panel_params: Panel parameters (vmp, imp, voc, isc, panel_count, panel_configuration)
            mppt_config: MPPT algorithm configuration
            temp_compensation: Temperature compensation data (if enabled)

        Returns:
            Calculated sensor value
        """
