"""Refactored Sun Allocator config flow."""

import uuid
import json
import logging
from datetime import time as dt_time

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
    CONF_MPPT_INPUTS,
    CONF_MPPT_COUNT,
    CONF_PV_POWER,
    CONF_PV_VOLTAGE,
    CONF_TEMPERATURE_COMPENSATION_ENABLED,
    CONF_ADVANCED_SETTINGS_ENABLED,
    CONF_ACTION,
    MPPT_MAX_COUNT,
    STEP_MAIN_MENU,
    STEP_MPPT_INPUT,
    STEP_SETTINGS,
    STEP_MANAGE_DEVICES,
    ACTION_ADD,
    ACTION_EDIT,
    ACTION_REMOVE,
    ACTION_SETTINGS,
    ACTION_MANAGE_DEVICES,
    ACTION_SIMULATION,
    ACTION_BACK,
    STEP_CONFIRM_REMOVE,
    STEP_SIMULATION,
    CONF_SIM_ENABLED,
    CONF_SIM_PV_POWER,
    CONF_SIM_PV_VOLTAGE,
    CONF_SIM_CONSUMPTION,
    CONF_SIM_BATTERY_POWER,
    CONF_SIM_BATTERY_SOC,
    CONF_SIM_OVERRIDE_CONSUMPTION,
    CONF_SIM_OVERRIDE_BATTERY_POWER,
    CONF_SIM_OVERRIDE_BATTERY_SOC,
    DEFAULT_SIM_PV_POWER,
    DEFAULT_SIM_PV_VOLTAGE,
    DEFAULT_SIM_CONSUMPTION,
    DEFAULT_SIM_BATTERY_POWER,
    DEFAULT_SIM_BATTERY_SOC,
)


def _json_default(obj):
    """JSON serializer for types not serializable by default (e.g. datetime.time)."""
    if isinstance(obj, dt_time):
        return obj.strftime("%H:%M:%S")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


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
        """Hub-level config: mppt_count + shared sensors + toggles."""
        errors = {}

        if user_input is not None:
            try:
                count = int(user_input.get(CONF_MPPT_COUNT, 0))
            except (ValueError, TypeError):
                count = 0
            if not 1 <= count <= MPPT_MAX_COUNT:
                errors[CONF_MPPT_COUNT] = "invalid_mppt_count"

            if not errors:
                user_input = self._process_hub_config_input(user_input)
                self._solar_config = dict(user_input)
                self._solar_config[CONF_MPPT_COUNT] = count
                self._solar_config[CONF_MPPT_INPUTS] = []  # reset accumulator
                self._solar_config[CONF_TEMPERATURE_COMPENSATION_ENABLED] = (
                    user_input.get(CONF_TEMPERATURE_COMPENSATION_ENABLED, False)
                )
                self._solar_config[CONF_ADVANCED_SETTINGS_ENABLED] = user_input.get(
                    CONF_ADVANCED_SETTINGS_ENABLED, False
                )
                audit_action("solar_hub_saved", {"config": self._solar_config})
                return await self.async_step_mppt_input()

        schema = self._get_solar_hub_schema(self._solar_config)

        extended_schema = schema.extend(
            {
                vol.Required(
                    CONF_TEMPERATURE_COMPENSATION_ENABLED,
                    default=self._solar_config.get(
                        CONF_TEMPERATURE_COMPENSATION_ENABLED, False
                    ),
                ): selector({"boolean": {}}),
                vol.Required(
                    CONF_ADVANCED_SETTINGS_ENABLED,
                    default=self._solar_config.get(
                        CONF_ADVANCED_SETTINGS_ENABLED, False
                    ),
                ): selector({"boolean": {}}),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=extended_schema,
            errors=errors,
        )


    async def async_step_mppt_input(self, user_input=None):
        """Per-MPPT panel config; loops mppt_count times."""
        errors = {}
        existing = self._solar_config.get(CONF_MPPT_INPUTS, [])
        idx = len(existing)
        total = self._solar_config.get(CONF_MPPT_COUNT, 1)

        if user_input is not None:
            errors = self._validate_panel_only(user_input)
            existing_powers = [m.get(CONF_PV_POWER) for m in existing]
            existing_voltages = [m.get(CONF_PV_VOLTAGE) for m in existing]
            if user_input.get(CONF_PV_POWER) in existing_powers:
                errors[CONF_PV_POWER] = "duplicate_mppt_sensor"
            if user_input.get(CONF_PV_VOLTAGE) in existing_voltages:
                errors[CONF_PV_VOLTAGE] = "duplicate_mppt_sensor"

            if not errors:
                self._solar_config[CONF_MPPT_INPUTS] = existing + [dict(user_input)]
                if len(self._solar_config[CONF_MPPT_INPUTS]) >= total:
                    if self._solar_config.get(CONF_TEMPERATURE_COMPENSATION_ENABLED, False):
                        return await self.async_step_temperature_compensation()
                    if self._solar_config.get(CONF_ADVANCED_SETTINGS_ENABLED, False):
                        return await self.async_step_advanced_settings()
                    return self._create_entry()
                return await self.async_step_mppt_input()

        defaults = existing[idx] if idx < len(existing) else None
        schema = self._get_mppt_input_schema(defaults)

        return self.async_show_form(
            step_id=STEP_MPPT_INPUT,
            data_schema=schema,
            description_placeholders={
                "index": str(idx + 1),
                "total": str(total),
            },
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

        # `config_entry` property on OptionsFlow is read-only in newer HA versions.
        # Store the provided entry in a private attribute and use that.
        self._config_entry = config_entry

        self._solar_config = {}
        self._devices = []
        self._device_config = {}
        self._device_index = None
        self._action = None
        self._device_to_remove = None
        self._existing_mppt_inputs = []


    async def async_step_init(self, _user_input=None):
        """Manage the options for the custom component."""
        self._solar_config = {
            k: v for k, v in self._config_entry.data.items() if k != CONF_DEVICES
        }
        self._devices = self._config_entry.data.get(CONF_DEVICES, [])

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
            if action == ACTION_SIMULATION:
                return await self.async_step_simulation()

        debug_active = logging.getLogger(
            "custom_components.sun_allocator"
        ).isEnabledFor(logging.DEBUG)
        menu_options = [ACTION_SETTINGS, ACTION_MANAGE_DEVICES]
        if debug_active:
            menu_options.append(ACTION_SIMULATION)

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
                                "options": menu_options,
                                "translation_key": "main_menu_action",
                            }
                        }
                    ),
                }
            ),
            description_placeholders={"devices_count": len(self._devices)},
            errors=errors,
        )


    async def async_step_simulation(self, user_input=None):
        """Debug simulation: override all sensor readings with fixed values."""
        if user_input is not None:
            self._solar_config[CONF_SIM_ENABLED] = user_input.get(CONF_SIM_ENABLED, False)
            self._solar_config[CONF_SIM_PV_POWER] = float(
                user_input.get(CONF_SIM_PV_POWER, DEFAULT_SIM_PV_POWER)
            )
            self._solar_config[CONF_SIM_PV_VOLTAGE] = float(
                user_input.get(CONF_SIM_PV_VOLTAGE, DEFAULT_SIM_PV_VOLTAGE)
            )
            self._solar_config[CONF_SIM_OVERRIDE_CONSUMPTION] = user_input.get(
                CONF_SIM_OVERRIDE_CONSUMPTION, False
            )
            self._solar_config[CONF_SIM_CONSUMPTION] = float(
                user_input.get(CONF_SIM_CONSUMPTION, DEFAULT_SIM_CONSUMPTION)
            )
            self._solar_config[CONF_SIM_OVERRIDE_BATTERY_POWER] = user_input.get(
                CONF_SIM_OVERRIDE_BATTERY_POWER, False
            )
            self._solar_config[CONF_SIM_BATTERY_POWER] = float(
                user_input.get(CONF_SIM_BATTERY_POWER, DEFAULT_SIM_BATTERY_POWER)
            )
            self._solar_config[CONF_SIM_OVERRIDE_BATTERY_SOC] = user_input.get(
                CONF_SIM_OVERRIDE_BATTERY_SOC, False
            )
            self._solar_config[CONF_SIM_BATTERY_SOC] = float(
                user_input.get(CONF_SIM_BATTERY_SOC, DEFAULT_SIM_BATTERY_SOC)
            )
            self._persist_config()
            await self.hass.config_entries.async_reload(self._config_entry.entry_id)
            return await self.async_step_main_menu()

        sim_on = self._solar_config.get(CONF_SIM_ENABLED, False)
        return self.async_show_form(
            step_id=STEP_SIMULATION,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SIM_ENABLED, default=sim_on): selector(
                        {"boolean": {}}
                    ),
                    vol.Optional(
                        CONF_SIM_PV_POWER,
                        default=self._solar_config.get(CONF_SIM_PV_POWER, DEFAULT_SIM_PV_POWER),
                    ): selector(
                        {"number": {"min": 0, "max": 10000, "step": 10, "unit_of_measurement": "W"}}
                    ),
                    vol.Optional(
                        CONF_SIM_PV_VOLTAGE,
                        default=self._solar_config.get(CONF_SIM_PV_VOLTAGE, DEFAULT_SIM_PV_VOLTAGE),
                    ): selector(
                        {"number": {"min": 0, "max": 200, "step": 0.5, "unit_of_measurement": "V"}}
                    ),
                    vol.Required(
                        CONF_SIM_OVERRIDE_CONSUMPTION,
                        default=self._solar_config.get(CONF_SIM_OVERRIDE_CONSUMPTION, False),
                    ): selector({"boolean": {}}),
                    vol.Optional(
                        CONF_SIM_CONSUMPTION,
                        default=self._solar_config.get(
                            CONF_SIM_CONSUMPTION, DEFAULT_SIM_CONSUMPTION
                        ),
                    ): selector(
                        {"number": {"min": 0, "max": 10000, "step": 10,
                                    "unit_of_measurement": "W"}}
                    ),
                    vol.Required(
                        CONF_SIM_OVERRIDE_BATTERY_POWER,
                        default=self._solar_config.get(CONF_SIM_OVERRIDE_BATTERY_POWER, False),
                    ): selector({"boolean": {}}),
                    vol.Optional(
                        CONF_SIM_BATTERY_POWER,
                        default=self._solar_config.get(
                            CONF_SIM_BATTERY_POWER, DEFAULT_SIM_BATTERY_POWER
                        ),
                    ): selector(
                        {"number": {"min": -10000, "max": 10000, "step": 10,
                                    "unit_of_measurement": "W"}}
                    ),
                    vol.Required(
                        CONF_SIM_OVERRIDE_BATTERY_SOC,
                        default=self._solar_config.get(CONF_SIM_OVERRIDE_BATTERY_SOC, False),
                    ): selector({"boolean": {}}),
                    vol.Optional(
                        CONF_SIM_BATTERY_SOC,
                        default=self._solar_config.get(
                            CONF_SIM_BATTERY_SOC, DEFAULT_SIM_BATTERY_SOC
                        ),
                    ): selector(
                        {"number": {"min": 0, "max": 100, "step": 1, "unit_of_measurement": "%"}}
                    ),
                }
            ),
        )


    async def async_step_settings(self, user_input=None):
        """Hub-level reconfigure: mppt_count + shared sensors + toggles."""
        errors = {}

        if user_input is not None:
            try:
                count = int(user_input.get(CONF_MPPT_COUNT, 0))
            except (ValueError, TypeError):
                count = 0
            if not 1 <= count <= MPPT_MAX_COUNT:
                errors[CONF_MPPT_COUNT] = "invalid_mppt_count"

            if not errors:
                user_input = self._process_hub_config_input(user_input)
                # Stash existing trackers for prefill on the per-MPPT step.
                self._existing_mppt_inputs = list(
                    self._solar_config.get(CONF_MPPT_INPUTS, [])
                )
                self._solar_config.update(user_input)
                self._solar_config[CONF_MPPT_COUNT] = count
                self._solar_config[CONF_MPPT_INPUTS] = []  # accumulator reset
                self._solar_config[CONF_TEMPERATURE_COMPENSATION_ENABLED] = (
                    user_input.get(CONF_TEMPERATURE_COMPENSATION_ENABLED, False)
                )
                self._solar_config[CONF_ADVANCED_SETTINGS_ENABLED] = user_input.get(
                    CONF_ADVANCED_SETTINGS_ENABLED, False
                )
                return await self.async_step_mppt_input()

        defaults = dict(self._solar_config)
        defaults.setdefault(
            CONF_MPPT_COUNT,
            len(self._solar_config.get(CONF_MPPT_INPUTS, [])) or 1,
        )
        schema = self._get_solar_hub_schema(defaults)

        extended_schema = schema.extend(
            {
                vol.Required(
                    CONF_TEMPERATURE_COMPENSATION_ENABLED,
                    default=self._solar_config.get(
                        CONF_TEMPERATURE_COMPENSATION_ENABLED, False
                    ),
                ): selector({"boolean": {}}),
                vol.Required(
                    CONF_ADVANCED_SETTINGS_ENABLED,
                    default=self._solar_config.get(
                        CONF_ADVANCED_SETTINGS_ENABLED, False
                    ),
                ): selector({"boolean": {}}),
            }
        )

        return self.async_show_form(
            step_id=STEP_SETTINGS,
            data_schema=extended_schema,
            errors=errors,
        )


    async def async_step_mppt_input(self, user_input=None):
        """Per-MPPT panel config for reconfigure flow."""
        errors = {}
        existing_collected = self._solar_config.get(CONF_MPPT_INPUTS, [])
        idx = len(existing_collected)
        total = self._solar_config.get(CONF_MPPT_COUNT, 1)
        prior = getattr(self, "_existing_mppt_inputs", [])

        if user_input is not None:
            errors = self._validate_panel_only(user_input)
            existing_powers = [m.get(CONF_PV_POWER) for m in existing_collected]
            existing_voltages = [m.get(CONF_PV_VOLTAGE) for m in existing_collected]
            if user_input.get(CONF_PV_POWER) in existing_powers:
                errors[CONF_PV_POWER] = "duplicate_mppt_sensor"
            if user_input.get(CONF_PV_VOLTAGE) in existing_voltages:
                errors[CONF_PV_VOLTAGE] = "duplicate_mppt_sensor"

            if not errors:
                self._solar_config[CONF_MPPT_INPUTS] = existing_collected + [
                    dict(user_input)
                ]
                if len(self._solar_config[CONF_MPPT_INPUTS]) >= total:
                    if self._solar_config.get(
                        CONF_TEMPERATURE_COMPENSATION_ENABLED, False
                    ):
                        return await self.async_step_temperature_compensation()
                    if self._solar_config.get(CONF_ADVANCED_SETTINGS_ENABLED, False):
                        return await self.async_step_advanced_settings()
                    return await self._save_and_return()
                return await self.async_step_mppt_input()

        defaults = prior[idx] if idx < len(prior) else None
        schema = self._get_mppt_input_schema(defaults)

        return self.async_show_form(
            step_id=STEP_MPPT_INPUT,
            data_schema=schema,
            description_placeholders={
                "index": str(idx + 1),
                "total": str(total),
            },
            errors=errors,
        )


    async def async_step_manage_devices(self, user_input=None):
        """Handle device management step."""
        errors = {}

        if user_input is not None:
            action = user_input.get(CONF_ACTION, "")
            selected_device_id = user_input.get(CONF_DEVICE_ID)

            if action == ACTION_ADD:
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

        action_options = [ACTION_ADD, ACTION_EDIT, ACTION_REMOVE, ACTION_BACK]

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
                log_debug("--- CONFIG FLOW REMOVE ---: Saving %d devices.", len(self._devices))
                self._persist_config()
                return await self.async_step_manage_devices()

            return await self.async_step_manage_devices()

        return self.async_show_form(
            step_id=STEP_CONFIRM_REMOVE,
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
            description_placeholders={
                "device_name": self._get_device_name(self._device_to_remove)
            },
        )


    def _persist_config(self) -> None:
        """Persist current solar config and device list to the config entry."""
        data = dict(self._config_entry.data)
        data.update(self._solar_config)
        data[CONF_DEVICES] = self._devices
        data["devices_str"] = json.dumps(self._devices, default=_json_default)
        data.pop("test_array", None)
        self.hass.config_entries.async_update_entry(self._config_entry, data=data)

    def _get_device_name(self, device_id):
        """Get device name by its ID."""
        for device in self._devices:
            if device[CONF_DEVICE_ID] == device_id:
                return device.get(CONF_DEVICE_NAME, "Unnamed device")
        return "Unknown device"


    async def _save_and_return(self):
        """Save configuration, reload integration and return to main menu."""
        log_debug("--- CONFIG FLOW SAVE ---: Saving %d devices.", len(self._devices))
        self._persist_config()
        await self.hass.config_entries.async_reload(self._config_entry.entry_id)
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

        log_debug("--- CONFIG FLOW FINALIZE ---: Saving %d devices.", len(self._devices))
        self._persist_config()
        await self.hass.config_entries.async_reload(self._config_entry.entry_id)
        return await self.async_step_manage_devices()


@callback
def async_get_options_flow(config_entry):
    """Get the options flow."""
    return SunAllocatorOptionsFlowHandler(config_entry)


# Export classes for Home Assistant
__all__ = ["SunAllocatorConfigFlow", "async_get_options_flow"]
