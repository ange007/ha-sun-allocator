"""Status sensor for a single device managed by SunAllocator."""

from __future__ import annotations
from typing import Any, Dict

from homeassistant.core import HomeAssistant, callback
from homeassistant.components.sensor import SensorDeviceClass

from ...const import DOMAIN, CONF_POWER_DISTRIBUTION
from ..utils import build_device_status, is_device_auto_control_enabled, DEVICE_STATUS_OPTIONS
from .base_device import BaseSunAllocatorDeviceSensor


class SunAllocatorDeviceStatusSensor(BaseSunAllocatorDeviceSensor):
    """Text status sensor for a SunAllocator device."""

    _attr_has_entity_name = True
    _attr_translation_key = "device_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = DEVICE_STATUS_OPTIONS
    _attr_icon = "mdi:information-outline"

    def __init__(
        self, hass: HomeAssistant, entry_id: str, device_config: Dict[str, Any]
    ):
        super().__init__(hass, entry_id, device_config)
        self._attr_unique_id = f"{entry_id}_{self._device_id}_status"

    @callback
    def _update_state(self):
        data = self._hass.data.get(DOMAIN, {}).get(self._entry_id)
        if not data:
            return

        pd_data = data.get(CONF_POWER_DISTRIBUTION, {})
        device_status = data.get("device_status", {})

        allocated_power = float(
            (pd_data.get("allocation", {}) or {}).get(self._device_id, 0.0)
        )
        auto_control_on = is_device_auto_control_enabled(
            data.get("config", {}), self._device_id
        )
        st = device_status.get(self._device_id, {}) or {}

        self._attr_native_value = build_device_status(
            self._device_id, device_status, allocated_power, auto_control_on,
        )
        retry_count = st.get("retry_count", 0)
        self._attr_extra_state_attributes = {
            "priority": st.get("priority"),
            "auto_control": auto_control_on,
            "manual_override": st.get("manual_override", False),
            "is_active": allocated_power > 0,
            "is_enabled": st.get("is_enabled", False),
            "is_candidate": st.get("is_active_candidate"),
            "actual_power_w": st.get("actual_power_w"),
            "active_feedback_sensor": st.get("active_feedback_sensor"),
            "actual_power_valid": st.get("actual_power_valid"),
            "actual_power_source": st.get("actual_power_source"),
            "is_consuming": st.get("is_consuming"),
            "battery_soc": st.get("battery_soc"),
            "battery_soc_sensor": st.get("battery_soc_sensor"),
            "battery_soc_valid": st.get("battery_soc_valid"),
            "min_battery_soc": st.get("min_battery_soc"),
            "battery_soc_blocked": st.get("battery_soc_blocked", False),
            "mode": st.get("mode"),
            "last_on_time": st.get("last_on_time"),
            "last_off_time": st.get("last_off_time"),
            "retry_count": retry_count if retry_count > 0 else None,
        }
        self.async_write_ha_state()
