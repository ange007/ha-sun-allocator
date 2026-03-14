"""Auto-control runtime switch entity for SunAllocator devices."""

from __future__ import annotations
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from ..const import (
    DOMAIN,
    CONF_DEVICE_ID,
    CONF_DEVICES,
    CONF_AUTO_CONTROL_ENABLED,
)
from ..sensor.utils import get_device_info


class SunAllocatorDeviceAutoControlSwitch(SwitchEntity, RestoreEntity):
    """Runtime toggle for auto-control of a single device."""

    _attr_has_entity_name = True
    _attr_translation_key = "auto_control"
    _attr_icon = "mdi:auto-fix"
    _attr_should_poll = False

    def __init__(self, hass, entry_id: str, device_config: dict[str, Any]) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._device_id = device_config.get(CONF_DEVICE_ID)
        self._device_config = device_config
        self._attr_unique_id = f"{entry_id}_{self._device_id}_auto_control"
        self._is_on = True

    @property
    def device_info(self) -> DeviceInfo:
        return get_device_info(self._hass, self._device_config, self._entry_id)

    @property
    def is_on(self) -> bool:
        return self._is_on

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._is_on = last_state.state != STATE_OFF
        self._write_runtime_flag()
        entry_data = self._hass.data.get(DOMAIN, {}).get(self._entry_id)
        if entry_data is not None:
            entry_data.setdefault("auto_control_switches", {})[self._device_id] = self

    async def async_will_remove_from_hass(self) -> None:
        entry_data = self._hass.data.get(DOMAIN, {}).get(self._entry_id)
        if entry_data is not None:
            entry_data.get("auto_control_switches", {}).pop(self._device_id, None)

    def _write_runtime_flag(self) -> None:
        entry_data = self._hass.data.get(DOMAIN, {}).get(self._entry_id)
        if entry_data is not None:
            entry_data.setdefault("device_auto_control_runtime", {})[self._device_id] = self._is_on

    def sync_state(self, is_on: bool) -> None:
        """Sync state from config flow without persisting to config entry."""
        self._is_on = is_on
        self._write_runtime_flag()
        self.async_write_ha_state()

    async def _persist_to_config(self, is_on: bool) -> None:
        """Persist new auto_control state to config entry (skips reload)."""
        config_entry = self._hass.config_entries.async_get_entry(self._entry_id)
        if config_entry is None:
            return
        devices = list(config_entry.data.get(CONF_DEVICES, []))
        changed = False
        for i, dev in enumerate(devices):
            if dev.get(CONF_DEVICE_ID) == self._device_id:
                if dev.get(CONF_AUTO_CONTROL_ENABLED) != is_on:
                    devices[i] = {**dev, CONF_AUTO_CONTROL_ENABLED: is_on}
                    changed = True
                break
        if changed:
            entry_data = self._hass.data.get(DOMAIN, {}).get(self._entry_id, {})
            entry_data["_skip_reload"] = True
            self._hass.config_entries.async_update_entry(
                config_entry, data={**config_entry.data, CONF_DEVICES: devices}
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._is_on = True
        self._write_runtime_flag()
        entry_data = self._hass.data.get(DOMAIN, {}).get(self._entry_id)
        if entry_data:
            entry_data.get("manual_overrides", {}).pop(self._device_id, None)
        self.async_write_ha_state()
        await self._persist_to_config(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._is_on = False
        self._write_runtime_flag()
        self.async_write_ha_state()
        await self._persist_to_config(False)
