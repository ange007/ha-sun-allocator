"""Maximum power sensor for Sun Allocator."""

from typing import Optional, Dict, Any

from homeassistant.core import HomeAssistant
from homeassistant.const import UnitOfPower

from .base import BaseSunAllocatorSensor
from ...core.logger import log_debug

from ...const import (
    CONF_TEMPERATURE_COMPENSATION_ENABLED,
    CONF_TEMPERATURE_SENSOR,
    CONF_PANEL_VOC,
    CONF_PANEL_ISC,
    CONF_PANEL_COUNT,
    CONF_PANEL_CONFIGURATION,
    SENSOR_MAX_POWER_SUFFIX,
)


class SunAllocatorMaxPowerSensor(BaseSunAllocatorSensor):
    """Sensor for maximum theoretical power."""

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
        """Override to listen only to temperature sensor if temperature compensation is enabled."""
        entity_ids = []

        # Only listen to temperature sensor if temperature compensation is enabled
        # Max power doesn't depend on current PV conditions, only on configuration
        if self._config.get(CONF_TEMPERATURE_COMPENSATION_ENABLED, False):
            temp_sensor = self._config.get(CONF_TEMPERATURE_SENSOR)
            if temp_sensor:
                entity_ids.append(temp_sensor)

        return entity_ids


    def _calculate_value(
        self,
        sensor_values: Dict[str, Any],
        panel_params: Dict[str, Any],
        mppt_config: Dict[str, float],
        temp_compensation: Optional[Dict[str, float]],
    ) -> float:
        """Calculate maximum theoretical power."""
        snapshot = self._get_shared_calculation_snapshot()
        panel_summary = self._get_theoretical_panel_summary(snapshot)
        pmax = panel_summary["pmax"]
        mppt_inputs = panel_summary["mppt_inputs"]
        primary_input = mppt_inputs[0]

        # Update attributes with panel information
        self._update_attributes(
            vmp=primary_input["vmp"],
            imp=primary_input["imp"],
            voc=panel_params[CONF_PANEL_VOC],
            isc=panel_params[CONF_PANEL_ISC],
            panel_count=panel_params[CONF_PANEL_COUNT],
            panel_configuration=panel_params[CONF_PANEL_CONFIGURATION],
            pmax=pmax,
            mppt_count=len(mppt_inputs),
            mppt_inputs=mppt_inputs,
            temperature_compensated=temp_compensation is not None,
        )

        log_debug(
            f"Max power calculation: MPPT inputs={len(mppt_inputs)}, "
            f"Configuration={panel_params[CONF_PANEL_CONFIGURATION]}, "
            f"Pmax={pmax:.1f}W"
        )

        return pmax
