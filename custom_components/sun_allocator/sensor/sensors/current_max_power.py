"""Current maximum power sensor for Sun Allocator."""

from typing import Optional, Dict, Any

from homeassistant.core import HomeAssistant
from homeassistant.const import UnitOfPower

from .base import BaseSunAllocatorSensor
from ...core.logger import log_debug

from ...const import (
    CONF_PV_VOLTAGE,
    CONF_PV_CURRENT,
    KEY_ENERGY_HARVESTING_POSSIBLE,
    KEY_RELATIVE_VOLTAGE,
    KEY_CALCULATION_REASON,
    SENSOR_CURRENT_MAX_POWER_SUFFIX,
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
            name=SENSOR_CURRENT_MAX_POWER_SUFFIX,
            unique_id_suffix=SENSOR_CURRENT_MAX_POWER_SUFFIX,
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
        snapshot = self._get_shared_calculation_snapshot()
        mppt_summary = self._get_shared_mppt_summary(snapshot)
        pv_power = mppt_summary["pv_power"]
        pv_voltage = sensor_values[CONF_PV_VOLTAGE]
        current_max_power = mppt_summary["current_max_power"]
        debug_info = mppt_summary["debug_info"]

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
            pv_current=sensor_values.get(CONF_PV_CURRENT),
            consumption=mppt_summary.get("consumption"),
            battery_power=mppt_summary.get("battery_power"),
            excess_possible=(
                debug_info[KEY_RELATIVE_VOLTAGE] > 1.0
                and debug_info[KEY_ENERGY_HARVESTING_POSSIBLE]
            ),
            untapped_power=mppt_summary["untapped_power"],
            mppt_count=mppt_summary["mppt_count"],
            mppt_inputs=mppt_summary["mppt_inputs"],
        )

        log_debug(
            f"Current max power: {current_max_power}W, "
            f"Reason: {debug_info[KEY_CALCULATION_REASON]}"
        )

        return current_max_power
