"""Base class for per-device sensors in SunAllocator."""

from __future__ import annotations
from typing import Any, Dict

from homeassistant.core import HomeAssistant, callback
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo

from ...const import CONF_DEVICE_ID, SIGNAL_POWER_DISTRIBUTION_UPDATED
from ..utils import get_device_info


class BaseSunAllocatorDeviceSensor(SensorEntity):
    """Shared base for all per-device SunAllocator sensors."""

    _attr_should_poll = False

    def __init__(
        self, hass: HomeAssistant, entry_id: str, device_config: Dict[str, Any]
    ) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._device_id = device_config.get(CONF_DEVICE_ID)
        self._device_config = device_config

    @property
    def device_info(self) -> DeviceInfo:
        return get_device_info(self._hass, self._device_config, self._entry_id)

    @callback
    def _update_state(self) -> None:
        """Override in subclass to update sensor state and attributes."""

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
