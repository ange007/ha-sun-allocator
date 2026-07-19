"""Device configuration module for Sun Allocator config flow."""

import uuid
from typing import Dict, Any, Optional

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, TemplateError
from homeassistant.helpers.template import Template
from homeassistant.helpers import (
    entity_registry as er,
    device_registry as dr,
)

from ..core.logger import log_debug, log_info, log_error, audit_action, log_exception
from ..utils import clean_entity_id_and_mode
from .device_config_form import (
    build_device_name_selection_schema,
    build_device_basic_settings_schema,
    build_device_advanced_settings_schema,
    build_device_schedule_schema,
    build_device_schedule_helper_schema,
)

from ..const import (
    DOMAIN,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_ENTITY_FRIENDLY_NAME,
    CONF_ESPHOME_MODE_SELECT_ENTITY,
    DOMAIN_CLIMATE,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_PRIORITY,
    CONF_DEVICE_CONTROL_MODE,
    CONTROL_MODE_ON_OFF,
    CONTROL_MODE_PROPORTIONAL,
    RELAY_MODE_PROPORTIONAL,
    DOMAIN_SELECT,
    CONF_DEVICE_MIN_EXPECTED_W,
    CONF_DEVICE_MAX_EXPECTED_W,
    CONF_DEVICE_STOP_BATTERY_SOC,
    CONF_BATTERY_PROTECTION_SOC,
    CONF_BATTERY_SHARING_SOC,
    CONF_DEVICE_DEBOUNCE_TIME,
    CONF_DEVICE_MIN_ON_TIME,
    CONF_DEVICE_CHECK_USABLE_TEMPLATE,
    CONF_DEVICE_SCHEDULE_MODE,
    SCHEDULE_MODE_STANDARD,
    SCHEDULE_MODE_HELPER,
    CONF_DEVICE_SCHEDULE_HELPER_ENTITY,
    CONF_START_TIME,
    CONF_END_TIME,
    CONF_DAYS_OF_WEEK,
    DAYS_OF_WEEK,
    STEP_DEVICE_NAME_TYPE,
    STEP_DEVICE_BASIC_SETTINGS,
    STEP_DEVICE_ADVANCED,
    STEP_DEVICE_SCHEDULE,
    STEP_DEVICE_SCHEDULE_HELPER,
    ACTION_ADD,
    NONE_OPTION,
    STATE_ON,
    STATE_OFF,
    DOMAIN_LIGHT,
    DOMAIN_SWITCH,
    DOMAIN_INPUT_BOOLEAN,
    DOMAIN_AUTOMATION,
    DOMAIN_SCRIPT,
)


ICON_MAP = {
    DOMAIN_LIGHT: "💡",
    DOMAIN_SWITCH: "🔌",
    DOMAIN_INPUT_BOOLEAN: "☑️",
    DOMAIN_AUTOMATION: "⚙️",
    DOMAIN_SCRIPT: "📜",
    DOMAIN_CLIMATE: "🌡️",
}


def find_esphome_mode_select(hass: HomeAssistant, ent_reg, light_entity_id: str):
    """Return the paired ESPHome mode-select entity_id for a light, or None.

    An ESPHome SunAllocator relay exposes a ``light`` plus a ``select`` (whose
    options include ``Proportional``) on the *same* device. We pair them via the
    entity registry so the user only picks the light; the select is auto-stored.
    """
    entry = ent_reg.async_get(light_entity_id)
    if not entry or not entry.device_id:
        return None
    for reg_entry in ent_reg.entities.values():
        if reg_entry.device_id != entry.device_id or reg_entry.domain != DOMAIN_SELECT:
            continue
        st = hass.states.get(reg_entry.entity_id)
        options = (st.attributes.get("options") if st else None) or []
        if RELAY_MODE_PROPORTIONAL in options:
            return reg_entry.entity_id
    return None


def _light_is_dimmable(state) -> bool:
    """True if a light supports brightness (proportional-capable)."""
    modes = state.attributes.get("supported_color_modes") or []
    if set(modes) - {"onoff", "unknown"}:
        return True
    # Legacy lights expose brightness without color modes.
    return state.attributes.get("brightness") is not None


def _entity_label_parts(ent_reg, dev_reg, entity_id: str, friendly: str):
    """Split an entity into (device_name, entity_name) for a 'Device — Entity' label.

    Falls back to the friendly_name when the entity has no registry/device entry.
    """
    entry = ent_reg.async_get(entity_id)
    device_name = ""
    entity_name = friendly or entity_id
    if entry:
        if entry.device_id:
            dev = dev_reg.async_get(entry.device_id)
            if dev:
                device_name = dev.name_by_user or dev.name or ""
        entity_name = entry.name or entry.original_name or entity_name
    # If the friendly fallback still carries the device prefix, strip it.
    if device_name and entity_name.startswith(device_name):
        entity_name = entity_name[len(device_name):].strip() or entity_name
    return device_name, entity_name


def _format_entity_label(icon: str, device_name: str, entity_name: str, mode_label: str = "") -> str:
    """Compose ``icon Device — Entity (Mode)`` (parts omitted when empty)."""
    base = f"{device_name} — {entity_name}" if device_name else entity_name
    if mode_label:
        base = f"{base} ({mode_label})"
    return f"{icon} {base}".strip()


class DeviceConfigMixin:
    """Mixin for device configuration steps."""

    def _proportional_select_for(self, hass: HomeAssistant, entity_id: str):
        """Return the paired ESPHome mode-select entity_id for a light, else None."""
        if not entity_id or entity_id.split(".")[0] != DOMAIN_LIGHT:
            return None
        return find_esphome_mode_select(hass, er.async_get(hass), entity_id)

    def _get_device_entities(self, hass: HomeAssistant) -> Dict[str, list]:
        """Get available device entities for selection.

        Proportional-capable entities (native dimmable lights, and ESPHome relays
        whose paired select offers ``Proportional``) yield two rows — ``(Switch)``
        for on/off and ``(Dimmer)`` for proportional — encoded via the mode suffix
        ``entity|on_off`` / ``entity|proportional``. Everything else is on/off only.
        """
        allowed_domains = [
            DOMAIN_LIGHT,
            DOMAIN_SWITCH,
            DOMAIN_INPUT_BOOLEAN,
            DOMAIN_AUTOMATION,
            DOMAIN_SCRIPT,
            DOMAIN_CLIMATE,
        ]
        ent_reg = er.async_get(hass)
        dev_reg = dr.async_get(hass)
        all_entities = []
        for e in hass.states.async_all():
            domain = e.entity_id.split(".")[0]
            if domain not in allowed_domains:
                continue
            icon = ICON_MAP.get(domain, "")
            friendly = e.attributes.get("friendly_name", "")

            if domain == DOMAIN_CLIMATE:
                self._append_climate_rows(all_entities, e, icon, friendly)
                continue

            if e.state not in [STATE_ON, STATE_OFF]:
                continue
            if (
                "sun_allocator" in e.entity_id.lower()
                or "sunallocator" in e.entity_id.lower()
            ):
                continue

            device_name, entity_name = _entity_label_parts(
                ent_reg, dev_reg, e.entity_id, friendly
            )

            proportional_capable = False
            if domain == DOMAIN_LIGHT:
                proportional_capable = _light_is_dimmable(e) or bool(
                    find_esphome_mode_select(hass, ent_reg, e.entity_id)
                )

            if proportional_capable:
                all_entities.append((
                    f"{e.entity_id}|{CONTROL_MODE_ON_OFF}",
                    _format_entity_label(icon, device_name, entity_name, "Switch"),
                    friendly,
                ))
                all_entities.append((
                    f"{e.entity_id}|{CONTROL_MODE_PROPORTIONAL}",
                    _format_entity_label(icon, device_name, entity_name, "Dimmer"),
                    friendly,
                ))
            else:
                all_entities.append((
                    f"{e.entity_id}|{CONTROL_MODE_ON_OFF}",
                    _format_entity_label(icon, device_name, entity_name),
                    friendly,
                ))

        all_entities.sort(key=lambda x: x[1])
        all_entities = [(NONE_OPTION, NONE_OPTION, "")] + all_entities
        return {"all_entities": all_entities}

    def _append_climate_rows(self, all_entities, e, icon, friendly):
        """Append climate hvac-mode rows (unchanged behaviour)."""
        label_base = friendly or e.entity_id
        hvac_modes = e.attributes.get("hvac_modes") or []
        active_modes = [m for m in hvac_modes if m != "off"]
        if not active_modes:
            # Entity unavailable or no info yet — show single entry, runtime will auto-detect
            all_entities.append((e.entity_id, f"{icon} {label_base}", friendly))
        elif len(active_modes) == 1:
            all_entities.append((f"{e.entity_id}|{active_modes[0]}", f"{icon} {label_base}", friendly))
        else:
            for mode in active_modes:
                all_entities.append((
                    f"{e.entity_id}|{mode}",
                    f"{icon} {label_base} ({mode.replace('_', ' ').title()})",
                    friendly,
                ))


    def _validate_device_name(self, user_input: Dict[str, Any]) -> Dict[str, str]:
        """Validate device name."""
        errors = {}
        device_name = user_input.get(CONF_DEVICE_NAME, "").strip()
        if not device_name:
            errors[CONF_DEVICE_NAME] = "device_name_required"

        return errors


    def _validate_basic_settings(self, user_input: Dict[str, Any]) -> Dict[str, str]:
        """Validate the essential fields on the Basic step (priority / power / entity)."""
        errors = {}

        try:
            priority = int(user_input.get(CONF_DEVICE_PRIORITY, 50))
            if not 1 <= priority <= 100:
                errors[CONF_DEVICE_PRIORITY] = "invalid_priority"
        except (ValueError, TypeError):
            errors[CONF_DEVICE_PRIORITY] = "invalid_priority"

        min_expected = 0
        try:
            min_expected = float(user_input.get(CONF_DEVICE_MIN_EXPECTED_W, 0) or 0)
            if min_expected < 1:
                errors[CONF_DEVICE_MIN_EXPECTED_W] = "invalid_min_expected_w"
        except (ValueError, TypeError):
            errors[CONF_DEVICE_MIN_EXPECTED_W] = "invalid_min_expected_w"

        try:
            max_expected = float(user_input.get(CONF_DEVICE_MAX_EXPECTED_W, min_expected) or min_expected)
            if max_expected < min_expected:
                errors[CONF_DEVICE_MAX_EXPECTED_W] = "invalid_max_expected_w"
        except (ValueError, TypeError):
            errors[CONF_DEVICE_MAX_EXPECTED_W] = "invalid_max_expected_w"

        try:
            auto_enabled = bool(user_input.get(CONF_AUTO_CONTROL_ENABLED, False))
            needs_max_w = (
                self._device_config.get(CONF_DEVICE_CONTROL_MODE) == CONTROL_MODE_PROPORTIONAL
            )
            if auto_enabled and needs_max_w:
                max_expected = float(user_input.get(CONF_DEVICE_MAX_EXPECTED_W, 0) or 0)
                if max_expected <= 0:
                    errors[CONF_DEVICE_MAX_EXPECTED_W] = "invalid_max_expected_w"
        except (ValueError, TypeError):
            pass

        return errors

    def _validate_advanced_settings(self, user_input: Dict[str, Any]) -> Dict[str, str]:
        """Validate the fine-tuning fields on the Advanced per-device step."""
        errors = {}

        if (
            CONF_DEVICE_DEBOUNCE_TIME in user_input
            and user_input[CONF_DEVICE_DEBOUNCE_TIME] is not None
        ):
            try:
                debounce_time = int(user_input[CONF_DEVICE_DEBOUNCE_TIME])
                if not 5 <= debounce_time <= 600:
                    errors[CONF_DEVICE_DEBOUNCE_TIME] = "invalid_debounce_time"
            except (ValueError, TypeError):
                errors[CONF_DEVICE_DEBOUNCE_TIME] = "invalid_debounce_time"

        if (
            CONF_DEVICE_MIN_ON_TIME in user_input
            and user_input[CONF_DEVICE_MIN_ON_TIME] is not None
        ):
            try:
                min_on_time = int(user_input[CONF_DEVICE_MIN_ON_TIME])
                if not 0 <= min_on_time <= 3600:
                    errors[CONF_DEVICE_MIN_ON_TIME] = "invalid_min_on_time"
            except (ValueError, TypeError):
                errors[CONF_DEVICE_MIN_ON_TIME] = "invalid_min_on_time"

        # stop_battery_soc: 0 = inherit the global protection floor (exempt). A NON-zero
        # value must not sit below the global protection floor.
        try:
            stop_soc = float(user_input.get(CONF_DEVICE_STOP_BATTERY_SOC, 0) or 0)
            if 0 < stop_soc < self._global_protection_soc():
                errors[CONF_DEVICE_STOP_BATTERY_SOC] = "stop_soc_below_protection"
        except (ValueError, TypeError):
            errors[CONF_DEVICE_STOP_BATTERY_SOC] = "stop_soc_below_protection"

        # Render the usability template once so a broken one is rejected at save
        # time instead of silently failing open at runtime (the runtime path still
        # fails open as a safety net). A valid template that merely references an
        # unavailable entity should use defaults (e.g. states('x')|float(0)).
        usable_template = user_input.get(CONF_DEVICE_CHECK_USABLE_TEMPLATE)
        if usable_template:
            try:
                Template(str(usable_template), self.hass).async_render(parse_result=True)
            except TemplateError:
                errors[CONF_DEVICE_CHECK_USABLE_TEMPLATE] = "invalid_check_usable_template"

        return errors


    def _validate_schedule_config(self, user_input: Dict[str, Any]) -> Dict[str, str]:
        """Validate schedule configuration."""
        errors = {}

        if CONF_START_TIME in user_input and user_input[CONF_START_TIME]:
            try:
                parts = str(user_input[CONF_START_TIME]).split(":")
                hour, minute = int(parts[0]), int(parts[1])
                if not 0 <= hour <= 23 or not 0 <= minute <= 59:
                    errors[CONF_START_TIME] = "invalid_time_format"
            except (ValueError, AttributeError, IndexError):
                errors[CONF_START_TIME] = "invalid_time_format"

        if CONF_END_TIME in user_input and user_input[CONF_END_TIME]:
            try:
                parts = str(user_input[CONF_END_TIME]).split(":")
                hour, minute = int(parts[0]), int(parts[1])
                if not 0 <= hour <= 23 or not 0 <= minute <= 59:
                    errors[CONF_END_TIME] = "invalid_time_format"
            except (ValueError, AttributeError, IndexError):
                errors[CONF_END_TIME] = "invalid_time_format"

        return errors


    def _process_device_input(
        self, user_input: Dict[str, Any], entities: Dict[str, list]
    ) -> Dict[str, Any]:
        """Process and clean device configuration input."""
        if user_input.get(CONF_DEVICE_ENTITY) == NONE_OPTION:
            user_input[CONF_DEVICE_ENTITY] = None
            user_input[CONF_DEVICE_ENTITY_FRIENDLY_NAME] = None
            user_input["hvac_mode"] = None
            user_input[CONF_DEVICE_CONTROL_MODE] = CONTROL_MODE_ON_OFF
            user_input[CONF_ESPHOME_MODE_SELECT_ENTITY] = None
        else:
            entity_id_from_input = user_input.get(CONF_DEVICE_ENTITY)
            cleaned_id, mode = clean_entity_id_and_mode(entity_id_from_input)
            domain = cleaned_id.split(".")[0] if "." in cleaned_id else ""
            user_input[CONF_DEVICE_ENTITY] = cleaned_id

            if domain == DOMAIN_CLIMATE:
                # Climate keeps the hvac_mode suffix; always driven as on/off.
                user_input["hvac_mode"] = mode
                user_input[CONF_DEVICE_CONTROL_MODE] = CONTROL_MODE_ON_OFF
                user_input[CONF_ESPHOME_MODE_SELECT_ENTITY] = None
            else:
                user_input["hvac_mode"] = None
                control_mode = (
                    CONTROL_MODE_PROPORTIONAL
                    if mode == CONTROL_MODE_PROPORTIONAL
                    else CONTROL_MODE_ON_OFF
                )
                user_input[CONF_DEVICE_CONTROL_MODE] = control_mode
                # ESPHome relays need their paired select to drive On/Off/Proportional.
                user_input[CONF_ESPHOME_MODE_SELECT_ENTITY] = self._proportional_select_for(
                    self.hass, cleaned_id
                )

            friendly_name = None
            if entities and "all_entities" in entities:
                for value, _, fn in entities["all_entities"]:
                    if value == entity_id_from_input:
                        friendly_name = fn
                        break

            user_input[CONF_DEVICE_ENTITY_FRIENDLY_NAME] = friendly_name

            log_debug(
                f"[DeviceConfigMixin] Process device input {entity_id_from_input}: "
                f"cleaned_id={cleaned_id}, control_mode={user_input.get(CONF_DEVICE_CONTROL_MODE)}, "
                f"mode_select={user_input.get(CONF_ESPHOME_MODE_SELECT_ENTITY)}, friendly_name={friendly_name}",
            )

        return user_input


    def _process_schedule_input(self, user_input: Dict[str, Any]) -> Dict[str, Any]:
        """Process and clean schedule configuration input."""
        for key in (CONF_START_TIME, CONF_END_TIME):
            if key in user_input and user_input[key] is not None:
                try:
                    parts = str(user_input[key]).split(":")
                    user_input[key] = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
                except (ValueError, AttributeError, IndexError):
                    pass

        days_of_week = []
        for day in DAYS_OF_WEEK:
            if day in user_input and user_input[day]:
                days_of_week.append(day)
        user_input[CONF_DAYS_OF_WEEK] = days_of_week

        return user_input


    def _get_device_name_selection_schema(
        self, entities: Dict[str, list], defaults: Optional[Dict[str, Any]] = None
    ) -> vol.Schema:
        """Get the combined schema for device name + entity selection."""
        return build_device_name_selection_schema(entities, defaults)


    def _get_device_basic_settings_schema(
        self, defaults: Optional[Dict[str, Any]] = None
    ) -> vol.Schema:
        """Get the schema for device basic settings configuration."""
        return build_device_basic_settings_schema(defaults)


    def _get_device_advanced_settings_schema(
        self, defaults: Optional[Dict[str, Any]] = None
    ) -> vol.Schema:
        """Get the schema for the fine-tuning per-device settings step."""
        return build_device_advanced_settings_schema(defaults)


    def _get_device_schedule_schema(
        self, defaults: Optional[Dict[str, Any]] = None
    ) -> vol.Schema:
        """Get the schema for device schedule configuration."""
        return build_device_schedule_schema(defaults)

    def _get_device_schedule_helper_schema(
        self, defaults: Optional[Dict[str, Any]] = None
    ) -> vol.Schema:
        """Get the schema for schedule helper entity selection."""
        return build_device_schedule_helper_schema(defaults)


    async def _finalize_device_config(self):
        """Finalize device configuration and persist."""
        if self._action == ACTION_ADD:
            self._device_config[CONF_DEVICE_ID] = str(uuid.uuid4())
            self._devices.append(self._device_config)

            log_info("[DeviceConfigMixin] Added device: %s", self._device_config)
            audit_action("device_add", {"device": self._device_config})
        else:
            self._device_config[CONF_DEVICE_ID] = self._device_config.get(CONF_DEVICE_ID) or str(uuid.uuid4())

            if self._device_index is not None:
                self._devices[self._device_index] = self._device_config
                log_info("[DeviceConfigMixin] Edited device: %s", self._device_config)
                audit_action("device_edit", {"device": self._device_config})

        if hasattr(self, "hass") and hasattr(self, "config_entry"):
            try:
                data = dict(self.config_entry.data)
                data[CONF_DEVICES] = self._devices
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=data
                )

                log_info(
                    "[DeviceConfigMixin] Persisted devices: %d devices",
                    len(self._devices),
                )
            except HomeAssistantError as e:
                log_error("[DeviceConfigMixin] Failed to persist devices: %s", e)
                log_exception("device_persist", e)

        if hasattr(self, "async_step_manage_devices"):
            return await self.async_step_manage_devices()

        return await self.async_step_devices()


    async def async_step_device_name_type(self, user_input=None):
        """Handle the combined device name + entity selection step."""
        errors = {}
        entities = self._get_device_entities(self.hass)

        if user_input is not None:
            errors = self._validate_device_name(user_input)

            # Duplicate entity check. The picker value carries a mode suffix
            # (entity|on_off / entity|proportional / entity|hvac_mode); compare on
            # the cleaned entity_id, matching how it is stored.
            raw_entity = user_input.get(CONF_DEVICE_ENTITY)
            entity_id, _ = clean_entity_id_and_mode(raw_entity) if raw_entity else (None, None)
            if not errors and entity_id and raw_entity != NONE_OPTION and hasattr(self, "_devices"):
                device_id_to_edit = self._device_config.get(CONF_DEVICE_ID)
                for d in getattr(self, "_devices", []):
                    if d.get(CONF_DEVICE_ID) != device_id_to_edit and d.get(CONF_DEVICE_ENTITY) == entity_id:
                        errors[CONF_DEVICE_ENTITY] = "duplicate_entity_id"
                        break

            if not errors:
                user_input = self._process_device_input(user_input, entities)
                self._device_config.update(user_input)
                return await self.async_step_device_basic_settings()

        schema = self._get_device_name_selection_schema(entities, self._device_config)

        return self.async_show_form(
            step_id=STEP_DEVICE_NAME_TYPE,
            data_schema=schema,
            description_placeholders={
                "action": "Add" if self._action == ACTION_ADD else "Edit",
                "device_name": self._device_config.get(CONF_DEVICE_NAME, "New Device"),
            },
            errors=errors,
        )


    def _get_entry_data(self):
        """Return entry_data dict for the current config entry, or None."""
        cfg_entry = getattr(self, "config_entry", None)
        if cfg_entry is None:
            return None
        return self.hass.data.get(DOMAIN, {}).get(cfg_entry.entry_id)

    def _global_soc(self, key: str) -> float:
        """Read a global SOC setting (protection / sharing), 0 if unset/unavailable.

        During the initial config flow (no config_entry yet) it may live on the
        in-progress solar config; fall back to 0 so a device can always be saved.
        """
        cfg_entry = getattr(self, "config_entry", None)
        source = cfg_entry.data if cfg_entry is not None else (getattr(self, "_solar_config", None) or {})
        try:
            return float(source.get(key, 0) or 0)
        except (ValueError, TypeError):
            return 0.0

    def _global_protection_soc(self) -> float:
        """The global battery_protection_soc (hard floor)."""
        return self._global_soc(CONF_BATTERY_PROTECTION_SOC)

    def _global_sharing_soc(self) -> float:
        """The global battery_sharing_soc (surplus-release threshold)."""
        return self._global_soc(CONF_BATTERY_SHARING_SOC)

    async def async_step_device_basic_settings(self, user_input=None):
        """Handle the device basic settings step."""
        errors = {}

        if user_input is not None:
            errors = self._validate_basic_settings(user_input)

            if not errors:
                self._device_config.update(user_input)

                # Sync the auto-control switch entity to the new config value.
                device_id = self._device_config.get(CONF_DEVICE_ID)
                new_enabled = self._device_config.get(CONF_AUTO_CONTROL_ENABLED, False)
                entry_data = self._get_entry_data()
                if device_id and entry_data is not None:
                    switch = entry_data.get("auto_control_switches", {}).get(device_id)
                    if switch:
                        switch.sync_state(new_enabled)

                return await self.async_step_device_advanced()

        # Pre-fill auto_control_enabled from the live switch state if available.
        display_defaults = dict(self._device_config)
        device_id = display_defaults.get(CONF_DEVICE_ID)
        if device_id:
            entry_data = self._get_entry_data()
            if entry_data is not None:
                switch = entry_data.get("auto_control_switches", {}).get(device_id)
                if switch is not None:
                    display_defaults[CONF_AUTO_CONTROL_ENABLED] = bool(switch.is_on)

        schema = self._get_device_basic_settings_schema(display_defaults)

        return self.async_show_form(
            step_id=STEP_DEVICE_BASIC_SETTINGS,
            data_schema=schema,
            description_placeholders={
                "device_name": self._device_config.get(CONF_DEVICE_NAME, "New Device"),
            },
            errors=errors,
        )


    async def async_step_device_advanced(self, user_input=None):
        """Handle the fine-tuning per-device settings step, then route to schedule."""
        errors = {}

        if user_input is not None:
            errors = self._validate_advanced_settings(user_input)

            if not errors:
                self._device_config.update(user_input)

                schedule_mode = self._device_config.get(CONF_DEVICE_SCHEDULE_MODE)
                if schedule_mode == SCHEDULE_MODE_STANDARD:
                    return await self.async_step_device_schedule()
                if schedule_mode == SCHEDULE_MODE_HELPER:
                    return await self.async_step_device_schedule_helper()

                return await self._finalize_device_config()

        # stop_battery_soc is shown as stored (0 stays 0 = inherit global protection).
        display_defaults = dict(self._device_config)

        schema = self._get_device_advanced_settings_schema(display_defaults)

        return self.async_show_form(
            step_id=STEP_DEVICE_ADVANCED,
            data_schema=schema,
            description_placeholders={
                "device_name": self._device_config.get(CONF_DEVICE_NAME, "New Device"),
                "sharing_soc": f"{self._global_sharing_soc():.0f}",
                "protection_soc": f"{self._global_protection_soc():.0f}",
            },
            errors=errors,
        )


    async def async_step_device_schedule(self, user_input=None):
        """Handle the device schedule step."""
        errors = {}

        if user_input is not None:
            errors = self._validate_schedule_config(user_input)

            if not errors:
                user_input = self._process_schedule_input(user_input)
                self._device_config.update(user_input)
                return await self._finalize_device_config()

        schema = self._get_device_schedule_schema(self._device_config)

        return self.async_show_form(
            step_id=STEP_DEVICE_SCHEDULE,
            data_schema=schema,
            description_placeholders={
                "device_name": self._device_config.get(CONF_DEVICE_NAME, "New Device"),
            },
            errors=errors,
        )

    async def async_step_device_schedule_helper(self, user_input=None):
        """Handle the schedule helper entity selection step."""
        errors = {}

        if user_input is not None:
            helper_entity = user_input.get(CONF_DEVICE_SCHEDULE_HELPER_ENTITY)
            if not helper_entity:
                errors[CONF_DEVICE_SCHEDULE_HELPER_ENTITY] = "schedule_helper_required"
            else:
                self._device_config.update(user_input)
                return await self._finalize_device_config()

        schema = self._get_device_schedule_helper_schema(self._device_config)

        return self.async_show_form(
            step_id=STEP_DEVICE_SCHEDULE_HELPER,
            data_schema=schema,
            description_placeholders={
                "device_name": self._device_config.get(CONF_DEVICE_NAME, "New Device"),
            },
            errors=errors,
        )
