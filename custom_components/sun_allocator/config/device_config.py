"""Device configuration module for Sun Allocator config flow."""
import voluptuous as vol
import uuid
from datetime import time
from homeassistant.core import HomeAssistant
from typing import Dict, Any, List, Optional

from ..const import (
    CONF_ESPHOME_RELAY_ENTITY,
    CONF_ESPHOME_MODE_SELECT_ENTITY,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_PRIORITY,
    CONF_DEVICE_TYPE,
    DEVICE_TYPE_NONE,
    DEVICE_TYPE_STANDARD,
    DEVICE_TYPE_CUSTOM,
    CONF_MIN_EXPECTED_W,
    CONF_MAX_EXPECTED_W,
    CONF_SCHEDULE_ENABLED,
    CONF_START_TIME,
    CONF_END_TIME,
    CONF_DAYS_OF_WEEK,
    DAYS_OF_WEEK,
    DAY_MONDAY,
    DAY_TUESDAY,
    DAY_WEDNESDAY,
    DAY_THURSDAY,
    DAY_FRIDAY,
    DAY_SATURDAY,
    DAY_SUNDAY,
    STEP_DEVICES,
    STEP_DEVICE_NAME_TYPE,
    STEP_DEVICE_SELECTION,
    STEP_DEVICE_BASIC_SETTINGS,
    STEP_DEVICE_SCHEDULE,
    STEP_MANAGE_DEVICES,
    ACTION_ADD,
    ACTION_EDIT,
    ACTION_REMOVE,
    ACTION_ADD_DEVICE,
    ACTION_MANAGE_DEVICES,
    NONE_OPTION,
    STATE_ON,
    STATE_OFF,
    DOMAIN_LIGHT,
    DOMAIN_SWITCH,
    DOMAIN_INPUT_BOOLEAN,
    DOMAIN_AUTOMATION,
    DOMAIN_SCRIPT,
    DOMAIN_SELECT,
)


class DeviceConfigMixin:
    """Mixin for device configuration steps."""
    
    def _get_device_entities(self, hass: HomeAssistant) -> Dict[str, list]:
        """Get available device entities categorized by type."""
        # Get ESPHome entities for relay control
        light_entities = [e.entity_id for e in hass.states.async_all() if e.entity_id.startswith(f"{DOMAIN_LIGHT}.")]
        select_entities = [e.entity_id for e in hass.states.async_all() if e.entity_id.startswith(f"{DOMAIN_SELECT}.")]
        
        # Get boolean entities from various domains for standard relay entities
        boolean_domains = [f"{DOMAIN_LIGHT}.", f"{DOMAIN_SWITCH}.", f"{DOMAIN_INPUT_BOOLEAN}.", f"{DOMAIN_AUTOMATION}.", f"{DOMAIN_SCRIPT}."]
        boolean_entities = []
        for e in hass.states.async_all():
            # Check if entity belongs to one of the boolean domains
            if any(e.entity_id.startswith(domain) for domain in boolean_domains):
                # Check if entity state is boolean (on/off)
                if e.state in [STATE_ON, STATE_OFF]:
                    # Exclude integration's own entities (old/new names)
                    if (
                        "sun_allocator" not in e.entity_id.lower()
                        and "sunallocator" not in e.entity_id.lower()
                        and "sun_allocator" not in e.entity_id.lower()
                        and "sunallocator" not in e.entity_id.lower()
                    ):
                        boolean_entities.append(e.entity_id)
        
        # Sort entities for better organization in dropdown list
        boolean_entities.sort()
        
        # Create separate lists for custom and standard entities
        custom_relay_entities = [
            e for e in light_entities
            if (
                "sun_allocator" in e.lower() or "sunallocator" in e.lower()
                or "sun_allocator" in e.lower() or "sunallocator" in e.lower()
            )
        ]
        standard_relay_entities = boolean_entities
        
        custom_mode_select_entities = [e for e in select_entities if "sun_allocator" in e.lower() or "sunallocator" in e.lower()]
        
        # Add a "None" option to all lists
        custom_relay_entities = [NONE_OPTION] + custom_relay_entities
        standard_relay_entities = [NONE_OPTION] + standard_relay_entities
        custom_mode_select_entities = [NONE_OPTION] + custom_mode_select_entities
        
        return {
            "custom_relay_entities": custom_relay_entities,
            "standard_relay_entities": standard_relay_entities,
            "custom_mode_select_entities": custom_mode_select_entities
        }
    
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
        if user_input.get(CONF_ESPHOME_RELAY_ENTITY) == NONE_OPTION:
            user_input[CONF_ESPHOME_RELAY_ENTITY] = None
        if user_input.get(CONF_ESPHOME_MODE_SELECT_ENTITY) == NONE_OPTION:
            user_input[CONF_ESPHOME_MODE_SELECT_ENTITY] = None
        
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
        """Get the schema for device name and type configuration."""
        if defaults is None:
            defaults = {}
        
        device_type_options = {
            DEVICE_TYPE_STANDARD: DEVICE_TYPE_STANDARD,
            DEVICE_TYPE_CUSTOM: DEVICE_TYPE_CUSTOM
        }
        
        # If the default type is "No Device", change it to "Custom"
        default_type = defaults.get(CONF_DEVICE_TYPE, DEVICE_TYPE_CUSTOM)
        if default_type == DEVICE_TYPE_NONE:
            default_type = DEVICE_TYPE_CUSTOM
        
        return vol.Schema({
            vol.Required(CONF_DEVICE_NAME, default=defaults.get(CONF_DEVICE_NAME, ""), description={"suggested_value": defaults.get(CONF_DEVICE_NAME, "")}): str,
            vol.Required(CONF_DEVICE_TYPE, default=default_type, description={"suggested_value": default_type}): vol.In(device_type_options),
        })
    
    def _get_device_selection_schema(self, entities: Dict[str, list], device_type: str, defaults: Optional[Dict[str, Any]] = None) -> vol.Schema:
        """Get the schema for device selection configuration."""
        if defaults is None:
            defaults = {}
        
        # Convert None values to "None" string for the dropdown
        default_relay = NONE_OPTION if defaults.get(CONF_ESPHOME_RELAY_ENTITY) is None else defaults.get(CONF_ESPHOME_RELAY_ENTITY, NONE_OPTION)
        default_mode = NONE_OPTION if defaults.get(CONF_ESPHOME_MODE_SELECT_ENTITY) is None else defaults.get(CONF_ESPHOME_MODE_SELECT_ENTITY, NONE_OPTION)
        
        schema = {}
        
        if device_type == DEVICE_TYPE_STANDARD:
            schema[vol.Optional(CONF_ESPHOME_RELAY_ENTITY, default=default_relay, description={"suggested_value": default_relay})] = vol.In(entities["standard_relay_entities"])
        
        if device_type == DEVICE_TYPE_CUSTOM:
            schema[vol.Optional(CONF_ESPHOME_RELAY_ENTITY, default=default_relay, description={"suggested_value": default_relay})] = vol.In(entities["custom_relay_entities"])
            schema[vol.Optional(CONF_ESPHOME_MODE_SELECT_ENTITY, default=default_mode, description={"suggested_value": default_mode})] = vol.In(entities["custom_mode_select_entities"])
        
        return vol.Schema(schema)
    
    def _get_device_basic_settings_schema(self, defaults: Optional[Dict[str, Any]] = None) -> vol.Schema:
        """Get the schema for device basic settings configuration."""
        if defaults is None:
            defaults = {}
        
        return vol.Schema({
            vol.Required(CONF_AUTO_CONTROL_ENABLED, default=defaults.get(CONF_AUTO_CONTROL_ENABLED, False), description={"suggested_value": defaults.get(CONF_AUTO_CONTROL_ENABLED, False)}): bool,
            vol.Optional(CONF_MIN_EXPECTED_W, default=defaults.get(CONF_MIN_EXPECTED_W, 0.0), description={"suggested_value": defaults.get(CONF_MIN_EXPECTED_W, 0.0)}): vol.Coerce(float),
            vol.Optional(CONF_MAX_EXPECTED_W, default=defaults.get(CONF_MAX_EXPECTED_W, 0.0), description={"suggested_value": defaults.get(CONF_MAX_EXPECTED_W, 0.0)}): vol.Coerce(float),
            vol.Required(CONF_DEVICE_PRIORITY, default=defaults.get(CONF_DEVICE_PRIORITY, 50), description={"suggested_value": defaults.get(CONF_DEVICE_PRIORITY, 50)}): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=100)
            ),
            vol.Required(CONF_SCHEDULE_ENABLED, default=defaults.get(CONF_SCHEDULE_ENABLED, False), description={"suggested_value": defaults.get(CONF_SCHEDULE_ENABLED, False)}): bool,
        })
    
    def _get_device_schedule_schema(self, defaults: Optional[Dict[str, Any]] = None) -> vol.Schema:
        """Get the schema for device schedule configuration."""
        if defaults is None:
            defaults = {}
        
        default_days = defaults.get(CONF_DAYS_OF_WEEK, DAYS_OF_WEEK)
        
        return vol.Schema({
            vol.Required(CONF_START_TIME, default=defaults.get(CONF_START_TIME, "08:00"), description={"suggested_value": defaults.get(CONF_START_TIME, "08:00")}): str,
            vol.Required(CONF_END_TIME, default=defaults.get(CONF_END_TIME, "20:00"), description={"suggested_value": defaults.get(CONF_END_TIME, "20:00")}): str,
            vol.Required(DAY_MONDAY, default=DAY_MONDAY in default_days, description={"suggested_value": DAY_MONDAY in default_days}): bool,
            vol.Required(DAY_TUESDAY, default=DAY_TUESDAY in default_days, description={"suggested_value": DAY_TUESDAY in default_days}): bool,
            vol.Required(DAY_WEDNESDAY, default=DAY_WEDNESDAY in default_days, description={"suggested_value": DAY_WEDNESDAY in default_days}): bool,
            vol.Required(DAY_THURSDAY, default=DAY_THURSDAY in default_days, description={"suggested_value": DAY_THURSDAY in default_days}): bool,
            vol.Required(DAY_FRIDAY, default=DAY_FRIDAY in default_days, description={"suggested_value": DAY_FRIDAY in default_days}): bool,
            vol.Required(DAY_SATURDAY, default=DAY_SATURDAY in default_days, description={"suggested_value": DAY_SATURDAY in default_days}): bool,
            vol.Required(DAY_SUNDAY, default=DAY_SUNDAY in default_days, description={"suggested_value": DAY_SUNDAY in default_days}): bool,
        })
    
    async def _finalize_device_config(self):
        """Finalize device configuration and return to appropriate screen."""
        # Add or update device ID
        if self._action == ACTION_ADD:
            self._device_config[CONF_DEVICE_ID] = str(uuid.uuid4())
            self._devices.append(self._device_config)
        else:  # ACTION_EDIT
            self._device_config[CONF_DEVICE_ID] = self._device_config.get(CONF_DEVICE_ID) or str(uuid.uuid4())
            if self._device_index is not None:
                self._devices[self._device_index] = self._device_config
        
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