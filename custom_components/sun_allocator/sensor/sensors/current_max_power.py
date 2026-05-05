"""Current maximum power sensor for Sun Allocator (multi-MPPT)."""

from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.const import UnitOfPower

from .base import BaseSunAllocatorSensor
from ...core.solar_optimizer import calculate_current_max_power
from ...core.logger import log_debug

from ...const import (
    CONF_PANEL_VMP,
    CONF_PANEL_IMP,
    CONF_PANEL_VOC,
    CONF_PANEL_ISC,
    CONF_PANEL_COUNT,
    CONF_PANEL_CONFIGURATION,
    KEY_CALCULATION_REASON,
    KEY_ENERGY_HARVESTING_POSSIBLE,
    KEY_RELATIVE_VOLTAGE,
    SENSOR_CURRENT_MAX_POWER_SUFFIX,
)


class SunAllocatorCurrentMaxPowerSensor(BaseSunAllocatorSensor):
    """Sensor for current maximum power, summed across MPPTs."""

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
            name=SENSOR_CURRENT_MAX_POWER_SUFFIX,
            unique_id_suffix=SENSOR_CURRENT_MAX_POWER_SUFFIX,
            unit_of_measurement=UnitOfPower.WATT,
        )


    def _calculate_value(
        self,
        sensor_values: Dict[str, Any],
        mppt_readings: List[Dict[str, Any]],
        mppt_config: Dict[str, float],
        temp_compensation: Optional[Dict[str, float]],
    ) -> float:
        """Sum current_max_power across all MPPT trackers using the MPPT model."""
        total_cmp = 0.0
        total_pv = 0.0
        any_excess_possible = False
        last_reason = ""
        breakdown: List[Dict[str, Any]] = []

        for idx, r in enumerate(mppt_readings):
            panel_params = r["panel_params"]
            cmp_value, debug = calculate_current_max_power(
                pv_voltage=r["pv_voltage"],
                pv_power=r["pv_power"],
                vmp=panel_params[CONF_PANEL_VMP],
                imp=panel_params[CONF_PANEL_IMP],
                voc=panel_params[CONF_PANEL_VOC],
                isc=panel_params[CONF_PANEL_ISC],
                panel_count=panel_params[CONF_PANEL_COUNT],
                panel_configuration=panel_params[CONF_PANEL_CONFIGURATION],
                **mppt_config,
                temperature_compensation=temp_compensation,
            )
            total_cmp += float(cmp_value)
            total_pv += float(r["pv_power"])
            if (
                debug.get(KEY_RELATIVE_VOLTAGE, 0.0) > 1.0
                and debug.get(KEY_ENERGY_HARVESTING_POSSIBLE)
            ):
                any_excess_possible = True
            last_reason = debug.get(KEY_CALCULATION_REASON, last_reason)
            breakdown.append({
                "index": idx,
                "pv_power": round(float(r["pv_power"]), 1),
                "pv_voltage": round(float(r["pv_voltage"]), 2),
                "current_max_power": round(float(cmp_value), 1),
                **debug,
            })

        first_voltage = (
            float(mppt_readings[0]["pv_voltage"]) if mppt_readings else 0.0
        )
        self._update_attributes(
            pv_power=round(total_pv, 1),
            pv_voltage=round(first_voltage, 2),
            current_max_power=round(total_cmp, 1),
            excess_possible=any_excess_possible,
            calculation_reason=last_reason,
            mppt_count=len(mppt_readings),
            mppt_breakdown=breakdown,
        )

        log_debug(
            f"Current max power total across {len(mppt_readings)} MPPT(s): "
            f"{total_cmp:.1f}W, any_excess_possible={any_excess_possible}"
        )

        return total_cmp
