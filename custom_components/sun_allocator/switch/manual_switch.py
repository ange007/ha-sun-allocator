"""Manual on/off proxy switch for a SunAllocator device.

Lets the user flip the controlled entity straight from the SunAllocator device card
(the real entity usually lives on a different device). It mirrors the controlled
entity's live state; toggling it commands that entity on/off.

Turning ON always creates a sticky ``manual_on`` override (forces the device on,
ignoring the schedule). Turning OFF is asymmetric by design:
- If an override is currently forcing the device ON (plain ``manual_on`` or an active
  timed run) — OFF means "release my override", so it's cleared entirely and
  auto-control decides from the next cycle (may turn back on if conditions allow).
- If there is no override (the device was simply auto-controlled, on or off) — OFF
  means "I want it off regardless of auto's opinion", so it creates a sticky
  ``manual_off`` that auto-control won't undo (matches flipping the underlying entity).
"""

from __future__ import annotations

from typing import Any

import homeassistant.util.dt as dt_util
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_UNKNOWN, STATE_UNAVAILABLE
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event

from ..const import DOMAIN, CONF_DEVICE_ID, CONF_DEVICE_ENTITY, CONF_DEVICE_NAME
from ..core.entity_control import (
    turn_on_entity,
    turn_off_entity,
    parse_relay_entity,
    is_entity_on,
)
from ..sensor.utils import get_device_info


class SunAllocatorDeviceManualSwitch(SwitchEntity):
    """Proxy toggle that drives the controlled entity directly from the device card."""

    _attr_has_entity_name = True
    _attr_translation_key = "manual_switch"
    _attr_icon = "mdi:toggle-switch"
    _attr_should_poll = False

    def __init__(self, hass, entry_id: str, device_config: dict[str, Any]) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._device_id = device_config.get(CONF_DEVICE_ID)
        self._device_config = device_config
        self._attr_unique_id = f"{entry_id}_{self._device_id}_manual_switch"
        self._relay_entity, self._hvac_mode = parse_relay_entity(
            device_config.get(CONF_DEVICE_ENTITY)
        )
        self._unsub = None

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
    def is_on(self) -> bool:
        if not self._relay_entity:
            return False
        state = self._hass.states.get(self._relay_entity)
        if state is None:
            return False
        domain = self._relay_entity.split(".")[0]
        return is_entity_on(domain, state)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._relay_entity:
            self._unsub = async_track_state_change_event(
                self._hass, [self._relay_entity], self._on_source_change
            )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    @callback
    def _on_source_change(self, _event) -> None:
        """Mirror the controlled entity's state onto this proxy switch."""
        self.async_write_ha_state()

    def _register_manual_override(self, on: bool) -> None:
        """Record a sticky manual override EXPLICITLY (no reliance on the external-change
        heuristic), so the choice takes effect on the very next allocation cycle without
        racing the schedule/usability filter."""
        entry_data = self._hass.data.get(DOMAIN, {}).get(self._entry_id)
        if entry_data is None or not self._device_id:
            return
        # Don't record an override for an entity that isn't actually controllable now —
        # avoids a sticky override on a ghost/unavailable entity the allocator can't drive.
        st = self._hass.states.get(self._relay_entity) if self._relay_entity else None
        if st is None or st.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        now = dt_util.now()
        entry_data.setdefault("manual_overrides", {})[self._device_id] = {
            "since": now,
            "state": on,
        }
        entry_data.setdefault("device_on_state", {})[self._device_id] = on
        # We are the ones commanding the relay — stamp (not clear) last_controlled_at so
        # a slow-to-confirm entity (cloud/Tuya lag) is read as "still catching up to our
        # own command" rather than a user toggle, which would otherwise immediately
        # clobber this override with a stale actual-state reading (race condition).
        entry_data.setdefault("last_controlled_at", {})[self._device_id] = now
        if not on:
            self._close_on_time_session(entry_data, now)

    def _close_on_time_session(self, entry_data: dict, now) -> None:
        """Fold an in-progress on-time session when WE command the device OFF here,
        directly. This bypasses the allocator's own gates (which normally close the
        session on an on→off transition), so without this the runtime sensor would
        silently drop the just-finished session. Delegates to the shared helper so the
        accounting is identical to every allocator-driven off-path."""
        from ..core.power_processor import _close_on_time_session

        on_time_state = entry_data.setdefault("device_on_time_state", {})
        _close_on_time_session(on_time_state, self._device_id, now)

    def _release_override_or_force_off(self) -> None:
        """OFF-button semantics (see module docstring): release an active forced-ON
        override (plain manual_on or timed run) back to auto, or — if there wasn't
        one — record a fresh sticky manual_off."""
        entry_data = self._hass.data.get(DOMAIN, {}).get(self._entry_id)
        if entry_data is None or not self._device_id:
            return
        overrides = entry_data.setdefault("manual_overrides", {})
        existing = overrides.get(self._device_id)
        if existing and existing.get("state"):
            now = dt_util.now()
            overrides.pop(self._device_id, None)
            entry_data.setdefault("device_on_state", {})[self._device_id] = False
            entry_data.setdefault("last_controlled_at", {})[self._device_id] = now
            self._close_on_time_session(entry_data, now)
            return
        self._register_manual_override(False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        if not self._relay_entity:
            return
        self._register_manual_override(True)
        await turn_on_entity(
            self._hass, self._relay_entity, self._hvac_mode,
            self._device_config.get(CONF_DEVICE_NAME, ""),
        )
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if not self._relay_entity:
            return
        self._release_override_or_force_off()
        await turn_off_entity(
            self._hass, self._relay_entity, self._device_config.get(CONF_DEVICE_NAME, "")
        )
        self.async_write_ha_state()
