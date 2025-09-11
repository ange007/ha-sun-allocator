"""Refactored Sun Allocator config flow."""
import voluptuous as vol
import uuid
from typing import Dict, Any

from homeassistant import config_entries
from homeassistant.core import callback

from .solar_config import SolarConfigMixin
from .device_config import DeviceConfigMixin
from .temperature_config import TemperatureConfigMixin
from .advanced_config import AdvancedConfigMixin
from ..utils.logger import log_warning # ADDED FOR DEBUGGING

from ..const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_TEMPERATURE_COMPENSATION_ENABLED,
    CONF_ADVANCED_SETTINGS_ENABLED,
    CONF_ACTION,
    CONF_ESPHOME_RELAY_ENTITY,
    CONF_ESPHOME_MODE_SELECT_ENTITY,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_MIN_EXPECTED_W,
    CONF_MAX_EXPECTED_W,
    CONF_DEVICE_PRIORITY,
    STEP_DEVICES,
    STEP_MAIN_MENU,
    STEP_SETTINGS,
    STEP_MANAGE_DEVICES,
    ACTION_ADD,
    ACTION_EDIT,
    ACTION_REMOVE,
    ACTION_SETTINGS,
    ACTION_ADD_DEVICE,
    ACTION_MANAGE_DEVICES,
    ACTION_FINISH,
    ACTION_BACK,
)


class SunAllocatorConfigFlow(
    SolarConfigMixin,
    DeviceConfigMixin,
    TemperatureConfigMixin,
    AdvancedConfigMixin,
    config_entries.ConfigFlow,
    domain=DOMAIN
):
    """Handle a config flow for Sun Allocator."""
    
    VERSION = 1
    
    def __init__(self):
        """Initialize the config flow."""
        self._solar_config = {}
        self._devices = []
        self._device_config = {}
        self._device_index = None
        self._action = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow."""
        return SunAllocatorOptionsFlowHandler(config_entry)

    async def async_step_devices(self, user_input=None):
        """Handle the device list step."""
        errors = {}

        if user_input is not None:
            action = user_input.get(CONF_ACTION, "")
            selected_device_id = user_input.get(CONF_DEVICE_ID)

            if action == ACTION_ADD:
                # Add a new device
                self._action = ACTION_ADD
                self._device_config = {}
                return await self.async_step_device_name_type()

            elif action == ACTION_EDIT:
                # Edit an existing device (requires selected device)
                if selected_device_id:
                    self._action = ACTION_EDIT
                    self._device_index = next(
                        (i for i, d in enumerate(self._devices) if d[CONF_DEVICE_ID] == selected_device_id),
                        None
                    )
                    if self._device_index is not None:
                        self._device_config = self._devices[self._device_index].copy()
                        return await self.async_step_device_name_type()
                # If no device selected, stay and show error
                errors[CONF_DEVICE_ID] = "device_name_required"

            elif action == ACTION_REMOVE:
                # Remove a device (requires selected device)
                if selected_device_id:
                    self._devices = [d for d in self._devices if d[CONF_DEVICE_ID] != selected_device_id]
                    # Stay on the devices page
                    return await self.async_step_devices()
                errors[CONF_DEVICE_ID] = "device_name_required"

            elif action == ACTION_FINISH:
                # Finish configuration
                data = self._solar_config.copy()
                data[CONF_DEVICES] = self._devices
                return self.async_create_entry(title="SunAllocator", data=data)

        from ..utils.ui_helpers import SelectSelectorBuilder
        # Build devices dropdown: value=id, label=name
        device_options = [
            {"label": d[CONF_DEVICE_NAME], "value": d[CONF_DEVICE_ID]}
            for d in self._devices
        ]
        # Build action dropdown for this step
        action_options = [
            {"label": "Back", "value": ACTION_BACK},
            {"label": "Edit", "value": ACTION_EDIT},
            {"label": "Remove", "value": ACTION_REMOVE},
        ]
        schema_dict = {}
        # Device selector
        if self._devices:
            default_device_id = self._devices[0][CONF_DEVICE_ID]
            schema_dict[vol.Required(
                CONF_DEVICE_ID,
                default=default_device_id,
                description={"suggested_value": default_device_id}
            )] = SelectSelectorBuilder(device_options).build()
        # Action selector
        schema_dict[vol.Required(
            CONF_ACTION,
            default=ACTION_FINISH,
            description={"suggested_value": ACTION_FINISH}
        )] = SelectSelectorBuilder(action_options).build()
        return self.async_show_form(
            step_id=STEP_DEVICES,
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "devices_count": len(self._devices),
                "devices_list": ", ".join([d[CONF_DEVICE_NAME] for d in self._devices]) or "None",
            },
            errors=errors,
        )

    # Device configuration methods are now in DeviceConfigMixin to avoid code duplication


class SunAllocatorOptionsFlowHandler(
    SolarConfigMixin,
    DeviceConfigMixin,
    TemperatureConfigMixin,
    AdvancedConfigMixin,
    config_entries.OptionsFlow
):
    """Handle options flow for Sun Allocator."""
    
    def __init__(self, config_entry):
        """Initialize options flow."""
        super().__init__()
        self._solar_config = {}
        self._devices = []
        self._device_config = {}
        self._device_index = None
        self._action = None

    async def async_step_init(self, user_input=None):
        """Manage the options for the custom component."""
        # Migrate old configuration format if needed
        if CONF_DEVICES not in self.config_entry.data:
            # Extract solar panel configuration
            self._solar_config = {
                k: v for k, v in self.config_entry.data.items() 
                if k not in [CONF_ESPHOME_RELAY_ENTITY, CONF_ESPHOME_MODE_SELECT_ENTITY, 
                            CONF_AUTO_CONTROL_ENABLED]
            }
            
            # Extract device configuration if available
            if self.config_entry.data.get(CONF_ESPHOME_RELAY_ENTITY) or self.config_entry.data.get(CONF_ESPHOME_MODE_SELECT_ENTITY):
                device = {
                    CONF_DEVICE_ID: str(uuid.uuid4()),
                    CONF_DEVICE_NAME: "Default Device",
                    CONF_ESPHOME_RELAY_ENTITY: self.config_entry.data.get(CONF_ESPHOME_RELAY_ENTITY),
                    CONF_ESPHOME_MODE_SELECT_ENTITY: self.config_entry.data.get(CONF_ESPHOME_MODE_SELECT_ENTITY),
                    CONF_AUTO_CONTROL_ENABLED: self.config_entry.data.get(CONF_AUTO_CONTROL_ENABLED, False),
                    CONF_MIN_EXPECTED_W: float(self.config_entry.data.get('min_excess_power', 0) or 0),
                    CONF_MAX_EXPECTED_W: 0.0,
                    CONF_DEVICE_PRIORITY: 50,
                }
                self._devices = [device]
            else:
                self._devices = []
        else:
            # Use existing configuration
            self._solar_config = {
                k: v for k, v in self.config_entry.data.items() if k != CONF_DEVICES
            }
            self._devices = self.config_entry.data.get(CONF_DEVICES, [])
        
        log_warning("--- CONFIG FLOW INIT ---: Loaded %d devices", len(self._devices))
        # Proceed to main menu
        return await self.async_step_main_menu()
        
    async def async_step_main_menu(self, user_input=None):
        """Handle the main menu step."""
        errors = {}
        
        if user_input is not None:
            action = user_input.get(CONF_ACTION, "")
            
            if action == ACTION_SETTINGS:
                # Go to settings
                return await self.async_step_settings()
            elif action == ACTION_ADD_DEVICE:
                # Add a new device
                self._action = ACTION_ADD
                self._device_config = {}
                return await self.async_step_device_name_type()
            elif action == ACTION_MANAGE_DEVICES:
                # Go to device management
                return await self.async_step_manage_devices()
        
        # Prepare the options for the form
        options = {
            ACTION_SETTINGS: "settings",
            ACTION_ADD_DEVICE: "add_device",
            ACTION_MANAGE_DEVICES: "manage_devices",
        }
        
        return self.async_show_form(
            step_id=STEP_MAIN_MENU,
            data_schema=vol.Schema({
                vol.Required(CONF_ACTION, default=ACTION_SETTINGS, description={"suggested_value": ACTION_SETTINGS}): vol.In(options),
            }),
            description_placeholders={
                "devices_count": len(self._devices),
            },
            errors=errors,
        )
        
    async def async_step_settings(self, user_input=None):
        """Handle the settings step."""
        errors = {}
        sensors = self._get_sensor_entities(self.hass)

        if user_input is not None:
            # Validate input
            errors = self._validate_solar_config(user_input)
            
            if not errors:
                # Process input
                user_input = self._process_solar_config_input(user_input)
                
                # Store solar panel configuration
                self._solar_config.update(user_input)
                
                # Check if temperature compensation is enabled
                if user_input.get(CONF_TEMPERATURE_COMPENSATION_ENABLED, False):
                    # Redirect to temperature compensation settings
                    return await self.async_step_temperature_compensation()
                # Check if advanced settings are enabled
                elif user_input.get(CONF_ADVANCED_SETTINGS_ENABLED, False):
                    # Redirect to advanced settings
                    return await self.async_step_advanced_settings()
                else:
                    # Save configuration and return to main menu
                    return await self._save_and_return()

        # Create schema with advanced settings and temperature compensation checkboxes
        original_schema = self._get_solar_config_schema(sensors, self._solar_config)
        
        # Extend the schema with advanced settings and temperature compensation checkboxes
        extended_schema = original_schema.extend({
            # Temperature compensation checkbox
            vol.Required(CONF_TEMPERATURE_COMPENSATION_ENABLED, 
                        default=self._solar_config.get(CONF_TEMPERATURE_COMPENSATION_ENABLED, False), 
                        description={"suggested_value": self._solar_config.get(CONF_TEMPERATURE_COMPENSATION_ENABLED, False)}): bool,
            # Advanced settings checkbox
            vol.Required(CONF_ADVANCED_SETTINGS_ENABLED, 
                        default=self._solar_config.get(CONF_ADVANCED_SETTINGS_ENABLED, False), 
                        description={"suggested_value": self._solar_config.get(CONF_ADVANCED_SETTINGS_ENABLED, False)}): bool,
        })
        
        return self.async_show_form(
            step_id=STEP_SETTINGS,
            data_schema=extended_schema,
            errors=errors,
        )
    
    async def async_step_manage_devices(self, user_input=None):
        """Handle device management step."""
        errors = {}

        if user_input is not None:
            action = user_input.get(CONF_ACTION, "")
            selected_device_id = user_input.get(CONF_DEVICE_ID)

            if action == ACTION_EDIT:
                self._action = ACTION_EDIT
                if selected_device_id:
                    self._device_index = next(
                        (i for i, d in enumerate(self._devices) if d[CONF_DEVICE_ID] == selected_device_id),
                        None
                    )
                    if self._device_index is not None:
                        self._device_config = self._devices[self._device_index].copy()
                        return await self.async_step_device_name_type()
                errors[CONF_DEVICE_ID] = "device_name_required"

            elif action == ACTION_REMOVE:
                if selected_device_id:
                    self._devices = [d for d in self._devices if d[CONF_DEVICE_ID] != selected_device_id]
                    # Persist changes immediately and stay on the manage devices page
                    data = self._solar_config.copy()
                    data[CONF_DEVICES] = self._devices
                    log_warning("--- CONFIG FLOW REMOVE ---: Saving %d devices", len(self._devices))
                    self.hass.config_entries.async_update_entry(self.config_entry, data=data)
                    return await self.async_step_manage_devices()
                errors[CONF_DEVICE_ID] = "device_name_required"

            elif action == ACTION_BACK:
                # Persist changes and return to main menu
                return await self._save_and_return()

        # Devices dropdown: id -> name
        device_options = {}
        for d in self._devices:
            device_options[d[CONF_DEVICE_ID]] = d[CONF_DEVICE_NAME]

        # Action dropdown for manage screen
        action_options = {
            ACTION_EDIT: "edit",
            ACTION_REMOVE: "remove",
            ACTION_BACK: "back",
        }

        schema_dict = {}

        # Device selector
        if self._devices:
            default_device_id = self._devices[0][CONF_DEVICE_ID]
            schema_dict[vol.Required(
                CONF_DEVICE_ID,
                default=default_device_id,
                description={"suggested_value": default_device_id}
            )] = vol.In(device_options)

        # Action selector
        schema_dict[vol.Required(
            CONF_ACTION,
            default=ACTION_EDIT,
            description={"suggested_value": ACTION_EDIT}
        )] = vol.In(action_options)

        return self.async_show_form(
            step_id=STEP_MANAGE_DEVICES,
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "devices_count": len(self._devices),
                "devices_list": ", ".join([d[CONF_DEVICE_NAME] for d in self._devices]) or "None",
            },
            errors=errors,
        )

    async def _save_and_return(self):
        """Save configuration, reload integration and return to main menu."""
        data = self._solar_config.copy()
        data[CONF_DEVICES] = self._devices
        log_warning("--- CONFIG FLOW SAVE ---: Saving %d devices", len(self._devices))
        self.hass.config_entries.async_update_entry(self.config_entry, data=data)
        # Live reload integration
        await self.hass.config_entries.async_reload(self.config_entry.entry_id)
        # Return to main menu
        return await self.async_step_main_menu()

    # Device configuration methods are inherited from DeviceConfigMixin
    # No need to override them as they work correctly through mixin inheritance

    async def _finalize_device_config(self):
        """Finalize device configuration, persist, reload integration, and return to manage devices."""
        # Add or update device ID
        if self._action == ACTION_ADD:
            self._device_config[CONF_DEVICE_ID] = str(uuid.uuid4())
            self._devices.append(self._device_config)
        else:  # ACTION_EDIT
            self._device_config[CONF_DEVICE_ID] = self._device_config.get(CONF_DEVICE_ID) or str(uuid.uuid4())
            if self._device_index is not None:
                self._devices[self._device_index] = self._device_config
        # Persist changes immediately so they survive HA restarts
        data = self._solar_config.copy()
        data[CONF_DEVICES] = self._devices
        log_warning("--- CONFIG FLOW FINALIZE ---: Saving %d devices", len(self._devices))
        self.hass.config_entries.async_update_entry(self.config_entry, data=data)
        # Live reload integration
        await self.hass.config_entries.async_reload(self.config_entry.entry_id)
        # Return to manage devices
        return await self.async_step_manage_devices()

@callback
def async_get_options_flow(config_entry):
    """Get the options flow."""
    return SunAllocatorOptionsFlowHandler(config_entry)

# Export classes for Home Assistant
__all__ = ["SunAllocatorConfigFlow", "async_get_options_flow"]