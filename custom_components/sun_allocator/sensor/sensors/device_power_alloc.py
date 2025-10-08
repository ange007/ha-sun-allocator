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
    SENSOR_NAME_PREFIX,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
)


class SunAllocatorDevicePowerSensor(SensorEntity):
    """Representation of a SunAllocator device power sensor."""

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
        self._device_name = device_config.get(CONF_DEVICE_NAME)

        self._attr_name = f"{SENSOR_NAME_PREFIX} {self._device_name}"
        self._attr_unique_id = f"{entry_id}_{self._device_id}"
        self._state = 0.0


    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=self._device_name,
            manufacturer="Sun Allocator",
            via_device=(DOMAIN, self._entry_id),
        )


    @callback
    def _update_state(self):
        """Update the sensor's state."""
        if not self._hass.data.get(DOMAIN) or not self._hass.data[DOMAIN].get(
            self._entry_id
        ):
            return

        data = self._hass.data[DOMAIN][self._entry_id]
        pd_data = data.get(CONF_POWER_DISTRIBUTION, {})
        device_status = data.get("device_status", {})
        filter_reasons = data.get("device_filter_reasons", {})

        # Get allocated power for this device
        allocated_power = (pd_data.get("allocation", {}) or {}).get(
            self._device_id, 0.0
        )
        self._attr_native_value = round(float(allocated_power), 1)

        # Get other attributes for this device
        status = device_status.get(self._device_id, {}) or {}
        self._attr_extra_state_attributes = {
            "priority": status.get("priority"),
            "power_percent": status.get("percent_actual"),
            "reason": status.get("reason", filter_reasons.get(self._device_id)),
            "device_id": self._device_id,
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
        # Initial state update
        self._update_state()
