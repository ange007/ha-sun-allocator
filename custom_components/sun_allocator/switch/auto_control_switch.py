"""Auto-control runtime switch entity for SunAllocator devices."""

from __future__ import annotations
from typing import Any

import homeassistant.util.dt as dt_util

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from ..core.entity_control import async_turn_off_entity
from ..core.logger import log_error
from ..const import (
    DOMAIN,
    CONF_DEVICE_ID,
    CONF_DEVICE_ENTITY,
    CONF_DEVICES,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_POWER_ALLOCATION,
    CONF_POWER_DISTRIBUTION,
    CONF_DEVICE_TURN_OFF_ON_AUTO_CONTROL_DISABLE,
)
from ..sensor.utils import get_device_info


class SunAllocatorDeviceAutoControlSwitch(SwitchEntity, RestoreEntity):
    """Runtime toggle for auto-control of a single device.

    State precedence on startup: RestoreEntity (last user state) > config value.
    Toggling persists to the config entry without triggering a reload (via the
    `_skip_reload` flag consumed by the entry update listener).
    """

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
        self._is_on = bool(device_config.get(CONF_AUTO_CONTROL_ENABLED, True))

    @property
    def device_info(self) -> DeviceInfo:
        return get_device_info(self._hass, self._device_config, self._entry_id)

    @property
    def is_on(self) -> bool:
        return self._is_on

    def _entry_data(self) -> dict | None:
        """Return entry_data dict or None if not available."""
        return self._hass.data.get(DOMAIN, {}).get(self._entry_id)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in ("on", STATE_OFF):
            self._is_on = last_state.state != STATE_OFF
        entry_data = self._entry_data()
        if entry_data is not None:
            entry_data.setdefault("auto_control_switches", {})[self._device_id] = self

    async def async_will_remove_from_hass(self) -> None:
        entry_data = self._entry_data()
        if entry_data is not None:
            entry_data.get("auto_control_switches", {}).pop(self._device_id, None)

    def sync_state(self, is_on: bool) -> None:
        """Sync state from config flow without persisting back to the config entry."""
        self._is_on = is_on
        self.async_write_ha_state()

    async def _turn_off_device_on_disable(self) -> None:
        """Immediately turn off the managed entity when the device opts into it."""
        if not self._device_config.get(CONF_DEVICE_TURN_OFF_ON_AUTO_CONTROL_DISABLE):
            return

        relay_entity = self._device_config.get(CONF_DEVICE_ENTITY)
        if not relay_entity:
            return

        try:
            await async_turn_off_entity(self._hass, relay_entity, blocking=False)
        except Exception as exc:
            log_error(
                "Failed to force turn off %s when disabling auto-control: %s",
                relay_entity,
                exc,
            )

        entry_data = self._hass.data.get(DOMAIN, {}).get(self._entry_id)
        if entry_data is None:
            return

        now = dt_util.now()
        entry_data.setdefault("device_on_state", {})[self._device_id] = False
        entry_data.get("manual_overrides", {}).pop(self._device_id, None)
        entry_data.setdefault("last_controlled_at", {})[self._device_id] = now

        device_on_time_state = entry_data.setdefault("device_on_time_state", {})
        timing = device_on_time_state.setdefault(self._device_id, {})
        timing.pop("last_on_time", None)
        timing.pop("startup_until", None)
        timing["last_off_time"] = now

        power_allocation = entry_data.get(CONF_POWER_ALLOCATION, {})
        if self._device_id in power_allocation:
            power_allocation[self._device_id] = 0.0

        power_distribution = entry_data.get(CONF_POWER_DISTRIBUTION, {})
        allocation = power_distribution.get("allocation")
        if isinstance(allocation, dict):
            allocation[self._device_id] = 0.0

        status_entry = entry_data.get("device_status", {}).get(self._device_id)
        if status_entry is not None:
            status_entry["is_enabled"] = False
            status_entry["last_off_time"] = now

    async def _persist_to_config(self, is_on: bool) -> None:
        """Persist new auto-control state and refresh listeners without reloading."""
        config_entry = self._hass.config_entries.async_get_entry(self._entry_id)
        if config_entry is None:
            return
        devices = list(config_entry.data.get(CONF_DEVICES, []))
        changed = False
        for i, dev in enumerate(devices):
            if dev.get(CONF_DEVICE_ID) == self._device_id:
                if dev.get(CONF_AUTO_CONTROL_ENABLED) != is_on:
                    devices[i] = {**dev, CONF_AUTO_CONTROL_ENABLED: is_on}
                    self._device_config = devices[i]
                    changed = True
                break
        if changed:
            entry_data = self._entry_data() or {}
            entry_data["_skip_reload"] = True
            self._hass.config_entries.async_update_entry(
                config_entry, data={**config_entry.data, CONF_DEVICES: devices}
            )
            from .. import setup_auto_control

            await setup_auto_control(self._hass, config_entry)

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._is_on = True
        entry_data = self._entry_data()
        if entry_data:
            entry_data.get("manual_overrides", {}).pop(self._device_id, None)
        self.async_write_ha_state()
        await self._persist_to_config(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._is_on = False
        await self._turn_off_device_on_disable()
        self.async_write_ha_state()
        await self._persist_to_config(False)
