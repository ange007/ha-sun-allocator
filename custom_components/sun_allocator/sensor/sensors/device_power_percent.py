"""Power percent sensor for a single device managed by SunAllocator."""

from __future__ import annotations
from typing import Any, Dict

from homeassistant.core import HomeAssistant, callback
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import PERCENTAGE

from ...const import (
    DOMAIN,
    CONF_POWER_DISTRIBUTION,
    SIGNAL_POWER_DISTRIBUTION_UPDATED,
    CONF_DEVICE_ID,
)
from ..utils import get_device_info


class SunAllocatorDevicePowerPercentSensor(SensorEntity):
    """Power usage percent sensor for a SunAllocator device."""

    _attr_has_entity_name = True
    _attr_translation_key = "device_power_percent"
    _attr_icon = "mdi:gauge"
    _attr_should_poll = False
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, hass: HomeAssistant, entry_id: str, device_config: Dict[str, Any]
    ):
        self._hass = hass
        self._entry_id = entry_id
        self._device_id = device_config.get(CONF_DEVICE_ID)
        self._device_config = device_config
        self._attr_unique_id = f"{entry_id}_{self._device_id}_power_percent"

    @property
    def device_info(self) -> DeviceInfo:
        return get_device_info(self._hass, self._device_config, self._entry_id)

    @callback
    def _update_state(self):
        data = self._hass.data.get(DOMAIN, {}).get(self._entry_id)
        if not data:
            return

        device_status = data.get("device_status", {})
        st = device_status.get(self._device_id, {}) or {}
        self._attr_native_value = round(float(st.get("percent_actual") or 0.0), 1)
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
