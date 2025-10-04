"""Current maximum power sensor for Sun Allocator."""

from typing import Optional, Dict, Any

from homeassistant.core import HomeAssistant
from homeassistant.const import UnitOfPower

from .base import BaseSunAllocatorSensor
from ...core.solar_optimizer import calculate_current_max_power
from ...core.logger import log_debug

from ...const import (
    CONF_CURVE_FACTOR_K,
    CONF_EFFICIENCY_CORRECTION_FACTOR,
    CONF_MIN_INVERTER_VOLTAGE,
    CONF_PV_POWER,
    CONF_PV_VOLTAGE,
    CONF_VMP,
    CONF_IMP,
    CONF_VOC,
    CONF_ISC,
    CONF_PANEL_COUNT,
    CONF_PANEL_CONFIGURATION,
    KEY_ENERGY_HARVESTING_POSSIBLE,
    KEY_RELATIVE_VOLTAGE,
    KEY_CALCULATION_REASON,
)


class SunAllocatorCurrentMaxPowerSensor(BaseSunAllocatorSensor):
    """Sensor for current maximum power at current conditions."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: Dict[str, Any],
        entry_id: str,
        entry_index: int,
    ):
        """Initialize the current max power sensor."""
        super().__init__(
            hass=hass,
            config=config,
            entry_id=entry_id,
            entry_index=entry_index,
            name="current_max_power",
            unique_id_suffix="current_max_power",
            unit_of_measurement=UnitOfPower.WATT,
        )

    def _calculate_value(
        self,
        sensor_values: Dict[str, Any],
        panel_params: Dict[str, Any],
        mppt_config: Dict[str, float],
        temp_compensation: Optional[Dict[str, float]],
    ) -> float:
        """Calculate current maximum power at current conditions."""
        pv_power = sensor_values[CONF_PV_POWER]
        pv_voltage = sensor_values[CONF_PV_VOLTAGE]

        # Calculate current maximum power using MPPT algorithm
        current_max_power, debug_info = calculate_current_max_power(
            pv_voltage=pv_voltage,
            pv_power=pv_power,
            vmp=panel_params[CONF_VMP],
            imp=panel_params[CONF_IMP],
            voc=panel_params[CONF_VOC],
            isc=panel_params[CONF_ISC],
            panel_count=panel_params[CONF_PANEL_COUNT],
            panel_configuration=panel_params[CONF_PANEL_CONFIGURATION],
            curve_factor_k=mppt_config[CONF_CURVE_FACTOR_K],
            efficiency_correction_factor=mppt_config[CONF_EFFICIENCY_CORRECTION_FACTOR],
            min_inverter_voltage=mppt_config[CONF_MIN_INVERTER_VOLTAGE],
            temperature_compensation=temp_compensation,
        )

        # Update attributes with detailed information
        common_attrs = self._get_common_attributes(
            debug_info=debug_info,
            panel_params=panel_params,
            pv_power=pv_power,
            pv_voltage=pv_voltage,
            current_max_power=current_max_power,
        )
        self._update_attributes(
            **common_attrs,
            excess_possible=(
                debug_info[KEY_RELATIVE_VOLTAGE] > 1.0
                and debug_info[KEY_ENERGY_HARVESTING_POSSIBLE]
            ),
        )

        log_debug(
            f"Current max power: {current_max_power}W, "
            f"Reason: {debug_info[KEY_CALCULATION_REASON]}"
        )

        return current_max_power
