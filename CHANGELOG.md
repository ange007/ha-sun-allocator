# Changelog

All notable changes to this project will be documented in this file.

## 1.1.1 - 2026-05-23

### Changed

- Entity control, auto-control shutdown, and watchdog `off` paths now dispatch non-blocking Home Assistant service calls to avoid synchronous wait chains during allocator updates.
- Advanced settings documentation and options-flow labels now consistently use the current Device Allocation Strategy naming.

### Fixed

- Prevented recursive `sensor.sun_allocator_power_distribution` state writes by deferring and coalescing dispatcher-driven updates onto the next loop tick.
- Prevented overdue debounce reruns from re-entering allocator processing in the same event-loop stack.
- Restored missing English and Ukrainian advanced-settings translations for inverter self-consumption and device allocation strategy.
- Fixed options-flow device removal so deleted devices are reloaded out of the integration before being removed from the Home Assistant device registry, avoiding double-remove errors on current HA releases.
- Updated device integration tests to match non-blocking service dispatch and the current MPPT excess-power model.

## 1.1.0 - 2026-05-10

### Added

- Optional dual-MPPT aggregation with PV2 power, voltage, and current inputs plus per-MPPT panel overrides.
- Optional per-device actual-power and active-feedback inputs for standard loads.
- Optional per-device minimum battery SOC gating and immediate turn-off when auto-control is disabled.
- Shared sensor calculation caching and richer runtime diagnostics, including the new `idle` device status.

### Changed

- `sensor.sun_allocator_excess_power` now represents total available solar headroom when a consumption sensor is configured, not only untapped power above Vmp.
- Auto-control processing now serializes overlapping reruns, supports partial recompute from device and battery updates, and refreshes watchdog freshness only from confirmed excess-sensor updates.
- Current/max/usage sensor calculations now aggregate independent MPPT inputs and expose richer MPPT metadata.

### Fixed

- Modernized Home Assistant config-entry tests to use the HA config-entry manager instead of direct integration entry-point calls.
- Stabilized minimum-on-time and runtime coverage on current Home Assistant releases.
- Synchronized English and Ukrainian documentation with the current runtime behavior.