"""Usage percentage sensor for Sun Allocator."""

from typing import Optional, Dict, Any

from homeassistant.core import HomeAssistant
from homeassistant.const import PERCENTAGE

from .base import BaseSunAllocatorSensor
from ...core.solar_optimizer import calculate_pmax
from ..utils import calculate_usage_percentage
from ...core.logger import log_debug

from ...const import (
    CONF_PV_POWER,
    CONF_PV_VOLTAGE,
    CONF_VMP,
    CONF_IMP,
    CONF_VOC,
    CONF_ISC,
    CONF_PANEL_COUNT,
    CONF_PANEL_CONFIGURATION,
)


class SunAllocatorUsagePercentSensor(BaseSunAllocatorSensor):
    """Sensor for usage percentage of solar panels."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: Dict[str, Any],
        entry_id: str,
        entry_index: int,
    ):
        """Initialize the usage percentage sensor."""
        super().__init__(
            hass=hass,
            config=config,
            entry_id=entry_id,
            entry_index=entry_index,
            name="usage_percent",
            unique_id_suffix="usage_percent",
            unit_of_measurement=PERCENTAGE,
        )

    def _calculate_value(
        self,
        sensor_values: Dict[str, Any],
        panel_params: Dict[str, Any],
        mppt_config: Dict[str, float],
        temp_compensation: Optional[Dict[str, float]],
    ) -> float:
        """Calculate usage percentage of solar panels."""
        pv_power = sensor_values[CONF_PV_POWER]
        pv_voltage = sensor_values[CONF_PV_VOLTAGE]

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
                f"Temp comp applied for usage: temp_diff={temp_diff}°C, "
                f"adj Vmp={vmp:.2f}V, adj Imp={imp:.2f}A"
            )

        # Calculate maximum theoretical power
        pmax = calculate_pmax(
            vmp=vmp,
            imp=imp,
            panel_count=panel_params[CONF_PANEL_COUNT],
            panel_configuration=panel_params[CONF_PANEL_CONFIGURATION],
        )

        # Calculate usage percentage
        usage = calculate_usage_percentage(pv_power, pmax)

        # Update attributes with relevant information
        self._update_attributes(
            pv_power=pv_power,
            pv_voltage=pv_voltage,
            consumption=0.0,  # Not used for usage calculation
            excess_possible=pv_voltage > panel_params[CONF_VMP]
            if pv_voltage > 0
            else False,
            energy_harvesting_possible=True,  # Assume possible if generating power
            min_system_voltage=0.0,  # Not relevant for usage calculation
            vmp=vmp,
            imp=imp,
            voc=panel_params[CONF_VOC],
            isc=panel_params[CONF_ISC],
            panel_count=panel_params[CONF_PANEL_COUNT],
            panel_configuration=panel_params[CONF_PANEL_CONFIGURATION],
            pmax=pmax,
            current_max_power=0.0,  # Not calculated here
            usage_percent=usage,
            temperature_compensated=temp_compensation is not None,
        )

        log_debug(
            f"Usage percentage calculation: PV Power={pv_power}W, "
            f"Pmax={pmax:.1f}W, Usage={usage:.1f}%"
        )

        return usage
