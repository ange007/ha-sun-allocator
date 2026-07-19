"""Accumulated daily run-time sensor for a single SunAllocator device."""

from __future__ import annotations
from typing import Any, Dict

import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant, callback
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import UnitOfTime

from ...const import (
    DOMAIN,
    SIGNAL_POWER_DISTRIBUTION_UPDATED,
    CONF_DEVICE_ID,
)
from ..utils import get_device_info


class SunAllocatorDeviceRuntimeSensor(SensorEntity):
    """Minutes the device has run today (completed sessions + current one)."""

    _attr_has_entity_name = True
    _attr_translation_key = "runtime"
    _attr_icon = "mdi:timer-outline"
    _attr_should_poll = False
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(
        self, hass: HomeAssistant, entry_id: str, device_config: Dict[str, Any]
    ) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._device_id = device_config.get(CONF_DEVICE_ID)
        self._device_config = device_config
        self._attr_unique_id = f"{entry_id}_{self._device_id}_runtime"

    @property
    def device_info(self) -> DeviceInfo:
        return get_device_info(self._hass, self._device_config, self._entry_id)

    @callback
    def _update_state(self):
        data = self._hass.data.get(DOMAIN, {}).get(self._entry_id)
        if not data:
            return
        # Deferred import: power_processor imports sensor.utils, so a module-level import
        # here would be circular during package initialization.
        from ...core.power_processor import _daily_on_time_sec

        on_time_state = data.get("device_on_time_state", {})
        currently_on = bool(data.get("device_on_state", {}).get(self._device_id))
        secs = _daily_on_time_sec(on_time_state, self._device_id, dt_util.now(), currently_on)
        self._attr_native_value = round(secs / 60.0, 1)
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
