"""Excess power sensor for Sun Allocator (multi-MPPT)."""

from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.const import UnitOfPower
import homeassistant.util.dt as dt_util

from .base import BaseSunAllocatorSensor
from ...core.logger import journal_event, log_error, log_info
from ...core.solar_optimizer import calculate_current_max_power
from ..utils import (
    calculate_excess_power_mppt,
    calculate_usage_percentage,
)

from ...const import (
    DOMAIN,
    CONF_BATTERY_POWER_REVERSED,
    CONF_CONSUMPTION,
    CONF_BATTERY_POWER,
    CONF_BATTERY_SOC_SENSOR,
    CONF_BATTERY_SHARING_SOC,
    CONF_RESERVE_BATTERY_POWER,
    CONF_INVERTER_SELF_CONSUMPTION,
    CONF_PANEL_VMP,
    CONF_PANEL_IMP,
    KEY_CALCULATION_REASON,
    KEY_ENERGY_HARVESTING_POSSIBLE,
    KEY_LIGHT_FACTOR,
    KEY_MIN_SYSTEM_VOLTAGE,
    KEY_PMAX,
    KEY_RELATIVE_VOLTAGE,
    KEY_VOC_RATIO,
    SENSOR_EXCESS_SUFFIX,
)


class SunAllocatorExcessSensor(BaseSunAllocatorSensor):
    """Sensor for excess power (untapped potential), aggregated across MPPTs."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: Dict[str, Any],
        entry_id: str,
        entry_index: int,
    ):
        """Initialize the excess power sensor."""
        super().__init__(
            hass=hass,
            config=config,
            entry_id=entry_id,
            entry_index=entry_index,
            name=SENSOR_EXCESS_SUFFIX,
            unique_id_suffix=SENSOR_EXCESS_SUFFIX,
            unit_of_measurement=UnitOfPower.WATT,
        )


    def _calculate_value(
        self,
        sensor_values: Dict[str, Any],
        mppt_readings: List[Dict[str, Any]],
        mppt_config: Dict[str, float],
        temp_compensation: Optional[Dict[str, float]],
    ) -> float:
        """Calculate excess power summed across all configured MPPT trackers."""
        consumption = sensor_values.get(CONF_CONSUMPTION, 0)
        battery_power = sensor_values.get(CONF_BATTERY_POWER, 0)
        battery_soc = sensor_values.get(CONF_BATTERY_SOC_SENSOR)
        battery_power_reversed = self._config.get(CONF_BATTERY_POWER_REVERSED, False)
        configured_reserve = self._config.get(CONF_RESERVE_BATTERY_POWER, 0)
        sharing_soc = self._config.get(CONF_BATTERY_SHARING_SOC, 0)
        inverter_self_consumption = self._config.get(
            CONF_INVERTER_SELF_CONSUMPTION, 0
        )
        has_consumption_sensor = self._config.get(CONF_CONSUMPTION) is not None

        if not mppt_readings:
            log_error(
                "No MPPT inputs configured. Cannot calculate excess power."
            )
            return 0.0

        # Guard clause: at least one MPPT must have valid panel params.
        for r in mppt_readings:
            pp = r["panel_params"]
            if pp.get(CONF_PANEL_VMP) is None or pp.get(CONF_PANEL_IMP) is None:
                log_error(
                    "Solar panel parameters (Vmp, Imp) are not configured for"
                    " an MPPT input. Cannot calculate excess power."
                )
                return 0.0

        # Per-MPPT untapped calculation with each tracker's own gating.
        total_pv_power = 0.0
        total_cmp = 0.0
        total_untapped = 0.0
        any_harvesting = False
        any_above_mpp = False
        light_factors: List[float] = []
        voc_ratios: List[float] = []
        pmax_sum = 0.0
        min_voltage_seen: Optional[float] = None
        per_mppt: List[Dict[str, Any]] = []

        for idx, r in enumerate(mppt_readings):
            pv_p = float(r["pv_power"])
            pv_v = float(r["pv_voltage"])
            cmp_value, debug = calculate_current_max_power(
                pv_voltage=pv_v,
                pv_power=pv_p,
                **r["panel_params"],
                **mppt_config,
                temperature_compensation=temp_compensation,
            )
            harvesting = bool(debug.get(KEY_ENERGY_HARVESTING_POSSIBLE))
            rel_v = float(debug.get(KEY_RELATIVE_VOLTAGE, 0.0))
            above_mpp = rel_v > 1.0

            if harvesting and above_mpp:
                untapped_i = max(0.0, float(cmp_value) - pv_p)
            else:
                untapped_i = 0.0

            total_pv_power += pv_p
            total_cmp += float(cmp_value)
            total_untapped += untapped_i
            any_harvesting = any_harvesting or harvesting
            any_above_mpp = any_above_mpp or above_mpp
            light_factors.append(float(debug.get(KEY_LIGHT_FACTOR, 0.0)))
            voc_ratios.append(float(debug.get(KEY_VOC_RATIO, 0.0)))
            pmax_sum += float(debug.get(KEY_PMAX, 0.0))
            min_v = float(debug.get(KEY_MIN_SYSTEM_VOLTAGE, 0.0))
            min_voltage_seen = (
                min_v if min_voltage_seen is None else min(min_voltage_seen, min_v)
            )
            per_mppt.append({
                "index": idx,
                "pv_power": round(pv_p, 1),
                "pv_voltage": round(pv_v, 2),
                "current_max_power": round(float(cmp_value), 1),
                "untapped": round(untapped_i, 1),
                **debug,
            })

        # Aggregate sentinels for downstream attribute consumers.
        avg_light = (
            sum(light_factors) / len(light_factors) if light_factors else 0.0
        )
        avg_voc = sum(voc_ratios) / len(voc_ratios) if voc_ratios else 0.0
        aggregate_relative_voltage = 2.0 if any_above_mpp else 0.0

        excess = calculate_excess_power_mppt(
            current_max_power=total_cmp,
            pv_power=total_pv_power,
            consumption=consumption if has_consumption_sensor else None,
            battery_power=battery_power,
            battery_power_reversed=battery_power_reversed,
            configured_reserve=configured_reserve,
            inverter_self_consumption=inverter_self_consumption,
            relative_voltage=aggregate_relative_voltage,
            energy_harvesting_possible=any_harvesting,
            untapped_power_override=total_untapped,
            battery_soc=battery_soc,
            sharing_soc=sharing_soc,
        )

        usage = calculate_usage_percentage(total_pv_power, total_cmp)
        battery_discharging = (
            battery_power > 0 if battery_power_reversed else battery_power < 0
        )

        self._update_attributes(
            pv_power=round(total_pv_power, 1),
            pv_voltage=round(float(mppt_readings[0]["pv_voltage"]), 2),
            consumption=consumption if has_consumption_sensor else None,
            battery_power=battery_power,
            battery_discharging=battery_discharging,
            excess_possible=excess > 5.0,
            current_max_power=round(total_cmp, 1),
            usage_percent=usage,
            energy_harvesting_possible=any_harvesting,
            min_system_voltage=min_voltage_seen if min_voltage_seen is not None else 0.0,
            pmax=round(pmax_sum, 1),
            light_factor=round(avg_light, 3),
            relative_voltage=round(aggregate_relative_voltage, 3),
            voc_ratio=round(avg_voc, 3),
            calculation_reason=(
                "aggregated multi-mppt"
                if len(mppt_readings) > 1
                else per_mppt[0].get(KEY_CALCULATION_REASON, "")
            ),
            mppt_count=len(mppt_readings),
            mppt_breakdown=per_mppt,
        )

        journal_event(
            "excess_power_calc",
            {
                "mode": "mppt_with_consumption" if has_consumption_sensor else "mppt",
                "excess": excess,
                "total_pv": total_pv_power,
                "total_cmp": total_cmp,
                "total_untapped": total_untapped,
                "mppt_count": len(mppt_readings),
            },
        )

        if (
            self.hass
            and self._entry_id
            and DOMAIN in self.hass.data
            and self._entry_id in self.hass.data[DOMAIN]
        ):
            try:
                entry_data = self.hass.data[DOMAIN][self._entry_id]
                entry_data["watchdog_last_seen"] = dt_util.utcnow()
                if entry_data.get("watchdog_alerted"):
                    entry_data["watchdog_alerted"] = False
                    log_info(
                        "SunAllocator watchdog: data fresh again; normal operation resumed"
                    )
            except KeyError:
                # During setup or teardown — safe to ignore.
                pass

        return excess
