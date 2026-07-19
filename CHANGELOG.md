# Changelog

All notable changes to **SunAllocator** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/).
Versions before `1.1.0` are reconstructed from commit history, so their grouping
is approximate. This project tracks its version in
`custom_components/sun_allocator/manifest.json` (used by HACS) and, from
`1.1.0` onward, in matching `vX.Y.Z` git release tags.

## [1.3.0] — 2026-07-19

### Added
- **Timed run** — a per-device **"Run Timer (min)"** number: enter minutes to force the
  device ON for exactly that long, **ignoring the battery limits and the schedule**. When
  the timer ends it resets to `0` and the device is released back to auto-control. Two
  read-only companion sensors: **"Run Time (today)"** (accumulated on-time, resets at
  local midnight, survives restarts) and **"Time Until Off"** (minutes left on an active
  timed run). Surfaced as a distinct `manual_timer` device status.
- **"Switch" proxy per device** — a convenience toggle that drives the controlled entity
  on/off straight from the SunAllocator card and mirrors its live state. Turning it OFF
  while a manual/timed override is active *releases* the override back to auto; turning it
  OFF with no override sets a sticky manual-off.
- **`unreachable` device status** — a device commanded ON that never confirms after
  repeated throttled retries is surfaced as `unreachable` (instead of looking like
  "insufficient power"); suppressed for climate, whose reported OFF is usually a satisfied
  thermostat.
- **On-time totals persist across restart** — the run-time sensor and the
  `max_on_time_per_day` budget keep today's accumulated total through a HA restart.
- **Manual-control sticky state** (`manual_active`) — a manual toggle of a
  controlled device is now sticky for the rest of the local day (cleared on daily
  rollover, on re-toggling auto-control, or by battery protection). While active it
  **overrides the device's schedule and usable-condition template**; only battery-SOC
  protection can force a manual-ON device off. Surfaced as a new device status,
  `manual_active`.
- **Asymmetric per-device battery-SOC thresholds** — `start_battery_soc` is the
  charge-side START gate (begin only when SOC is at/above it; renamed from
  `min_battery_soc`, migrated automatically). `stop_battery_soc` is the new
  discharge-side STOP floor: while the battery is discharging a running device is
  forced off below it (default `100` = never discharge the battery for that device).
- **Global battery-protection floor** (`battery_protection_soc`) — an absolute SOC
  floor: below it *every* controlled device is forced off regardless of charge
  direction, and it is the hard minimum any per-device `stop_battery_soc` may take.
- **Per-device "Allow Speculative Surplus"** (`allow_probe`) — gates whether a device
  may use probe/forecast headroom. With it off the device runs only on genuine
  (cautious) excess; with it on it can be started by the active probe or by
  forecast-guided headroom.
- **Dedicated Battery settings page** — battery sensors and the reserve / sharing /
  protection / discharge-tolerance thresholds now live on their own **Battery** step.

### Changed
- **Device control mode is chosen from the entity picker** — dimmable lights and
  ESPHome relays now appear twice in the entity list: **(Switch)** for on/off and
  **(Dimmer)** for proportional control. The separate device-type selector
  ("standard vs custom ESPHome") is gone; proportional control still requires
  `max_expected_w`. ESPHome relays auto-pair their mode-select entity at save time.
  Existing devices are migrated to a per-device `control_mode` automatically.
- **Probe recovers curtailed solar in more setups** — the active probe (which grows a
  controllable load and validates it against the battery to recover solar the cautious
  MPPT excess cannot see) now runs either with `calculation_method = mppt_probe` **or**
  with the plain `mppt` method when a PV forecast sensor is configured. In both cases
  each device's `allow_probe` gates use of the probe/forecast headroom.
- **Per-device configuration split into Basic + Advanced** — everyday knobs (auto
  control, priority, expected load, schedule mode) on the **Basic** step; fine-tuning
  (timing, `allow_probe`, per-device SOC thresholds, actual-power sensor, usability
  template) on the **Advanced** step. The global **Advanced Settings** page now carries
  only algorithm/probe knobs.

### Removed
- Dropped dead options that no logic reads: the legacy proportional-ramp tunables
  `ramp_up_step`, `ramp_down_step`, `ramp_deadband`, and the orphan per-device
  `min_excess_power`. Existing installs are migrated automatically (the keys are
  pruned on the first launch after upgrade).
- The legacy `device_type` shim is no longer written or read at runtime (superseded by
  the per-device `control_mode`); diagnostics now report `control_mode`.

### Fixed
- **On-time accounting is now consistent across every off-path** — a running device shed
  by the schedule/usable filter or the discharge stop-floor now closes its on-time
  session (previously that time was silently dropped, under-counting the run-time sensor
  and the `max_on_time_per_day` budget).
- **No phantom session / grace churn on a vetoed start** — the on-time session and
  startup-grace deadline are recorded only after every gate confirms the start survives,
  so an SOC-blocked device no longer writes a phantom session or rewrites its grace
  deadline to storage every cycle.
- **Phantom manual-off eliminated** — external-change detection now requires the entity's
  last change to be *recent*, so a stale expected/actual mismatch after a quiet period or
  a restart is no longer misread as a user toggle that stuck a device in manual-off.
- **Battery SOC no longer falsely "stale"** — a flat SOC reading (e.g. a full battery
  reporting 100 % unchanged for hours) is trusted as the last known value instead of
  being discarded, which had been fail-safe-blocking SOC-gated device starts exactly when
  the battery was fullest. Genuine sensor loss (HA `unavailable`/`unknown`) is still handled.
- **Command retries are throttled, not hammered** — a device commanded ON that stays OFF
  is re-sent at most once every ~2 minutes (was every cycle) and never permanently given
  up on, so it recovers on its own when it comes back online.
- **Excess no longer flickers on battery noise** — a discharge must persist for several
  ticks before it zeroes the excess, so ±noise around a full battery no longer flaps
  excess and cycles devices.
- **Manual / timed overrides survive a HA restart** (persisted and restored on setup).
- `device_power` sensor now declares the power device-class + measurement state-class
  (correct formatting + long-term statistics).
- **Config UX:** panel spec fields (Vmp/Imp/Voc/Isc/count) no longer pre-fill misleading
  example values — you enter your own datasheet numbers; the Schedule-Helper picker now
  accepts `input_boolean` / `switch` helpers, not only `schedule`.
- Documentation and the example cards were corrected (current device-status list, the
  `reasons` attribute shape, honest labelling of the cautious excess vs the probe budget,
  and a broken conditional-card example).

### Internal
- Split the oversized modules for maintainability: excess-power math moved to
  `sensor/excess_math.py`; battery-SOC gates to `core/battery_gates.py`; on-time
  accounting to `core/device_timing.py` (all re-exported, no API change). Removed dead
  code and a duplicated helper; added an end-to-end config-flow test and fixed a stale
  and a no-op test.
- The journal/audit trail now logs at `DEBUG` (was `INFO`) so a per-cycle diagnostic
  line no longer floods the log at normal levels; it reappears when the integration
  logger is set to `debug`.

## [1.2.0] — 2026-06-29

### Added
- **Selectable excess-calculation method** (Advanced Settings): `mppt` (cautious,
  default), `mppt_probe` (active probing), `export` (energy-balance for grid-export
  inverters). Existing setups are migrated to `mppt`.
- **Active probe controller** (`mppt_probe`) — discovers curtailed solar empirically
  by growing a headroom budget and validating it against the battery, recovering the
  potential the cautious estimate leaves on the table when the battery is full and the
  house load is low. Per-device opt-out via `allow_probe`.
- **PV production forecast sensor** (optional) — surfaces `forecast_potential_w` /
  `forecast_untapped_w`, and when set becomes the probe's battery-validated growth
  target. The published excess stays cautious in every method.
- **Curtailment detection** — `curtailment_detected` diagnostic attribute on the
  excess sensor.
- **Probe battery-assist tolerance** (`probe_battery_assist_w`, default 100 W) — how
  much battery draw a probe-driven load may use before backing off, kept separate from
  the strict base excess discharge guard.
- **Hub device metadata** — model, software version (read from `manifest.json`),
  service entry type and icon.

### Changed
- **Probe trusts the forecast at the start-gate** — under curtailment the MPPT
  back-estimate collapses, so the probe now sizes the start-gate from the forecast
  (when present); a large load such as an air conditioner is no longer gated out by
  the curtailed under-estimate.
- **Probe adopts an already-running load** — a device kept on by manual control (or
  held through a transient excess dip) is floored into the budget instead of being
  dropped and rediscovered.
- **Probe charge handling aligned with battery-sharing SOC** — at/above the sharing
  threshold a charge no longer stands the probe down (solar covers the load and tops
  up the battery); below it the battery keeps absolute priority. Only a discharge ever
  backs the headroom off.
- **Manual-override lockout** shortened from 300 s to 120 s, so a manual toggle (or a
  self-cycling device whose switch flip reads as user-initiated) no longer suppresses
  auto-control for long.
- Probe settle interval between steps lengthened 20 s → 30 s.
- `VERSION` is now read from `manifest.json` at runtime instead of being hardcoded.

## [1.1.1] — 2026-06-25

### Added
- **Battery discharge tolerance** (`battery_discharge_tolerance_w`, default 20 W) —
  small battery oscillations within this band (typical inverter self-draw jitter)
  are treated as neutral instead of forcing excess to 0. Previously *any* discharge
  blocked the excess calculation, so a load covered mostly by solar with a few watts
  of battery dip was wrongly reported as having no surplus. Set to 0 for the old
  strict behaviour; increase if your battery oscillates more.
- **Excess-power write deadband** — the excess sensor now suppresses sub-threshold
  fluctuations (`max(10 W, 1.5% of current_max_power)`), cutting recorder/listener
  churn while always publishing zero-crossings.
- **Battery-sign sanity warning** — logs once if the configured battery power sensor
  only ever reports non-negative values while reversal is off, which indicates a
  magnitude (unsigned) sensor was chosen and would skew the excess calculation.

### Changed
- **Power-percent entity renamed** — the per-device `Power (%)` sensor is now
  `Power Percent`, fixing the duplicate-slug collision that produced confusing
  `_power_2` entity IDs. Existing `*_power_2` entities are migrated automatically to
  `*_power_percent` on the first launch after upgrade.
- **`current_max_power` clamped to nameplate Pmax** with near-Voc back-estimate
  damping, so the estimated maximum can no longer overshoot the physical panel rating.
- Excess sensor state is rounded to 1 decimal (previously surfaced as a long raw
  float, e.g. `159.323368872324 W`).

### Fixed
- **Stale battery SOC** readings (older than 30 min) are now treated as unavailable,
  so SOC-based logic follows its fail-open / fail-safe paths instead of acting on
  stale data.
- **Usable-condition template** is validated when the device form is saved; an
  invalid Jinja template now surfaces a form error instead of failing silently at
  runtime.
- **Orphan per-device entities** are reconciled against the current device list and
  removed from the entity registry on reload.
- Missing device-form translation labels (`actual_power_sensor`,
  `actual_power_threshold_w`, `max_on_time_per_day`, `check_usable_template`,
  `min_on_time`) added in English and Ukrainian.
- Documentation corrected: removed the inaccurate "Parallel Mode auto-activates"
  claim — there is a single MPPT-based calculation that a consumption sensor refines;
  removed dead `is_excess_possible` helper.

## [1.1.0] — 2026-06-18

### Added
- **Per-device actual power sensor** (`actual_power_sensor`) — account a device's
  real draw instead of its declared `min_expected_w`, giving a more accurate
  remaining-power budget for the rest of the devices.
- **`idle` device status** — a relay that is commanded ON but drawing below the
  configurable threshold (`actual_power_threshold_w`, default 10 W) now reports
  `idle` instead of `active` (e.g. a boiler that reached temperature).
- **Battery SOC gating** (`battery_soc_sensor` at hub level, `min_battery_soc`
  per device) — block new device starts until the battery reaches a charge level,
  with sticky hysteresis (`[min, min + 2%]`) and fail-safe behaviour when the
  configured SOC sensor is unavailable.
- **Battery charge priority / SOC-modulated reserve** (`battery_sharing_soc`, %) —
  below this SOC the battery takes absolute charge priority (`reserve_battery_power`
  is effectively set to 0, so no surplus reaches devices). At or above the threshold
  the configured `reserve_battery_power` applies as usual: the battery keeps that
  many watts, the rest goes to devices. Set to 0 (default) to keep the previous
  behaviour. Fail-open: if the SOC sensor is unavailable the threshold is ignored.
- **Turn off on auto-control disable** (`turn_off_on_auto_control_disable`) —
  optionally send a turn-off command when a device's auto-control is switched off.
- **Max on-time per day** (`max_on_time_per_day`, minutes) — cap a device's daily
  runtime; blocks new starts and turns a running device off once the budget is hit.
- **Usable-condition template** (`check_usable_template`) — an arbitrary Jinja
  template that gates device usability beyond the schedule (e.g. tank temperature).
- **Simulation mode** (debug-only) — when the `custom_components.sun_allocator`
  logger is set to `DEBUG`, a hidden **Simulation [DEBUG]** option appears in the
  settings menu. It replaces live PV power/voltage readings with fixed values so
  you can verify allocation logic without sunlight. Consumption, battery power, and
  SOC sensors still read from their real HA entities.

### Changed
- **Shared sensor snapshot cache** — the four hub sensors now build their common
  input snapshot once per source change (event-invalidated), instead of each
  reading and recomputing independently. Scales with MPPT-tracker count.
- **Serialized + coalesced processing** — overlapping allocator triggers are
  serialized through a lock and rapid bursts collapse into a single trailing run
  on the most recent value.
- Boolean config options (temperature compensation, advanced settings, etc.) now
  render as toggle switches; panel count accepts a plain integer.

### Fixed
- Reduced journal log spam (no longer logs every sensor read; HA "logging too
  frequently" warning gone).
- Auto-generated entity IDs are now lowercase — fixes the HA "invalid entity ID"
  warning for ULID-based entry IDs.
- Optional entity selectors (consumption, battery power, battery SOC) pre-fill with
  the saved value when reopening settings.
- Test suite migrated to the `async_setup` config-entry pattern (HA core no longer
  allows forwarding setup from a `NOT_LOADED` entry).

## [1.0.8] — Multi-MPPT

### Added
- **Multi-MPPT (N-MPPT) support** — configure 1–4 independent MPPT trackers, each
  with its own power/voltage sensors and panel parameters. Hub sensors aggregate
  per-tracker readings with per-panel-set temperature compensation.
- Migration that wraps a legacy flat single-MPPT config into the new
  `mppt_inputs[]` list.

## [1.0.5] — Stability & tests

### Changed
- Code optimization, expanded test coverage, documentation updates.

## [1.0.4] — Climate & schedule fixes

### Fixed
- Climate devices: auto-detect `hvac_mode` from supported modes
  (`heat` → `heat_cool` → `auto`); handle non-standard mode lists.
- Schedule save error.

## [1.0.3] — Scheduling & per-device entities

### Added
- Scheduling per device: time-based windows or a Home Assistant helper entity.
- Per-device sensors (allocated power, power percent, device status ENUM).
- Per-device auto-control toggle switch (state restored across restarts).

## [1.0.2] — Devices & localization

### Changed
- Device handling and settings fixes; documentation translated to Ukrainian.

## [1.0.1] — Algorithm & tests

### Changed
- MPPT/allocation algorithm refinements and additional tests.

## [1.0.0] — First public release

### Added
- Solar excess (untapped potential) estimation from PV power/voltage and panel
  datasheet (Vmp/Imp/Voc/Isc) via an MPPT model.
- Estimated current maximum power and usage-percentage hub sensors.
- Priority-based automatic control of devices (switches, lights, climate,
  ESPHome relays), on/off and proportional modes.
- Configurable debounce, hysteresis and minimum on-time.
- Temperature compensation.
- Full configuration through the Home Assistant UI.
