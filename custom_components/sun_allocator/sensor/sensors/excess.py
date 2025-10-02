"""Excess power sensor for Sun Allocator."""

from typing import Optional, Dict, Any

from homeassistant.core import HomeAssistant
from homeassistant.const import UnitOfPower

from .base import BaseSunAllocatorSensor
from ...core.logger import log_debug, journal_event
from ...core.solar_optimizer import calculate_current_max_power
from ..utils import (
    calculate_excess_power_mppt,
    calculate_excess_power_parallel,
    calculate_usage_percentage,
    create_sensor_attributes,
)

from ...const import (
    CONF_CURVE_FACTOR_K,
    CONF_EFFICIENCY_CORRECTION_FACTOR,
    CONF_MIN_INVERTER_VOLTAGE,
    CONF_BATTERY_POWER_REVERSED,
    CONF_CONSUMPTION,
    CONF_RESERVE_BATTERY_POWER,
    CONF_INVERTER_SELF_CONSUMPTION,
    CONF_PV_POWER,
    CONF_PV_VOLTAGE,
    CONF_BATTERY_POWER,
    CONF_VMP,
    CONF_IMP,
    CONF_VOC,
    CONF_ISC,
    CONF_PANEL_COUNT,
    CONF_PANEL_CONFIGURATION,
    KEY_PMAX,
)


class SunAllocatorExcessSensor(BaseSunAllocatorSensor):
    """Sensor for excess power (untapped potential)."""

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
            name="excess",
            unique_id_suffix="excess",
            unit_of_measurement=UnitOfPower.WATT,
        )

    def _get_default_attributes(self) -> Dict[str, Any]:
        """Get default attributes for the sensor."""
        return create_sensor_attributes(
            pv_power=0.0,
            pv_voltage=0.0,
            consumption=0.0,
            battery_power=0.0,
            excess_possible=False,
            energy_harvesting_possible=False,
            battery_discharging=False,
            usage_percent=0.0,
        )

    def _calculate_value(
        self,
        sensor_values: Dict[str, Any],
        panel_params: Dict[str, Any],
        mppt_config: Dict[str, float],
        temp_compensation: Optional[Dict[str, float]],
    ) -> float:
        """Calculate excess power by dispatching to the correct calculation mode."""

        # Get common sensor values
        pv_power = sensor_values.get(CONF_PV_POWER, 0)
        consumption = sensor_values.get(CONF_CONSUMPTION, 0)
        battery_power = sensor_values.get(CONF_BATTERY_POWER, 0)
        battery_power_reversed = self._config.get(CONF_BATTERY_POWER_REVERSED, False)
        configured_reserve = self._config.get(CONF_RESERVE_BATTERY_POWER, 0)
        inverter_self_consumption = self._config.get(CONF_INVERTER_SELF_CONSUMPTION, 0)

        # --- Automatic Mode Selection ---
        # Parallel mode if consumption sensor is configured, otherwise MPPT mode.
        if self._config.get(CONF_CONSUMPTION):
            # --- Parallel Distribution Mode (Consumption sensor is configured) ---
            excess = calculate_excess_power_parallel(
                pv_power=pv_power,
                consumption=consumption,
                battery_power=battery_power,
                battery_power_reversed=battery_power_reversed,
                configured_reserve=configured_reserve,
                inverter_self_consumption=inverter_self_consumption,
            )

            battery_discharging = (
                battery_power > 0 if battery_power_reversed else battery_power < 0
            )

            self._update_attributes(
                pv_power=pv_power,
                consumption=consumption,
                battery_power=battery_power,
                battery_discharging=battery_discharging,
                excess_possible=excess > 5.0,
                usage_percent=None,  # Not applicable in this mode
            )

            journal_event("excess_power_calc", {"mode": "parallel", "excess": excess})
            return excess

        # --- Original MPPT Mode (No consumption sensor) ---
        pv_voltage = sensor_values.get(CONF_PV_VOLTAGE, 0)

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

        excess = calculate_excess_power_mppt(
            current_max_power=current_max_power,
            pv_power=pv_power,
            consumption=None,  # Explicitly pass None as consumption sensor is absent
            battery_power=battery_power,
            battery_power_reversed=battery_power_reversed,
            configured_reserve=configured_reserve,
            inverter_self_consumption=inverter_self_consumption,
        )

        battery_discharging = (
            battery_power > 0 if battery_power_reversed else battery_power < 0
        )
        usage = calculate_usage_percentage(pv_power, debug_info[KEY_PMAX])

        common_attrs = self._get_common_attributes(
            debug_info=debug_info,
            panel_params=panel_params,
            pv_power=pv_power,
            pv_voltage=pv_voltage,
            current_max_power=current_max_power,
        )
        self._update_attributes(
            **common_attrs,
            consumption=consumption,
            battery_power=battery_power,
            battery_discharging=battery_discharging,
            excess_possible=excess > 5.0,
            usage_percent=usage,
        )

        log_debug(
            f"Excess power calculation (MPPT): PV Power={pv_power}W, "
            f"Current Max Power={current_max_power}W, Excess={excess}W, "
            f"Reason: {debug_info.get('calculation_reason')}"
        )
        journal_event(
            "excess_power_calc", {"mode": "mppt", "excess": excess, **debug_info}
        )

        return excess
