"""Tests for the scalar probe controller (core/probe.py).

The probe sizes a ``headroom_w`` budget by battery feedback; the existing
allocator handles device-level cascade/partial/priority. These tests cover the
pure decision core: enable gate, battery sign, growth gate, and the
plan_headroom feedback loop (grow / hold / back-off / cooldown / caps).
"""

from custom_components.sun_allocator.core import probe
from custom_components.sun_allocator.const import (
    CALC_METHOD_MPPT,
    CALC_METHOD_MPPT_PROBE,
    CALC_METHOD_EXPORT,
    PROBE_STEP_W,
    PROBE_MAX_HEADROOM_W,
    PROBE_FORECAST_APPROACH_FRACTION,
)


# --- helpers ---------------------------------------------------------------

def _state(headroom=0.0, ceiling=PROBE_MAX_HEADROOM_W, baseline=None, backoff_ts=0.0,
           streak=0, failure=0):
    return {
        "headroom_w": headroom,
        "ceiling_w": ceiling,
        "baseline_soc": baseline,
        "last_backoff_ts": backoff_ts,
        "discharge_streak": streak,
        "failure_count": failure,
    }


def _plan(**kw):
    base = dict(
        enabled=True, has_target=True, battery_soc=100.0, net_charge_w=0.0,
        discharge_tolerance_w=20.0, state=_state(), now_ts=100000.0,
    )
    base.update(kw)
    return probe.plan_headroom(**base)


# --- simple helpers --------------------------------------------------------

def test_is_probe_enabled():
    assert probe.is_probe_enabled(CALC_METHOD_MPPT_PROBE) is True
    assert probe.is_probe_enabled(CALC_METHOD_MPPT) is False
    assert probe.is_probe_enabled(CALC_METHOD_EXPORT) is False
    assert probe.is_probe_enabled(None) is False


def test_battery_net_charge_sign():
    # reversed=True → positive sensor value = discharging → negate.
    assert probe.battery_net_charge_w(50.0, True) == -50.0
    assert probe.battery_net_charge_w(-50.0, True) == 50.0
    # reversed=False → as-is (negative = discharging).
    assert probe.battery_net_charge_w(-50.0, False) == -50.0


def test_has_growth_target():
    assert probe.has_growth_target(["active", "insufficient_power"]) is True
    assert probe.has_growth_target(["active", "idle"]) is False
    assert probe.has_growth_target([]) is False


def test_effective_excess():
    assert probe.effective_excess(100.0, 300.0) == 400.0
    assert probe.effective_excess(100.0, -5.0) == 100.0  # negative headroom ignored


def test_growth_target_waiting_device():
    # not enabled, no refusals, not candidate → waiting only for power.
    waiting = {"is_enabled": False, "refusal_reasons": [], "is_active_candidate": False}
    assert probe.growth_target_present([waiting]) is True


def test_growth_target_ignores_gated_device():
    # has a refusal (e.g. SOC/schedule gate) → not a probe target.
    gated = {"is_enabled": False, "refusal_reasons": ["Startup grace"], "is_active_candidate": False}
    assert probe.growth_target_present([gated]) is False


def test_growth_target_proportional_below_max():
    from custom_components.sun_allocator.const import RELAY_MODE_PROPORTIONAL
    prop = {"is_enabled": True, "mode": RELAY_MODE_PROPORTIONAL,
            "allocated_w": 300.0, "max_expected_w": 1000.0}
    assert probe.growth_target_present([prop]) is True


def test_growth_target_none_when_all_satisfied():
    from custom_components.sun_allocator.const import RELAY_MODE_PROPORTIONAL
    maxed = {"is_enabled": True, "mode": RELAY_MODE_PROPORTIONAL,
             "allocated_w": 1000.0, "max_expected_w": 1000.0}
    on = {"is_enabled": True, "refusal_reasons": [], "is_active_candidate": True}
    assert probe.growth_target_present([maxed, on]) is False


def test_growth_target_skips_opt_out_device():
    # A waiting device opted out of probing must not drive headroom growth.
    opt_out = {"is_enabled": False, "refusal_reasons": [], "is_active_candidate": False,
               "allow_probe": False}
    assert probe.growth_target_present([opt_out]) is False


def test_growth_target_counts_probe_allowed_device():
    waiting = {"is_enabled": False, "refusal_reasons": [], "is_active_candidate": False,
               "allow_probe": True}
    assert probe.growth_target_present([waiting]) is True


def test_growth_target_missing_allow_probe_treated_as_allowed():
    waiting = {"is_enabled": False, "refusal_reasons": [], "is_active_candidate": False}
    assert probe.growth_target_present([waiting]) is True


def test_custom_max_headroom_caps_growth():
    # A dynamic cap (e.g. from N×untapped) below the global max is respected.
    out = _plan(state=_state(headroom=250.0), max_headroom_w=300.0)
    assert out["headroom_w"] == 300.0
    out2 = _plan(state=_state(headroom=300.0), max_headroom_w=300.0)
    assert out2["headroom_w"] == 300.0  # already at cap → hold


# --- plan_headroom: gates --------------------------------------------------

def test_disabled_releases_headroom():
    out = _plan(enabled=False, state=_state(headroom=300.0))
    assert out["headroom_w"] == 0.0


def test_actively_charging_releases_headroom():
    # net charge 200W > idle band → battery still hungry → release (battery-first).
    out = _plan(net_charge_w=200.0, state=_state(headroom=300.0))
    assert out["headroom_w"] == 0.0


def test_charge_within_idle_band_grows():
    # trickle charge 30W (<= 50W idle) → at limit → probe may grow.
    out = _plan(net_charge_w=30.0, state=_state(headroom=0.0))
    assert out["headroom_w"] == PROBE_STEP_W


# --- plan_headroom: growth -------------------------------------------------

def test_healthy_grows_by_step():
    out = _plan(state=_state(headroom=0.0))
    assert out["headroom_w"] == PROBE_STEP_W


def test_no_growth_target_holds():
    out = _plan(has_target=False, state=_state(headroom=300.0))
    assert out["headroom_w"] == 300.0


def test_growth_caps_at_max():
    out = _plan(state=_state(headroom=PROBE_MAX_HEADROOM_W - 50.0))
    assert out["headroom_w"] == PROBE_MAX_HEADROOM_W


def test_no_soc_sensor_treated_as_full_and_grows():
    out = _plan(battery_soc=None, state=_state(headroom=0.0))
    assert out["headroom_w"] == PROBE_STEP_W


# --- plan_headroom: back-off ----------------------------------------------

def test_single_discharge_tick_holds_not_backoff():
    # One momentary dip must NOT collapse headroom (debounce): hold + streak=1.
    out = _plan(net_charge_w=-50.0, state=_state(headroom=300.0, baseline=100.0))
    assert out["headroom_w"] == 300.0          # held, not backed off
    assert out["discharge_streak"] == 1


def test_confirmed_discharge_backs_off_and_sets_cooldown():
    # Second consecutive dip (streak already 1) → confirmed → back off.
    out = _plan(net_charge_w=-50.0,
                state=_state(headroom=300.0, baseline=100.0, streak=1), now_ts=100000.0)
    assert out["headroom_w"] == 200.0          # 300 - step(100)
    assert out["ceiling_w"] == 200.0           # ceiling lowered to the safe level
    assert out["last_backoff_ts"] == 100000.0  # cooldown started
    assert out["discharge_streak"] == 0        # streak reset after back-off


def test_discharge_within_tolerance_does_not_back_off():
    # -10W with 20W tolerance → not discharging → grows, streak reset.
    out = _plan(net_charge_w=-10.0, state=_state(headroom=100.0, streak=1))
    assert out["headroom_w"] == 200.0
    assert out["discharge_streak"] == 0


def test_soc_drop_backs_off_when_confirmed():
    out = _plan(net_charge_w=0.0, battery_soc=98.0,
                state=_state(headroom=300.0, baseline=100.0, streak=1))  # dropped 2% >= 1%
    assert out["headroom_w"] == 200.0
    assert out["last_backoff_ts"] == 100000.0


def test_backoff_floors_at_zero():
    out = _plan(net_charge_w=-50.0, state=_state(headroom=50.0, baseline=100.0, streak=1))
    assert out["headroom_w"] == 0.0
    assert out["ceiling_w"] == 0.0


# --- plan_headroom: cooldown ----------------------------------------------

def test_cooldown_blocks_growth():
    # backoff at t=100000, now t=100100 (100s < 300s cooldown) → hold at ceiling.
    out = _plan(state=_state(headroom=200.0, ceiling=200.0, backoff_ts=100000.0),
                now_ts=100100.0)
    assert out["headroom_w"] == 200.0


def test_cooldown_expiry_recovers_ceiling_and_grows():
    # now t=100400 (400s >= 300s) → ceiling recovers to max, grows again.
    out = _plan(state=_state(headroom=200.0, ceiling=200.0, backoff_ts=100000.0),
                now_ts=100400.0)
    assert out["ceiling_w"] == PROBE_MAX_HEADROOM_W
    assert out["headroom_w"] == 300.0


# --- start-gate (don't chase a load bigger than plausible headroom) --------

def test_start_gate_blocks_oversized_device():
    # AC needs 700 W; untapped 100 W × factor 3 = 300 < 700 → not a growth target.
    waiting = {"is_enabled": False, "refusal_reasons": [], "is_active_candidate": False,
               "min_expected_w": 700.0}
    assert probe.growth_target_present([waiting], untapped_w=100.0) is False


def test_start_gate_allows_device_within_factor():
    # untapped 300 × 3 = 900 >= 700 → allowed.
    waiting = {"is_enabled": False, "refusal_reasons": [], "is_active_candidate": False,
               "min_expected_w": 700.0}
    assert probe.growth_target_present([waiting], untapped_w=300.0) is True


def test_start_gate_not_applied_without_untapped():
    waiting = {"is_enabled": False, "refusal_reasons": [], "is_active_candidate": False,
               "min_expected_w": 700.0}
    assert probe.growth_target_present([waiting]) is True  # untapped_w=None → no gate


def test_start_gate_does_not_block_proportional_below_max():
    from custom_components.sun_allocator.const import RELAY_MODE_PROPORTIONAL
    prop = {"is_enabled": True, "mode": RELAY_MODE_PROPORTIONAL,
            "allocated_w": 100.0, "max_expected_w": 1000.0, "min_expected_w": 700.0}
    # Proportional can use any amount → not start-gated even with tiny untapped.
    assert probe.growth_target_present([prop], untapped_w=10.0) is True


# --- adaptive cooldown -----------------------------------------------------

def test_adaptive_cooldown_doubles_after_failure():
    # failure_count=1 → effective cooldown = 300 × 2 = 600s. now 400s after backoff
    # → still in cooldown → hold (no grow).
    out = _plan(state=_state(headroom=200.0, ceiling=200.0, backoff_ts=100000.0,
                             failure=1),
                now_ts=100400.0)
    assert out["headroom_w"] == 200.0  # 400 < 600 → blocked


def test_backoff_increments_failure_count():
    out = _plan(net_charge_w=-50.0,
                state=_state(headroom=300.0, baseline=100.0, streak=1, failure=2))
    assert out["failure_count"] == 3


def test_sustained_hold_resets_failures():
    # Healthy hold with headroom in use (device sustained) → reset failures.
    out = _plan(has_target=False, state=_state(headroom=300.0, failure=3))
    assert out["headroom_w"] == 300.0
    assert out["failure_count"] == 0


def test_accepting_charge_resets_failures():
    out = _plan(net_charge_w=200.0, state=_state(headroom=300.0, failure=3))
    assert out["headroom_w"] == 0.0
    assert out["failure_count"] == 0


# --- forecast_target_w (pure) ----------------------------------------------

def test_forecast_target_none_when_no_forecast():
    # No forecast configured → None → caller probes blind (no target).
    assert probe.forecast_target_w(None, 5000.0) is None


def test_forecast_target_passes_through_within_bounds():
    assert probe.forecast_target_w(800.0, 5000.0) == 800.0


def test_forecast_target_clamped_to_max_headroom():
    # Forecast can never exceed the array nameplate Pmax.
    assert probe.forecast_target_w(6000.0, 5000.0) == 5000.0


def test_forecast_target_negative_clamped_to_zero():
    assert probe.forecast_target_w(-10.0, 5000.0) == 0.0


# --- plan_headroom: battery-sharing charge override ------------------------

def test_sharing_active_charge_grows_instead_of_releasing():
    # SOC 98 >= sharing 95 → user authorised sharing surplus → a charge no longer
    # zeroes the headroom; the probe keeps growing (charge = solar covers load + tops
    # up battery, the best case).
    out = _plan(net_charge_w=200.0, battery_soc=98.0, sharing_soc=95.0,
                state=_state(headroom=300.0))
    assert out["headroom_w"] == 300.0 + PROBE_STEP_W


def test_below_sharing_soc_charge_releases():
    # SOC 90 < sharing 95 → battery absolute priority → charge releases the headroom.
    out = _plan(net_charge_w=200.0, battery_soc=90.0, sharing_soc=95.0,
                state=_state(headroom=300.0))
    assert out["headroom_w"] == 0.0


def test_sharing_disabled_charge_releases():
    # sharing_soc=0 (disabled) → original battery-first: any charge releases.
    out = _plan(net_charge_w=200.0, battery_soc=100.0, sharing_soc=0.0,
                state=_state(headroom=300.0))
    assert out["headroom_w"] == 0.0


def test_sharing_unknown_soc_charge_releases():
    # SOC unknown → cannot confirm sharing range → battery-first: charge releases.
    out = _plan(net_charge_w=200.0, battery_soc=None, sharing_soc=95.0,
                state=_state(headroom=300.0))
    assert out["headroom_w"] == 0.0


def test_sharing_active_still_backs_off_on_discharge():
    # Above sharing SOC a charge is fine, but a confirmed discharge still backs off —
    # discharge remains the only signal that shrinks the headroom.
    out = _plan(net_charge_w=-50.0, battery_soc=98.0, sharing_soc=95.0,
                discharge_tolerance_w=20.0,
                state=_state(headroom=300.0, baseline=100.0, streak=1))
    assert out["headroom_w"] == 200.0
    assert out["backed_off"] is True


# --- running_controllable_floor_w (pure) -----------------------------------

def test_floor_counts_running_probe_device():
    status = {"ac": {"allow_probe": True, "min_expected_w": 700.0}}
    assert probe.running_controllable_floor_w(status, {"ac": True}) == 700.0


def test_floor_ignores_off_device():
    status = {"ac": {"allow_probe": True, "min_expected_w": 700.0}}
    assert probe.running_controllable_floor_w(status, {"ac": False}) == 0.0


def test_floor_ignores_opt_out_device():
    status = {"ac": {"allow_probe": False, "min_expected_w": 700.0}}
    assert probe.running_controllable_floor_w(status, {"ac": True}) == 0.0


def test_floor_ignores_manual_override_device():
    status = {"ac": {"allow_probe": True, "min_expected_w": 700.0,
                     "manual_override": True}}
    assert probe.running_controllable_floor_w(status, {"ac": True}) == 0.0


def test_floor_sums_multiple_running_devices():
    status = {"ac": {"allow_probe": True, "min_expected_w": 700.0},
              "heater": {"allow_probe": True, "min_expected_w": 300.0}}
    on = {"ac": True, "heater": True}
    assert probe.running_controllable_floor_w(status, on) == 1000.0


# --- plan_headroom: running-load floor --------------------------------------

def test_floor_lifts_headroom_on_grow():
    # Fresh probe, a 700 W load already running → headroom jumps straight to the floor.
    out = _plan(state=_state(headroom=0.0), floor_w=700.0)
    assert out["headroom_w"] == 700.0


def test_floor_exceeds_forecast_target():
    # Running 700 W proves more available than a 656 W forecast target → floor wins.
    out = _plan(state=_state(headroom=0.0), target_w=656.0,
                approach_fraction=PROBE_FORECAST_APPROACH_FRACTION, floor_w=700.0)
    assert out["headroom_w"] == 700.0


def test_floor_holds_running_load_when_no_target():
    # No device wants more (has_target False) but one is running → hold at the floor.
    out = _plan(has_target=False, state=_state(headroom=0.0), floor_w=700.0)
    assert out["headroom_w"] == 700.0


def test_floor_not_applied_on_confirmed_discharge():
    # Running load draining the battery → must back off below the floor, not be pinned.
    out = _plan(net_charge_w=-200.0, discharge_tolerance_w=20.0,
                state=_state(headroom=700.0, baseline=100.0, streak=1), floor_w=700.0)
    assert out["headroom_w"] == 600.0
    assert out["backed_off"] is True


def test_floor_not_applied_when_releasing_charge():
    # Below sharing SOC the battery reclaims charge → release to 0 despite a floor.
    out = _plan(net_charge_w=200.0, battery_soc=90.0, sharing_soc=95.0,
                state=_state(headroom=700.0), floor_w=700.0)
    assert out["headroom_w"] == 0.0


# --- plan_headroom: forecast target ----------------------------------------

def test_target_step_closes_quarter_of_gap():
    # Gap 1000, fraction 0.25 → step 250 (> floor 100) → grow to 250.
    out = _plan(state=_state(headroom=0.0), target_w=1000.0,
                approach_fraction=PROBE_FORECAST_APPROACH_FRACTION)
    assert out["headroom_w"] == 250.0


def test_target_step_floored_at_step_w():
    # Gap 200, 0.25×200=50 < step_w(100) → floored at 100 → grow to 100.
    out = _plan(state=_state(headroom=800.0), target_w=1000.0,
                approach_fraction=PROBE_FORECAST_APPROACH_FRACTION)
    assert out["headroom_w"] == 900.0


def test_target_caps_growth():
    # One step would overshoot the target → clamp to the target.
    out = _plan(state=_state(headroom=950.0), target_w=1000.0,
                approach_fraction=PROBE_FORECAST_APPROACH_FRACTION)
    assert out["headroom_w"] == 1000.0


def test_target_below_headroom_holds_does_not_shrink():
    # Forecast dropped below current headroom → growth gate closed → hold (shrink
    # is left to the discharge back-off, not the target).
    out = _plan(state=_state(headroom=500.0), target_w=300.0,
                approach_fraction=PROBE_FORECAST_APPROACH_FRACTION)
    assert out["headroom_w"] == 500.0


def test_target_zero_no_growth():
    out = _plan(state=_state(headroom=0.0), target_w=0.0,
                approach_fraction=PROBE_FORECAST_APPROACH_FRACTION)
    assert out["headroom_w"] == 0.0


def test_no_target_is_byte_for_byte_blind_step():
    # target_w=None + approach_fraction=0.0 (defaults) → original fixed step_w.
    out = _plan(state=_state(headroom=0.0))
    assert out["headroom_w"] == PROBE_STEP_W
    out2 = _plan(state=_state(headroom=250.0), target_w=None)
    assert out2["headroom_w"] == 250.0 + PROBE_STEP_W


# --- plan_headroom: backed_off flag ----------------------------------------

def test_backed_off_true_only_on_confirmed_backoff():
    out = _plan(net_charge_w=-50.0,
                state=_state(headroom=300.0, baseline=100.0, streak=1))
    assert out["headroom_w"] == 200.0
    assert out["backed_off"] is True


def test_backed_off_false_on_grow():
    assert _plan(state=_state(headroom=0.0))["backed_off"] is False


def test_backed_off_false_on_disabled():
    assert _plan(enabled=False, state=_state(headroom=300.0))["backed_off"] is False


def test_backed_off_false_on_accepting_charge():
    assert _plan(net_charge_w=200.0)["backed_off"] is False


def test_backed_off_false_on_unconfirmed_dip():
    # First discharge tick (streak 0→1) holds, not a back-off.
    out = _plan(net_charge_w=-50.0, state=_state(headroom=300.0, baseline=100.0))
    assert out["discharge_streak"] == 1
    assert out["backed_off"] is False


def test_backed_off_false_on_hold():
    out = _plan(has_target=False, state=_state(headroom=300.0))
    assert out["backed_off"] is False


def test_initial_state_has_backed_off():
    assert probe.initial_state()["backed_off"] is False
