"""Sensor for power allocated to a single device by SunAllocator."""

from __future__ import annotations
from typing import Any, Dict

from homeassistant.core import HomeAssistant, callback
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import UnitOfPower
from homeassistant.helpers.entity import DeviceInfo

from ...const import (
    DOMAIN,
    CONF_POWER_DISTRIBUTION,
    SIGNAL_POWER_DISTRIBUTION_UPDATED,
    CONF_DEVICE_ID,
    CONF_DEVICE_SCHEDULE_MODE,
    SCHEDULE_MODE_DISABLED,
)
from ..utils import get_device_info, build_device_status


class SunAllocatorDevicePowerSensor(SensorEntity):
    """Representation of a SunAllocator device power sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "device_power"
    _attr_icon = "mdi:power-plug"
    _attr_should_poll = False
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_extra_state_attributes: Dict[str, Any] | None = None

    def __init__(
        self, hass: HomeAssistant, entry_id: str, device_config: Dict[str, Any]
    ):
        """Initialize the sensor."""
        self._hass = hass
        self._entry_id = entry_id
        self._device_id = device_config.get(CONF_DEVICE_ID)
        self._device_config = device_config
        self._schedule_mode = device_config.get(CONF_DEVICE_SCHEDULE_MODE, SCHEDULE_MODE_DISABLED)
        self._attr_unique_id = f"{entry_id}_{self._device_id}_power"
        self._state = 0.0

    @property
    def device_info(self) -> DeviceInfo:
        return get_device_info(self._hass, self._device_config, self._entry_id)

    @callback
    def _update_state(self):
        """Update the sensor's state."""
        data = self._hass.data.get(DOMAIN, {}).get(self._entry_id)
        if not data:
            return

        pd_data = data.get(CONF_POWER_DISTRIBUTION, {})
        device_status = data.get("device_status", {})
        runtime_flags = data.get("device_auto_control_runtime", {})

        allocated_power = float(
            (pd_data.get("allocation", {}) or {}).get(self._device_id, 0.0)
        )
        self._attr_native_value = round(allocated_power, 1)

        auto_control_on = runtime_flags.get(self._device_id, True)
        st = device_status.get(self._device_id, {}) or {}

        self._attr_extra_state_attributes = {
            "power_percent": round(float(st.get("percent_actual") or 0.0), 1),
            "min_expected_w": st.get("min_expected_w"),
            "max_expected_w": st.get("max_expected_w") or None,
            "priority": st.get("priority"),
            "schedule_mode": self._schedule_mode,
            "last_on_time": st.get("last_on_time"),
            "last_off_time": st.get("last_off_time"),
            "status": build_device_status(
                self._device_id, device_status, allocated_power, auto_control_on,
            ),
        }
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self._hass,
                f"{SIGNAL_POWER_DISTRIBUTION_UPDATED}_{self._entry_id}",
                self._update_state,
            )
        )
        self._update_state()
