"""Battery-SOC gating for Sun Allocator.

Pure/side-effect-light decision helpers that decide whether a device may START
(charge-side ``_apply_battery_soc_gate``) or must be SHED while running
(discharge-side ``_apply_battery_stop_floor`` / the pure ``decide_battery_soc_stop``).
Extracted from ``power_processor`` to shrink the hot-path module; re-exported there so
existing call sites and tests (which reference them via ``power_processor``) are
unchanged.
"""

from __future__ import annotations

from .logger import log_debug

from ..const import (
    CONF_DEVICE_NAME,
    CONF_DEVICE_START_BATTERY_SOC,
    CONF_DEVICE_STOP_BATTERY_SOC,
    DEFAULT_DEVICE_STOP_BATTERY_SOC,
    DEFAULT_BATTERY_SOC_HYSTERESIS,
)


def _apply_battery_soc_gate(
    device, device_id, is_active, prev_on, battery_soc, soc_configured, gate_state, status_entry
) -> bool:
    """Block new device starts when battery SOC is below the per-device START threshold.

    Only NEW starts are gated; running devices (prev_on=True) are never turned off here
    (the discharge-side ``_apply_battery_stop_floor`` handles shedding running loads).

    Hysteresis (sticky-state band ``[start, start + DEFAULT_BATTERY_SOC_HYSTERESIS]``):
      - allow a start at SOC >= ``start`` while the device has not been blocked;
      - once SOC drops below ``start`` the device is marked blocked and must climb back
        to ``start + hysteresis`` (the recovery threshold) before it may start again.
      ``gate_state`` (a per-entry dict keyed by device_id) carries the blocked flag
      between cycles, since ``status_entry`` is rebuilt each run.

    Fail behaviour when the device has a ``start_battery_soc`` requirement:
      - no hub SOC sensor configured at all → fail-open (requirement is meaningless
        without a sensor; don't permanently block a device over a forgotten config).
      - sensor configured but currently unavailable → fail-safe (block; we cannot
        verify charge, so don't risk draining the battery).
    """
    if prev_on:
        # Running device: never start-gated, and clear any sticky block.
        gate_state.pop(device_id, None)
        return is_active
    if not is_active:
        return is_active  # not a start candidate this cycle — leave block state as-is

    start_soc = float(device.get(CONF_DEVICE_START_BATTERY_SOC, 0) or 0)
    if start_soc <= 0:
        gate_state.pop(device_id, None)
        return is_active  # device opted out of START SOC gating

    if not soc_configured:
        return is_active  # fail-open: per-device start with no hub sensor

    if battery_soc is None:
        # Sensor configured but unavailable → fail-safe block, and stay sticky so a
        # full recovery is required once the sensor returns.
        gate_state[device_id] = True
        status_entry["refusal_reasons"].append(
            "Battery SOC sensor unavailable — start blocked (fail-safe)"
        )
        log_debug(
            f"[soc_gate] Blocking start for {device.get(CONF_DEVICE_NAME)}: "
            "SOC sensor unavailable (fail-safe)"
        )
        return False

    recovery = min(100.0, start_soc + DEFAULT_BATTERY_SOC_HYSTERESIS)
    was_blocked = bool(gate_state.get(device_id))

    if was_blocked and battery_soc < recovery:
        status_entry["refusal_reasons"].append(
            f"Battery SOC {battery_soc:.1f}% < recovery threshold {recovery:.1f}%"
            f" (was blocked below start {start_soc:.1f}%)"
        )
        log_debug(
            f"[soc_gate] Holding block for {device.get(CONF_DEVICE_NAME)}: "
            f"SOC={battery_soc:.1f}% < recovery {recovery:.1f}%"
        )
        return False

    if battery_soc < start_soc:
        gate_state[device_id] = True
        status_entry["refusal_reasons"].append(
            f"Battery SOC {battery_soc:.1f}% < start minimum {start_soc:.1f}%"
        )
        log_debug(
            f"[soc_gate] Blocking start for {device.get(CONF_DEVICE_NAME)}: "
            f"SOC={battery_soc:.1f}% < start {start_soc:.1f}%"
        )
        return False

    # SOC at or above the applicable threshold → clear sticky block and allow.
    gate_state.pop(device_id, None)
    return is_active


def decide_battery_soc_stop(
    *, battery_soc, soc_configured, discharging, stop_soc, protection_soc,
    was_blocked=False, hysteresis=DEFAULT_BATTERY_SOC_HYSTERESIS,
) -> bool:
    """Pure: should a running/starting device be forced OFF for battery protection?

    Two axes:
      * ``protection_soc`` (global hard floor) — absolute: fires in ANY charge direction.
      * ``stop_soc`` (per-device) — fires only while the battery is DISCHARGING, so a
        device stays on while solar still covers it (net ≈ 0). ``stop_soc == 0`` means
        "inherit the global protection floor" (no extra per-device rule); ``100`` means
        "never discharge the battery for this device".
    ``was_blocked`` raises the release threshold by ``hysteresis`` so the gate does not flap
    at the boundary. Fail-open on unknown SOC: never sheds a running load on a missing
    reading (the start gate is the fail-safe path).
    """
    if not soc_configured or battery_soc is None:
        return False
    band = hysteresis if was_blocked else 0.0
    protection = float(protection_soc or 0)
    if protection > 0 and battery_soc < protection + band:
        return True
    # 0 → inherit the global protection floor (already handled by the absolute axis above).
    eff_stop = float(stop_soc) if (stop_soc and float(stop_soc) > 0) else protection
    if discharging and eff_stop > 0 and battery_soc < eff_stop + band:
        return True
    return False


def _effective_stop_soc(device, protection_soc) -> float:
    """Binding discharge floor for messages: max(protection, per-device stop). 0 → global."""
    stop_soc = device.get(CONF_DEVICE_STOP_BATTERY_SOC, DEFAULT_DEVICE_STOP_BATTERY_SOC)
    stop = float(stop_soc) if (stop_soc and float(stop_soc) > 0) else 0.0
    return max(float(protection_soc or 0), stop)


def _apply_battery_stop_floor(
    device, device_id, is_active, battery_soc, soc_configured, discharging,
    protection_soc, gate_state, status_entry,
) -> bool:
    """Force a running/starting device OFF on the discharge side (battery protection).

    Unlike the start gate, this DOES turn off a running device. ``gate_state`` carries a
    sticky block between cycles for hysteresis so it will not flap at the floor.
    """
    if not is_active:
        return is_active

    was_blocked = bool(gate_state.get(device_id))
    stop = decide_battery_soc_stop(
        battery_soc=battery_soc,
        soc_configured=soc_configured,
        discharging=discharging,
        stop_soc=device.get(CONF_DEVICE_STOP_BATTERY_SOC, DEFAULT_DEVICE_STOP_BATTERY_SOC),
        protection_soc=protection_soc,
        was_blocked=was_blocked,
    )
    if stop:
        gate_state[device_id] = True
        eff = _effective_stop_soc(device, protection_soc)
        status_entry["refusal_reasons"].append(
            f"Battery protection (SOC {battery_soc:.0f}% < {eff:.0f}%)"
        )
        log_debug(
            f"[stop_floor] Forcing OFF {device.get(CONF_DEVICE_NAME)}: "
            f"SOC={battery_soc:.1f}% floor={eff:.1f}% discharging={discharging}"
        )
        return False

    gate_state.pop(device_id, None)
    return is_active
