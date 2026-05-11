"""Base sensor class for Sun Allocator sensors."""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.typing import StateType

from ...core.logger import log_error, journal_event
from ...core.solar_optimizer import (
    calculate_pmax,
    calculate_multi_mppt_power,
    get_panel_parameters_with_fallbacks,
)
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
    CONF_PV_CURRENT,
    CONF_MPPT2_ENABLED,
    CONF_PV2_POWER,
    CONF_PV2_VOLTAGE,
    CONF_PV2_CURRENT,
    CONF_CONSUMPTION,
    CONF_BATTERY_POWER,
    CONF_PANEL_VMP,
    CONF_PANEL_IMP,
    CONF_PANEL_VOC,
    CONF_PANEL_ISC,
    CONF_PANEL_COUNT,
    CONF_PANEL_CONFIGURATION,
    CONF_PANEL2_VMP,
    CONF_PANEL2_IMP,
    CONF_PANEL2_VOC,
    CONF_PANEL2_ISC,
    CONF_PANEL2_COUNT,
    CONF_PANEL2_CONFIGURATION,
    CONF_CURVE_FACTOR_K,
    CONF_EFFICIENCY_CORRECTION_FACTOR,
    CONF_MIN_INVERTER_VOLTAGE,
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

        # Sensor identification
        self._attr_translation_key = name
        self._attr_unique_id = f"{entry_id}_{unique_id_suffix}"
        self._attr_native_unit_of_measurement = unit_of_measurement

        # Configuration values
        self._pv_power = config.get(CONF_PV_POWER)
        self._pv_voltage = config.get(CONF_PV_VOLTAGE)
        self._pv_current = config.get(CONF_PV_CURRENT)
        self._pv2_power = config.get(CONF_PV2_POWER)
        self._pv2_voltage = config.get(CONF_PV2_VOLTAGE)
        self._pv2_current = config.get(CONF_PV2_CURRENT)
        self._consumption = config.get(CONF_CONSUMPTION)
        self._battery_power = config.get(CONF_BATTERY_POWER)
        self._vmp = config.get(CONF_PANEL_VMP)
        self._imp = config.get(CONF_PANEL_IMP)
        self._voc = config.get(CONF_PANEL_VOC)
        self._isc = config.get(CONF_PANEL_ISC)
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
            pv_current=0.0,
            consumption=0.0,
            battery_power=0.0,
            excess_possible=False,
            energy_harvesting_possible=False,
            current_max_power=0.0,
            untapped_power=0.0,
            usage_percent=0.0,
            mppt_count=1,
            mppt_inputs=[],
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
        # Set up state change listeners
        entity_ids = self._get_entity_ids_to_listen()

        @callback
        def _update_sensor(*_):
            """Update the sensor when underlying data changes."""
            self._invalidate_entry_sensor_cache()
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

        if self._pv_current:
            entity_ids.append(self._pv_current)

        if self._pv2_power:
            entity_ids.append(self._pv2_power)

        if self._pv2_voltage:
            entity_ids.append(self._pv2_voltage)

        if self._pv2_current:
            entity_ids.append(self._pv2_current)

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

        pv_current = None
        if self._pv_current:
            pv_current, _ = get_sensor_state_safely(
                self._hass, self._pv_current, "PV Current"
            )

        pv2_power = 0.0
        if self._pv2_power:
            pv2_power, _ = get_sensor_state_safely(
                self._hass, self._pv2_power, "PV2 Power"
            )

        pv2_voltage = 0.0
        if self._pv2_voltage:
            pv2_voltage, _ = get_sensor_state_safely(
                self._hass, self._pv2_voltage, "PV2 Voltage"
            )

        pv2_current = None
        if self._pv2_current:
            pv2_current, _ = get_sensor_state_safely(
                self._hass, self._pv2_current, "PV2 Current"
            )

        if not self._pv2_power and pv2_current is not None and pv2_voltage:
            pv2_power = pv2_voltage * pv2_current

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
            "pv_current": pv_current,
            "pv2_power": pv2_power,
            "pv2_voltage": pv2_voltage,
            "pv2_current": pv2_current,
            "consumption": consumption,
            "battery_power": battery_power,
        }


    def _get_entry_data(self) -> Dict[str, Any]:
        """Return per-entry runtime storage for shared sensor calculations."""
        return self._hass.data.setdefault(DOMAIN, {}).setdefault(self._entry_id, {})


    def _get_entry_sensor_cache(self) -> Dict[str, Any]:
        """Return the shared sensor cache for this config entry."""
        return self._get_entry_data().setdefault("sensor_calc_cache", {})


    def _invalidate_entry_sensor_cache(self) -> None:
        """Invalidate cached shared sensor calculations for this entry."""
        entry_data = self._hass.data.get(DOMAIN, {}).get(self._entry_id)
        if entry_data is None:
            return
        entry_data.pop("sensor_calc_cache", None)


    def _get_shared_calculation_snapshot(self) -> Dict[str, Any]:
        """Get or build the shared calculation snapshot for this entry."""
        cache = self._get_entry_sensor_cache()
        snapshot = cache.get("shared_snapshot")
        if snapshot is None:
            snapshot = {
                "sensor_values": self._get_sensor_values(),
                "panel_params": self._get_panel_parameters(),
                "mppt_config": self._get_mppt_config(),
                "temp_compensation": self._get_temperature_compensation(),
            }
            cache["shared_snapshot"] = snapshot
        return snapshot


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


    def _is_mppt2_enabled(self) -> bool:
        """Return whether the config includes a second MPPT input."""
        if CONF_MPPT2_ENABLED in self._config:
            return bool(self._config.get(CONF_MPPT2_ENABLED))

        return bool(
            self._pv2_power
            or self._pv2_voltage
            or self._pv2_current
        )


    def _config_or_fallback(self, key: str, fallback: Any) -> Any:
        """Return a config value, treating empty optional fields as missing."""
        value = self._config.get(key)
        return fallback if value in (None, "") else value


    def _get_mppt_panel_configs(self, panel_params: Dict[str, Any]) -> list[Dict[str, Any]]:
        """Build panel parameter configs for all active MPPT inputs."""
        panel_configs = [
            {
                "id": "mppt1",
                "name": "MPPT 1",
                **panel_params,
            }
        ]

        if self._is_mppt2_enabled():
            vmp, imp, voc, isc, panel_count = get_panel_parameters_with_fallbacks(
                self._config_or_fallback(CONF_PANEL2_VMP, panel_params[CONF_PANEL_VMP]),
                self._config_or_fallback(CONF_PANEL2_IMP, panel_params[CONF_PANEL_IMP]),
                self._config_or_fallback(CONF_PANEL2_VOC, panel_params[CONF_PANEL_VOC]),
                self._config_or_fallback(CONF_PANEL2_ISC, panel_params[CONF_PANEL_ISC]),
                self._config_or_fallback(CONF_PANEL2_COUNT, panel_params[CONF_PANEL_COUNT]),
            )
            panel_configs.append(
                {
                    "id": "mppt2",
                    "name": "MPPT 2",
                    CONF_PANEL_VMP: vmp,
                    CONF_PANEL_IMP: imp,
                    CONF_PANEL_VOC: voc,
                    CONF_PANEL_ISC: isc,
                    CONF_PANEL_COUNT: panel_count,
                    CONF_PANEL_CONFIGURATION: self._config_or_fallback(
                        CONF_PANEL2_CONFIGURATION,
                        panel_params[CONF_PANEL_CONFIGURATION],
                    ),
                }
            )

        return panel_configs


    def _get_mppt_inputs(
        self,
        sensor_values: Dict[str, Any],
        panel_params: Dict[str, Any],
    ) -> list[Dict[str, Any]]:
        """Build current operating data for all active MPPT inputs."""
        panel_configs = self._get_mppt_panel_configs(panel_params)
        mppt_inputs = [
            {
                **panel_configs[0],
                "pv_power": sensor_values.get(CONF_PV_POWER, 0.0),
                "pv_voltage": sensor_values.get(CONF_PV_VOLTAGE, 0.0),
                "pv_current": sensor_values.get(CONF_PV_CURRENT),
            }
        ]

        if len(panel_configs) > 1:
            mppt_inputs.append(
                {
                    **panel_configs[1],
                    "pv_power": sensor_values.get(CONF_PV2_POWER, 0.0),
                    "pv_voltage": sensor_values.get(CONF_PV2_VOLTAGE, 0.0),
                    "pv_current": sensor_values.get(CONF_PV2_CURRENT),
                }
            )

        return mppt_inputs


    def _calculate_mppt_summary(
        self,
        sensor_values: Dict[str, Any],
        panel_params: Dict[str, Any],
        mppt_config: Dict[str, float],
        temp_compensation: Optional[Dict[str, float]],
    ) -> Dict[str, Any]:
        """Calculate aggregate current power data for all MPPT inputs."""
        return calculate_multi_mppt_power(
            self._get_mppt_inputs(sensor_values, panel_params),
            curve_factor_k=mppt_config[CONF_CURVE_FACTOR_K],
            efficiency_correction_factor=mppt_config[CONF_EFFICIENCY_CORRECTION_FACTOR],
            min_inverter_voltage=mppt_config[CONF_MIN_INVERTER_VOLTAGE],
            temperature_compensation=temp_compensation,
            consumption=sensor_values.get(CONF_CONSUMPTION),
            battery_power=sensor_values.get(CONF_BATTERY_POWER),
        )


    def _get_shared_mppt_summary(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Get or build the shared MPPT summary for this entry snapshot."""
        mppt_summary = snapshot.get("mppt_summary")
        if mppt_summary is None:
            mppt_summary = self._calculate_mppt_summary(
                sensor_values=snapshot["sensor_values"],
                panel_params=snapshot["panel_params"],
                mppt_config=snapshot["mppt_config"],
                temp_compensation=snapshot["temp_compensation"],
            )
            snapshot["mppt_summary"] = mppt_summary
        return mppt_summary


    def _get_theoretical_panel_summary(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Get or build the temperature-adjusted theoretical panel summary."""
        panel_summary = snapshot.get("theoretical_panel_summary")
        if panel_summary is not None:
            return panel_summary

        panel_params = snapshot["panel_params"]
        temp_compensation = snapshot["temp_compensation"]
        mppt_inputs = []
        pmax = 0.0

        for panel_config in self._get_mppt_panel_configs(panel_params):
            vmp = panel_config[CONF_PANEL_VMP]
            imp = panel_config[CONF_PANEL_IMP]

            if temp_compensation:
                temp_diff = temp_compensation["temp_diff"]
                voc_coef = temp_compensation["voc_coef"]
                pmax_coef = temp_compensation["pmax_coef"]

                vmp = vmp * (1 + voc_coef * temp_diff)
                imp = imp * (1 + (pmax_coef - voc_coef) * temp_diff)

            input_pmax = calculate_pmax(
                vmp=vmp,
                imp=imp,
                panel_count=panel_config[CONF_PANEL_COUNT],
                panel_configuration=panel_config[CONF_PANEL_CONFIGURATION],
            )
            pmax += input_pmax
            mppt_inputs.append(
                {
                    "id": panel_config["id"],
                    "name": panel_config["name"],
                    "vmp": round(vmp, 3),
                    "imp": round(imp, 3),
                    "voc": panel_config[CONF_PANEL_VOC],
                    "isc": panel_config[CONF_PANEL_ISC],
                    "panel_count": panel_config[CONF_PANEL_COUNT],
                    "panel_configuration": panel_config[CONF_PANEL_CONFIGURATION],
                    "pmax": round(input_pmax, 1),
                }
            )

        panel_summary = {
            "pmax": round(pmax, 1),
            "mppt_inputs": mppt_inputs,
        }
        snapshot["theoretical_panel_summary"] = panel_summary
        return panel_summary


    def _get_mppt_config(self) -> Dict[str, float]:
        """Get MPPT algorithm configuration."""
        return get_mppt_algorithm_config(self._config)


    def _get_temperature_compensation(self) -> Optional[Dict[str, float]]:
        """Get temperature compensation data if enabled."""
        return get_temperature_compensation_data(self._hass, self._config)


    @staticmethod
    def _build_legacy_mppt_aliases(
        mppt_inputs: Optional[list[Dict[str, Any]]],
        theoretical_mppt_inputs: Optional[list[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Expose flat PV1/PV2-style attributes alongside structured MPPT lists."""
        aliases: Dict[str, Any] = {}
        current_suffix_map = {
            "name": "name",
            "pv_power": "power",
            "pv_voltage": "voltage",
            "pv_current": "current",
            "current_max_power": "current_max_power",
            "untapped_power": "untapped_power",
            "vmp": "vmp",
            "imp": "imp",
            "voc": "voc",
            "isc": "isc",
            "panel_count": "panel_count",
            "panel_configuration": "panel_configuration",
            "light_factor": "light_factor",
            "relative_voltage": "relative_voltage",
            "voc_ratio": "voc_ratio",
            "calculation_reason": "calculation_reason",
            "energy_harvesting_possible": "energy_harvesting_possible",
        }

        for index, input_data in enumerate(mppt_inputs or [], start=1):
            prefix = f"pv{index}"
            aliases[f"{prefix}_id"] = input_data.get("id")
            for source_key, alias_suffix in current_suffix_map.items():
                aliases[f"{prefix}_{alias_suffix}"] = input_data.get(source_key)

        for index, input_data in enumerate(theoretical_mppt_inputs or [], start=1):
            prefix = f"pv{index}"
            aliases[f"{prefix}_theoretical_pmax"] = input_data.get("pmax")

        return aliases


    def _clear_legacy_mppt_aliases(self) -> None:
        """Remove stale flat PV aliases before writing fresh MPPT attributes."""
        for key in list(self._attr_extra_state_attributes):
            if key.startswith("pv") and len(key) > 3 and key[2].isdigit() and "_" in key[3:]:
                self._attr_extra_state_attributes.pop(key, None)


    def _update_attributes(self, **kwargs) -> None:
        """Update sensor attributes."""
        if "mppt_inputs" in kwargs or "theoretical_mppt_inputs" in kwargs:
            self._clear_legacy_mppt_aliases()
            kwargs.update(
                self._build_legacy_mppt_aliases(
                    kwargs.get("mppt_inputs"),
                    kwargs.get("theoretical_mppt_inputs"),
                )
            )
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
            "pv_power": round(float(pv_power), 1),
            "pv_voltage": round(float(pv_voltage), 2),
            "energy_harvesting_possible": debug_info[KEY_ENERGY_HARVESTING_POSSIBLE],
            "min_system_voltage": debug_info[KEY_MIN_SYSTEM_VOLTAGE],
            "vmp": round(float(panel_params[CONF_PANEL_VMP]), 3),
            "imp": round(float(panel_params[CONF_PANEL_IMP]), 3),
            "voc": round(float(panel_params[CONF_PANEL_VOC]), 3),
            "isc": round(float(panel_params[CONF_PANEL_ISC]), 3),
            "panel_count": panel_params[CONF_PANEL_COUNT],
            "panel_configuration": panel_params[CONF_PANEL_CONFIGURATION],
            "pmax": debug_info[KEY_PMAX],
            "current_max_power": round(float(current_max_power), 1),
            "light_factor": debug_info[KEY_LIGHT_FACTOR],
            "relative_voltage": debug_info[KEY_RELATIVE_VOLTAGE],
            "voc_ratio": debug_info[KEY_VOC_RATIO],
            "calculation_reason": debug_info[KEY_CALCULATION_REASON],
        }


    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        try:
            snapshot = self._get_shared_calculation_snapshot()

            # Calculate sensor-specific value
            value = self._calculate_value(
                sensor_values=snapshot["sensor_values"],
                panel_params=snapshot["panel_params"],
                mppt_config=snapshot["mppt_config"],
                temp_compensation=snapshot["temp_compensation"],
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
