"""Timed-run number for a SunAllocator device.

A single per-device field "Run Timer (min)". Writing a value > 0 forces the device ON
for that many minutes, ignoring battery + schedule limits; the field reads back the
configured minutes while the run is active and resets to 0 when it ends (see
``core/timed_run.py``). The live count-down is exposed by a separate read-only sensor.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNKNOWN, STATE_UNAVAILABLE, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo

from ..const import (
    DOMAIN,
    SIGNAL_POWER_DISTRIBUTION_UPDATED,
    CONF_DEVICE_ID,
    CONF_DEVICE_ENTITY,
)
from ..core.entity_control import parse_relay_entity
from ..core.timed_run import start_timed_run, cancel_timed_run, is_timed_override
from ..sensor.utils import get_device_info

TIMED_RUN_MAX_MIN = 720


class SunAllocatorDeviceTimedRunNumber(NumberEntity):
    """Per-device 'run for N minutes, ignoring battery + schedule' control."""

    _attr_has_entity_name = True
    _attr_translation_key = "timed_run"
    _attr_icon = "mdi:timer-play"
    _attr_should_poll = False
    _attr_native_min_value = 0
    _attr_native_max_value = TIMED_RUN_MAX_MIN
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, device_config: dict[str, Any]
    ) -> None:
        self._hass = hass
        self._config_entry = config_entry
        self._entry_id = config_entry.entry_id
        self._device_id = device_config.get(CONF_DEVICE_ID)
        self._device_config = device_config
        self._attr_unique_id = f"{self._entry_id}_{self._device_id}_timed_run"
        self._relay_entity, _ = parse_relay_entity(device_config.get(CONF_DEVICE_ENTITY))

    @property
    def device_info(self) -> DeviceInfo:
        return get_device_info(self._hass, self._device_config, self._entry_id)

    @property
    def available(self) -> bool:
        if not self._relay_entity:
            return False
        state = self._hass.states.get(self._relay_entity)
        return state is not None and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)

    @property
    def native_value(self) -> float:
        """Configured minutes while a timed run is active, else 0."""
        data = self._hass.data.get(DOMAIN, {}).get(self._entry_id)
        if not data:
            return 0.0
        override = data.get("manual_overrides", {}).get(self._device_id)
        if is_timed_override(override):
            return float(override.get("timer_minutes") or 0)
        return 0.0

    async def async_set_native_value(self, value: float) -> None:
        minutes = int(value)
        if minutes > 0:
            await start_timed_run(self._hass, self._config_entry, self._device_config, minutes)
        else:
            await cancel_timed_run(self._hass, self._config_entry, self._device_id)
        self.async_write_ha_state()

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self._hass,
                f"{SIGNAL_POWER_DISTRIBUTION_UPDATED}_{self._entry_id}",
                self._on_update,
            )
        )
