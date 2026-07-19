"""Pure tests for manual-control classification and the battery SOC stop decision.

``decide_manual_state`` now only classifies the override (auto / manual_off / manual_on);
battery-protection force-off moved to ``decide_battery_soc_stop`` (used by both the manual
and the auto paths). Daily rollover and the relay/accounting side-effects live in the async
orchestrator and are verified on HA; this covers the pure logic.
"""

from custom_components.sun_allocator.core.power_processor import (
    decide_manual_state,
    decide_battery_soc_stop,
)


def _ov(state=True, since=None):
    return {"state": state, "since": since}


# --- decide_manual_state (3-state classifier) --------------------------------

def test_no_override_is_auto():
    assert decide_manual_state(None) == "auto"


def test_state_off_is_manual_off():
    assert decide_manual_state(_ov(False)) == "manual_off"


def test_state_on_is_manual_on():
    assert decide_manual_state(_ov(True)) == "manual_on"


# --- decide_battery_soc_stop (force-off decision) ----------------------------

def _stop(**kw):
    base = dict(
        battery_soc=90.0, soc_configured=True, discharging=True,
        stop_soc=100.0, protection_soc=0.0, was_blocked=False,
    )
    base.update(kw)
    return decide_battery_soc_stop(**base)


def test_stop_default_100_sheds_on_any_discharge():
    # stop=100, discharging, SOC 90 < 100 → force off.
    assert _stop(stop_soc=100.0, battery_soc=90.0) is True


def test_no_stop_while_charging():
    # Not discharging → discharge-gated axis never fires (solar covers the load).
    assert _stop(discharging=False, stop_soc=100.0, battery_soc=50.0) is False


def test_stop_below_device_floor_while_discharging():
    assert _stop(stop_soc=60.0, battery_soc=55.0, discharging=True) is True
    assert _stop(stop_soc=60.0, battery_soc=65.0, discharging=True) is False


def test_protection_floor_is_absolute_any_direction():
    # Below the global hard floor forces off even while charging.
    assert _stop(protection_soc=40.0, battery_soc=35.0, discharging=False, stop_soc=0.0) is True
    assert _stop(protection_soc=40.0, battery_soc=45.0, discharging=False, stop_soc=0.0) is False


def test_stop_zero_inherits_global_protection():
    # stop=0 → inherit the global protection floor (no extra per-device rule).
    # No protection set → no discharge-side floor at all (device may discharge freely).
    assert _stop(stop_soc=0.0, protection_soc=0.0, battery_soc=5.0, discharging=True) is False
    # With a protection floor, stop=0 device is force-off below it (absolute axis).
    assert _stop(stop_soc=0.0, protection_soc=70.0, battery_soc=65.0, discharging=True) is True
    assert _stop(stop_soc=0.0, protection_soc=70.0, battery_soc=75.0, discharging=True) is False


def test_effective_floor_is_max_of_stop_and_protection():
    # stop 50, protection 70 → effective 70 → 65 < 70 → off (while discharging).
    assert _stop(stop_soc=50.0, protection_soc=70.0, battery_soc=65.0, discharging=True) is True


def test_hysteresis_release_band():
    # Was blocked at stop 80 → must recover to 80 + 2 before release.
    assert _stop(stop_soc=80.0, battery_soc=81.0, was_blocked=True, discharging=True) is True
    assert _stop(stop_soc=80.0, battery_soc=82.0, was_blocked=True, discharging=True) is False


def test_no_stop_when_soc_unknown():
    assert _stop(battery_soc=None, stop_soc=100.0) is False


def test_no_stop_when_sensor_not_configured():
    assert _stop(soc_configured=False, battery_soc=5.0, stop_soc=100.0) is False
