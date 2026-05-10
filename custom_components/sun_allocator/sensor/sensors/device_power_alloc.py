"""Sensor for power allocated to a single device by SunAllocator."""

from __future__ import annotations
from typing import Any, Dict

from homeassistant.core import HomeAssistant, callback
from homeassistant.const import UnitOfPower

from ...const import (
    DOMAIN,
    CONF_POWER_DISTRIBUTION,
    CONF_DEVICE_SCHEDULE_MODE,
    SCHEDULE_MODE_DISABLED,
)
from ..utils import build_device_status, is_device_auto_control_enabled
from .base_device import BaseSunAllocatorDeviceSensor


class SunAllocatorDevicePowerSensor(BaseSunAllocatorDeviceSensor):
    """Representation of a SunAllocator device power sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "device_power"
    _attr_icon = "mdi:power-plug"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_extra_state_attributes: Dict[str, Any] | None = None

    def __init__(
        self, hass: HomeAssistant, entry_id: str, device_config: Dict[str, Any]
    ):
        super().__init__(hass, entry_id, device_config)
        self._schedule_mode = device_config.get(CONF_DEVICE_SCHEDULE_MODE, SCHEDULE_MODE_DISABLED)
        self._attr_unique_id = f"{entry_id}_{self._device_id}_power"

    @callback
    def _update_state(self):
        """Update the sensor's state."""
        data = self._hass.data.get(DOMAIN, {}).get(self._entry_id)
        if not data:
            return

        pd_data = data.get(CONF_POWER_DISTRIBUTION, {})
        device_status = data.get("device_status", {})

        allocated_power = float(
            (pd_data.get("allocation", {}) or {}).get(self._device_id, 0.0)
        )
        self._attr_native_value = round(allocated_power, 1)

        auto_control_on = is_device_auto_control_enabled(
            data.get("config", {}), self._device_id
        )
        st = device_status.get(self._device_id, {}) or {}

        self._attr_extra_state_attributes = {
            "power_percent": round(float(st.get("percent_actual") or 0.0), 1),
            "min_expected_w": st.get("min_expected_w"),
            "max_expected_w": st.get("max_expected_w") or None,
            "actual_power_w": st.get("actual_power_w"),
            "actual_power_sensor": st.get("actual_power_sensor"),
            "active_feedback_sensor": st.get("active_feedback_sensor"),
            "actual_power_valid": st.get("actual_power_valid"),
            "actual_power_source": st.get("actual_power_source"),
            "actual_power_threshold_w": st.get("actual_power_threshold_w"),
            "reserved_w": st.get("reserved_w"),
            "is_consuming": st.get("is_consuming"),
            "priority": st.get("priority"),
            "schedule_mode": self._schedule_mode,
            "last_on_time": st.get("last_on_time"),
            "last_off_time": st.get("last_off_time"),
            "status": build_device_status(
                self._device_id, device_status, allocated_power, auto_control_on,
            ),
        }
        self.async_write_ha_state()

