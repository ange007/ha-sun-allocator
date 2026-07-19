"""Time-until-off sensor for a SunAllocator device's active timed run."""

from __future__ import annotations
from typing import Any, Dict

import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant, callback
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import UnitOfTime

from ...const import (
    DOMAIN,
    SIGNAL_POWER_DISTRIBUTION_UPDATED,
    CONF_DEVICE_ID,
)
from ...core.timed_run import timed_run_remaining_min
from ..utils import get_device_info


class SunAllocatorDeviceTimerRemainingSensor(SensorEntity):
    """Whole minutes left on an active timed run, else 0."""

    _attr_has_entity_name = True
    _attr_translation_key = "timer_remaining"
    _attr_icon = "mdi:timer-sand"
    _attr_should_poll = False
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = SensorDeviceClass.DURATION

    def __init__(
        self, hass: HomeAssistant, entry_id: str, device_config: Dict[str, Any]
    ) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._device_id = device_config.get(CONF_DEVICE_ID)
        self._device_config = device_config
        self._attr_unique_id = f"{entry_id}_{self._device_id}_timer_remaining"

    @property
    def device_info(self) -> DeviceInfo:
        return get_device_info(self._hass, self._device_config, self._entry_id)

    @callback
    def _update_state(self):
        data = self._hass.data.get(DOMAIN, {}).get(self._entry_id)
        if not data:
            self._attr_native_value = 0
        else:
            override = data.get("manual_overrides", {}).get(self._device_id)
            self._attr_native_value = timed_run_remaining_min(override, dt_util.now())
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self._hass,
                f"{SIGNAL_POWER_DISTRIBUTION_UPDATED}_{self._entry_id}",
                self._update_state,
            )
        )
        self._update_state()
