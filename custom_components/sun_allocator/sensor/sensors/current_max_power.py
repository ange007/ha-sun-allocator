"""Current maximum power sensor for Sun Allocator."""
from typing import Optional, Dict, Any

from homeassistant.core import HomeAssistant
from homeassistant.const import UnitOfPower

from .base import BaseSunAllocatorSensor
from ...utils.mppt import calculate_current_max_power
from ...utils.logger import log_debug

from ...const import (
    CONF_CURVE_FACTOR_K,
    CONF_EFFICIENCY_CORRECTION_FACTOR,
    CONF_MIN_INVERTER_VOLTAGE,
    KEY_PV_POWER,
    KEY_PV_VOLTAGE,
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


class SunAllocatorCurrentMaxPowerSensor(BaseSunAllocatorSensor):
    """Sensor for current maximum power at current conditions."""
    
    def __init__(self, hass: HomeAssistant, config: Dict[str, Any], entry_id: str, entry_index: int):
        """Initialize the current maximum power sensor."""
        super().__init__(
            hass=hass,
            config=config,
            entry_id=entry_id,
            entry_index=entry_index,
            name="Current Max Power",
            unique_id_suffix="current_max_power",
            unit_of_measurement=UnitOfPower.WATT
        )
    
    def _calculate_value(
        self,
        sensor_values: Dict[str, Any],
        panel_params: Dict[str, Any],
        mppt_config: Dict[str, float],
        temp_compensation: Optional[Dict[str, float]]
    ) -> float:
        """Calculate current maximum power at current conditions."""
        pv_power = sensor_values[KEY_PV_POWER]
        pv_voltage = sensor_values[KEY_PV_VOLTAGE]
        
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
        
        # Update attributes with detailed information
        self._update_attributes(
            pv_power=pv_power,
            pv_voltage=pv_voltage,
            consumption=0.0,  # Not used for current max power calculation
            excess_possible=(debug_info[KEY_RELATIVE_VOLTAGE] > 1.0 and debug_info[KEY_ENERGY_HARVESTING_POSSIBLE]),
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
            usage_percent=0.0,  # Not calculated here
            light_factor=debug_info[KEY_LIGHT_FACTOR],
            relative_voltage=debug_info[KEY_RELATIVE_VOLTAGE],
            voc_ratio=debug_info[KEY_VOC_RATIO],
            calculation_reason=debug_info[KEY_CALCULATION_REASON]
        )
        
        log_debug(
            f"Current max power calculation: PV Voltage={pv_voltage}V, "
            f"PV Power={pv_power}W, Current Max Power={current_max_power}W, "
            f"Light Factor={debug_info[KEY_LIGHT_FACTOR]:.2f}, "
            f"Reason: {debug_info[KEY_CALCULATION_REASON]}"
        )
        
        return current_max_power