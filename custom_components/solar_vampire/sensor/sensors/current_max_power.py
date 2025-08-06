"""Current maximum power sensor for Solar Vampire."""
import logging
from typing import Optional, Dict, Any
from homeassistant.core import HomeAssistant

from .base import BaseSolarVampireSensor
from ...utils import calculate_current_max_power
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

_LOGGER = logging.getLogger(__name__)


class SolarVampireCurrentMaxPowerSensor(BaseSolarVampireSensor):
    """Sensor for current maximum power at current conditions."""
    
    def __init__(self, hass: HomeAssistant, config: Dict[str, Any], entry_id: str):
        """Initialize the current maximum power sensor."""
        super().__init__(
            hass=hass,
            config=config,
            entry_id=entry_id,
            name="Current Max Power",
            unique_id_suffix="current_max_power",
            unit_of_measurement="W"
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
            excess_possible=pv_voltage > panel_params[KEY_VMP] if pv_voltage > 0 else False,
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
        
        _LOGGER.debug(
            f"Current max power calculation: PV Voltage={pv_voltage}V, "
            f"PV Power={pv_power}W, Current Max Power={current_max_power}W, "
            f"Light Factor={debug_info[KEY_LIGHT_FACTOR]:.2f}, "
            f"Reason: {debug_info[KEY_CALCULATION_REASON]}"
        )
        
        return current_max_power