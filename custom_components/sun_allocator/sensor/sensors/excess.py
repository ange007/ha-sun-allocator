"""Excess power sensor for Sun Allocator."""
from typing import Optional, Dict, Any

from homeassistant.core import HomeAssistant
from homeassistant.const import UnitOfPower

from .base import BaseSunAllocatorSensor
from ...core.logger import log_debug, journal_event
from ...core.solar_optimizer import calculate_current_max_power
from ..utils import (
    calculate_excess_power,
    calculate_usage_percentage,
    get_sensor_state_safely,
)

from ...const import (
    CONF_CURVE_FACTOR_K,
    CONF_EFFICIENCY_CORRECTION_FACTOR,
    CONF_MIN_INVERTER_VOLTAGE,
    CONF_BATTERY_POWER_REVERSED,
    KEY_PV_POWER,
    KEY_PV_VOLTAGE,
    KEY_CONSUMPTION,
    KEY_BATTERY_POWER,
    KEY_VMP,
    KEY_IMP,
    KEY_VOC,
    KEY_ISC,
    KEY_PANEL_COUNT,
    KEY_PANEL_CONFIGURATION,
    KEY_PMAX,
    KEY_ENERGY_HARVESTING_POSSIBLE,
    KEY_RELATIVE_VOLTAGE,
    KEY_CALCULATION_REASON,
    SENSOR_ID_PREFIX,
    SENSOR_POWER_DISTRIBUTION_SUFFIX,
)


class SunAllocatorExcessSensor(BaseSunAllocatorSensor):
    """Sensor for excess power (untapped potential)."""

    def __init__(
        self, hass: HomeAssistant, config: Dict[str, Any], entry_id: str, entry_index: int
    ):
        """Initialize the excess power sensor."""
        super().__init__(
            hass=hass,
            config=config,
            entry_id=entry_id,
            entry_index=entry_index,
            name="Excess",
            unique_id_suffix="excess",
            unit_of_measurement=UnitOfPower.WATT,
        )

    # pylint: disable=too-many-locals
    def _calculate_value(
        self,
        sensor_values: Dict[str, Any],
        panel_params: Dict[str, Any],
        mppt_config: Dict[str, float],
        temp_compensation: Optional[Dict[str, float]],
    ) -> float:
        """Calculate excess power (untapped potential)."""
        pv_power = sensor_values[KEY_PV_POWER]
        pv_voltage = sensor_values[KEY_PV_VOLTAGE]
        battery_power = sensor_values[KEY_BATTERY_POWER]

        # Get consumption value and success flag
        consumption, consumption_success = get_sensor_state_safely(
            self.hass, self._config.get(KEY_CONSUMPTION), "Consumption"
        )

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
            efficiency_correction_factor=mppt_config[
                CONF_EFFICIENCY_CORRECTION_FACTOR
            ],
            min_inverter_voltage=mppt_config[CONF_MIN_INVERTER_VOLTAGE],
            temperature_compensation=temp_compensation,
        )

        # Calculate excess power based on generation, consumption, and battery
        # Note: allocated_power is no longer used in the calculation to avoid double counting
        battery_power_reversed = self._config.get(CONF_BATTERY_POWER_REVERSED, False)
        excess = calculate_excess_power(
            current_max_power=current_max_power,
            pv_power=pv_power,
            consumption=consumption if consumption_success else None,
            battery_power=battery_power,
            battery_power_reversed=battery_power_reversed,
        )

        # Determine if battery is discharging (for diagnostics/UI)
        battery_discharging = (
            battery_power > 0 if battery_power_reversed else (battery_power < 0)
        )

        # Calculate usage percentage
        usage = calculate_usage_percentage(pv_power, debug_info[KEY_PMAX])

        # Determine actionable excess flag
        epsilon = 5.0  # small hysteresis to avoid flicker
        excess_possible = excess > epsilon

        # Update attributes with all relevant information
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
            excess_possible=excess_possible,
            usage_percent=usage,
        )

        log_debug(
            f"Excess power calculation: PV Power={pv_power}W, "
            f"Current Max Power={current_max_power}W, Excess={excess}W, "
            f"Reason: {debug_info[KEY_CALCULATION_REASON]}"
        )
        journal_event(
            "excess_power_calc",
            {
                "pv_power": pv_power,
                "current_max_power": current_max_power,
                "excess": excess,
                "reason": debug_info[KEY_CALCULATION_REASON],
                "usage_percent": usage,
                "battery_discharging": battery_discharging,
                "excess_possible": excess_possible,
            },
        )

        return excess
