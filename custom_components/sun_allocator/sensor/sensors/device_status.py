"""Status sensor for a single device managed by SunAllocator."""

from __future__ import annotations
from typing import Any, Dict

from homeassistant.core import HomeAssistant, callback
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo

from ...const import (
    DOMAIN,
    CONF_POWER_DISTRIBUTION,
    SIGNAL_POWER_DISTRIBUTION_UPDATED,
    CONF_DEVICE_ID,
)
from ..utils import get_device_info, build_device_status, DEVICE_STATUS_OPTIONS


class SunAllocatorDeviceStatusSensor(SensorEntity):
    """Text status sensor for a SunAllocator device."""

    _attr_has_entity_name = True
    _attr_translation_key = "device_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = DEVICE_STATUS_OPTIONS
    _attr_icon = "mdi:information-outline"
    _attr_should_poll = False

    def __init__(
        self, hass: HomeAssistant, entry_id: str, device_config: Dict[str, Any]
    ):
        """Initialize the sensor."""
        self._hass = hass
        self._entry_id = entry_id
        self._device_id = device_config.get(CONF_DEVICE_ID)
        self._device_config = device_config
        self._attr_unique_id = f"{entry_id}_{self._device_id}_status"

    @property
    def device_info(self) -> DeviceInfo:
        return get_device_info(self._hass, self._device_config, self._entry_id)

    @callback
    def _update_state(self):
        data = self._hass.data.get(DOMAIN, {}).get(self._entry_id)
        if not data:
            return

        pd_data = data.get(CONF_POWER_DISTRIBUTION, {})
        device_status = data.get("device_status", {})
        runtime_flags = data.get("device_auto_control_runtime", {})

        allocated_power = float(
            (pd_data.get("allocation", {}) or {}).get(self._device_id, 0.0)
        )
        auto_control_on = runtime_flags.get(self._device_id, True)
        st = device_status.get(self._device_id, {}) or {}

        self._attr_native_value = build_device_status(
            self._device_id, device_status, allocated_power, auto_control_on,
        )
        self._attr_extra_state_attributes = {
            "priority": st.get("priority"),
            "auto_control": auto_control_on,
            "manual_override": st.get("manual_override", False),
            "is_active": allocated_power > 0,
            "is_candidate": st.get("is_active_candidate"),
            "mode": st.get("mode"),
            "last_on_time": st.get("last_on_time"),
            "last_off_time": st.get("last_off_time"),
        }
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
