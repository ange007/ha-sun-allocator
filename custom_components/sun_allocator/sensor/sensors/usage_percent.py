"""Usage percentage sensor for Sun Allocator (multi-MPPT)."""

from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.const import PERCENTAGE

from .base import BaseSunAllocatorSensor
from ...core.solar_optimizer import calculate_pmax
from ..utils import calculate_usage_percentage
from ...core.logger import log_debug

from ...const import (
    CONF_PANEL_COUNT,
    CONF_PANEL_CONFIGURATION,
    SENSOR_USAGE_PERCENT_SUFFIX,
)


class SunAllocatorUsagePercentSensor(BaseSunAllocatorSensor):
    """Sensor for usage percentage of solar panels (aggregated across MPPTs)."""

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
            name=SENSOR_USAGE_PERCENT_SUFFIX,
            unique_id_suffix=SENSOR_USAGE_PERCENT_SUFFIX,
            unit_of_measurement=PERCENTAGE,
        )


    def _calculate_value(
        self,
        sensor_values: Dict[str, Any],
        mppt_readings: List[Dict[str, Any]],
        mppt_config: Dict[str, float],
        temp_compensation: Optional[Dict[str, float]],
    ) -> float:
        """Calculate usage % as total_pv / total_pmax across all MPPTs."""
        total_pv = sum(float(r["pv_power"]) for r in mppt_readings)
        total_pmax = 0.0

        for r in mppt_readings:
            panel_params = r["panel_params"]
            vmp, imp = self._apply_temp_compensation_to_panel(
                panel_params, temp_compensation
            )
            total_pmax += calculate_pmax(
                vmp=vmp,
                imp=imp,
                panel_count=panel_params[CONF_PANEL_COUNT],
                panel_configuration=panel_params[CONF_PANEL_CONFIGURATION],
            )

        usage = calculate_usage_percentage(total_pv, total_pmax)

        first_voltage = (
            float(mppt_readings[0]["pv_voltage"]) if mppt_readings else 0.0
        )
        self._update_attributes(
            pv_power=round(total_pv, 1),
            pv_voltage=round(first_voltage, 2),
            pmax=round(total_pmax, 1),
            mppt_count=len(mppt_readings),
            temperature_compensated=temp_compensation is not None,
        )

        log_debug(
            f"Usage % across {len(mppt_readings)} MPPT(s): "
            f"PV={total_pv:.1f}W / Pmax={total_pmax:.1f}W = {usage:.1f}%"
        )

        return usage
