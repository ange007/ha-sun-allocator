# Changelog

All notable changes to **SunAllocator** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/).
Versions before `1.1.0` are reconstructed from commit history, so their grouping
is approximate. This project tracks its version in
`custom_components/sun_allocator/manifest.json` (used by HACS) and, from
`1.1.0` onward, in matching `vX.Y.Z` git release tags.

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
