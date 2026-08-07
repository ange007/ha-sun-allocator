# Changelog

All notable changes to **SunAllocator** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/).
Versions before `1.1.0` are reconstructed from commit history, so their grouping
is approximate. This project tracks its version in
`custom_components/sun_allocator/manifest.json` (used by HACS) and, from
`1.1.0` onward, in matching `vX.Y.Z` git release tags.

## [1.3.1] — 2026-08-03

### Added
- **Grid-availability manual bypass** — an optional grid-voltage sensor on the **Battery**
  page. When it reads at/above the threshold (default `200 V`), a manually-forced device
  ignores the battery-protection force-off: the grid carries the load, so the inverter's
  own low-SOC cutoff protects the battery. Auto-control is unaffected; leave the sensor
  empty to disable.
- **Configurable daily reset time** (Advanced Settings, time picker, default `06:00`) —
  the sticky manual overrides and the on-time / `max_on_time_per_day` accumulators now roll
  over on this "logical day" boundary instead of calendar midnight, so a manual choice made
  late in the evening survives past midnight and only clears in the morning. Set to `00:00`
  for the old midnight behaviour.

### Fixed
- **Watchdog no longer forces everything OFF at night** — the fail-safe that turns every
  device off when the excess-power sensor goes stale now re-derives liveness from the
  sensor's actual state. A live reading that merely holds steady (0 W all night with the PV
  dark, or a deadbanded flat value) is no longer mistaken for a dead sensor, so it stops
  force-clearing manual overrides and cutting a manually-run load every few minutes after
  dark. Only a genuinely `unavailable`/`unknown` sensor (real inverter/integration loss)
  still trips the fail-safe.
- **Devices no longer flap on brief connection drops** — a controlled entity that
  momentarily reads `unavailable` (WiFi/Modbus hiccup) no longer wipes its state or manual
  override. The last known state is held through outages shorter than 120 s, so the relay
  stops turning off/on around comms glitches. A manual force-on now genuinely survives a
  restart, which a startup blip used to clear.
- **Run-time survives a restart during a continuous run** — the in-progress on-time
  session is persisted, so a device running unbroken across a HA restart keeps its
  accumulated run-time instead of resetting to zero.

## [1.3.0] — 2026-07-19

### Added
- **Timed run** — a per-device **"Run Timer (min)"**: force a device ON for N minutes,
  ignoring the battery limits and the schedule; it resets to `0` and releases back to
  auto when the timer ends. Companion sensors **"Run Time (today)"** and **"Time Until
  Off"**; distinct `manual_timer` status.
- **Per-device "Switch"** — a card toggle that drives the controlled entity; turning it
  off releases an active override to auto, or sets a sticky manual-off.
- **Sticky manual control** (`manual_active`) — a manual toggle holds for the rest of the
  local day (cleared on daily rollover, auto-control re-toggle, or battery protection) and
  overrides the schedule + usable-condition template; only battery-SOC protection can
  force a manual-ON device off.
- **Asymmetric per-device battery-SOC thresholds** — `start_battery_soc` (charge-side
  start gate; renamed from `min_battery_soc`, auto-migrated) and `stop_battery_soc`
  (discharge-side stop floor; default `100` = never discharge the battery for that device).
- **Global battery-protection floor** (`battery_protection_soc`) — an absolute SOC floor:
  below it every device is forced off, and the hard minimum any per-device stop floor may take.
- **Per-device "Allow Speculative Surplus"** (`allow_probe`) — gates whether a device may
  use probe/forecast headroom or only genuine (cautious) excess.
- **Dedicated Battery settings page.**
- **`unreachable` device status** — a device commanded ON that never confirms after
  throttled retries (suppressed for climate, whose reported OFF is usually a satisfied
  thermostat).

### Changed
- **Control mode is chosen from the entity picker** — dimmable lights and ESPHome relays
  appear as **(Switch)** and **(Dimmer)**; the old device-type selector is gone and
  existing devices are auto-migrated to a per-device `control_mode`.
- **Probe recovers curtailed solar in more setups** — the active probe now runs with
  `calculation_method = mppt_probe` **or** with plain `mppt` plus a PV forecast sensor;
  each device's `allow_probe` gates use of the headroom.
- **Per-device configuration split into Basic + Advanced steps.**

### Removed
- Dead options `ramp_up_step` / `ramp_down_step` / `ramp_deadband` / `min_excess_power`,
  and the legacy `device_type` shim (superseded by `control_mode`). Existing installs are
  migrated automatically on first launch after upgrade.

### Fixed
- **No phantom manual-off** — a stale expected/actual mismatch after a quiet period or a
  restart is no longer misread as a user toggle that sticks a device in manual-off.
- **On-time accounting is consistent across every off-path** (schedule/usable filter,
  discharge stop-floor) — previously that time was silently dropped, under-counting the
  run-time sensor and the `max_on_time_per_day` budget.
- **No phantom session / grace churn on a vetoed start** — the session and startup-grace
  deadline are recorded only after every gate confirms the start survives.
- **Battery SOC no longer falsely "stale"** — a flat reading (e.g. a full battery at 100 %
  for hours) is trusted as the last known value; genuine `unavailable`/`unknown` is still handled.
- **Command retries are throttled** (~once every 2 minutes, not every cycle) and never
  permanently abandoned, so a device recovers on its own when it comes back online.
- **Excess no longer flickers on battery noise** — a discharge must persist for several
  ticks before it zeroes the excess.
- **Manual / timed overrides persist across a HA restart.**
- `device_power` sensor now declares the power device-class + measurement state-class
  (correct formatting + long-term statistics).
- **Config UX:** panel spec fields (Vmp/Imp/Voc/Isc/count) no longer pre-fill misleading
  example values; the Schedule-Helper picker now accepts `input_boolean` / `switch` helpers.
- Documentation and the example cards were corrected.

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
