"""Maximum power sensor for Sun Allocator (multi-MPPT)."""

from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.const import UnitOfPower

from .base import BaseSunAllocatorSensor
from ...core.solar_optimizer import calculate_pmax
from ...core.logger import log_debug

from ...const import (
    CONF_TEMPERATURE_COMPENSATION_ENABLED,
    CONF_TEMPERATURE_SENSOR,
    CONF_PANEL_VMP,
    CONF_PANEL_IMP,
    CONF_PANEL_VOC,
    CONF_PANEL_ISC,
    CONF_PANEL_COUNT,
    CONF_PANEL_CONFIGURATION,
    SENSOR_MAX_POWER_SUFFIX,
)


class SunAllocatorMaxPowerSensor(BaseSunAllocatorSensor):
    """Sensor for maximum theoretical power, summed across MPPTs."""

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
            name=SENSOR_MAX_POWER_SUFFIX,
            unique_id_suffix=SENSOR_MAX_POWER_SUFFIX,
            unit_of_measurement=UnitOfPower.WATT,
        )


    def _get_entity_ids_to_listen(self) -> list:
        """Override: max power is config-static, only react to temp sensor changes."""
        entity_ids = []
        if self._config.get(CONF_TEMPERATURE_COMPENSATION_ENABLED, False):
            temp_sensor = self._config.get(CONF_TEMPERATURE_SENSOR)
            if temp_sensor:
                entity_ids.append(temp_sensor)
        return entity_ids


    def _calculate_value(
        self,
        sensor_values: Dict[str, Any],
        mppt_readings: List[Dict[str, Any]],
        mppt_config: Dict[str, float],
        temp_compensation: Optional[Dict[str, float]],
    ) -> float:
        """Sum maximum theoretical power across all MPPT trackers."""
        total_pmax = 0.0
        breakdown: List[Dict[str, Any]] = []

        for idx, r in enumerate(mppt_readings):
            panel_params = r["panel_params"]
            vmp, imp = self._apply_temp_compensation_to_panel(
                panel_params, temp_compensation
            )
            pmax = calculate_pmax(
                vmp=vmp,
                imp=imp,
                panel_count=panel_params[CONF_PANEL_COUNT],
                panel_configuration=panel_params[CONF_PANEL_CONFIGURATION],
            )
            total_pmax += pmax
            breakdown.append({
                "index": idx,
                CONF_PANEL_VMP: round(vmp, 3),
                CONF_PANEL_IMP: round(imp, 3),
                CONF_PANEL_VOC: round(float(panel_params[CONF_PANEL_VOC]), 3),
                CONF_PANEL_ISC: round(float(panel_params[CONF_PANEL_ISC]), 3),
                CONF_PANEL_COUNT: panel_params[CONF_PANEL_COUNT],
                CONF_PANEL_CONFIGURATION: panel_params[CONF_PANEL_CONFIGURATION],
                "pmax": round(pmax, 1),
            })
            log_debug(
                f"Max power MPPT[{idx}]: Vmp={vmp:.2f}V, Imp={imp:.2f}A, "
                f"count={panel_params[CONF_PANEL_COUNT]}, "
                f"cfg={panel_params[CONF_PANEL_CONFIGURATION]}, "
                f"Pmax={pmax:.1f}W"
            )

        # Top-level attributes — back-compat scalar (first tracker) + breakdown.
        first = breakdown[0] if breakdown else {}
        self._update_attributes(
            vmp=first.get(CONF_PANEL_VMP, 0.0),
            imp=first.get(CONF_PANEL_IMP, 0.0),
            voc=first.get(CONF_PANEL_VOC, 0.0),
            isc=first.get(CONF_PANEL_ISC, 0.0),
            panel_count=first.get(CONF_PANEL_COUNT, 0),
            panel_configuration=first.get(CONF_PANEL_CONFIGURATION, ""),
            pmax=round(total_pmax, 1),
            mppt_count=len(mppt_readings),
            mppt_breakdown=breakdown,
            temperature_compensated=temp_compensation is not None,
        )

        log_debug(f"Max power total across {len(mppt_readings)} MPPT(s): {total_pmax:.1f}W")
        return total_pmax
