"""Excess power sensor for Sun Allocator."""

from typing import Optional, Dict, Any

from homeassistant.core import HomeAssistant
from homeassistant.const import UnitOfPower
import homeassistant.util.dt as dt_util

from .base import BaseSunAllocatorSensor
from ...core.logger import journal_event, log_error, log_info
from ..utils import (
    calculate_excess_power_mppt,
    calculate_usage_percentage,
)

from ...const import (
    DOMAIN,
    CONF_BATTERY_POWER_REVERSED,
    CONF_CONSUMPTION,
    CONF_RESERVE_BATTERY_POWER,
    CONF_INVERTER_SELF_CONSUMPTION,
    CONF_PV_POWER,
    CONF_PV_VOLTAGE,
    CONF_PV_CURRENT,
    CONF_BATTERY_POWER,
    CONF_PANEL_VMP,
    CONF_PANEL_IMP,
    SENSOR_EXCESS_SUFFIX,
)


class SunAllocatorExcessSensor(BaseSunAllocatorSensor):
    """Sensor for excess power (untapped potential)."""

    def _journal_excess_if_changed(self, mode, excess, debug_info):
        """Emit excess journal only when the effective payload changes."""
        entry_data = self._hass.data.setdefault(DOMAIN, {}).setdefault(self._entry_id, {})
        journal_state = {
            "mode": mode,
            "excess": round(float(excess), 1),
            "calculation_reason": debug_info.get("calculation_reason"),
            "energy_harvesting_possible": debug_info.get("energy_harvesting_possible"),
            "relative_voltage": round(float(debug_info.get("relative_voltage", 0.0)), 4),
        }
        if entry_data.get("last_excess_journal") == journal_state:
            return

        entry_data["last_excess_journal"] = journal_state
        journal_event(
            "excess_power_calc",
            {
                "mode": mode,
                "excess": excess,
                **debug_info,
            },
        )

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
        panel_params: Dict[str, Any],
        mppt_config: Dict[str, float],
        temp_compensation: Optional[Dict[str, float]],
    ) -> float:
        """Calculate excess power using a unified MPPT-based approach."""

        # Get common sensor values
        pv_power = sensor_values.get(CONF_PV_POWER, 0)
        pv_voltage = sensor_values.get(CONF_PV_VOLTAGE, 0)
        pv_current = sensor_values.get(CONF_PV_CURRENT)
        consumption = sensor_values.get(CONF_CONSUMPTION, 0)
        battery_power = sensor_values.get(CONF_BATTERY_POWER, 0)
        battery_power_reversed = self._config.get(CONF_BATTERY_POWER_REVERSED, False)
        configured_reserve = self._config.get(CONF_RESERVE_BATTERY_POWER, 0)
        inverter_self_consumption = self._config.get(
            CONF_INVERTER_SELF_CONSUMPTION, 0
        )

        # Guard clause: Panel parameters are essential for MPPT mode
        has_panel_params = (
            panel_params.get(CONF_PANEL_VMP) is not None
            and panel_params.get(CONF_PANEL_IMP) is not None
        )
        if not has_panel_params:
            log_error(
                "Solar panel parameters (Vmp, Imp) are not configured. "
                "Cannot calculate excess power. Please configure your panels."
            )
            self._update_attributes(
                pv_power=pv_power,
                pv_voltage=pv_voltage,
                consumption=consumption,
                battery_power=battery_power,
                current_max_power=0,
                usage_percent=0,
            )
            return 0.0

        snapshot = self._get_shared_calculation_snapshot()
        mppt_summary = self._get_shared_mppt_summary(snapshot)
        pv_power = mppt_summary["pv_power"]
        current_max_power = mppt_summary["current_max_power"]
        debug_info = mppt_summary["debug_info"]

        # Determine if consumption sensor is used for the calculation
        has_consumption_sensor = self._config.get(CONF_CONSUMPTION) is not None

        # Calculate excess using the unified MPPT function
        excess = calculate_excess_power_mppt(
            current_max_power=current_max_power,
            pv_power=pv_power,
            consumption=consumption if has_consumption_sensor else None,
            battery_power=battery_power,
            battery_power_reversed=battery_power_reversed,
            configured_reserve=configured_reserve,
            inverter_self_consumption=inverter_self_consumption,
            untapped_power=mppt_summary["untapped_power"],
            **debug_info,
        )

        # Update all attributes consistently
        usage = calculate_usage_percentage(pv_power, current_max_power)
        battery_discharging = (
            battery_power > 0 if battery_power_reversed else battery_power < 0
        )

        self._update_attributes(
            pv_power=pv_power,
            pv_voltage=pv_voltage,
            pv_current=pv_current,
            consumption=consumption if has_consumption_sensor else None,
            battery_power=battery_power,
            battery_discharging=battery_discharging,
            excess_possible=excess > 5.0,
            current_max_power=current_max_power,
            untapped_power=mppt_summary["untapped_power"],
            usage_percent=usage,
            mppt_count=mppt_summary["mppt_count"],
            mppt_inputs=mppt_summary["mppt_inputs"],
            **debug_info,
        )

        self._journal_excess_if_changed(
            "mppt_with_consumption" if has_consumption_sensor else "mppt",
            excess,
            debug_info,
        )

        # Update watchdog timestamp to indicate the sensor is alive
        if self._hass and self._entry_id and DOMAIN in self._hass.data and self._entry_id in self._hass.data[DOMAIN]:
            try:
                entry_data = self._hass.data[DOMAIN][self._entry_id]
                entry_data["watchdog_last_seen"] = dt_util.utcnow()
                if entry_data.get("watchdog_alerted"):
                    entry_data["watchdog_alerted"] = False
                    log_info("SunAllocator watchdog: data fresh again; normal operation resumed")
            except KeyError:
                # This can happen during setup or teardown, it's safe to ignore
                pass

        return excess
