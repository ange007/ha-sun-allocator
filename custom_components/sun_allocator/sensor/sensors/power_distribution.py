
"""Power Distribution sensor for SunAllocator.
Provides overview of total allocated power with per-device allocation in W and % plus metadata.
"""
from __future__ import annotations
from typing import Any, Dict

from homeassistant.core import HomeAssistant, callback
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import UnitOfPower

from ...utils.logger import log_debug
from ...utils.journal import journal_event

from ...const import (
    DOMAIN,
    CONF_POWER_DISTRIBUTION,
    SIGNAL_POWER_DISTRIBUTION_UPDATED,
    SENSOR_NAME_PREFIX,
    SENSOR_ID_PREFIX,
)

class SunAllocatorPowerDistributionSensor(SensorEntity):
    _attr_icon = "mdi:flash"

    def __init__(self, hass: HomeAssistant, entry_id: str):
        self._hass = hass
        self._entry_id = entry_id
        # Try to extract a numeric suffix from entry_id, fallback to entry_id
        numeric_suffix = None
        if entry_id.isdigit():
            numeric_suffix = entry_id
        else:
            import re
            m = re.search(r'(\d+)$', entry_id)
            if m:
                numeric_suffix = m.group(1)
            else:
                numeric_suffix = entry_id[-4:]
        self._attr_name = f"{SENSOR_NAME_PREFIX} Power Distribution"
        self._attr_unique_id = f"{SENSOR_ID_PREFIX}_power_distribution_{numeric_suffix}"
        self.entity_id = f"sensor.{SENSOR_ID_PREFIX}_power_distribution_{numeric_suffix}"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._state = 0.0
        self._attr_extra_state_attributes: Dict[str, Any] = {}

    @property
    def should_poll(self) -> bool:
        return False

    @property
    def native_value(self):
        try:
            # Get integration data for this entry
            data = self._hass.data.get(DOMAIN, {}).get(self._entry_id, {})
            pd: Dict[str, Any] = data.get(CONF_POWER_DISTRIBUTION, {}) or {}
            device_status: Dict[str, Any] = data.get("device_status", {}) or {}
            allocation: Dict[str, float] = pd.get("allocation", {}) or {}

            # Get all configured devices from config (for diagnostics)
            config = data.get("config", {})
            all_devices = config.get("devices", []) or []
            all_devices_info = []
            all_device_ids = []
            ha_entity_ids = set(e.entity_id for e in self._hass.states.async_all())
            for d in all_devices:
                dev_id = d.get("id") or d.get("device_id") or d.get("entity_id")
                entity_id = d.get("entity_id") or d.get("esphome_relay_entity") or d.get("device_entity")
                device_type = d.get("type") or d.get("device_type")
                name = d.get("name") or d.get("device_name")
                reason = None
                if not entity_id:
                    reason = "No entity_id configured"
                elif entity_id not in ha_entity_ids:
                    reason = "Entity not found in Home Assistant"
                elif dev_id not in device_status:
                    reason = "Not present in device_status (possibly filtered/skipped)"
                all_devices_info.append({
                    "id": dev_id,
                    "name": name,
                    "entity_id": entity_id,
                    "type": device_type,
                    "in_device_status": dev_id in device_status,
                    "reason": reason,
                })
                if entity_id:
                    all_device_ids.append(entity_id)
            # If no devices in config, fallback to device_status keys
            if not all_devices_info:
                for dev_id in device_status.keys():
                    all_devices_info.append({
                        "id": dev_id,
                        "name": device_status[dev_id].get("name"),
                        "entity_id": device_status[dev_id].get("entity_id"),
                        "type": device_status[dev_id].get("type"),
                        "in_device_status": True,
                        "reason": None,
                    })
                    all_device_ids.append(device_status[dev_id].get("entity_id"))
            not_found_entities = [eid for eid in all_device_ids if eid not in ha_entity_ids]

            total = float(pd.get("total_power", 0.0) or 0.0)
            remaining = float(pd.get("remaining_power", 0.0) or 0.0)
            allocated = float(pd.get("allocated_power", total - remaining) or 0.0)

            allocation_percent: Dict[str, float] = {}
            for dev_id, st in device_status.items():
                pct = st.get("percent_actual")
                if pct is None:
                    pct = st.get("percent_target", 0.0)
                try:
                    allocation_percent[dev_id] = float(pct or 0.0)
                except (TypeError, ValueError):
                    allocation_percent[dev_id] = 0.0

            # Diagnostic reasons for each device
            reasons = {}
            for dev_id, st in device_status.items():
                reason = []
                if st.get("auto_control_enabled") is False:
                    reason.append("Auto control disabled")
                if st.get("schedule_enabled") and not st.get("schedule_active", True):
                    reason.append("Out of schedule")
                if st.get("allocated_w", 0) < st.get("min_expected_w", 0):
                    reason.append("Not enough excess power")
                if st.get("manual_override", False):
                    reason.append("Manual override")
                if not reason and st.get("percent_actual", 0) > 0:
                    reason.append("Active")
                reasons[dev_id] = ", ".join(reason)

            # Add debug logging for troubleshooting
            log_debug("SunAllocatorPowerDistributionSensor data: %s", data)
            journal_event("power_distribution_status", {
                "total": total,
                "remaining": remaining,
                "allocated": allocated,
                "allocation": allocation,
                "allocation_percent": allocation_percent,
                "device_meta": device_status,
                "reasons": reasons,
                "diagnostics": {
                    "all_devices_info": all_devices_info,
                    "visible_devices": list(device_status.keys()),
                    "not_found_entities": not_found_entities,
                    "device_count": len(all_devices_info),
                    "visible_count": len(device_status),
                    "raw_data_keys": list(data.keys()),
                },
            })

            # Compose extra state attributes, including diagnostics
            self._attr_extra_state_attributes = {
                "total_power": total,
                "remaining_power": remaining,
                "allocated_power": allocated,
                "allocation_w": allocation,
                "allocation_percent": allocation_percent,
                "device_meta": device_status,
                "reasons": reasons,
                "diagnostics": {
                    "all_devices_info": all_devices_info,
                    "visible_devices": list(device_status.keys()),
                    "not_found_entities": not_found_entities,
                    "device_count": len(all_devices_info),
                    "visible_count": len(device_status),
                    "raw_data_keys": list(data.keys()),
                },
            }

            self._state = allocated
            return self._state
        except Exception as e:
            log_debug("PowerDistribution sensor error: %s", e)
            journal_event("power_distribution_error", {"error": str(e)})
            return self._state

    async def async_added_to_hass(self):
        @callback
        def _update(*_):
            self.async_schedule_update_ha_state(True)
        # Subscribe to dispatcher updates
        self._unsub = async_dispatcher_connect(
            self._hass, f"{SIGNAL_POWER_DISTRIBUTION_UPDATED}_{self._entry_id}", _update
        )
        # Initial update
        self.async_schedule_update_ha_state(True)

    async def async_will_remove_from_hass(self) -> None:
        # Unsubscribe from dispatcher if set
        unsub = getattr(self, "_unsub", None)
        if unsub:
            try:
                unsub()
            except Exception:
                pass
            self._unsub = None
