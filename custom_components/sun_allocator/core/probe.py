"""Active probing controller for ``calculation_method == mppt_probe``.

On a load-following hybrid inverter the MPPT untapped-headroom estimate
underreports when the battery is at its charge limit and the house load is low:
the inverter curtails the panels to match load, so ``pv_power`` no longer reflects
the true solar potential. No passive calculation can see that hidden headroom.
"At its charge limit" is detected from the charge POWER (battery not absorbing),
not SOC, because many inverters cap charging below 100%.

The probe discovers it **empirically**, as a scalar feedback controller. It grows
a ``headroom_w`` budget — extra watts added on top of the cautious excess — so the
*existing* priority allocator turns on / ramps waiting devices. Then it watches
the battery:

* battery stays out of discharge (and SOC holds) → the added load is covered by
  previously-curtailed PV (*free*) → grow ``headroom_w`` further;
* battery starts discharging (or SOC drops) → the load is **not** free → back the
  headroom off below that level and start a cooldown before retrying (so an
  on/off device such as an AC compressor is not cycled).

Crucially the probe does **not** itself pick devices, ramp percentages, or handle
priority — it only sizes the budget. All cascade / partial-fill / priority / min-
threshold behaviour falls out of the normal allocator consuming
``excess + headroom_w``. This keeps the probe a small, well-tested scalar loop and
reuses every existing allocation rule for free.

Why battery-based and not pv-based: ``pv_power`` is a noisy, regulated signal on
these inverters, but "is the battery discharging?" is the unambiguous physical
truth about whether the extra load is solar-powered (confirmed by live A/B
testing — pv rises with load while the battery stays full during curtailment).

``plan_headroom`` is a pure function (unit-tested); the async orchestrator wires
it to live RAW sensor reads on a periodic tick (raw, not the excess sensor's
attributes, which the write-deadband freezes while excess is pinned at 0).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from ..const import (
    CALC_METHOD_MPPT_PROBE,
    PROBE_STEP_W,
    PROBE_COOLDOWN_S,
    PROBE_COOLDOWN_MAX_S,
    PROBE_MAX_HEADROOM_W,
    PROBE_SOC_BACKOFF_DROP,
    PROBE_BACKOFF_STREAK,
    PROBE_START_GATE_FACTOR,
    BATTERY_CHARGE_IDLE_W,
    RELAY_MODE_PROPORTIONAL,
    CONF_DEVICE_MIN_EXPECTED_W,
)

# device_status ENUM key meaning "would run, but there isn't enough surplus".
_STATUS_INSUFFICIENT_POWER = "insufficient_power"


def is_probe_enabled(method: Optional[str]) -> bool:
    """True when the configured calculation method enables active probing."""
    return method == CALC_METHOD_MPPT_PROBE


def battery_net_charge_w(battery_power: float, battery_power_reversed: bool) -> float:
    """Battery net charge in W (positive = charging), sign-convention-independent."""
    return -battery_power if battery_power_reversed else battery_power


def has_growth_target(statuses: Iterable[str]) -> bool:
    """True when at least one device is waiting only for more surplus.

    Used to stop the headroom growing once nothing more could consume it. A
    proportional device still below its max reports ``active`` (not
    ``insufficient_power``); the orchestrator adds that case separately.
    """
    return any(s == _STATUS_INSUFFICIENT_POWER for s in statuses)


def effective_excess(excess: float, headroom_w: float) -> float:
    """Budget the allocator should use: cautious excess plus discovered headroom."""
    return float(excess) + max(0.0, float(headroom_w))


def growth_target_present(
    status_entries: Iterable[Dict[str, Any]],
    untapped_w: Optional[float] = None,
    factor: float = PROBE_START_GATE_FACTOR,
) -> bool:
    """True when some device could consume more power if the budget grew.

    Reads the raw ``device_status`` entries the allocator produced:
    * a device that is **not** enabled, has **no** refusals and is **not** a
      candidate is waiting only for more surplus (the ``insufficient_power``
      case) — it is gated solely by the budget, not by SOC/schedule/etc.;
    * a proportional device that is enabled but allocated below its
      ``max_expected_w`` could ramp higher with more budget.

    Start-gate: when ``untapped_w`` is given, a waiting on/off device is counted
    only if its minimum draw fits within ``factor × untapped_w``. This is checked
    while the device is OFF (untapped is valid then — it has not collapsed under
    load), so the probe will not blindly chase a load far larger than the
    plausible curtailed headroom (which would just cycle it). Proportional devices
    can use any amount, so they are not start-gated.

    Devices blocked by a real gate (schedule, SOC, min-on-time) carry refusals
    and are therefore ignored, so the probe never fights a protective gate.
    Devices opted out of probing (``allow_probe`` False) are skipped entirely.
    """
    for st in status_entries:
        if st.get("allow_probe") is False:
            continue
        refusals = st.get("refusal_reasons") or []
        if not st.get("is_enabled") and not refusals and not st.get("is_active_candidate"):
            need = float(st.get(CONF_DEVICE_MIN_EXPECTED_W, 0) or 0)
            if untapped_w is not None and need > factor * max(0.0, float(untapped_w)):
                continue  # too big for the plausible curtailed headroom — don't chase
            return True
        if (
            st.get("mode") == RELAY_MODE_PROPORTIONAL
            and st.get("is_enabled")
            and float(st.get("allocated_w", 0) or 0) < float(st.get("max_expected_w", 0) or 0)
        ):
            return True
    return False


def running_controllable_floor_w(
    status_entries_by_id: Dict[str, Dict[str, Any]],
    on_state: Dict[str, Any],
) -> float:
    """Watts of probe-eligible controllable load **already running**.

    A device that is currently ON, allows probing, and is not under a manual
    override is — by the fact that it is running while the battery is healthy —
    empirical proof of that much sustainable headroom. The probe floors its budget
    to this sum so an already-running load is never dropped just because the
    cautious excess (or an under-shooting forecast target) dipped below the device's
    threshold: the running device IS the measured ceiling, no rediscovery needed.

    Opt-out devices (``allow_probe`` False) draw only from the cautious real pool, so
    they never contribute to the speculative headroom floor. Manually-overridden
    devices are the user's to control and are excluded until the override clears.
    """
    total = 0.0
    for did, st in status_entries_by_id.items():
        if not on_state.get(did):
            continue
        if st.get("allow_probe", True) is False:
            continue
        if st.get("manual_override"):
            continue
        total += float(st.get(CONF_DEVICE_MIN_EXPECTED_W, 0) or 0)
    return total


def initial_state() -> Dict[str, Any]:
    """Fresh probe state."""
    return {
        "headroom_w": 0.0,
        "ceiling_w": PROBE_MAX_HEADROOM_W,
        "baseline_soc": None,
        "last_backoff_ts": 0.0,
        "discharge_streak": 0,
        "failure_count": 0,
        "backed_off": False,
    }


def forecast_target_w(
    forecast_untapped_w: Optional[float], max_headroom_w: float
) -> Optional[float]:
    """Headroom growth target derived from the PV-production forecast.

    ``forecast_untapped_w`` is the excess sensor's ``max(0, forecast − pv)`` — the
    watts the forecast predicts are available beyond the current PV output, which
    is exactly the curtailed headroom the probe tries to recover. Returns ``None``
    when no forecast is configured (the caller then probes blind), otherwise the
    forecast clamped to ``[0, max_headroom_w]`` (the array can never make more than
    its nameplate Pmax). The forecast is only a *target*: ``plan_headroom`` still
    validates every step against the battery, so an over-optimistic evening
    forecast is caught and backed off — no separate "trust" bookkeeping needed.
    """
    if forecast_untapped_w is None:
        return None
    return max(0.0, min(float(forecast_untapped_w), float(max_headroom_w)))


def plan_headroom(
    *,
    enabled: bool,
    has_target: bool,
    battery_soc: Optional[float],
    net_charge_w: float,
    discharge_tolerance_w: float,
    state: Optional[Dict[str, Any]],
    now_ts: float,
    charge_idle_w: float = BATTERY_CHARGE_IDLE_W,
    soc_backoff_drop: float = PROBE_SOC_BACKOFF_DROP,
    step_w: float = PROBE_STEP_W,
    cooldown_s: float = PROBE_COOLDOWN_S,
    max_headroom_w: float = PROBE_MAX_HEADROOM_W,
    target_w: Optional[float] = None,
    approach_fraction: float = 0.0,
    sharing_soc: float = 0.0,
    floor_w: float = 0.0,
) -> Dict[str, Any]:
    """Pure scalar controller for one probe tick. Returns the new probe state
    ``{headroom_w, ceiling_w, baseline_soc, last_backoff_ts, discharge_streak,
    failure_count, backed_off}``.

    The caller adds ``headroom_w`` to the excess budget, re-runs allocation, and
    on the next tick passes the resulting battery reading back in.

    ``target_w`` (when not ``None``) caps growth at a forecast-derived level and
    makes each step close ``approach_fraction`` of the remaining gap, floored at
    ``step_w`` — the probe still validates every step against the battery, so an
    over-optimistic forecast is caught and backed off exactly as a blind probe is.
    ``target_w=None`` + ``approach_fraction=0.0`` (the defaults) is the blind
    probe: byte-for-byte the original fixed-step grow-to-``max_headroom_w``.
    ``backed_off`` is ``True`` only on the tick a sustained discharge forces a
    back-off.

    ``sharing_soc`` aligns the probe with the battery-sharing setting: at/above it
    the user has authorised releasing surplus, so a charge no longer forces the
    probe to stand down (a charge means solar covers the load *and* tops up the
    battery — the best case). Below it (or when sharing is disabled / SOC unknown)
    the battery keeps absolute priority and any charge releases the headroom. A
    discharge is always the only signal that shrinks the headroom; charge never is.

    ``floor_w`` is the watts of probe-eligible load already running (see
    ``running_controllable_floor_w``). While the battery is healthy the result is
    floored to it so an already-running device is never dropped because the forecast
    target or cautious excess dipped below its threshold — the running load is the
    measured ceiling and may exceed ``target_w``. The floor is **not** applied while
    the battery is discharging (the running load may not be free → it must be free to
    back off below it) nor while charge is being released to the battery.
    """
    st = state or initial_state()
    headroom = float(st.get("headroom_w", 0.0))
    ceiling = float(st.get("ceiling_w", max_headroom_w))
    baseline_soc = st.get("baseline_soc")
    last_backoff_ts = float(st.get("last_backoff_ts", 0.0))
    streak = int(st.get("discharge_streak", 0))
    failures = int(st.get("failure_count", 0))

    # Disabled → release all probe-driven load.
    if not enabled:
        return {
            "headroom_w": 0.0, "ceiling_w": max_headroom_w,
            "baseline_soc": None, "last_backoff_ts": last_backoff_ts,
            "discharge_streak": 0, "failure_count": 0, "backed_off": False,
        }

    # "At charge limit" is detected from charge POWER, not SOC: many inverters cap
    # charging below 100% (SOC limit / stop-charging voltage / preserve mode), so
    # an SOC test would never fire on those systems.
    #
    # Battery-sharing override: at/above ``sharing_soc`` the user has authorised
    # releasing surplus, so a charge no longer stands the probe down — solar then
    # covers the load AND tops up the battery (the best case), and only a discharge
    # ever backs the headroom off. Below ``sharing_soc`` (or sharing disabled / SOC
    # unknown) the battery keeps absolute priority: any charge releases the headroom.
    sharing_active = (
        battery_soc is not None
        and 0 < sharing_soc <= battery_soc
    )
    accepting_charge = net_charge_w > charge_idle_w and not sharing_active
    discharging = net_charge_w < -discharge_tolerance_w
    soc_dropped = (
        baseline_soc is not None
        and battery_soc is not None
        and (baseline_soc - battery_soc) >= soc_backoff_drop
    )

    # Battery still actively absorbing charge → it is not done; do not steal it.
    # Conditions clearly changed, so reset the failure counter (fresh start).
    if accepting_charge:
        return {
            "headroom_w": 0.0, "ceiling_w": max_headroom_w,
            "baseline_soc": battery_soc, "last_backoff_ts": last_backoff_ts,
            "discharge_streak": 0, "failure_count": 0, "backed_off": False,
        }

    # Possible overshoot: the headroom drew from the battery. Require the deficit to
    # PERSIST for several ticks before backing off, so a single momentary dip (a
    # compressor peak or a passing cloud) does not collapse the headroom and drop a
    # device. Until confirmed, hold (do not grow, do not back off).
    if discharging or soc_dropped:
        streak += 1
        if streak < PROBE_BACKOFF_STREAK:
            return {
                "headroom_w": headroom, "ceiling_w": ceiling,
                "baseline_soc": battery_soc, "last_backoff_ts": last_backoff_ts,
                "discharge_streak": streak, "failure_count": failures,
                "backed_off": False,
            }
        # Confirmed sustained: back off below the offending level, lower the ceiling
        # and start the cooldown. Each consecutive failure raises the failure count,
        # which lengthens the (adaptive) cooldown so a load that cannot be sustained
        # is retried less and less often instead of cycling. backed_off=True signals
        # the caller (a forecast target was overshot — the forecast was optimistic).
        backed = max(0.0, headroom - step_w)
        return {
            "headroom_w": backed, "ceiling_w": backed,
            "baseline_soc": battery_soc, "last_backoff_ts": now_ts,
            "discharge_streak": 0, "failure_count": min(failures + 1, 6),
            "backed_off": True,
        }

    # Battery healthy. Adaptive cooldown: base × 2**failures, capped — repeated
    # failures back the retry off exponentially. After it elapses the ceiling
    # recovers so the probe re-discovers headroom (e.g. more sun, lighter load).
    effective_cooldown = min(cooldown_s * (2 ** failures), PROBE_COOLDOWN_MAX_S)
    in_cooldown = (now_ts - last_backoff_ts) < effective_cooldown
    if in_cooldown:
        cap = min(ceiling, max_headroom_w)
    else:
        ceiling = max_headroom_w
        cap = max_headroom_w

    # A forecast target caps growth at the (battery-validated) forecast level — the
    # probe never chases beyond what the forecast claims is available.
    if target_w is not None:
        cap = min(cap, max(0.0, float(target_w)))

    if has_target and not in_cooldown and headroom < cap:
        # Growing (still attempting) — keep the failure count until proven sustained.
        # With a forecast target, close a fraction of the remaining gap (floored at
        # step_w) so the approach is fast while far and gentle near the target; blind
        # (no target) keeps the original fixed step.
        if target_w is not None:
            step = max(step_w, approach_fraction * (cap - headroom))
        else:
            step = step_w
        grown = max(min(cap, headroom + step), float(floor_w))
        return {
            "headroom_w": grown, "ceiling_w": ceiling,
            "baseline_soc": battery_soc, "last_backoff_ts": last_backoff_ts,
            "discharge_streak": 0, "failure_count": failures, "backed_off": False,
        }

    # Hold: keep current devices running; keep the existing baseline so a slow
    # multi-tick SOC drain can still accumulate to the back-off threshold. A
    # healthy hold with headroom in use is a sustained success → reset failures.
    # Floor to the already-running load so a sustained device is never dropped.
    held = max(headroom, float(floor_w))
    return {
        "headroom_w": held, "ceiling_w": ceiling,
        "baseline_soc": baseline_soc, "last_backoff_ts": last_backoff_ts,
        "discharge_streak": 0, "failure_count": 0 if held > 0 else failures,
        "backed_off": False,
    }
