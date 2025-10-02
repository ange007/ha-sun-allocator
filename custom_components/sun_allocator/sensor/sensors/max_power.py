"""Maximum power sensor for Sun Allocator."""

from typing import Optional, Dict, Any

from homeassistant.core import HomeAssistant
from homeassistant.const import UnitOfPower

from .base import BaseSunAllocatorSensor
from ...core.solar_optimizer import calculate_pmax
from ...core.logger import log_debug

from ...const import (
    CONF_TEMPERATURE_COMPENSATION_ENABLED,
    CONF_TEMPERATURE_SENSOR,
    CONF_VMP,
    CONF_IMP,
    CONF_VOC,
    CONF_ISC,
    CONF_PANEL_COUNT,
    CONF_PANEL_CONFIGURATION,
)


class SunAllocatorMaxPowerSensor(BaseSunAllocatorSensor):
    """Sensor for maximum theoretical power."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: Dict[str, Any],
        entry_id: str,
        entry_index: int,
    ):
        """Initialize the maximum power sensor."""
        super().__init__(
            hass=hass,
            config=config,
            entry_id=entry_id,
            entry_index=entry_index,
            name="max_power",
            unique_id_suffix="max_power",
            unit_of_measurement=UnitOfPower.WATT,
        )

    def _get_entity_ids_to_listen(self) -> list:
        """Override to listen only to temperature sensor if temperature compensation is enabled."""
        entity_ids = []

        # Only listen to temperature sensor if temperature compensation is enabled
        # Max power doesn't depend on current PV conditions, only on configuration
        if self._config.get(CONF_TEMPERATURE_COMPENSATION_ENABLED, False):
            temp_sensor = self._config.get(CONF_TEMPERATURE_SENSOR)
            if temp_sensor:
                entity_ids.append(temp_sensor)

        return entity_ids

    def _calculate_value(
        self,
        sensor_values: Dict[str, Any],
        panel_params: Dict[str, Any],
        mppt_config: Dict[str, float],
        temp_compensation: Optional[Dict[str, float]],
    ) -> float:
        """Calculate maximum theoretical power."""
        vmp = panel_params[CONF_VMP]
        imp = panel_params[CONF_IMP]

        # Apply temperature compensation if provided
        if temp_compensation:
            temp_diff = temp_compensation["temp_diff"]
            voc_coef = temp_compensation["voc_coef"]
            pmax_coef = temp_compensation["pmax_coef"]

            # Adjust Vmp and Imp for temperature
            vmp = vmp * (1 + voc_coef * temp_diff)
            imp = imp * (1 + pmax_coef * temp_diff + voc_coef * temp_diff)

            log_debug(
                f"Temperature compensation applied: temp_diff={temp_diff}°C, "
                f"adjusted Vmp={vmp:.2f}V, adjusted Imp={imp:.2f}A"
            )

        # Calculate maximum power based on panel configuration
        pmax = calculate_pmax(
            vmp=vmp,
            imp=imp,
            panel_count=panel_params[CONF_PANEL_COUNT],
            panel_configuration=panel_params[CONF_PANEL_CONFIGURATION],
        )

        # Update attributes with panel information
        self._update_attributes(
            pv_power=0.0,  # Not applicable for max power sensor
            pv_voltage=0.0,  # Not applicable for max power sensor
            consumption=0.0,  # Not applicable for max power sensor
            excess_possible=False,  # Not applicable for max power sensor
            energy_harvesting_possible=True,  # Assume possible at max power
            min_system_voltage=0.0,  # Not applicable for max power sensor
            vmp=vmp,
            imp=imp,
            voc=panel_params[CONF_VOC],
            isc=panel_params[CONF_ISC],
            panel_count=panel_params[CONF_PANEL_COUNT],
            panel_configuration=panel_params[CONF_PANEL_CONFIGURATION],
            pmax=pmax,
            current_max_power=pmax,  # At ideal conditions, current max = theoretical max
            usage_percent=0.0,  # Not applicable for max power sensor
            temperature_compensated=temp_compensation is not None,
        )

        log_debug(
            f"Max power calculation: Vmp={vmp:.2f}V, Imp={imp:.2f}A, "
            f"Panel Count={panel_params[CONF_PANEL_COUNT]}, "
            f"Configuration={panel_params[CONF_PANEL_CONFIGURATION]}, "
            f"Pmax={pmax:.1f}W"
        )

        return pmax
