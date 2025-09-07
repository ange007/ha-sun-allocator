"""Excess power sensor for Sun Allocator."""
import logging
from typing import Optional, Dict, Any
from homeassistant.core import HomeAssistant
from homeassistant.const import UnitOfPower

from .base import BaseSunAllocatorSensor
from ...utils import (
    calculate_current_max_power,
    calculate_excess_power,
    calculate_usage_percentage,
)
from ...const import (
    CONF_CURVE_FACTOR_K,
    CONF_EFFICIENCY_CORRECTION_FACTOR,
    CONF_MIN_INVERTER_VOLTAGE,
    CONF_BATTERY_POWER_REVERSED,
    KEY_PV_POWER,
    KEY_PV_VOLTAGE,
    KEY_CONSUMPTION,
    KEY_BATTERY_POWER,
    KEY_VMP,
    KEY_IMP,
    KEY_VOC,
    KEY_ISC,
    KEY_PANEL_COUNT,
    KEY_PANEL_CONFIGURATION,
    KEY_PMAX,
    KEY_ENERGY_HARVESTING_POSSIBLE,
    KEY_MIN_SYSTEM_VOLTAGE,
    KEY_LIGHT_FACTOR,
    KEY_RELATIVE_VOLTAGE,
    KEY_VOC_RATIO,
    KEY_CALCULATION_REASON,
)

_LOGGER = logging.getLogger(__name__)


class SunAllocatorExcessSensor(BaseSunAllocatorSensor):
    """Sensor for excess power (untapped potential)."""
    
    def __init__(self, hass: HomeAssistant, config: Dict[str, Any], entry_id: str):
        """Initialize the excess power sensor."""
        super().__init__(
            hass=hass,
            config=config,
            entry_id=entry_id,
            name="Excess",
            unique_id_suffix="excess",
            unit_of_measurement=UnitOfPower.WATT
        )
    
    def _calculate_value(
        self,
        sensor_values: Dict[str, Any],
        panel_params: Dict[str, Any],
        mppt_config: Dict[str, float],
        temp_compensation: Optional[Dict[str, float]]
    ) -> float:
        """Calculate excess power (untapped potential)."""
        pv_power = sensor_values[KEY_PV_POWER]
        pv_voltage = sensor_values[KEY_PV_VOLTAGE]
        consumption = sensor_values[KEY_CONSUMPTION]
        battery_power = sensor_values[KEY_BATTERY_POWER]
        
        # Calculate current maximum power using MPPT algorithm
        current_max_power, debug_info = calculate_current_max_power(
            pv_voltage=pv_voltage,
            pv_power=pv_power,
            vmp=panel_params[KEY_VMP],
            imp=panel_params[KEY_IMP],
            voc=panel_params[KEY_VOC],
            isc=panel_params[KEY_ISC],
            panel_count=panel_params[KEY_PANEL_COUNT],
            panel_configuration=panel_params[KEY_PANEL_CONFIGURATION],
            curve_factor_k=mppt_config[CONF_CURVE_FACTOR_K],
            efficiency_correction_factor=mppt_config[CONF_EFFICIENCY_CORRECTION_FACTOR],
            min_inverter_voltage=mppt_config[CONF_MIN_INVERTER_VOLTAGE],
            temperature_compensation=temp_compensation
        )
        
        # Calculate excess power
        battery_power_reversed = self._config.get(CONF_BATTERY_POWER_REVERSED, False)
        excess = calculate_excess_power(current_max_power, pv_power, battery_power, battery_power_reversed)
        # Determine if battery is discharging (for diagnostics/UI)
        battery_discharging = (battery_power > 0) if battery_power_reversed else (battery_power < 0)
        
        # Calculate usage percentage
        usage = calculate_usage_percentage(pv_power, debug_info[KEY_PMAX])
        
        # Determine actionable and topology-based excess flags
        epsilon = 5.0  # small hysteresis to avoid flicker
        excess_possible = excess > epsilon
        topology_excess_possible = (
            debug_info[KEY_RELATIVE_VOLTAGE] > 1.0
            and debug_info[KEY_ENERGY_HARVESTING_POSSIBLE]
        )
        
        # Update attributes with all relevant information
        self._update_attributes(
            pv_power=pv_power,
            pv_voltage=pv_voltage,
            consumption=consumption,
            battery_power=battery_power,
            battery_discharging=battery_discharging,
            excess_possible=excess_possible,
            excess_possible_topology=topology_excess_possible,
            energy_harvesting_possible=debug_info[KEY_ENERGY_HARVESTING_POSSIBLE],
            min_system_voltage=debug_info[KEY_MIN_SYSTEM_VOLTAGE],
            vmp=panel_params[KEY_VMP],
            imp=panel_params[KEY_IMP],
            voc=panel_params[KEY_VOC],
            isc=panel_params[KEY_ISC],
            panel_count=panel_params[KEY_PANEL_COUNT],
            panel_configuration=panel_params[KEY_PANEL_CONFIGURATION],
            pmax=debug_info[KEY_PMAX],
            current_max_power=current_max_power,
            usage_percent=usage,
            light_factor=debug_info[KEY_LIGHT_FACTOR],
            relative_voltage=debug_info[KEY_RELATIVE_VOLTAGE],
            voc_ratio=debug_info[KEY_VOC_RATIO],
            calculation_reason=debug_info[KEY_CALCULATION_REASON]
        )
        
        _LOGGER.debug(
            f"Excess power calculation: PV Power={pv_power}W, "
            f"Current Max Power={current_max_power}W, Excess={excess}W, "
            f"Reason: {debug_info[KEY_CALCULATION_REASON]}"
        )
        
        return excess