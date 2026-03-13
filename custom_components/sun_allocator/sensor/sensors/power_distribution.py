"""Power Distribution sensor for SunAllocator.
Provides overview of total allocated power with per-device allocation in W and % plus metadata.
"""

from __future__ import annotations
from typing import Any, Dict

from homeassistant.core import HomeAssistant, callback
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import UnitOfPower
from homeassistant.helpers.entity import DeviceInfo

from ...core.logger import log_debug, journal_event

from ...const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_POWER_DISTRIBUTION,
    SENSOR_POWER_DISTRIBUTION_SUFFIX,
    SIGNAL_POWER_DISTRIBUTION_UPDATED,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_DEVICE_ENTITY,
    CONF_AUTO_CONTROL_ENABLED,
)


class SunAllocatorPowerDistributionSensor(SensorEntity):
    """Representation of a SunAllocator power distribution sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = SENSOR_POWER_DISTRIBUTION_SUFFIX
    _attr_icon = "mdi:flash"
    _attr_should_poll = False
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _unsub: Any = None

    def _get_default_attributes(self) -> Dict[str, Any]:
        """Return the default attributes for the sensor."""
        return {
            "total_power": None,
            "remaining_power": None,
            "allocated_power": None,
            "allocation_w": None,
            "allocation_percent": None,
            "device_meta": None,
            "reasons": None,
            "diagnostics": None,
        }


    def __init__(self, hass: HomeAssistant, entry_id: str, entry_index: int):
        """Initialize the sensor."""
        self._hass = hass
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_{SENSOR_POWER_DISTRIBUTION_SUFFIX}"
        self._state = 0.0
        self._attr_extra_state_attributes = self._get_default_attributes()


    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        entry = self._hass.config_entries.async_get_entry(self._entry_id)
        name = entry.title if entry else "SunAllocator"
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=name,
            manufacturer="Sun Allocator",
        )


    @property
    def native_value(self):
        """Return the cached state (updated via async_update)."""
        return self._state

    async def async_update(self) -> None:
        """Compute and cache the sensor state and attributes."""
        try:
            data = self._hass.data.get(DOMAIN, {}).get(self._entry_id, {})
            pd_data: Dict[str, Any] = data.get(CONF_POWER_DISTRIBUTION, {}) or {}
            device_status: Dict[str, Any] = data.get("device_status", {}) or {}
            allocation: Dict[str, float] = pd_data.get("allocation", {}) or {}

            config = data.get("config", {})
            all_devices = config.get(CONF_DEVICES, []) or []

            filter_reasons = data.get("device_filter_reasons", {})
            all_devices_info = []
            all_device_ids = []

            def _entity_exists(eid: str) -> bool:
                """Check if entity exists using individual lookup instead of async_all()."""
                if not eid:
                    return False
                # Strip |hvac_mode suffix for climate entities
                clean_eid = eid.split("|")[0] if "|" in eid else eid
                return self._hass.states.get(clean_eid) is not None

            for dev in all_devices:
                dev_id = dev.get(CONF_DEVICE_ID)
                entity_id = dev.get(CONF_DEVICE_ENTITY)
                device_type = dev.get(CONF_DEVICE_TYPE)
                name = dev.get(CONF_DEVICE_NAME)

                reason = None
                if not entity_id:
                    reason = "No entity_id configured"
                elif not _entity_exists(entity_id):
                    reason = "Entity not found in Home Assistant"
                elif dev_id not in device_status:
                    reason = filter_reasons.get(dev_id, "Filtered (unknown reason)")

                all_devices_info.append({
                    "device_id": dev_id,
                    "name": name,
                    "entity_id": entity_id,
                    "type": device_type,
                    "auto_control": dev.get(CONF_AUTO_CONTROL_ENABLED, "missing"),
                    "in_device_status": (dev_id in device_status) if dev_id else False,
                    "reason": reason,
                })
                if entity_id:
                    all_device_ids.append(entity_id)

            if not all_devices_info:
                for dev_id in device_status:
                    all_devices_info.append({
                        "id": dev_id,
                        "name": device_status[dev_id].get(CONF_DEVICE_NAME),
                        "entity_id": device_status[dev_id].get(CONF_DEVICE_ENTITY),
                        "type": device_status[dev_id].get(CONF_DEVICE_TYPE),
                        "in_device_status": True,
                        "reason": None,
                    })
                    all_device_ids.append(device_status[dev_id].get(CONF_DEVICE_ENTITY))

            not_found_entities = [
                eid for eid in all_device_ids if not _entity_exists(eid)
            ]

            total = float(pd_data.get("total_power", 0.0) or 0.0)
            remaining = float(pd_data.get("remaining_power", 0.0) or 0.0)
            allocated = float(pd_data.get("allocated_power", total - remaining) or 0.0)

            allocation_percent: Dict[str, float] = {}
            for dev_id, st in device_status.items():
                pct = st.get("percent_actual")
                if pct is None:
                    pct = st.get("percent_target", 0.0)
                try:
                    allocation_percent[dev_id] = float(pct or 0.0)
                except (TypeError, ValueError):
                    allocation_percent[dev_id] = 0.0

            reasons = {}
            for dev_id, st in device_status.items():
                reason_list = []
                if st.get(CONF_AUTO_CONTROL_ENABLED) is False:
                    reason_list.append("Auto control disabled")
                if st.get("schedule_enabled") and not st.get("schedule_active", True):
                    reason_list.append("Out of schedule")

                is_active = st.get("allocated_w", 0) > 0
                is_active_candidate = st.get("is_active_candidate")

                if is_active_candidate is not None:
                    if not is_active and not is_active_candidate:
                        reason_list.append("Not enough excess power")
                    elif not is_active and is_active_candidate:
                        reason_list.append("Debouncing")
                    elif is_active and not is_active_candidate:
                        reason_list.append("Debouncing (turning off)")
                elif not is_active and not st.get("manual_override", False):
                    if st.get("allocated_w", 0) < st.get("min_expected_w", 0):
                        reason_list.append("Not enough excess power")

                if st.get("manual_override", False):
                    reason_list.append("Manual override")

                if not reason_list:
                    reason_list.append("Active" if is_active else "Idle")

                reasons[dev_id] = ", ".join(reason_list)

            diagnostics = {
                "all_devices_info": all_devices_info,
                "visible_devices": list(device_status.keys()),
                "not_found_entities": not_found_entities,
                "device_count": len(all_devices_info),
                "visible_count": len(device_status),
                "raw_data_keys": list(data.keys()),
            }

            old_allocated = self._attr_extra_state_attributes.get("allocated_power")
            old_reasons = self._attr_extra_state_attributes.get("reasons")
            if allocated != old_allocated or reasons != old_reasons:
                log_debug("SunAllocatorPowerDistributionSensor state changed")
                journal_event(
                    "power_distribution_status",
                    {
                        "total": total,
                        "remaining": remaining,
                        "allocated": allocated,
                        "allocation": allocation,
                        "allocation_percent": allocation_percent,
                        "device_meta": device_status,
                        "reasons": reasons,
                        "diagnostics": diagnostics,
                    },
                )

            self._attr_extra_state_attributes.update({
                "total_power": total,
                "remaining_power": remaining,
                "allocated_power": allocated,
                "allocation_w": allocation,
                "allocation_percent": allocation_percent,
                "device_meta": {k: dict(v) for k, v in device_status.items()},
                "reasons": reasons,
                "diagnostics": diagnostics,
            })
            self._state = allocated

        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            log_debug("PowerDistribution sensor error: %s", exc)
            journal_event("power_distribution_error", {"error": str(exc)})


    async def async_added_to_hass(self):
        """Handle entity which will be added."""
        await super().async_added_to_hass()

        @callback
        def _update(*_):
            """Schedule a state refresh when dispatcher fires."""
            self.async_schedule_update_ha_state(True)

        self._unsub = async_dispatcher_connect(
            self._hass, f"{SIGNAL_POWER_DISTRIBUTION_UPDATED}_{self._entry_id}", _update
        )
        await self.async_update()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsub:
            try:
                self._unsub()
            except (TypeError, AttributeError):
                pass
            self._unsub = None
