"""Refactored Solar Vampire config flow."""
import voluptuous as vol
import uuid
from homeassistant import config_entries
from homeassistant.core import callback
from typing import Dict, Any

from .solar_config import SolarConfigMixin
from .device_config import DeviceConfigMixin
from .temperature_config import TemperatureConfigMixin
from ..const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_TEMPERATURE_COMPENSATION_ENABLED,
    STEP_DEVICES,
    STEP_DEVICE_NAME_TYPE,
    STEP_DEVICE_SELECTION,
    STEP_DEVICE_BASIC_SETTINGS,
    STEP_DEVICE_SCHEDULE,
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


class SolarVampireConfigFlow(
    SolarConfigMixin,
    DeviceConfigMixin,
    TemperatureConfigMixin,
    config_entries.ConfigFlow,
    domain=DOMAIN
):
    """Handle a config flow for Solar Vampire."""
    
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
        return SolarVampireOptionsFlowHandler(config_entry)

    async def async_step_devices(self, user_input=None):
        """Handle the device list step."""
        errors = {}
        
        if user_input is not None:
            action = user_input.get("action", "")
            
            if action == ACTION_ADD:
                # Add a new device
                self._action = ACTION_ADD
                self._device_config = {}
                return await self.async_step_device_name_type()
            
            elif action.startswith(f"{ACTION_EDIT}_"):
                # Edit an existing device
                self._action = ACTION_EDIT
                device_id = action[len(f"{ACTION_EDIT}_"):]
                self._device_index = next((i for i, d in enumerate(self._devices) if d[CONF_DEVICE_ID] == device_id), None)
                if self._device_index is not None:
                    self._device_config = self._devices[self._device_index].copy()
                    return await self.async_step_device_name_type()
            
            elif action.startswith(f"{ACTION_REMOVE}_"):
                # Remove a device
                device_id = action[len(f"{ACTION_REMOVE}_"):]
                self._devices = [d for d in self._devices if d[CONF_DEVICE_ID] != device_id]
                # Stay on the devices page
                return await self.async_step_devices()
            
            elif action == ACTION_FINISH:
                # Finish configuration
                data = self._solar_config.copy()
                data[CONF_DEVICES] = self._devices
                return self.async_create_entry(title="SolarVampire", data=data)
        
        # Prepare the options for the form
        options = {
            ACTION_ADD: "add",
            ACTION_FINISH: "finish"
        }
        
        # Add edit/remove options for existing devices
        for device in self._devices:
            device_id = device[CONF_DEVICE_ID]
            device_name = device[CONF_DEVICE_NAME]
            options[f"{ACTION_EDIT}_{device_id}"] = f"edit_{device_name}"
            options[f"{ACTION_REMOVE}_{device_id}"] = f"remove_{device_name}"
        
        return self.async_show_form(
            step_id=STEP_DEVICES,
            data_schema=vol.Schema({
                vol.Required("action", default=ACTION_FINISH): vol.In(options),
            }),
            description_placeholders={
                "devices_count": len(self._devices),
                "devices_list": ", ".join([d[CONF_DEVICE_NAME] for d in self._devices]) or "None",
            },
            errors=errors,
        )

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
        device_type = self._device_config.get("device_type", "custom")
        
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
            errors = self._validate_device_config(user_input)
            
            if not errors:
                # Store basic settings
                self._device_config.update(user_input)
                
                # If scheduling is enabled, proceed to schedule step
                if self._device_config.get("schedule_enabled", False):
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


class SolarVampireOptionsFlowHandler(
    SolarConfigMixin,
    DeviceConfigMixin,
    TemperatureConfigMixin,
    config_entries.OptionsFlow
):
    """Handle options flow for Solar Vampire."""
    
    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry
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
                if k not in ["esphome_relay_entity", "esphome_mode_select_entity", 
                            "auto_control_enabled", "min_excess_power"]
            }
            
            # Extract device configuration if available
            if self.config_entry.data.get("esphome_relay_entity") or self.config_entry.data.get("esphome_mode_select_entity"):
                device = {
                    CONF_DEVICE_ID: str(uuid.uuid4()),
                    CONF_DEVICE_NAME: "Default Device",
                    "esphome_relay_entity": self.config_entry.data.get("esphome_relay_entity"),
                    "esphome_mode_select_entity": self.config_entry.data.get("esphome_mode_select_entity"),
                    "auto_control_enabled": self.config_entry.data.get("auto_control_enabled", False),
                    "min_excess_power": self.config_entry.data.get("min_excess_power", 50),
                    "device_priority": 50,
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
        
        # Proceed to main menu
        return await self.async_step_main_menu()
        
    async def async_step_main_menu(self, user_input=None):
        """Handle the main menu step."""
        errors = {}
        
        if user_input is not None:
            action = user_input.get("action", "")
            
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
                vol.Required("action", default=ACTION_SETTINGS): vol.In(options),
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
                else:
                    # Save configuration and return to main menu
                    return await self._save_and_return()

        # Create schema with MPPT parameters and temperature compensation checkbox
        schema_dict = self._get_solar_config_schema(sensors, self._solar_config).schema
        
        # Add MPPT algorithm parameters
        schema_dict.update({
            vol.Optional("curve_factor_k", default=self._solar_config.get("curve_factor_k", 0.2)): 
                vol.All(vol.Coerce(float), vol.Range(min=0.1, max=0.5)),
            vol.Optional("efficiency_correction_factor", default=self._solar_config.get("efficiency_correction_factor", 1.05)): 
                vol.All(vol.Coerce(float), vol.Range(min=1.0, max=1.2)),
            vol.Optional("min_inverter_voltage", default=self._solar_config.get("min_inverter_voltage", 100.0)): 
                vol.Coerce(float),
            # Temperature compensation checkbox
            vol.Required(CONF_TEMPERATURE_COMPENSATION_ENABLED, 
                        default=self._solar_config.get(CONF_TEMPERATURE_COMPENSATION_ENABLED, False)): bool,
        })
        
        return self.async_show_form(
            step_id=STEP_SETTINGS,
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )
    
    async def async_step_manage_devices(self, user_input=None):
        """Handle device management step."""
        errors = {}
        
        if user_input is not None:
            action = user_input.get("action", "")
            
            if action.startswith(f"{ACTION_EDIT}_"):
                # Edit an existing device
                self._action = ACTION_EDIT
                device_id = action[len(f"{ACTION_EDIT}_"):]
                self._device_index = next((i for i, d in enumerate(self._devices) if d[CONF_DEVICE_ID] == device_id), None)
                if self._device_index is not None:
                    self._device_config = self._devices[self._device_index].copy()
                    return await self.async_step_device_name_type()
            
            elif action.startswith(f"{ACTION_REMOVE}_"):
                # Remove a device
                device_id = action[len(f"{ACTION_REMOVE}_"):]
                self._devices = [d for d in self._devices if d[CONF_DEVICE_ID] != device_id]
                # Stay on the manage devices page
                return await self.async_step_manage_devices()
            
            elif action == ACTION_BACK:
                # Return to main menu
                return await self.async_step_main_menu()
        
        # Prepare the options for the form
        options = {ACTION_BACK: "back"}
        
        # Add edit/remove options for existing devices
        for device in self._devices:
            device_id = device[CONF_DEVICE_ID]
            device_name = device[CONF_DEVICE_NAME]
            options[f"{ACTION_EDIT}_{device_id}"] = f"Edit {device_name}"
            options[f"{ACTION_REMOVE}_{device_id}"] = f"Remove {device_name}"
        
        return self.async_show_form(
            step_id=STEP_MANAGE_DEVICES,
            data_schema=vol.Schema({
                vol.Required("action", default=ACTION_BACK): vol.In(options),
            }),
            description_placeholders={
                "devices_count": len(self._devices),
                "devices_list": ", ".join([d[CONF_DEVICE_NAME] for d in self._devices]) or "None",
            },
            errors=errors,
        )

    async def _save_and_return(self):
        """Save configuration and return to main menu."""
        data = self._solar_config.copy()
        data[CONF_DEVICES] = self._devices
        self.hass.config_entries.async_update_entry(self.config_entry, data=data)
        
        # Return to main menu
        return await self.async_step_main_menu()

    # Inherit device configuration methods from DeviceConfigMixin
    async def async_step_device_name_type(self, user_input=None):
        """Handle the device name and type step in options flow."""
        return await super().async_step_device_name_type(user_input)
    
    async def async_step_device_selection(self, user_input=None):
        """Handle the device selection step in options flow."""
        return await super().async_step_device_selection(user_input)
    
    async def async_step_device_basic_settings(self, user_input=None):
        """Handle the device basic settings step in options flow."""
        return await super().async_step_device_basic_settings(user_input)
    
    async def async_step_device_schedule(self, user_input=None):
        """Handle the device schedule step in options flow."""
        return await super().async_step_device_schedule(user_input)

    async def _finalize_device_config(self):
        """Finalize device configuration and return to manage devices."""
        # Add or update device ID
        if self._action == ACTION_ADD:
            self._device_config[CONF_DEVICE_ID] = str(uuid.uuid4())
            self._devices.append(self._device_config)
        else:  # ACTION_EDIT
            self._device_config[CONF_DEVICE_ID] = self._device_config.get(CONF_DEVICE_ID) or str(uuid.uuid4())
            if self._device_index is not None:
                self._devices[self._device_index] = self._device_config
        
        # Return to manage devices
        return await self.async_step_manage_devices()

@callback
def async_get_options_flow(config_entry):
    """Get the options flow."""
    return SolarVampireOptionsFlowHandler(config_entry)

# Export classes for Home Assistant
__all__ = ["SolarVampireConfigFlow", "async_get_options_flow"]