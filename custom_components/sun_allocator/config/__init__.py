"""Refactored Sun Allocator config flow."""

import uuid
import json

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import selector

from . import solar_config
from . import device_config
from . import temperature_config
from . import advanced_config
from ..core.logger import log_debug, audit_action

from ..const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_TEMPERATURE_COMPENSATION_ENABLED,
    CONF_ADVANCED_SETTINGS_ENABLED,
    CONF_ACTION,
    STEP_MAIN_MENU,
    STEP_SETTINGS,
    STEP_MANAGE_DEVICES,
    ACTION_ADD,
    ACTION_EDIT,
    ACTION_REMOVE,
    ACTION_SETTINGS,
    ACTION_ADD_DEVICE,
    ACTION_MANAGE_DEVICES,
    ACTION_BACK,
    STEP_CONFIRM_REMOVE,
)


class SunAllocatorConfigFlow(
    solar_config.SolarConfigMixin,
    temperature_config.TemperatureConfigMixin,
    advanced_config.AdvancedConfigMixin,
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    """Handle a config flow for Sun Allocator."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._solar_config = {}
        self._devices = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow."""
        return SunAllocatorOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle the initial step - solar panel configuration."""
        errors = {}

        if user_input is not None:
            errors = self._validate_solar_config(user_input)

            if not errors:
                user_input = self._process_solar_config_input(user_input)
                self._solar_config = user_input
                audit_action("solar_config_saved", {"config": user_input})

                self._solar_config[CONF_TEMPERATURE_COMPENSATION_ENABLED] = user_input.get(
                    CONF_TEMPERATURE_COMPENSATION_ENABLED, False
                )
                self._solar_config[CONF_ADVANCED_SETTINGS_ENABLED] = user_input.get(
                    CONF_ADVANCED_SETTINGS_ENABLED, False
                )

                if self._solar_config.get(CONF_TEMPERATURE_COMPENSATION_ENABLED, False):
                    return await self.async_step_temperature_compensation()
                if self._solar_config.get(CONF_ADVANCED_SETTINGS_ENABLED, False):
                    return await self.async_step_advanced_settings()

                return self._create_entry()

        schema = self._get_solar_config_schema(self._solar_config)

        extended_schema = schema.extend(
            {
                vol.Required(
                    CONF_TEMPERATURE_COMPENSATION_ENABLED,
                    default=self._solar_config.get(
                        CONF_TEMPERATURE_COMPENSATION_ENABLED, False
                    ),
                ): bool,
                vol.Required(
                    CONF_ADVANCED_SETTINGS_ENABLED,
                    default=self._solar_config.get(
                        CONF_ADVANCED_SETTINGS_ENABLED, False
                    ),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=extended_schema,
            errors=errors,
        )

    def _create_entry(self):
        """Create the config entry."""
        data = self._solar_config.copy()
        data[CONF_DEVICES] = [] 
        
        return self.async_create_entry(
            title="Sun Allocator",
            data=data,
        )

    async def _save_and_return(self):
        """Save config and proceed to entry creation."""
        return self._create_entry()


# TODO: Fix deprecation warning for explicit config_entry setting in OptionsFlow.
# This will require changes in how the options flow is tested.
# The current test environment does not seem to automatically provide the config_entry
# to the handler, which causes tests to fail when the deprecation is fixed.
# This needs to be addressed before HA version 2025.12.
class SunAllocatorOptionsFlowHandler(
    solar_config.SolarConfigMixin,
    device_config.DeviceConfigMixin,
    temperature_config.TemperatureConfigMixin,
    advanced_config.AdvancedConfigMixin,
    config_entries.OptionsFlow,
):
    """Handle options flow for Sun Allocator."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        super().__init__()
        self.config_entry = config_entry
        self._solar_config = {}
        self._devices = []
        self._device_config = {}
        self._device_index = None
        self._action = None
        self._device_to_remove = None

    async def async_step_init(self, _user_input=None):
        """Manage the options for the custom component."""
        self._solar_config = {
            k: v for k, v in self.config_entry.data.items() if k != CONF_DEVICES
        }
        self._devices = self.config_entry.data.get(CONF_DEVICES, [])

        log_debug("Loaded %d devices", len(self._devices))
        return await self.async_step_main_menu()

    async def async_step_main_menu(self, user_input=None):
        """Handle the main menu step."""
        errors = {}

        if user_input is not None:
            action = user_input.get(CONF_ACTION, "")

            if action == ACTION_SETTINGS:
                return await self.async_step_settings()
            if action == ACTION_MANAGE_DEVICES:
                return await self.async_step_manage_devices()

        return self.async_show_form(
            step_id=STEP_MAIN_MENU,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ACTION,
                        default=ACTION_SETTINGS,
                    ): selector(
                        {
                            "select": {
                                "options": [ACTION_SETTINGS, ACTION_MANAGE_DEVICES],
                                "translation_key": "main_menu_action",
                            }
                        }
                    ),
                }
            ),
            description_placeholders={"devices_count": len(self._devices)},
            errors=errors,
        )

    async def async_step_settings(self, user_input=None):
        """Handle the settings step."""
        errors = {}

        if user_input is not None:
            errors = self._validate_solar_config(user_input)

            if not errors:
                user_input = self._process_solar_config_input(user_input)
                self._solar_config.update(user_input)

                if user_input.get(CONF_TEMPERATURE_COMPENSATION_ENABLED, False):
                    return await self.async_step_temperature_compensation()
                if user_input.get(CONF_ADVANCED_SETTINGS_ENABLED, False):
                    return await self.async_step_advanced_settings()

                return await self._save_and_return()

        schema = self._get_solar_config_schema(self._solar_config)

        extended_schema = schema.extend(
            {
                vol.Required(
                    CONF_TEMPERATURE_COMPENSATION_ENABLED,
                    default=self._solar_config.get(
                        CONF_TEMPERATURE_COMPENSATION_ENABLED, False
                    ),
                ): bool,
                vol.Required(
                    CONF_ADVANCED_SETTINGS_ENABLED,
                    default=self._solar_config.get(
                        CONF_ADVANCED_SETTINGS_ENABLED, False
                    ),
                ): bool,
            }
        )

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

            if action == ACTION_ADD_DEVICE:
                self._action = ACTION_ADD
                self._device_config = {}
                return await self.async_step_device_name_type()

            if action == ACTION_EDIT:
                self._action = ACTION_EDIT
                if selected_device_id:
                    self._device_index = next(
                        (
                            i
                            for i, d in enumerate(self._devices)
                            if d[CONF_DEVICE_ID] == selected_device_id
                        ),
                        None,
                    )
                    if self._device_index is not None:
                        self._device_config = self._devices[self._device_index].copy()
                        return await self.async_step_device_name_type()
                errors[CONF_DEVICE_ID] = "device_name_required"

            if action == ACTION_REMOVE:
                if selected_device_id:
                    self._device_to_remove = selected_device_id
                    return await self.async_step_confirm_remove()
                errors[CONF_DEVICE_ID] = "device_name_required"

            if action == ACTION_BACK:
                return await self._save_and_return()

        device_options = {d[CONF_DEVICE_ID]: d[CONF_DEVICE_NAME] for d in self._devices}

        action_options = [ACTION_ADD_DEVICE, ACTION_EDIT, ACTION_REMOVE, ACTION_BACK]

        schema_dict = {}

        if self._devices:
            default_device_id = self._devices[0][CONF_DEVICE_ID]
            schema_dict[
                vol.Required(
                    CONF_DEVICE_ID,
                    default=default_device_id,
                )
            ] = vol.In(device_options)

        schema_dict[
            vol.Required(
                CONF_ACTION,
                default=ACTION_EDIT,
            )
        ] = selector(
            {
                "select": {
                    "options": action_options,
                    "translation_key": "manage_devices_action",
                }
            }
        )

        devices_list_str = ", ".join([d[CONF_DEVICE_NAME] for d in self._devices])
        return self.async_show_form(
            step_id=STEP_MANAGE_DEVICES,
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "devices_count": len(self._devices),
                "devices_list": devices_list_str or "None",
            },
            errors=errors,
        )

    async def async_step_confirm_remove(self, user_input=None):
        """Confirmation step for device removal."""
        if user_input is not None:
            if user_input.get("confirm"):
                # Remove device from device registry
                device_registry = dr.async_get(self.hass)
                device_to_remove = device_registry.async_get_device(
                    identifiers={(DOMAIN, self._device_to_remove)}
                )
                if device_to_remove:
                    device_registry.async_remove_device(device_to_remove.id)

                self._devices = [
                    d
                    for d in self._devices
                    if d[CONF_DEVICE_ID] != self._device_to_remove
                ]
                data = dict(self.config_entry.data)
                data.update(self._solar_config)
                data[CONF_DEVICES] = self._devices

                data["devices_str"] = json.dumps(self._devices)
                log_debug(
                    "--- CONFIG FLOW REMOVE ---: Saving %d devices. Data: %s",
                    len(self._devices),
                    data,
                )
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=data
                )
                return await self.async_step_manage_devices()

            return await self.async_step_manage_devices()

        return self.async_show_form(
            step_id=STEP_CONFIRM_REMOVE,
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
            description_placeholders={
                "device_name": self._get_device_name(self._device_to_remove)
            },
        )

    def _get_device_name(self, device_id):
        """Get device name by its ID."""
        for device in self._devices:
            if device[CONF_DEVICE_ID] == device_id:
                return device.get(CONF_DEVICE_NAME, "Unnamed device")
        return "Unknown device"

    async def _save_and_return(self):
        """Save configuration, reload integration and return to main menu."""
        data = dict(self.config_entry.data)
        data.update(self._solar_config)
        data[CONF_DEVICES] = self._devices
        data["devices_str"] = json.dumps(self._devices)
        data.pop("test_array", None)
        log_debug(
            "--- CONFIG FLOW SAVE ---: Saving %d devices. Data: %s",
            len(self._devices),
            data,
        )
        self.hass.config_entries.async_update_entry(self.config_entry, data=data)
        await self.hass.config_entries.async_reload(self.config_entry.entry_id)
        return await self.async_step_main_menu()

    async def _finalize_device_config(self):
        """Finalize device configuration, persist, and reload."""
        if self._action == ACTION_ADD:
            self._device_config[CONF_DEVICE_ID] = str(uuid.uuid4())
            self._devices.append(self._device_config)
        else:  # ACTION_EDIT
            self._device_config[CONF_DEVICE_ID] = self._device_config.get(
                CONF_DEVICE_ID
            ) or str(uuid.uuid4())
            if self._device_index is not None:
                self._devices[self._device_index] = self._device_config

        data = dict(self.config_entry.data)
        data.update(self._solar_config)
        data[CONF_DEVICES] = self._devices
        data["devices_str"] = json.dumps(self._devices)
        data.pop("test_array", None)
        log_debug(
            "--- CONFIG FLOW FINALIZE ---: Saving %d devices. Data: %s",
            len(self._devices),
            data,
        )
        self.hass.config_entries.async_update_entry(self.config_entry, data=data)
        await self.hass.config_entries.async_reload(self.config_entry.entry_id)
        return await self.async_step_manage_devices()


@callback
def async_get_options_flow(config_entry):
    """Get the options flow."""
    return SunAllocatorOptionsFlowHandler(config_entry)


# Export classes for Home Assistant
__all__ = ["SunAllocatorConfigFlow", "async_get_options_flow"]
