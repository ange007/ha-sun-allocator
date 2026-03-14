"""Device configuration module for Sun Allocator config flow."""

import uuid
from typing import Dict, Any, Optional

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from ..core.logger import log_debug, log_info, log_error, audit_action, log_exception
from ..utils import clean_entity_id_and_mode
from .device_config_form import (
    build_device_name_type_schema,
    build_device_selection_schema,
    build_device_basic_settings_schema,
    build_device_schedule_schema,
    build_device_schedule_helper_schema,
)

from ..const import (
    DOMAIN,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_ENTITY_FRIENDLY_NAME,
    DOMAIN_CLIMATE,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_PRIORITY,
    CONF_DEVICE_TYPE,
    DEVICE_TYPE_CUSTOM,
    CONF_DEVICE_MIN_EXPECTED_W,
    CONF_DEVICE_MAX_EXPECTED_W,
    CONF_DEVICE_DEBOUNCE_TIME,
    CONF_DEVICE_SCHEDULE_MODE,
    SCHEDULE_MODE_STANDARD,
    SCHEDULE_MODE_HELPER,
    CONF_DEVICE_SCHEDULE_HELPER_ENTITY,
    CONF_START_TIME,
    CONF_END_TIME,
    CONF_DAYS_OF_WEEK,
    DAYS_OF_WEEK,
    STEP_DEVICE_NAME_TYPE,
    STEP_DEVICE_SELECTION,
    STEP_DEVICE_BASIC_SETTINGS,
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


class DeviceConfigMixin:
    """Mixin for device configuration steps."""

    def _get_device_entities(self, hass: HomeAssistant) -> Dict[str, list]:
        """Get available device entities for selection."""
        allowed_domains = [
            DOMAIN_LIGHT,
            DOMAIN_SWITCH,
            DOMAIN_INPUT_BOOLEAN,
            DOMAIN_AUTOMATION,
            DOMAIN_SCRIPT,
            DOMAIN_CLIMATE,
        ]
        icon_map = {
            DOMAIN_LIGHT: "💡",
            DOMAIN_SWITCH: "🔌",
            DOMAIN_INPUT_BOOLEAN: "☑️",
            DOMAIN_AUTOMATION: "⚙️",
            DOMAIN_SCRIPT: "📜",
            DOMAIN_CLIMATE: "🌡️",
        }
        all_entities = []
        device_type = getattr(self, "_device_config", {}).get(CONF_DEVICE_TYPE)
        for e in hass.states.async_all():
            domain = e.entity_id.split(".")[0]
            icon = icon_map.get(domain, "")
            state = e.state
            friendly = e.attributes.get("friendly_name", "")
            is_esphome = (
                ".esphome_" in e.entity_id
                or e.attributes.get("integration") == "esphome"
            )
            if device_type == DEVICE_TYPE_CUSTOM:
                if (
                    domain
                    in [
                        DOMAIN_SWITCH,
                        DOMAIN_LIGHT,
                        DOMAIN_INPUT_BOOLEAN,
                        DOMAIN_SCRIPT,
                        DOMAIN_AUTOMATION,
                    ]
                    and is_esphome
                ):
                    value = e.entity_id
                    label = f"{icon} {friendly}" if friendly else f"{icon} {value}"
                    all_entities.append((value, label, friendly))
            else:
                if domain in allowed_domains:
                    if domain == DOMAIN_CLIMATE:
                        hvac_modes = e.attributes.get("hvac_modes") or []
                        active_modes = [m for m in hvac_modes if m != "off"]
                        if not active_modes:
                            # Entity unavailable or no info yet — show single entry, runtime will auto-detect
                            label = f"{icon} {friendly}" if friendly else f"{icon} {e.entity_id}"
                            all_entities.append((e.entity_id, label, friendly))
                        elif len(active_modes) == 1:
                            # Only one non-off mode — no need for suffix
                            label = f"{icon} {friendly}" if friendly else f"{icon} {e.entity_id}"
                            all_entities.append((f"{e.entity_id}|{active_modes[0]}", label, friendly))
                        else:
                            for mode in active_modes:
                                value = f"{e.entity_id}|{mode}"
                                label = (
                                    f"{icon} {friendly} ({mode.replace('_', ' ').title()})"
                                    if friendly
                                    else f"{icon} {e.entity_id} ({mode})"
                                )
                                all_entities.append((value, label, friendly))
                    elif state in [STATE_ON, STATE_OFF]:
                        if (
                            "sun_allocator" not in e.entity_id.lower()
                            and "sunallocator" not in e.entity_id.lower()
                        ):
                            value = e.entity_id
                            label = (
                                f"{icon} {friendly}" if friendly else f"{icon} {value}"
                            )
                            all_entities.append((value, label, friendly))

        all_entities.sort(key=lambda x: x[1])
        all_entities = [(NONE_OPTION, NONE_OPTION, "")] + all_entities
        return {"all_entities": all_entities}


    def _validate_device_name(self, user_input: Dict[str, Any]) -> Dict[str, str]:
        """Validate device name."""
        errors = {}
        device_name = user_input.get(CONF_DEVICE_NAME, "").strip()
        if not device_name:
            errors[CONF_DEVICE_NAME] = "device_name_required"

        return errors


    def _validate_basic_settings(self, user_input: Dict[str, Any]) -> Dict[str, str]:
        """Validate the fields present on the Basic Settings step."""
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

        try:
            auto_enabled = bool(user_input.get(CONF_AUTO_CONTROL_ENABLED, False))
            device_type = self._device_config.get(CONF_DEVICE_TYPE)
            if auto_enabled and device_type == DEVICE_TYPE_CUSTOM:
                max_expected = float(user_input.get(CONF_DEVICE_MAX_EXPECTED_W, 0) or 0)
                if max_expected <= 0:
                    errors[CONF_DEVICE_MAX_EXPECTED_W] = "invalid_max_expected_w"
        except (ValueError, TypeError):
            pass

        entity_id = user_input.get(CONF_DEVICE_ENTITY)
        if entity_id and hasattr(self, "_devices"):
            # Check for duplicates, excluding the device being edited
            device_id_to_edit = self._device_config.get(CONF_DEVICE_ID)
            for d in getattr(self, "_devices", []):
                if d.get(CONF_DEVICE_ID) != device_id_to_edit and d.get(CONF_DEVICE_ENTITY) == entity_id:
                    errors[CONF_DEVICE_ENTITY] = "duplicate_entity_id"
                    break

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
        else:
            entity_id_from_input = user_input.get(CONF_DEVICE_ENTITY)
            cleaned_id, hvac_mode = clean_entity_id_and_mode(entity_id_from_input)
            user_input[CONF_DEVICE_ENTITY] = cleaned_id
            user_input["hvac_mode"] = hvac_mode

            friendly_name = None
            if entities and "all_entities" in entities:
                for value, _, fn in entities["all_entities"]:
                    if value == entity_id_from_input:
                        friendly_name = fn
                        break

            user_input[CONF_DEVICE_ENTITY_FRIENDLY_NAME] = friendly_name

            log_debug(
                f"[DeviceConfigMixin] Process device input {entity_id_from_input}: cleaned_id={cleaned_id}, hvac_mode={hvac_mode}, friendly_name={friendly_name}",
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


    def _get_device_name_type_schema(
        self, defaults: Optional[Dict[str, Any]] = None
    ) -> vol.Schema:
        """Get the schema for device name and type configuration."""
        return build_device_name_type_schema(defaults)


    def _get_device_selection_schema(
        self, entities: Dict[str, list], defaults: Optional[Dict[str, Any]] = None
    ) -> vol.Schema:
        """Get the schema for device selection configuration."""
        return build_device_selection_schema(entities, defaults)


    def _get_device_basic_settings_schema(
        self, defaults: Optional[Dict[str, Any]] = None
    ) -> vol.Schema:
        """Get the schema for device basic settings configuration."""
        return build_device_basic_settings_schema(defaults)


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
        """Handle the device name and type step."""
        errors = {}

        if user_input is not None:
            errors = self._validate_device_name(user_input)

            if not errors:
                self._device_config.update(user_input)
                return await self.async_step_device_selection()

        schema = self._get_device_name_type_schema(self._device_config)

        return self.async_show_form(
            step_id=STEP_DEVICE_NAME_TYPE,
            data_schema=schema,
            description_placeholders={
                "action": "Add" if self._action == ACTION_ADD else "Edit",
                "device_name": self._device_config.get(CONF_DEVICE_NAME, "New Device"),
            },
            errors=errors,
        )


    async def async_step_device_selection(self, user_input=None):
        """Handle the device selection step."""
        errors = {}
        entities = self._get_device_entities(self.hass)

        if user_input is not None:
            user_input = self._process_device_input(user_input, entities)
            self._device_config.update(user_input)
            return await self.async_step_device_basic_settings()

        schema = self._get_device_selection_schema(entities, self._device_config)

        return self.async_show_form(
            step_id=STEP_DEVICE_SELECTION,
            data_schema=schema,
            description_placeholders={
                "device_name": self._device_config.get(CONF_DEVICE_NAME, "New Device"),
                "device_type": self._device_config.get(CONF_DEVICE_TYPE, DEVICE_TYPE_CUSTOM),
            },
            errors=errors,
        )


    def _get_entry_data(self):
        """Return entry_data dict for the current config entry, or None."""
        cfg_entry = getattr(self, "config_entry", None)
        if cfg_entry is None:
            return None
        return self.hass.data.get(DOMAIN, {}).get(cfg_entry.entry_id)

    async def async_step_device_basic_settings(self, user_input=None):
        """Handle the device basic settings step."""
        errors = {}

        if user_input is not None:
            errors = self._validate_basic_settings(user_input)

            if not errors:
                self._device_config.update(user_input)

                # Sync auto_control runtime state immediately (before reload)
                device_id = self._device_config.get(CONF_DEVICE_ID)
                new_enabled = self._device_config.get(CONF_AUTO_CONTROL_ENABLED, False)
                entry_data = self._get_entry_data()
                if device_id and entry_data is not None:
                    entry_data.setdefault("device_auto_control_runtime", {})[device_id] = new_enabled
                    switch = entry_data.get("auto_control_switches", {}).get(device_id)
                    if switch:
                        switch.sync_state(new_enabled)

                schedule_mode = self._device_config.get(CONF_DEVICE_SCHEDULE_MODE)
                if schedule_mode == SCHEDULE_MODE_STANDARD:
                    return await self.async_step_device_schedule()
                if schedule_mode == SCHEDULE_MODE_HELPER:
                    return await self.async_step_device_schedule_helper()

                return await self._finalize_device_config()

        # Pre-fill auto_control_enabled from runtime switch state
        display_defaults = dict(self._device_config)
        device_id = display_defaults.get(CONF_DEVICE_ID)
        if device_id:
            entry_data = self._get_entry_data()
            if entry_data is not None:
                runtime = entry_data.get("device_auto_control_runtime", {}).get(device_id)
                if runtime is not None:
                    display_defaults[CONF_AUTO_CONTROL_ENABLED] = runtime

        schema = self._get_device_basic_settings_schema(display_defaults)

        return self.async_show_form(
            step_id=STEP_DEVICE_BASIC_SETTINGS,
            data_schema=schema,
            description_placeholders={
                "device_name": self._device_config.get(CONF_DEVICE_NAME, "New Device"),
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
