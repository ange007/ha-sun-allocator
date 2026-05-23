"""The Sun Allocator integration."""

import asyncio
from datetime import timedelta
import datetime as dt_stdlib

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    config_validation as cv,
    entity_registry as er,
)
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
    async_track_time_interval,
)
import homeassistant.util.dt as dt_util
from homeassistant.const import (
    ATTR_ENTITY_ID,
    STATE_UNKNOWN,
    STATE_UNAVAILABLE,
)

from .core.entity_control import set_mode_for_entity, parse_relay_entity
from .core.logger import log_info, log_debug, log_warning, log_error
from .core.settings import LOG_STARTUP_DEVICES
from .core.device_restore import (
    persist_device_state,
    restore_entity_state,
    restore_all_devices,
    load_grace_state,
    _load_restore_data,
)
from .core.services import handle_set_relay_mode, handle_set_relay_power, rebuild_device_index
from .core.migrations import ConfigEntryMigrator
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
    CONF_DEVICE_DEBOUNCE_TIME,
    CONF_DEVICE_ACTUAL_POWER_SENSOR,
    CONF_DEVICE_ACTIVE_FEEDBACK_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_POWER_ALLOCATION,
    NONE_OPTION,
    STATE_ON,
    DOMAIN_LIGHT,
    DOMAIN_SWITCH,
    DOMAIN_INPUT_BOOLEAN,
    DOMAIN_AUTOMATION,
    DOMAIN_SCRIPT,
    DOMAIN_CLIMATE,
    MAX_BRIGHTNESS,
    MAX_PERCENTAGE,
    DEFAULT_DEBOUNCE_TIME,
)

def _call_unsubscribers(entry_data: dict, keys: list[str]) -> None:
    """Invoke and clear any unsubscribe callbacks stored under the given keys."""
    for key in keys:
        unsub = entry_data.get(key)
        if not unsub:
            continue
        try:
            unsub()
        except Exception as exc:  # noqa: BLE001 — defensive; HA unsub never raises in practice
            log_error("Unsubscribe %s failed: %s", key, exc)
        entry_data[key] = None


SET_RELAY_MODE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_DEVICE_ID): cv.string,
        vol.Required("mode"): vol.In(
            [RELAY_MODE_OFF, RELAY_MODE_ON, RELAY_MODE_PROPORTIONAL]
        ),
    }
)

SET_RELAY_POWER_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_DEVICE_ID): cv.string,
        vol.Required("power"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    }
)


def _mark_watchdog_fresh(entry_data):
    """Refresh watchdog freshness from a confirmed excess-sensor update."""
    entry_data["watchdog_last_seen"] = dt_util.utcnow()
    entry_data["watchdog_alerted"] = False


def _choose_earliest_recompute_start(entry_data, first_device_id, second_device_id):
    """Return the earliest device in priority order for partial recompute."""
    if first_device_id is None or second_device_id is None:
        return None

    device_order = entry_data.get("auto_control_device_order", [])
    try:
        first_index = device_order.index(first_device_id)
        second_index = device_order.index(second_device_id)
    except ValueError:
        return None

    return first_device_id if first_index <= second_index else second_device_id


def _merge_process_request(entry_data, queued_request, incoming_request):
    """Merge overlapping allocator requests into the smallest safe rerun."""
    if queued_request is None:
        return incoming_request

    if (
        queued_request.get("start_from_device_id") is None
        or incoming_request.get("start_from_device_id") is None
    ):
        start_from_device_id = None
    else:
        start_from_device_id = _choose_earliest_recompute_start(
            entry_data,
            queued_request.get("start_from_device_id"),
            incoming_request.get("start_from_device_id"),
        )

    return {
        "excess_power": incoming_request["excess_power"],
        "start_from_device_id": start_from_device_id,
    }


def _get_next_debounce_deadline(config_entry, entry_data):
    """Return the earliest pending debounce completion time, if any."""
    devices_by_id = {
        device.get(CONF_DEVICE_ID): device
        for device in config_entry.data.get(CONF_DEVICES, [])
        if device.get(CONF_AUTO_CONTROL_ENABLED, False) and device.get(CONF_DEVICE_ID)
    }

    earliest_deadline = None
    for device_id, debounce_info in entry_data.get("device_debounce_state", {}).items():
        state_change_time = debounce_info.get("state_change_time")
        if not state_change_time:
            continue

        if isinstance(state_change_time, str):
            try:
                state_change_time = dt_stdlib.datetime.fromisoformat(state_change_time)
            except ValueError:
                continue

        device = devices_by_id.get(device_id)
        if device is None:
            continue

        debounce_time_s = float(
            device.get(CONF_DEVICE_DEBOUNCE_TIME, DEFAULT_DEBOUNCE_TIME) or 0
        )
        if debounce_time_s <= 0:
            continue

        deadline = state_change_time + timedelta(seconds=debounce_time_s)
        if earliest_deadline is None or deadline < earliest_deadline:
            earliest_deadline = deadline

    return earliest_deadline


def _schedule_debounce_recheck(
    hass,
    config_entry,
    entry_data,
    *,
    processor=process_excess_power,
):
    """Re-run the allocator when the next debounce timer expires."""
    _call_unsubscribers(entry_data, ["unsub_debounce_recheck"])

    deadline = _get_next_debounce_deadline(config_entry, entry_data)
    entry_data["debounce_recheck_deadline"] = deadline
    if deadline is None:
        return

    deadline_utc = dt_util.as_utc(deadline)

    async def _debounce_recheck_callback(_now):
        entry_data["unsub_debounce_recheck"] = None
        entry_data["debounce_recheck_deadline"] = None

        excess_sensor_id = entry_data.get("tracked_excess_sensor_id")
        if not excess_sensor_id:
            return

        excess_state = hass.states.get(excess_sensor_id)
        if not excess_state or excess_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return

        try:
            await _queue_process_excess_power(
                hass,
                config_entry,
                entry_data,
                float(excess_state.state),
                processor=processor,
            )
        except (ValueError, TypeError) as exc:
            log_error("Error processing debounce recheck value: %s", exc)
        except Exception as exc:
            log_error("Unexpected error in debounce recheck: %s", exc)

    if deadline_utc <= dt_util.utcnow():
        # Defer overdue rechecks by one loop tick so eager tasks do not recurse
        # back into the allocator while the current run is still unwinding.
        hass.loop.call_soon(hass.async_create_task, _debounce_recheck_callback(deadline_utc))
        return

    entry_data["unsub_debounce_recheck"] = async_track_point_in_utc_time(
        hass,
        _debounce_recheck_callback,
        deadline_utc,
    )


async def _queue_process_excess_power(
    hass,
    config_entry,
    entry_data,
    excess_power,
    *,
    start_from_device_id=None,
    processor=process_excess_power,
):
    """Serialize allocator runs and coalesce overlapping triggers."""
    process_lock = entry_data.setdefault("process_excess_power_lock", asyncio.Lock())
    request = {
        "excess_power": excess_power,
        "start_from_device_id": start_from_device_id,
    }

    if process_lock.locked():
        entry_data["pending_process_request"] = _merge_process_request(
            entry_data,
            entry_data.get("pending_process_request"),
            request,
        )
        return

    next_request = request
    while True:
        async with process_lock:
            await processor(
                hass,
                config_entry,
                next_request["excess_power"],
                start_from_device_id=next_request.get("start_from_device_id"),
            )

        _schedule_debounce_recheck(
            hass,
            config_entry,
            entry_data,
            processor=processor,
        )

        queued_request = entry_data.pop("pending_process_request", None)
        if queued_request is None:
            return
        next_request = queued_request


async def _handle_auto_control_state_change(
    hass,
    config_entry,
    entry_data,
    excess_sensor_id,
    changed_entity_id,
    new_state,
    *,
    processor=process_excess_power,
):
    """Handle tracked auto-control updates with correct watchdog semantics."""
    if changed_entity_id == excess_sensor_id:
        excess_state = new_state
    else:
        excess_state = hass.states.get(excess_sensor_id)

    if not excess_state or excess_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return

    if changed_entity_id == excess_sensor_id:
        _mark_watchdog_fresh(entry_data)

    start_from_device_id = None
    if changed_entity_id != excess_sensor_id:
        battery_soc_sensor = entry_data.get("tracked_battery_soc_sensor")
        if changed_entity_id != battery_soc_sensor:
            start_from_device_id = entry_data.get("tracked_device_sensor_map", {}).get(
                changed_entity_id
            )

    try:
        excess_power = float(excess_state.state)
        await _queue_process_excess_power(
            hass,
            config_entry,
            entry_data,
            excess_power,
            start_from_device_id=start_from_device_id,
            processor=processor,
        )
    except (ValueError, TypeError) as exc:
        log_error(f"Error processing excess power value: {exc}")
    except Exception as exc:
        log_error(f"Unexpected error in process_excess_power: {exc}")


async def _setup_entity_state_listeners(hass, config_entry, entry_data):
    """Setup listeners for entity state changes to persist and restore state."""

    async def _entity_state_listener(event):
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if not new_state:
            return
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

        was_unavailable = (old_state is None) or (
            old_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE)
        )
        now_available = new_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
        now_unavailable = new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE)

        if now_unavailable:
            # Reset device_on_state and clear any manual override so that when the
            # entity recovers it starts fresh without triggering a false override.
            for dev in config_entry.data.get(CONF_DEVICES, []):
                dev_entity_id, _ = parse_relay_entity(dev.get(CONF_DEVICE_ENTITY))
                if dev_entity_id and dev_entity_id == entity_id:
                    dev_id = dev.get(CONF_DEVICE_ID)
                    if dev_id:
                        entry_data.get("device_on_state", {}).pop(dev_id, None)
                        entry_data.get("manual_overrides", {}).pop(dev_id, None)

        if was_unavailable and now_available:
            await restore_entity_state(hass, config_entry, entity_id)

    relay_entities = set()
    mode_entities = set()
    for dev in config_entry.data.get(CONF_DEVICES, []):
        relay_entity, _ = parse_relay_entity(dev.get(CONF_DEVICE_ENTITY))
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


async def _setup_esphome_mode_tracking(hass, config_entry, entry_data):
    """Setup tracking and resyncing of ESPHome modes."""
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

    # Fallback: load persisted last_mode from Storage
    restore_data = await _load_restore_data(hass, config_entry)
    for dev in devices:
        entity = dev.get(CONF_ESPHOME_MODE_SELECT_ENTITY)
        if entity and entity not in desired_modes:
            persisted = restore_data.get(entity, {}).get("last_mode")
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


async def _initial_pass_with_retry(hass, config_entry, entry_data, excess_sensor_id):
    """Perform an initial pass to set the state of the devices."""
    for i in range(3):
        initial_state = hass.states.get(excess_sensor_id)
        log_debug(
            "--- INITIAL PASS (attempt %d) ---: id=%s, state=%s",
            i + 1,
            excess_sensor_id,
            initial_state,
        )
        if initial_state and initial_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                excess_power = float(initial_state.state)
                _mark_watchdog_fresh(entry_data)
                await _queue_process_excess_power(
                    hass,
                    config_entry,
                    entry_data,
                    excess_power,
                )
                log_info(
                    "Initial pass successful for %s: %sW",
                    initial_state.entity_id,
                    excess_power,
                )
                return
            except (ValueError, TypeError):
                log_debug(
                    "Excess sensor state not numeric yet for initial pass: %s",
                    initial_state.state,
                )
            except Exception as exc:
                log_error("Unexpected error during initial pass: %s", exc)
        await asyncio.sleep(0.1 * (i + 1))
    log_warning("Failed to perform initial pass after multiple retries.")


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigType):
    """Set up SunAllocator from a config entry."""
    log_info(
        "--- COMPONENT SETUP ---: Loading entry. Data: %s",
        config_entry.data,
    )
    # Apply data migrations from older integration versions before anything reads
    # config_entry.data. Each migration is documented in core/migrations.py.
    await ConfigEntryMigrator(hass, config_entry).run()

    hass.data.setdefault(DOMAIN, {})
    entry_data = {
        "config": config_entry.data,
        "unsub_update_listener": None,
        "unsub_auto_control": None,
    }
    hass.data[DOMAIN][config_entry.entry_id] = entry_data
    rebuild_device_index(hass)

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

    async def _on_ha_started(_):
        await restore_all_devices(hass, config_entry)
        _entry_data = hass.data[DOMAIN][config_entry.entry_id]
        if not _entry_data.get("unsub_auto_control"):
            log_info("Retrying auto-control setup after HA started (sensor was not ready at initial setup)")
            await setup_auto_control(hass, config_entry)

    unsub_ha_start = hass.bus.async_listen_once("homeassistant_started", _on_ha_started)
    entry_data["unsub_ha_start"] = unsub_ha_start

    await _setup_entity_state_listeners(hass, config_entry, entry_data)
    await hass.config_entries.async_forward_entry_setups(config_entry, ["sensor", "switch"])

    root = hass.data[DOMAIN]
    root.setdefault("_entry_count", 0)
    root.setdefault("_services_registered", False)
    if not root["_services_registered"]:

        async def _handle_set_relay_mode(call):
            await handle_set_relay_mode(hass, call)

        async def _handle_set_relay_power(call):
            await handle_set_relay_power(hass, call)

        hass.services.async_register(
            DOMAIN, SERVICE_SET_RELAY_MODE, _handle_set_relay_mode,
            schema=SET_RELAY_MODE_SCHEMA,
        )
        hass.services.async_register(
            DOMAIN, SERVICE_SET_RELAY_POWER, _handle_set_relay_power,
            schema=SET_RELAY_POWER_SCHEMA,
        )
        root["_services_registered"] = True

    root["_entry_count"] = int(root.get("_entry_count", 0)) + 1

    await _setup_esphome_mode_tracking(hass, config_entry, entry_data)
    await setup_auto_control(hass, config_entry)

    entry_data["unsub_update_listener"] = config_entry.add_update_listener(
        update_listener
    )

    return True


async def setup_auto_control(hass: HomeAssistant, config_entry: ConfigType):
    """Set up automatic control of the relay based on excess power."""
    log_info("--- SETUP AUTO CONTROL ---")
    entry_data = hass.data[DOMAIN][config_entry.entry_id]

    _call_unsubscribers(entry_data, ["unsub_auto_control", "unsub_watchdog_timer"])

    devices = config_entry.data.get(CONF_DEVICES, [])
    auto_control_devices = [
        dev for dev in devices if dev.get(CONF_AUTO_CONTROL_ENABLED, False)
    ]
    if not auto_control_devices:
        log_debug("No devices with auto-control enabled")
        return

    auto_control_devices.sort(
        key=lambda dev: int(dev.get(CONF_DEVICE_PRIORITY, 50)), reverse=True
    )
    log_debug(f"Setting up auto-control for {len(auto_control_devices)} devices")
    entry_data["auto_control_device_order"] = [
        device.get(CONF_DEVICE_ID)
        for device in auto_control_devices
        if device.get(CONF_DEVICE_ID)
    ]

    power_allocation = {}
    for device in auto_control_devices:
        device_id = device.get(CONF_DEVICE_ID)
        if device_id:
            power_allocation[device_id] = 0
    entry_data[CONF_POWER_ALLOCATION] = power_allocation

    # Seed device_on_time_state with persisted startup-grace deadlines so a HA
    # restart inside the grace window doesn't accidentally turn devices off.
    grace_state = await load_grace_state(hass, config_entry)
    now_utc = dt_util.utcnow()
    if grace_state:
        device_on_time_state = entry_data.setdefault("device_on_time_state", {})
        for device_id, deadline in grace_state.items():
            # dt_util.utcnow() is offset-aware; deadline is also offset-aware (saved
            # via dt_util.now() through power_processor's `now` argument). If a
            # legacy naive datetime sneaks in, treat it as expired and skip.
            if deadline.tzinfo is None or deadline <= now_utc:
                continue
            device_on_time_state.setdefault(device_id, {})["startup_until"] = deadline
            log_info(
                "[grace] Restored startup grace for %s until %s (%.0fs remaining)",
                device_id, deadline, (deadline - now_utc).total_seconds(),
            )

    watchdog_period = timedelta(seconds=60)
    entry_data["watchdog_last_seen"] = dt_util.utcnow()
    entry_data["watchdog_alerted"] = False

    async def _watchdog_timer_callback(now):
        await watchdog_check(hass, config_entry)

    entry_data["unsub_watchdog_timer"] = async_track_time_interval(
        hass, _watchdog_timer_callback, watchdog_period
    )

    entry_data["process_excess_power"] = process_excess_power

    async def handle_state_change(event):
        event_data = event.data if hasattr(event, "data") else {}
        changed_entity_id = event_data.get("entity_id")
        new_state = event_data.get("new_state")
        await _handle_auto_control_state_change(
            hass,
            config_entry,
            entry_data,
            excess_sensor_id,
            changed_entity_id,
            new_state,
        )

    registry = er.async_get(hass)
    excess_sensor_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{config_entry.entry_id}_excess"
    )

    if not excess_sensor_id:
        log_warning(
            "Excess sensor not found in entity registry (looked for unique_id=%s_excess). "
            "Will retry after homeassistant_started event.",
            config_entry.entry_id,
        )
        return
    entry_data["tracked_excess_sensor_id"] = excess_sensor_id

    actual_power_sensors = {
        sensor_entity
        for sensor_entity in (
            dev.get(CONF_DEVICE_ACTUAL_POWER_SENSOR) for dev in auto_control_devices
        )
        if sensor_entity and sensor_entity != NONE_OPTION
    }
    relay_entities = set()
    for device in auto_control_devices:
        relay_entity = device.get(CONF_DEVICE_ENTITY)
        if not relay_entity or relay_entity == NONE_OPTION:
            continue
        relay_entities.add(relay_entity.split("|")[0])

    active_feedback_sensors = {
        sensor_entity
        for sensor_entity in (
            dev.get(CONF_DEVICE_ACTIVE_FEEDBACK_SENSOR) for dev in auto_control_devices
        )
        if sensor_entity and sensor_entity != NONE_OPTION
    }
    tracked_device_sensor_map = {}
    for device in auto_control_devices:
        device_id = device.get(CONF_DEVICE_ID)
        if not device_id:
            continue
        relay_entity = device.get(CONF_DEVICE_ENTITY)
        if relay_entity and relay_entity != NONE_OPTION:
            tracked_device_sensor_map[relay_entity.split("|")[0]] = device_id
        actual_power_sensor = device.get(CONF_DEVICE_ACTUAL_POWER_SENSOR)
        if actual_power_sensor and actual_power_sensor != NONE_OPTION:
            tracked_device_sensor_map[actual_power_sensor] = device_id
        active_feedback_sensor = device.get(CONF_DEVICE_ACTIVE_FEEDBACK_SENSOR)
        if active_feedback_sensor and active_feedback_sensor != NONE_OPTION:
            tracked_device_sensor_map[active_feedback_sensor] = device_id

    battery_soc_sensor = config_entry.data.get(CONF_BATTERY_SOC_SENSOR)
    tracked_entities = sorted(
        {
            excess_sensor_id,
            *relay_entities,
            *actual_power_sensors,
            *active_feedback_sensors,
            *([battery_soc_sensor] if battery_soc_sensor and battery_soc_sensor != NONE_OPTION else []),
        }
    )
    entry_data["tracked_auto_control_entities"] = tracked_entities
    entry_data["tracked_device_sensor_map"] = tracked_device_sensor_map
    entry_data["tracked_battery_soc_sensor"] = (
        battery_soc_sensor if battery_soc_sensor and battery_soc_sensor != NONE_OPTION else None
    )

    log_info(
        "Tracking auto-control sensors: excess=%s, relay=%s, actual_power=%s, active_feedback=%s, battery_soc=%s",
        excess_sensor_id,
        sorted(relay_entities),
        sorted(actual_power_sensors),
        sorted(active_feedback_sensors),
        battery_soc_sensor,
    )
    entry_data["unsub_auto_control"] = async_track_state_change_event(
        hass, tracked_entities, handle_state_change
    )

    entry_data["initial_pass_task"] = hass.async_create_task(
        _initial_pass_with_retry(hass, config_entry, entry_data, excess_sensor_id)
    )

    log_info(f"Auto-control set up for {len(auto_control_devices)} devices")


async def update_listener(hass: HomeAssistant, config_entry: ConfigType):
    """Handle options update."""
    entry_data = hass.data.get(DOMAIN, {}).get(config_entry.entry_id, {})
    # Keep cached config in sync with the latest entry data so the device index
    # rebuild and switch-sync paths see the new values without a reload.
    if isinstance(entry_data, dict):
        entry_data["config"] = config_entry.data
    rebuild_device_index(hass)
    if entry_data.pop("_skip_reload", False):
        log_debug("--- UPDATE LISTENER ---: skipping reload (switch sync)")
        return
    log_debug("--- UPDATE LISTENER ---: Entry updated. Data: %s", config_entry.data)
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigType):
    """Unload a config entry."""
    await hass.config_entries.async_forward_entry_unload(config_entry, "sensor")
    await hass.config_entries.async_forward_entry_unload(config_entry, "switch")

    entry_data = hass.data[DOMAIN][config_entry.entry_id]

    _call_unsubscribers(
        entry_data,
        [
            "unsub_update_listener",
            "unsub_auto_control",
            "unsub_mode_listener",
            "unsub_watchdog_timer",
            "unsub_debounce_recheck",
            "unsub_restore_listener",
            "unsub_ha_start",
        ],
    )
    if entry_data.get("initial_pass_task"):
        entry_data["initial_pass_task"].cancel()
        try:
            await entry_data["initial_pass_task"]
        except asyncio.CancelledError:
            pass

    root = hass.data.get(DOMAIN, {})
    root.pop(config_entry.entry_id, None)
    rebuild_device_index(hass)

    try:
        root["_entry_count"] = max(0, int(root.get("_entry_count", 1)) - 1)
    except (TypeError, ValueError):
        root["_entry_count"] = 0

    if root.get("_entry_count", 0) == 0 and root.get("_services_registered"):
        hass.services.async_remove(DOMAIN, SERVICE_SET_RELAY_MODE)
        hass.services.async_remove(DOMAIN, SERVICE_SET_RELAY_POWER)
        root["_services_registered"] = False

    return True
