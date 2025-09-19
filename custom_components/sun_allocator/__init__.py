"""The Sun Allocator integration."""
import asyncio
from datetime import timedelta

import voluptuous as vol

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
import homeassistant.util.dt as dt_util
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    STATE_UNKNOWN,
    STATE_UNAVAILABLE,
)
from homeassistant.exceptions import HomeAssistantError

from .core.entity_control import set_mode_for_entity, set_power_for_entity
from .core.logger import log_info, log_debug, log_warning, log_error
from .core.settings import LOG_STARTUP_DEVICES
from .core.device_restore import (
    persist_device_state,
    restore_entity_state,
    restore_all_devices,
)
from .core.services import handle_set_relay_mode, handle_set_relay_power
from .core.mode_select import mode_select_state_listener
from .core.power_processor import process_excess_power
from .core.watchdog import watchdog_check

from .const import (
    DOMAIN,
    SERVICE_SET_RELAY_MODE,
    SERVICE_SET_RELAY_POWER,
    RELAY_MODE_OFF,
    RELAY_MODE_ON,
    RELAY_MODE_PROPORTIONAL,
    CONF_ESPHOME_MODE_SELECT_ENTITY,
    CONF_DEVICE_ENTITY,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_PRIORITY,
    CONF_DEVICE_TYPE,
    DEVICE_TYPE_STANDARD,
    DEVICE_TYPE_CUSTOM,
    CONF_SCHEDULE_ENABLED,
    CONF_START_TIME,
    CONF_END_TIME,
    CONF_DAYS_OF_WEEK,
    DAYS_OF_WEEK,
    CONF_MIN_EXPECTED_W,
    CONF_MAX_EXPECTED_W,
    CONF_POWER_ALLOCATION,
    CONF_POWER_DISTRIBUTION,
    STATE_ON,
    DOMAIN_LIGHT,
    DOMAIN_SWITCH,
    DOMAIN_SELECT,
    DOMAIN_INPUT_BOOLEAN,
    DOMAIN_AUTOMATION,
    DOMAIN_SCRIPT,
    DOMAIN_CLIMATE,
    MAX_BRIGHTNESS,
    MAX_PERCENTAGE,
    DEFAULT_MIN_START_W,
    DEFAULT_HYSTERESIS_W,
    SENSOR_ID_PREFIX,
    SENSOR_EXCESS_SUFFIX,
    SIGNAL_POWER_DISTRIBUTION_UPDATED,
    CONF_RAMP_UP_STEP,
    CONF_RAMP_DOWN_STEP,
    CONF_RAMP_DEADBAND,
    CONF_DEFAULT_MIN_START_W,
    CONF_HYSTERESIS_W,
    CONF_DEBOUNCE_TIME,
    DEFAULT_DEBOUNCE_TIME,
)

# Service schema for set_relay_mode
SET_RELAY_MODE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_DEVICE_ID): cv.string,
        vol.Required("mode"): vol.In(
            [RELAY_MODE_OFF, RELAY_MODE_ON, RELAY_MODE_PROPORTIONAL]
        ),
    }
)

# Service schema for set_relay_power
SET_RELAY_POWER_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_DEVICE_ID): cv.string,
        vol.Required("power"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    }
)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigType):
    """Set up SunAllocator from a config entry."""
    log_warning(
        "--- COMPONENT SETUP ---: Loading entry. Data: %s",
        config_entry.data,
    )
    # Store config entry data EARLY so it's available for all listeners
    hass.data.setdefault(DOMAIN, {})
    entry_data = {
        "config": config_entry.data,
        "unsub_update_listener": None,
        "unsub_auto_control": None,
    }
    hass.data[DOMAIN][config_entry.entry_id] = entry_data

    # --- Log all loaded devices for diagnostics ---
    devices = config_entry.data.get(CONF_DEVICES, [])
    if LOG_STARTUP_DEVICES:
        if devices:
            log_info("[Startup] Loaded %d devices from config:", len(devices))
            for dev in devices:
                log_info(
                    "[Startup] Device: id=%s, name=%s, type=%s, entity=%s",
                    dev.get(CONF_DEVICE_ID),
                    dev.get(CONF_DEVICE_NAME),
                    dev.get(CONF_DEVICE_TYPE),
                    dev.get(CONF_DEVICE_ENTITY),
                )
        else:
            log_info("[Startup] No devices loaded from config.")

    # --- Restore device state after Home Assistant restart ---
    async def _on_ha_started(_):
        """Restore device state after Home Assistant restart."""
        await restore_all_devices(hass, config_entry)

    hass.bus.async_listen_once("homeassistant_started", _on_ha_started)

    # Listen for entity state changes to persist and restore state
    @callback
    async def _entity_state_listener(event):
        """Handle entity state changes to persist and restore state."""
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if not new_state:
            return
        # Persist percent and ON/OFF for relay entities
        try:
            percent = None
            is_on = None
            domain = entity_id.split(".")[0]
            if domain == DOMAIN_LIGHT:
                br = int(new_state.attributes.get("brightness", 0))
                percent = (br / MAX_BRIGHTNESS) * MAX_PERCENTAGE if br > 0 else 0
                is_on = new_state.state == STATE_ON
            elif domain in [
                DOMAIN_SWITCH,
                DOMAIN_INPUT_BOOLEAN,
                DOMAIN_AUTOMATION,
                DOMAIN_SCRIPT,
            ]:
                is_on = new_state.state == STATE_ON
                percent = 100 if is_on else 0
            elif domain == DOMAIN_CLIMATE:
                is_on = new_state.state != "off"
                percent = 100 if is_on else 0
            await persist_device_state(
                hass, config_entry, entity_id, percent=percent, is_on=is_on
            )
        except (TypeError, ValueError, OSError) as exc:
            log_debug(f"[Persist] Error persisting state for {entity_id}: {exc}")
        # Restore if entity just became available
        was_unavailable = (old_state is None) or (
            old_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE)
        )
        now_available = new_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
        if was_unavailable and now_available:
            await restore_entity_state(hass, config_entry, entity_id)

    # Subscribe to all relevant entity state changes
    relay_entities = set()
    mode_entities = set()
    for dev in config_entry.data.get(CONF_DEVICES, []):
        relay_entity = dev.get(CONF_DEVICE_ENTITY)
        if relay_entity and "|" in relay_entity:
            relay_entity = relay_entity.split("|")[0]
        mode_select_entity = dev.get(CONF_ESPHOME_MODE_SELECT_ENTITY)
        if relay_entity:
            relay_entities.add(relay_entity)
        if mode_select_entity:
            mode_entities.add(mode_select_entity)

    all_entities = list(relay_entities | mode_entities)
    if all_entities:
        entry_data["unsub_restore_listener"] = async_track_state_change_event(
            hass, all_entities, _entity_state_listener
        )

    # Set up sensors
    await hass.config_entries.async_forward_entry_setups(config_entry, ["sensor"])

    # Register the services once (global) and track entry count
    root = hass.data[DOMAIN]
    root.setdefault("_entry_count", 0)
    root.setdefault("_services_registered", False)
    if not root["_services_registered"]:
        async def _handle_set_relay_mode(call):
            await handle_set_relay_mode(hass, call)
        
        async def _handle_set_relay_power(call):
            await handle_set_relay_power(hass, call)
        
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_RELAY_MODE,
            _handle_set_relay_mode,
            schema=SET_RELAY_MODE_SCHEMA,
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_RELAY_POWER,
            _handle_set_relay_power,
            schema=SET_RELAY_POWER_SCHEMA,
        )
        root["_services_registered"] = True
    # Increment active entry count
    root["_entry_count"] = int(root.get("_entry_count", 0)) + 1

    # Track and resync desired modes for ESPHome select entities
    valid_modes = {RELAY_MODE_OFF, RELAY_MODE_ON, RELAY_MODE_PROPORTIONAL}
    desired_modes = {}
    select_entity_ids = []
    devices = config_entry.data.get(CONF_DEVICES, [])
    for dev in devices:
        entity = dev.get(CONF_ESPHOME_MODE_SELECT_ENTITY)
        if entity:
            select_entity_ids.append(entity)
            state = hass.states.get(entity)
            if state and state.state in valid_modes:
                desired_modes[entity] = state.state
    entry_data["desired_modes"] = desired_modes

    # Fallback: load persisted last_mode
    for dev in devices:
        entity = dev.get(CONF_ESPHOME_MODE_SELECT_ENTITY)
        if entity and entity not in desired_modes:
            persisted = dev.get("last_mode")
            if persisted in valid_modes:
                desired_modes[entity] = persisted

    if select_entity_ids:
        entry_data["unsub_mode_listener"] = async_track_state_change_event(
            hass,
            select_entity_ids,
            lambda event: mode_select_state_listener(
                hass, config_entry, event, desired_modes, select_entity_ids
            ),
        )
        # Initial re-assert of desired mode
        for _entity_id in select_entity_ids:
            _state = hass.states.get(_entity_id)
            _desired = desired_modes.get(_entity_id)
            if (
                _desired
                and _state
                and _state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
                and _state.state != _desired
            ):
                log_debug("Re-applying desired mode %s to %s", _desired, _entity_id)
                await set_mode_for_entity(hass, _entity_id, _desired)

    # Set up auto-control
    await setup_auto_control(hass, config_entry)

    # Listen for config entry updates
    entry_data["unsub_update_listener"] = config_entry.add_update_listener(
        update_listener
    )

    return True


async def setup_auto_control(hass: HomeAssistant, config_entry: ConfigType):
    """Set up automatic control of the relay based on excess power."""
    log_warning("--- SETUP AUTO CONTROL ---")
    entry_data = hass.data[DOMAIN][config_entry.entry_id]

    # Cancel any existing auto-control
    if entry_data.get("unsub_auto_control"):
        entry_data["unsub_auto_control"]()
        entry_data["unsub_auto_control"] = None

    # Cancel existing watchdog timer
    if entry_data.get("unsub_watchdog_timer"):
        entry_data["unsub_watchdog_timer"]()
        entry_data["unsub_watchdog_timer"] = None

    # Cancel existing ramp timer
    if entry_data.get("unsub_ramp_timer"):
        entry_data["unsub_ramp_timer"]()
        entry_data["unsub_ramp_timer"] = None

    # Get devices from config
    devices = config_entry.data.get(CONF_DEVICES, [])
    auto_control_devices = [
        dev for dev in devices if dev.get(CONF_AUTO_CONTROL_ENABLED, False)
    ]
    if not auto_control_devices:
        log_debug("No devices with auto-control enabled")
        return
    
    auto_control_devices.sort(key=lambda dev: dev.get(CONF_DEVICE_PRIORITY, 50), reverse=True)
    log_debug(f"Setting up auto-control for {len(auto_control_devices)} devices")
    
    power_allocation = {}
    for device in auto_control_devices:
        device_id = device.get(CONF_DEVICE_ID)
        if device_id:
            power_allocation[device_id] = 0
    entry_data[CONF_POWER_ALLOCATION] = power_allocation

    # Watchdog for stale excess sensor
    watchdog_period = timedelta(seconds=60)
    entry_data["watchdog_last_seen"] = dt_util.utcnow()
    entry_data["watchdog_alerted"] = False

    entry_data["unsub_watchdog_timer"] = async_track_time_interval(
        hass, lambda now: watchdog_check(hass, config_entry), watchdog_period
    )

    entry_data["process_excess_power"] = process_excess_power

    @callback
    async def handle_state_change(event):
        """Handle changes to the excess power sensor."""
        new_state = event.data.get("new_state") if hasattr(event, "data") else None
        if not new_state or new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return

        entry_data["watchdog_last_seen"] = dt_util.utcnow()
        entry_data["watchdog_alerted"] = False

        try:
            excess_power = float(new_state.state)
            await process_excess_power(hass, config_entry, excess_power)
        except (ValueError, TypeError) as exc:
            log_error(f"Error processing excess power value: {exc}")

    excess_sensor_id = (
        f"sensor.{SENSOR_ID_PREFIX}_{SENSOR_EXCESS_SUFFIX}_{config_entry.entry_id}"
    )
    legacy_excess_sensor_id = f"sensor.{SENSOR_ID_PREFIX}_{SENSOR_EXCESS_SUFFIX}_1"
    entry_data["unsub_auto_control"] = async_track_state_change_event(
        hass, [excess_sensor_id, legacy_excess_sensor_id], handle_state_change
    )

    async def initial_pass_with_retry():
        """Perform an initial pass to set the state of the devices."""
        for i in range(3):  # Try 3 times
            initial_state = hass.states.get(excess_sensor_id) or hass.states.get(
                legacy_excess_sensor_id
            )
            log_warning(
                "--- INITIAL PASS (attempt %d) ---: id=%s, state=%s",
                i + 1,
                excess_sensor_id,
                initial_state,
            )
            if initial_state and initial_state.state not in (
                STATE_UNKNOWN,
                STATE_UNAVAILABLE,
            ):
                try:
                    excess_power = float(initial_state.state)
                    entry_data["watchdog_last_seen"] = dt_util.utcnow()
                    entry_data["watchdog_alerted"] = False
                    await process_excess_power(hass, config_entry, excess_power)
                    log_info(
                        "Initial pass successful for %s: %sW",
                        initial_state.entity_id,
                        excess_power,
                    )
                    return  # Success
                except (ValueError, TypeError):
                    log_debug(
                        "Excess sensor state not numeric yet for initial pass: %s",
                        initial_state.state,
                    )

            await asyncio.sleep(5 * (i + 1))

        log_warning(
            "Failed to perform initial pass after multiple retries."
        )

    entry_data["initial_pass_task"] = hass.async_create_task(initial_pass_with_retry())

    log_info(f"Auto-control set up for {len(auto_control_devices)} devices")


async def update_listener(hass: HomeAssistant, config_entry: ConfigType):
    """Handle options update."""
    log_warning("--- UPDATE LISTENER ---: Entry updated. Data: %s", config_entry.data)
    await setup_auto_control(hass, config_entry)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigType):
    """Unload a config entry."""
    await hass.config_entries.async_forward_entry_unload(config_entry, "sensor")

    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    if entry_data.get("unsub_update_listener"):
        entry_data["unsub_update_listener"]()

    if entry_data.get("unsub_auto_control"):
        entry_data["unsub_auto_control"]()

    if entry_data.get("unsub_mode_listener"):
        entry_data["unsub_mode_listener"]()

    if entry_data.get("unsub_watchdog_timer"):
        entry_data["unsub_watchdog_timer"]()

    if entry_data.get("unsub_ramp_timer"):
        entry_data["unsub_ramp_timer"]()

    if entry_data.get("initial_pass_task"):
        entry_data["initial_pass_task"].cancel()
        try:
            await entry_data["initial_pass_task"]
        except asyncio.CancelledError:
            pass

    root = hass.data.get(DOMAIN, {})
    root.pop(config_entry.entry_id, None)

    try:
        root["_entry_count"] = max(0, int(root.get("_entry_count", 1)) - 1)
    except Exception:
        root["_entry_count"] = 0

    if root.get("_entry_count", 0) == 0 and root.get("_services_registered"):
        hass.services.async_remove(DOMAIN, SERVICE_SET_RELAY_MODE)
        hass.services.async_remove(DOMAIN, SERVICE_SET_RELAY_POWER)
        root["_services_registered"] = False

    return True