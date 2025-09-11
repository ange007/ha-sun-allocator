"""Device configuration module for Sun Allocator config flow."""
import voluptuous as vol
import uuid
from datetime import time
from typing import Dict, Any, List, Optional

from homeassistant.core import HomeAssistant

from ..utils.logger import get_logger, log_info, log_error
from ..utils.journal import audit_action, log_exception
from ..utils.sensor_utils import clean_entity_id_and_mode
from .device_config_form import (
    build_device_name_type_schema,
    build_device_selection_schema,
    build_device_basic_settings_schema,
    build_device_schedule_schema
)

from ..const import (
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
    CONF_MIN_EXPECTED_W,
    CONF_MAX_EXPECTED_W,
    CONF_SCHEDULE_ENABLED,
    CONF_START_TIME,
    CONF_END_TIME,
    CONF_DAYS_OF_WEEK,
    DAYS_OF_WEEK,
    STEP_DEVICE_NAME_TYPE,
    STEP_DEVICE_SELECTION,
    STEP_DEVICE_BASIC_SETTINGS,
    STEP_DEVICE_SCHEDULE,
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
        """Get available device entities for selection (switch, light, climate, etc). For custom (ESPHome) — only ESPHome relays."""
        allowed_domains = [DOMAIN_LIGHT, DOMAIN_SWITCH, DOMAIN_INPUT_BOOLEAN, DOMAIN_AUTOMATION, DOMAIN_SCRIPT, DOMAIN_CLIMATE]
        icon_map = {
            DOMAIN_LIGHT: "💡",
            DOMAIN_SWITCH: "🔌",
            DOMAIN_INPUT_BOOLEAN: "☑️",
            DOMAIN_AUTOMATION: "⚙️",
            DOMAIN_SCRIPT: "📜",
            DOMAIN_CLIMATE: "🌡️",
        }
        all_entities = []
        device_type = getattr(self, '_device_config', {}).get('device_type', None) or getattr(self, '_device_config', {}).get('type', None)
        for e in hass.states.async_all():
            domain = e.entity_id.split(".")[0]
            icon = icon_map.get(domain, "")
            state = e.state
            friendly = e.attributes.get("friendly_name", "")
            # ESPHome only: entity_id contains 'esphome' (e.g. switch.esphome_*)
            is_esphome = ".esphome_" in e.entity_id or e.attributes.get("integration") == "esphome"
            if device_type == "custom":
                # Only ESPHome relays (switch, light, input_boolean, script, automation) with esphome in entity_id
                if domain in [DOMAIN_SWITCH, DOMAIN_LIGHT, DOMAIN_INPUT_BOOLEAN, DOMAIN_SCRIPT, DOMAIN_AUTOMATION] and is_esphome:
                    value, _ = clean_entity_id_and_mode(e.entity_id)
                    label = f"{icon} {friendly}" if friendly else f"{icon} {value}"
                    all_entities.append((value, label, friendly))
            else:
                if domain in allowed_domains:
                    if domain == DOMAIN_CLIMATE:
                        value_heat, _ = clean_entity_id_and_mode(f"{e.entity_id}|heat")
                        label_heat = f"{icon} {friendly} (Heat)" if friendly else f"{icon} {e.entity_id} (Heat)"
                        all_entities.append((value_heat, label_heat, friendly))
                        value_cool, _ = clean_entity_id_and_mode(f"{e.entity_id}|cool")
                        label_cool = f"{icon} {friendly} (Cool)" if friendly else f"{icon} {e.entity_id} (Cool)"
                        all_entities.append((value_cool, label_cool, friendly))
                    elif state in [STATE_ON, STATE_OFF]:
                        if "sun_allocator" not in e.entity_id.lower() and "sunallocator" not in e.entity_id.lower():
                            value, _ = clean_entity_id_and_mode(e.entity_id)
                            label = f"{icon} {friendly}" if friendly else f"{icon} {value}"
                            all_entities.append((value, label, friendly))
        all_entities.sort(key=lambda x: x[1])
        all_entities = [(NONE_OPTION, NONE_OPTION, "")] + all_entities
        return {"all_entities": all_entities}
    
    def _validate_device_config(self, user_input: Dict[str, Any]) -> Dict[str, str]:
        """Validate device configuration."""
        errors = {}
        
        # Validate device name
        device_name = user_input.get(CONF_DEVICE_NAME, "").strip()
        if not device_name:
            errors[CONF_DEVICE_NAME] = "device_name_required"
        
        # Validate device priority
        try:
            priority = int(user_input.get(CONF_DEVICE_PRIORITY, 50))
            if priority < 1 or priority > 100:
                errors[CONF_DEVICE_PRIORITY] = "invalid_priority"
        except (ValueError, TypeError):
            errors[CONF_DEVICE_PRIORITY] = "invalid_priority"
        
        # Validate expected load limits (optional, >= 0)
        try:
            min_expected = float(user_input.get(CONF_MIN_EXPECTED_W, 0) or 0)
            if min_expected < 0:
                errors[CONF_MIN_EXPECTED_W] = "invalid_min_expected_w"
        except (ValueError, TypeError):
            errors[CONF_MIN_EXPECTED_W] = "invalid_min_expected_w"
        try:
            max_expected = float(user_input.get(CONF_MAX_EXPECTED_W, 0) or 0)
            if max_expected < 0:
                errors[CONF_MAX_EXPECTED_W] = "invalid_max_expected_w"
        except (ValueError, TypeError):
            errors[CONF_MAX_EXPECTED_W] = "invalid_max_expected_w"
        
        # Validate duplicate entity_id
        entity_id = user_input.get(CONF_DEVICE_ENTITY)
        if entity_id and hasattr(self, '_devices'):
            for d in getattr(self, '_devices', []):
                if d.get(CONF_DEVICE_ENTITY) == entity_id:
                    errors[CONF_DEVICE_ENTITY] = "duplicate_entity_id"

        return errors

    def _validate_basic_settings(self, user_input: Dict[str, Any]) -> Dict[str, str]:
        """Validate only the fields present on the Basic Settings step."""
        errors = {}

        # Validate device priority
        try:
            priority = int(user_input.get(CONF_DEVICE_PRIORITY, 50))
            if priority < 1 or priority > 100:
                errors[CONF_DEVICE_PRIORITY] = "invalid_priority"
        except (ValueError, TypeError):
            errors[CONF_DEVICE_PRIORITY] = "invalid_priority"

        # Validate expected load limits (optional, >= 0)
        try:
            min_expected = float(user_input.get(CONF_MIN_EXPECTED_W, 0) or 0)
            if min_expected < 0:
                errors[CONF_MIN_EXPECTED_W] = "invalid_min_expected_w"
        except (ValueError, TypeError):
            errors[CONF_MIN_EXPECTED_W] = "invalid_min_expected_w"
        try:
            max_expected = float(user_input.get(CONF_MAX_EXPECTED_W, 0) or 0)
            if max_expected < 0:
                errors[CONF_MAX_EXPECTED_W] = "invalid_max_expected_w"
        except (ValueError, TypeError):
            errors[CONF_MAX_EXPECTED_W] = "invalid_max_expected_w"

        # Enforce Variant A: For Custom devices with Auto Control, max_expected_w must be > 0
        try:
            auto_enabled = bool(user_input.get(CONF_AUTO_CONTROL_ENABLED, False))
            device_type = self._device_config.get(CONF_DEVICE_TYPE)
            if auto_enabled and device_type == DEVICE_TYPE_CUSTOM:
                max_expected = float(user_input.get(CONF_MAX_EXPECTED_W, 0) or 0)
                if max_expected <= 0:
                    errors[CONF_MAX_EXPECTED_W] = "invalid_max_expected_w"
        except Exception:
            # If anything goes wrong, fall back to not blocking the form
            pass

        return errors
    
    def _validate_schedule_config(self, user_input: Dict[str, Any]) -> Dict[str, str]:
        """Validate schedule configuration."""
        errors = {}
        
        # Validate time format
        if CONF_START_TIME in user_input and user_input[CONF_START_TIME]:
            try:
                hour, minute = map(int, user_input[CONF_START_TIME].split(':'))
                if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                    errors[CONF_START_TIME] = "invalid_time_format"
            except (ValueError, AttributeError):
                errors[CONF_START_TIME] = "invalid_time_format"
        
        if CONF_END_TIME in user_input and user_input[CONF_END_TIME]:
            try:
                hour, minute = map(int, user_input[CONF_END_TIME].split(':'))
                if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                    errors[CONF_END_TIME] = "invalid_time_format"
            except (ValueError, AttributeError):
                errors[CONF_END_TIME] = "invalid_time_format"
        
        return errors
    
    def _process_device_input(self, user_input: Dict[str, Any]) -> Dict[str, Any]:
        """Process and clean device configuration input."""
        # Convert "None" string to actual None value
        if user_input.get(CONF_DEVICE_ENTITY) == NONE_OPTION:
            user_input[CONF_DEVICE_ENTITY] = None
            user_input[CONF_DEVICE_ENTITY_FRIENDLY_NAME] = None
            user_input['hvac_mode'] = None
        else:
            label = user_input.get(CONF_DEVICE_ENTITY)
            # Always normalize entity_id and extract hvac_mode
            cleaned_id, hvac_mode = clean_entity_id_and_mode(label)
            user_input[CONF_DEVICE_ENTITY] = cleaned_id
            user_input['hvac_mode'] = hvac_mode
            # Parse friendly_name from label if present
            if label and "(" in label and label.endswith(")"):
                entity_id = label.split(" (", 1)[0]
                friendly = label[label.find("(")+1:-1]
                user_input[CONF_DEVICE_ENTITY_FRIENDLY_NAME] = friendly
            else:
                user_input[CONF_DEVICE_ENTITY_FRIENDLY_NAME] = None
        return user_input
    
    def _process_schedule_input(self, user_input: Dict[str, Any]) -> Dict[str, Any]:
        """Process and clean schedule configuration input."""
        # Convert time strings to time objects
        if CONF_START_TIME in user_input and user_input[CONF_START_TIME]:
            try:
                hour, minute = map(int, user_input[CONF_START_TIME].split(':'))
                user_input[CONF_START_TIME] = time(hour, minute)
            except (ValueError, AttributeError):
                pass  # Error will be caught in validation
        
        if CONF_END_TIME in user_input and user_input[CONF_END_TIME]:
            try:
                hour, minute = map(int, user_input[CONF_END_TIME].split(':'))
                user_input[CONF_END_TIME] = time(hour, minute)
            except (ValueError, AttributeError):
                pass  # Error will be caught in validation
        
        # Collect days of week
        days_of_week = []
        for day in DAYS_OF_WEEK:
            if day in user_input and user_input[day]:
                days_of_week.append(day)
        user_input[CONF_DAYS_OF_WEEK] = days_of_week
        
        return user_input
    
    def _get_device_name_type_schema(self, defaults: Optional[Dict[str, Any]] = None) -> vol.Schema:
        """Get the schema for device name and type configuration using device_config_form.py."""
        return build_device_name_type_schema(defaults)
    
    def _get_device_selection_schema(self, entities: Dict[str, list], device_type: str, defaults: Optional[Dict[str, Any]] = None) -> vol.Schema:
        """Get the schema for device selection configuration using device_config_form.py."""
        return build_device_selection_schema(entities, device_type, defaults)
    
    def _get_device_basic_settings_schema(self, defaults: Optional[Dict[str, Any]] = None) -> vol.Schema:
        """Get the schema for device basic settings configuration using device_config_form.py."""
        return build_device_basic_settings_schema(defaults)
    
    def _get_device_schedule_schema(self, defaults: Optional[Dict[str, Any]] = None) -> vol.Schema:
        """Get the schema for device schedule configuration using device_config_form.py."""
        return build_device_schedule_schema(defaults)

    async def _finalize_device_config(self):
        """Finalize device configuration, persist devices, and return to appropriate screen."""
        _LOGGER = get_logger(__name__)
        # Add or update device ID
        if self._action == ACTION_ADD:
            self._device_config[CONF_DEVICE_ID] = str(uuid.uuid4())
            self._devices.append(self._device_config)
            log_info("[DeviceConfigMixin] Added device: %s", self._device_config)
            audit_action("device_add", {"device": self._device_config})
        else:  # ACTION_EDIT
            self._device_config[CONF_DEVICE_ID] = self._device_config.get(CONF_DEVICE_ID) or str(uuid.uuid4())
            if self._device_index is not None:
                self._devices[self._device_index] = self._device_config
                log_info("[DeviceConfigMixin] Edited device: %s", self._device_config)
                audit_action("device_edit", {"device": self._device_config})
        # Persist devices to config_entry.data if possible
        if hasattr(self, "hass") and hasattr(self, "config_entry"):
            # Try to persist devices immediately
            try:
                data = getattr(self, "_solar_config", {}).copy() if hasattr(self, "_solar_config") else {}
                data[CONF_DEVICES] = self._devices
                self.hass.config_entries.async_update_entry(self.config_entry, data=data)
                log_info("[DeviceConfigMixin] Persisted devices to config_entry.data: %d devices", len(self._devices))
            except Exception as e:
                log_error("[DeviceConfigMixin] Failed to persist devices: %s", e)
                log_exception("device_persist", e)
        # Check which method to call based on available methods
        if hasattr(self, 'async_step_manage_devices'):
            # For SunAllocatorOptionsFlowHandler
            return await self.async_step_manage_devices()
        else:
            # For SunAllocatorConfigFlow
            return await self.async_step_devices()
    
    # Device configuration flow methods
    async def async_step_device_name_type(self, user_input=None):
        """Handle the device name and type step."""
        errors = {}
        
        if user_input is not None:
            # Validate input
            errors = self._validate_device_config(user_input)
            
            if not errors:
                # Store device name and type
                self._device_config.update(user_input)
                
                # Proceed to device selection step
                return await self.async_step_device_selection()
        
        # Create schema for device name and type
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
        device_type = self._device_config.get(CONF_DEVICE_TYPE, DEVICE_TYPE_CUSTOM)
        
        if user_input is not None:
            # Process input
            user_input = self._process_device_input(user_input)
            
            # Store device selection
            self._device_config.update(user_input)
            
            # Proceed to basic settings step
            return await self.async_step_device_basic_settings()
        
        # Create schema based on device type
        schema = self._get_device_selection_schema(entities, device_type, self._device_config)
        
        return self.async_show_form(
            step_id=STEP_DEVICE_SELECTION,
            data_schema=schema,
            description_placeholders={
                "device_name": self._device_config.get(CONF_DEVICE_NAME, "New Device"),
                "device_type": device_type,
            },
            errors=errors,
        )
        
    async def async_step_device_basic_settings(self, user_input=None):
        """Handle the device basic settings step."""
        errors = {}
        
        if user_input is not None:
            # Validate input
            errors = self._validate_basic_settings(user_input)
            
            if not errors:
                # Store basic settings
                self._device_config.update(user_input)
                
                # If scheduling is enabled, proceed to schedule step
                if self._device_config.get(CONF_SCHEDULE_ENABLED, False):
                    return await self.async_step_device_schedule()
                else:
                    # If scheduling is not enabled, finalize device configuration
                    return await self._finalize_device_config()
        
        # Create schema for basic settings
        schema = self._get_device_basic_settings_schema(self._device_config)
        
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
            # Validate input
            errors = self._validate_schedule_config(user_input)
            
            if not errors:
                # Process and store schedule settings
                user_input = self._process_schedule_input(user_input)
                self._device_config.update(user_input)
                
                # Finalize device configuration
                return await self._finalize_device_config()
        
        # Create schema for schedule settings
        schema = self._get_device_schedule_schema(self._device_config)
        
        return self.async_show_form(
            step_id=STEP_DEVICE_SCHEDULE,
            data_schema=schema,
            description_placeholders={
                "device_name": self._device_config.get(CONF_DEVICE_NAME, "New Device"),
            },
            errors=errors,
        )