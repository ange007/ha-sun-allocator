"""Config entry data migrations for SunAllocator.

Each migration is registered as its own method on :class:`ConfigEntryMigrator`
and tagged with the integration version that introduced it. Migrations are
idempotent: re-running them on already-migrated data is a no-op. Once the
oldest supported user version moves past a migration, that method can be
deleted from this file in isolation.

Add a new migration by:
1. Writing a method ``_migrate_<short_name>`` that returns the (possibly
   mutated) ``data`` dict.
2. Setting ``self.changed = True`` if the method actually rewrote anything.
3. Adding a call to it from :meth:`run` *after* prior migrations.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ..const import (
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_ESPHOME_MODE_SELECT_ENTITY,
    CONF_DEVICE_CONTROL_MODE,
    CONTROL_MODE_ON_OFF,
    CONTROL_MODE_PROPORTIONAL,
    CONF_DEVICE_START_BATTERY_SOC,
    CONF_DEVICE_STOP_BATTERY_SOC,
    DEFAULT_DEVICE_STOP_BATTERY_SOC,
    CONF_DEVICE_SCHEDULE_MODE,
    CONF_MPPT_INPUTS,
    CONF_PV_POWER,
    CONF_PV_VOLTAGE,
    CONF_PANEL_VMP,
    CONF_PANEL_IMP,
    CONF_PANEL_VOC,
    CONF_PANEL_ISC,
    CONF_PANEL_COUNT,
    CONF_PANEL_CONFIGURATION,
    CONF_CALCULATION_METHOD,
    DEFAULT_CALCULATION_METHOD,
    SCHEDULE_MODE_DISABLED,
    SCHEDULE_MODE_STANDARD,
)
from .logger import log_info


class ConfigEntryMigrator:
    """Run all applicable data migrations against a single config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.changed = False

    async def run(self) -> bool:
        """Apply migrations in order. Persists the entry if any migration mutated data.

        Returns ``True`` if data was rewritten.
        """
        data = dict(self.entry.data)

        # --- Migrations: oldest first. Each method is tagged with the version
        # it was introduced in via its docstring; remove once that version is
        # below the integration's minimum supported install age.
        data = self._migrate_schedule_enabled_to_mode(data)
        data = self._migrate_flat_solar_to_mppt_inputs(data)
        data = self._migrate_add_calculation_method(data)
        data = self._migrate_add_control_mode(data)
        data = self._migrate_soc_start_stop(data)
        data = self._migrate_prune_dead_options(data)

        if self.changed:
            self.hass.config_entries.async_update_entry(self.entry, data=data)
        return self.changed

    # --- Migrations ----------------------------------------------------------

    def _migrate_schedule_enabled_to_mode(self, data: dict) -> dict:
        """Added in v1.0.5.

        Per-device ``schedule_enabled`` (bool) was replaced with
        ``schedule_mode`` (``disabled`` / ``standard`` / ``helper``). Existing
        installs would otherwise lose their schedules silently because the old
        key is no longer read anywhere.

        - ``schedule_enabled: True``  → ``schedule_mode: standard``
        - ``schedule_enabled: False`` → ``schedule_mode: disabled``
        - ``schedule_mode`` already present → leave untouched.
        """
        old_key = "schedule_enabled"
        devices = data.get(CONF_DEVICES, []) or []
        if not any(old_key in dev for dev in devices):
            return data

        new_devices = []
        for dev in devices:
            if old_key not in dev:
                new_devices.append(dev)
                continue
            old_value = dev[old_key]
            new_dev = {k: v for k, v in dev.items() if k != old_key}
            # Don't clobber an explicitly-set new value (defensive: shouldn't happen).
            new_dev.setdefault(
                CONF_DEVICE_SCHEDULE_MODE,
                SCHEDULE_MODE_STANDARD if old_value else SCHEDULE_MODE_DISABLED,
            )
            new_devices.append(new_dev)
            self.changed = True
            log_info(
                "[migrate v1.0.5] device %s: schedule_enabled=%s -> schedule_mode=%s",
                dev.get(CONF_DEVICE_ID),
                old_value,
                new_dev[CONF_DEVICE_SCHEDULE_MODE],
            )
        return {**data, CONF_DEVICES: new_devices}

    def _migrate_add_calculation_method(self, data: dict) -> dict:
        """Added in v1.2.0.

        Backfill the new ``calculation_method`` selector with the default
        (``mppt``) so existing installs keep their current behaviour and the
        Advanced Settings form pre-fills correctly. No-op once the key exists.
        """
        if CONF_CALCULATION_METHOD in data:
            return data
        data = {**data, CONF_CALCULATION_METHOD: DEFAULT_CALCULATION_METHOD}
        self.changed = True
        log_info(
            "[migrate v1.2.0] added calculation_method=%s (default)",
            DEFAULT_CALCULATION_METHOD,
        )
        return data

    def _migrate_add_control_mode(self, data: dict) -> dict:
        """Added in v1.3.0.

        The user-facing device-type selector was collapsed into a per-device
        ``control_mode`` (``on_off`` / ``proportional``), now chosen via the
        entity-picker mode suffix. Backfill existing devices: a device with a
        paired ESPHome mode select is proportional; everything else is on/off.
        No-op once ``control_mode`` is present on every device.
        """
        devices = data.get(CONF_DEVICES, []) or []
        if not devices or all(CONF_DEVICE_CONTROL_MODE in dev for dev in devices):
            return data

        new_devices = []
        for dev in devices:
            if CONF_DEVICE_CONTROL_MODE in dev:
                new_devices.append(dev)
                continue
            control_mode = (
                CONTROL_MODE_PROPORTIONAL
                if dev.get(CONF_ESPHOME_MODE_SELECT_ENTITY)
                else CONTROL_MODE_ON_OFF
            )
            new_devices.append({**dev, CONF_DEVICE_CONTROL_MODE: control_mode})
            self.changed = True
            log_info(
                "[migrate v1.3.0] device %s: control_mode=%s",
                dev.get(CONF_DEVICE_ID),
                control_mode,
            )
        return {**data, CONF_DEVICES: new_devices}

    def _migrate_soc_start_stop(self, data: dict) -> dict:
        """Added in v1.3.0.

        Split the overloaded per-device ``min_battery_soc`` into an asymmetric pair:
          * rename ``min_battery_soc`` → ``start_battery_soc`` (charge-side START gate;
            unchanged meaning);
          * backfill ``stop_battery_soc = 100`` (discharge-side STOP floor; safe default
            = "never discharge the battery for this device" until the user lowers it).
        No-op once every device already carries ``stop_battery_soc``.
        """
        old_key = "min_battery_soc"
        devices = data.get(CONF_DEVICES, []) or []
        if not devices or all(CONF_DEVICE_STOP_BATTERY_SOC in dev for dev in devices):
            return data

        new_devices = []
        for dev in devices:
            new_dev = dict(dev)
            if old_key in new_dev and CONF_DEVICE_START_BATTERY_SOC not in new_dev:
                new_dev[CONF_DEVICE_START_BATTERY_SOC] = new_dev.pop(old_key)
                self.changed = True
            elif old_key in new_dev:
                # Both present (defensive): drop the legacy key, keep the new one.
                new_dev.pop(old_key)
                self.changed = True
            if CONF_DEVICE_STOP_BATTERY_SOC not in new_dev:
                new_dev[CONF_DEVICE_STOP_BATTERY_SOC] = DEFAULT_DEVICE_STOP_BATTERY_SOC
                self.changed = True
            new_devices.append(new_dev)
            log_info(
                "[migrate v1.3.0] device %s: start_battery_soc=%s stop_battery_soc=%s",
                dev.get(CONF_DEVICE_ID),
                new_dev.get(CONF_DEVICE_START_BATTERY_SOC),
                new_dev.get(CONF_DEVICE_STOP_BATTERY_SOC),
            )
        return {**data, CONF_DEVICES: new_devices}

    def _migrate_prune_dead_options(self, data: dict) -> dict:
        """Added in v1.3.0.

        Drop options that no logic reads: the legacy proportional-ramp tunables
        (``ramp_up_step`` / ``ramp_down_step`` / ``ramp_deadband``, replaced by the
        probe) at the top level, and the orphan per-device ``min_excess_power``.
        Idempotent — no-op once none are present.
        """
        dead_top = ("ramp_up_step", "ramp_down_step", "ramp_deadband")
        dead_dev = ("min_excess_power",)
        devices = data.get(CONF_DEVICES, []) or []

        has_top = any(k in data for k in dead_top)
        has_dev = any(k in dev for dev in devices for k in dead_dev)
        if not has_top and not has_dev:
            return data

        new_data = {k: v for k, v in data.items() if k not in dead_top}
        if has_dev:
            new_data[CONF_DEVICES] = [
                {k: v for k, v in dev.items() if k not in dead_dev} for dev in devices
            ]
        self.changed = True
        log_info(
            "[migrate v1.3.0] pruned dead options: top=%s device=%s",
            [k for k in dead_top if k in data],
            [k for k in dead_dev if has_dev],
        )
        return new_data

    def _migrate_flat_solar_to_mppt_inputs(self, data: dict) -> dict:
        """Added in v1.0.8.

        Flat solar keys (``pv_power``, ``vmp``, ``imp``, ...) are wrapped into
        a single-element list under ``mppt_inputs`` to enable multi-MPPT
        support. The flat keys are removed from top level afterwards.

        - ``mppt_inputs`` already present → no-op (already migrated).
        - ``pv_power`` missing or empty string → no-op (entry has no solar
          config; defensive — should not happen for fully-configured entries).
        """
        if CONF_MPPT_INPUTS in data:
            return data
        if not data.get(CONF_PV_POWER):
            return data

        flat_keys = [
            CONF_PV_POWER,
            CONF_PV_VOLTAGE,
            CONF_PANEL_VMP,
            CONF_PANEL_IMP,
            CONF_PANEL_VOC,
            CONF_PANEL_ISC,
            CONF_PANEL_COUNT,
            CONF_PANEL_CONFIGURATION,
        ]
        mppt_entry = {k: data[k] for k in flat_keys if k in data}

        new_data = {k: v for k, v in data.items() if k not in flat_keys}
        new_data[CONF_MPPT_INPUTS] = [mppt_entry]
        self.changed = True
        log_info(
            "[migrate v1.0.8] flat solar keys -> mppt_inputs[0]: pv_power=%s, vmp=%s, panel_count=%s",
            mppt_entry.get(CONF_PV_POWER),
            mppt_entry.get(CONF_PANEL_VMP),
            mppt_entry.get(CONF_PANEL_COUNT),
        )
        return new_data
