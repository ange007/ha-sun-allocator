[🇬🇧 English](./configuration.md) | [🇺🇦 Українська](./configuration_uk.md)

# Detailed Configuration

SunAllocator is configured through the Home Assistant UI. This document provides a detailed explanation of all the configuration parameters.

After initial setup, you can modify your configuration by going to **Settings → Devices & Services**, finding your **SunAllocator** integration, and clicking the **"CONFIGURE"** button.

This will open a menu with the following options:
- **Settings**: Modify main solar panel and sensor configuration. The flow walks through one page per purpose: **Hub** (MPPT count and shared sensors) → **Battery** → **per-MPPT inputs** → [Temperature Compensation, if enabled] → [Advanced Settings, if enabled].
- **Manage Devices**: Add, edit, or remove devices.
- **Temperature Compensation**: Configure temperature-based adjustments for solar panel output.
- **Advanced Settings**: Fine-tune the algorithm for power calculation and distribution.

> **Migration note (v1.3.0):** existing installs are migrated automatically on first launch after upgrade — the per-device `min_battery_soc` is renamed to `start_battery_soc`, a `stop_battery_soc` of `100` is backfilled, and dead options (`ramp_up_step`, `ramp_down_step`, `ramp_deadband`, `min_excess_power`) are stripped. No manual action required.

---

## Settings

This section covers the primary sensors and the physical characteristics of your solar array. Each page has a single purpose and the flow is: **Hub** → **Battery** → **per-MPPT inputs** → [Temperature Compensation] → [Advanced Settings]. The last two pages appear only when their toggle is enabled on the Hub page.

### Hub-level Sensors

- **Number of MPPT trackers**: How many independent MPPT trackers your inverter exposes. Choose 1 for a single-tracker setup, or 2–4 for dual/multi-MPPT inverters (Deye, Growatt, Goodwe, etc.). Each tracker is configured separately on the per-MPPT step.
- **Consumption Sensor**: (Optional) The sensor that measures your total house power consumption in Watts (W). When provided, it *refines* the excess calculation — the available power is additionally bounded by your real measured consumption, which is more accurate. It is not a separate mode; see [Concepts → Calculate Excess Power](concepts.md#step-1--calculate-excess-power).
- **PV Forecast Sensor (W)**: (Optional) An external solar-production forecast in Watts (e.g. from Forecast.Solar or Open-Meteo Solar Forecast) for the *expected* PV output right now. It is surfaced on the excess sensor as the `forecast_potential_w` and `forecast_untapped_w` (`max(0, forecast − pv_power)`) diagnostic attributes so you can compare the independent forecast against the MPPT estimate. When set, it also becomes the **probe's growth target**: in `mppt_probe` the probe grows toward the forecast (battery-validated) instead of probing blind, and in the plain `mppt` method the forecast enables the same battery-validated growth — but only into the *speculative* budget that devices with **Allow Speculative Surplus** may use, so opt-out devices stay on the plain cautious excess. The published `excess_power` value itself is **never** lifted by the forecast. For a multi-string array (e.g. panels on two roof slopes), combine the per-string forecast entities into a single value with a template helper and select that here. Note: summing per-slope forecasts can over-estimate the real combined output for series-coupled strings with different orientations (mismatch) — the battery validation guards against acting on such an over-estimate.
- **Enable Temperature Compensation**: When on, the flow adds the [Temperature Compensation](#temperature-compensation) page.
- **Enable Advanced Settings**: When on, the flow adds the [Advanced Settings](#advanced-settings) page.

### Battery

A dedicated page groups every battery-related setting in one place.

- **Battery Power Sensor**: (Optional) The sensor that measures your battery power in Watts (W). Used to determine if the battery is charging or discharging.
- **Reverse Battery Power Values**: (Optional) Enable this if your battery power sensor shows a positive value for discharging and a negative value for charging. By default, the integration assumes negative values for discharging and positive for charging.
- **Battery SOC Sensor**: (Optional) The sensor that reports the battery state of charge in percent (%). Required for the per-device **Start Above Battery SOC** / **Stop Below Battery SOC** gates, the global **Battery Protection Floor SOC**, and the **Share Surplus Above SOC** charge-priority feature. If left empty, all SOC-based features are disabled (fail-open).
- **Battery Power Reserve (W)**: A certain amount of power to be reserved and not used by the allocator, so your battery keeps charging with a minimum power. This reserve is the watt-budget modulated by the **Share Surplus Above SOC** threshold below: below the threshold it is effectively unlimited (battery first), at/above it the configured value applies and the rest is shared with devices.
- **Share Surplus Above SOC (%)**: (Optional, `0` = disabled) Battery charge-priority threshold. **Below** this SOC the battery takes absolute charge priority — the **Battery Power Reserve** value is effectively forced to unlimited, so no surplus is released to devices (excess = 0) and the battery charges as fast as possible. **At or above** this SOC the configured **Battery Power Reserve** applies as usual: the battery keeps that many watts and the remaining surplus is shared with your devices. Requires both the **Battery SOC Sensor** and a non-zero **Battery Power Reserve** to share anything. Fail-open: if the SOC sensor is unavailable the threshold is ignored and the plain reserve applies.
- **Battery Protection Floor SOC (%)**: (Optional, `0` = disabled) An absolute hard floor. Below this SOC **every** controlled device is forced off, regardless of whether the battery is charging or discharging. It is also the hard minimum for any **non-zero** per-device **Stop Below Battery SOC** — a non-zero per-device stop can never be set below it (a per-device stop of `0` instead *inherits* this floor).
- **Battery Discharge Tolerance (W)**: (Default `20`) How much battery discharge is tolerated before excess is forced to `0`. Brief battery oscillations within this band (typical inverter self-draw jitter) are treated as neutral, so a device covered mostly by solar is not switched off by minor dips into the battery. Discharge beyond the tolerance still blocks excess. Set to `0` for strict behaviour (any discharge blocks excess); increase (e.g. `50`–`100` W) if your battery oscillates more.
- **Grid Voltage Sensor**: (Optional) A sensor measuring the **grid-side** AC voltage. When set and reading at/above **Grid Present Above Voltage**, a *manually* forced device (manual-on or a timed run) ignores the battery-protection force-off — the grid carries the load, so the inverter's own low-SOC cutoff protects the battery. Auto-control is never affected. Leave empty to disable. **Important:** point this at the utility-input voltage, not the inverter's regulated output (which stays ~230 V even during a blackout, so it would never register the grid as absent).
- **Grid Present Above Voltage (V)**: (Default `200`) The voltage at/above which the grid counts as present for the manual bypass above. Below it (brownout / blackout) the bypass disengages on the next cycle and normal battery protection resumes.

### Per-MPPT Settings

For each MPPT tracker you configure (one form per tracker):

- **PV Power Sensor**: (Required) The sensor that measures power output of this tracker's string in Watts (W).
- **PV Voltage Sensor**: (Required) The sensor that measures voltage of this tracker's string in Volts (V).
- **Solar Panel Specifications** — values from the datasheet of the panels wired to this tracker. Different trackers can have different panels (different model, count, wiring).
  - **Vmp (Voltage at Maximum Power)**: The voltage at which a single panel produces maximum power.
  - **Imp (Current at Maximum Power)**: The current at which a single panel produces maximum power.
  - **Voc (Open Circuit Voltage)**: The maximum voltage a single panel can produce with no load.
  - **Isc (Short Circuit Current)**: The maximum current a single panel can produce in a short-circuit condition.
  - **Panel Count**: The number of panels in this tracker's string.
  - **Panel Configuration**: How the panels are wired together for this tracker.
    - **Series**: Panels connected end-to-end. Voltage = sum, current stays the same.
    - **Parallel**: Panels connected side-by-side. Current = sum, voltage stays the same.
    - **Parallel-Series**: Combination of both.

> **Migration note (v1.0.8):** existing single-MPPT installations are migrated automatically — your previous flat configuration becomes a single-element `mppt_inputs` list on the first launch after upgrade. No manual action required.

> **Limitation:** the temperature sensor and temperature coefficients are shared across all trackers. If your strings face different directions (east vs west), the same temperature compensation is applied to both. Per-tracker temperature is on the roadmap.

---

## Manage Devices

In this section, you can add, edit, or remove the devices (loads) that you want to control with your excess solar power.

### Name and Entity

The first step captures the device name and the entity to control.

- **Device Name**: A friendly name for the device.
- **Device Entity**: The Home Assistant entity that represents your device. The **control mode is chosen through the entity picker itself** — there is no separate device-type selector. Each option is labelled `icon Device — Entity (Mode)`, where the device name comes from the device registry and the entity name from the entity registry.
  - **Dimmable lights and ESPHome relays appear twice** in the dropdown: `... (Switch)` for simple on/off control and `... (Dimmer)` for proportional control. Pick the one that matches how you want the device driven.
  - On/off-only entities (`switch`, `input_boolean`, `automation`, `script`, and non-dimmable lights) appear **once**.
  - `climate` entities (thermostat, heat pump) show each available HVAC mode as a separate option (e.g., "Thermostat — heat", "Thermostat — cool"); pick the desired mode and the integration stores it automatically.
  - Your choice is stored as the per-device `control_mode` (`on_off` or `proportional`). **ESPHome relays** (a `light` plus a paired `select` that offers a "Proportional" option on the same device) are auto-detected: their mode-select entity is discovered and stored for you, so there is no manual "ESPHome mode select" field.

Supported entity behaviour:
- `switch`, `input_boolean` — controlled via `turn_on` / `turn_off`
- `light` — proportional (Dimmer) adjusts brightness as a percentage of available power; on/off (Switch) uses `turn_on` at full brightness / `turn_off`
- `climate` — controlled via `set_hvac_mode` (selected mode to turn on, `off` to turn off)
- `automation`, `script` — triggered via `turn_on` / `turn_off`

Per-device configuration is then split into two steps: **Basic Device Settings** and **Advanced Device Settings**.

### Basic Device Settings

The everyday knobs.

- **Enable Auto Control**: Enable or disable automatic control for this device.
- **Turn Off When Auto Control Disabled**: (Optional) When enabled, flipping this device's auto-control switch off (or disabling auto-control in config) sends an explicit turn-off command. When disabled, the device is simply left in its current state.
- **Device Priority**: A number from 1 to 100 that determines the order in which devices are turned on. Devices with higher priority are turned on first.
- **Minimum Expected Load (W)**: (Required) The minimum power in Watts the device consumes when it's on. This is used to determine if the device is actually running.
- **Maximum Expected Load (W)**: (Proportional devices only) The maximum power in Watts the device consumes at 100% load. This is required for proportional control.
- **Schedule Mode**: Selects how the device's allowed control window is determined (see [Schedule Settings](#schedule-settings)).

### Advanced Device Settings

Fine-tuning: timing, speculative surplus, per-device battery SOC gates, actual-power feedback, and usability.

- **Debounce Time (s)**: The time in seconds the system will wait before turning a device on or off. This prevents the device from rapidly switching on and off.
- **Minimum On-Time (s)**: The minimum time in seconds that the device must remain on before it can be turned off. This is useful for appliances like compressors or pumps that should not be cycled on and off rapidly.
- **Allow Speculative Surplus (probe or forecast headroom)**: (Default on) Whether this device may consume the *speculative* budget discovered by active probing or by the PV-forecast headroom. It applies both in the `mppt_probe` method **and** in the plain `mppt` method when a PV Forecast Sensor is configured. Turn it **off** for self-modulating loads the integration can only switch on/off (e.g. an inverter AC compressor) so they run only on genuine cautious excess and are never cycled by the probe.
- **Start Above Battery SOC (%)**: (Charge-side START gate, `0` = off) The device may start only when the battery SOC is **at or above** this level. Sticky hysteresis is applied over the range `[start, start + 2%]` so the device does not rapidly cycle around the threshold. Only *new* starts are gated — a device already running is never turned off by this gate. Note: a value below the global **Share Surplus Above SOC** is a no-op, because no surplus exists below the sharing threshold (this hint is shown on the step). Failure behaviour depends on *why* SOC is missing:
  - **No Battery SOC Sensor configured at all** → **fail-open**: the gate is ignored and the device may start. A per-device minimum is meaningless without a sensor, so a forgotten config never permanently blocks a device.
  - **Sensor configured but currently unavailable** → **fail-safe**: the start is blocked (and stays sticky until the sensor returns and SOC climbs back above the recovery threshold). The charge cannot be verified, so the battery is protected.
- **Stop Below Battery SOC (%)**: (Discharge-side STOP floor, default `100`) While the battery is **discharging**, a running device is forced off when SOC drops **below** this level.
  - **`100`** (default) means "never discharge the battery for this device".
  - **`0`** means "inherit the global **Battery Protection Floor SOC**" — no extra per-device rule is applied, so the device may discharge the battery down to the global protection floor. `0` stays `0` on the form (it is not rewritten to the floor).
  - Any **non-zero** value must be **≥** the global **Battery Protection Floor SOC**; a non-zero value below the floor is **rejected with an error on save** (it is *not* clamped or raised to the floor). Lower a non-zero value to allow deeper discharge for this load.
- **Actual Power Sensor**: (Optional) A sensor reporting the device's real power draw in Watts. When set, the allocator subtracts the device's *actual* consumption from the remaining power budget instead of its declared **Minimum Expected Load (W)**, giving a more accurate budget for the rest of the devices.
- **Active Power Threshold (W)**: (Default 10 W) Used together with the **Actual Power Sensor**. A device commanded ON but drawing **below** this threshold reports the `idle` status instead of `active` (e.g. a boiler that has reached temperature and stopped drawing power).
- **Max On Time Per Day (min)**: (Optional, `0` = unlimited) Caps the device's total runtime per calendar day. Once the budget is reached the device is turned off and blocked from starting again until the next day.
- **Usable Condition Template**: (Optional) An arbitrary Jinja2 template evaluated to gate device usability beyond the schedule — e.g. `{{ states('sensor.tank_temp') | float < 60 }}` to only run a heater while the tank is below 60 °C. The device is considered usable only when the template renders to a truthy value (`true`, `on`, `1`, etc.).

### Schedule Settings
The **Schedule Mode** field selects how the device's allowed control window is determined:
- **Disabled** — the device may be controlled at any time (default).
- **Standard** — a built-in time window with day-of-week selection.
- **Helper** — gate control on the state of an existing Home Assistant boolean entity (e.g. an `input_boolean`, a `schedule` helper, or any entity whose `on` / `off` state you control elsewhere).

When **Standard** is selected:
- **Start Time** / **End Time**: time window during which the device may be controlled. Overnight windows (end < start) are supported.
- **Days of the Week**: at least one day must be ticked, otherwise the device is treated as outside the schedule.

When **Helper** is selected:
- **Helper Entity**: pick any entity whose state is `on` / `off`. Auto-control is paused whenever the helper is `off`.

Note: the schedule defines *when auto-control is allowed*, while the per-device **Auto-Control switch** entity (`switch.sun_allocator_<device>_auto_control`) is the runtime kill-switch you can flip from automations or dashboards. Both must allow control for the device to be driven.

### Per-device entities

Once a device is added, the integration creates the following entities for it:

| Entity | Purpose |
|---|---|
| `sensor.sun_allocator_<device>_power` | Allocated power in W. |
| `sensor.sun_allocator_<device>_power_percent` | Proportional duty %. |
| `sensor.sun_allocator_<device>_device_status` | ENUM status (`active`, `idle`, `insufficient_power`, `debouncing_on`/`off`, `auto_control_off`, `manual_override`, `manual_active`, `manual_timer`, `filtered`, `trying_on`/`off`, `unreachable`). `idle` = commanded ON but drawing below the **Active Power Threshold**; `unreachable` = commanded ON but the entity never confirmed after repeated throttled retries; `manual_timer` = running under a timed run. |
| `sensor.sun_allocator_<device>_run_time_today` | Accumulated on-time today (minutes). Resets at local midnight; survives restarts. |
| `sensor.sun_allocator_<device>_time_until_off` | Minutes left on an active timed run, else `0`. |
| `switch.sun_allocator_<device>_auto_control` | Runtime auto-control toggle. State persists across restarts. |
| `switch.sun_allocator_<device>_switch` | **"Switch"** — a convenience proxy that toggles the device's controlled entity on/off straight from the SunAllocator card and mirrors its live on/off state. While auto-control is on, flipping it is registered as a sticky manual toggle (`manual_active`), exactly like toggling the underlying entity. Turning it OFF while a manual/timed override is active *releases* the override back to auto; turning it OFF with no override sets a sticky manual-off. Only created for devices that control an entity. |
| `number.sun_allocator_<device>_run_timer_min` | **"Run Timer (min)"** — enter minutes to force the device ON for exactly that long, ignoring the battery limits and schedule. Resets to `0` when the timer ends (device then returns to auto). Only created for devices that control an entity. |

Unique IDs follow the pattern `<entry_id>_<device_id>_<suffix>` and are stable across reloads.
When a device is removed, its entities are cleaned up from the entity registry on the next
reload (the integration reconciles entities against the current device list).

---

## Temperature Compensation

This feature allows the integration to adjust the solar panel's maximum power point (MPP) based on the ambient temperature, as the panel's efficiency is affected by it.

- **Temperature Sensor**: The sensor that measures the ambient temperature in Celsius (°C).
- **Voc Temp Coefficient (%/°C)**: The temperature coefficient of the open-circuit voltage (Voc), found on the panel's datasheet. It's usually a negative percentage.
- **Pmax Temp Coefficient (%/°C)**: The temperature coefficient of the maximum power (Pmax), also found on the panel's datasheet. It's also typically a negative percentage.

---

## Advanced Settings

This page appears only when **Enable Advanced Settings** is ticked on the Hub page. It lets you fine-tune the behavior of the power allocation algorithm. (Battery-related knobs — reserve, sharing/protection SOC, discharge tolerance — live on the [Battery](#battery) page.)

- **Excess Calculation Method**: Selects how available surplus is estimated, to match your inverter topology. See [Concepts → Calculation Method](concepts.md#calculation-method-mppt--mppt_probe--export).
  - **MPPT (cautious)** *(default)*: Untapped-headroom estimate from the panel I-V model. Safe and conservative; works without a consumption sensor. On a hybrid inverter that curtails the panels when the battery is full and load is low, it *underestimates* the real surplus (the `curtailment_detected` attribute on the excess sensor flags this). When a PV Forecast Sensor is configured, forecast-guided headroom growth is offered to devices that **Allow Speculative Surplus**.
  - **MPPT + probe**: Same published excess as MPPT, plus active probing that recovers curtailed energy. When curtailment is detected and a device is waiting only for more power, it gently raises load and keeps it if the battery stays out of discharge (free, curtailed PV); otherwise it backs off and waits out a cooldown (so an on/off load such as an AC compressor is not cycled). Only devices that **Allow Speculative Surplus** may consume the probed budget. Best for islanded / full-battery setups where MPPT underestimates. Detects "battery at its limit" from charge *power* near zero, not SOC, so it works even if your inverter caps charging below 100%.
  - **Export (energy balance)**: `excess = pv − consumption − inverter self-consumption − reserved battery charge`. For grid-export inverters where PV output reflects true generation. Needs a consumption sensor to be meaningful.
- **Inverter Self-Consumption (W)**: The amount of power the inverter itself consumes for its operation. This value is subtracted from the available solar power, providing a more accurate calculation of the real excess power. You can find this value in your inverter's datasheet or measure it.
- **Device Allocation Strategy**: Defines how power is allocated to multiple proportional devices.
  - **Fill one by one**: The highest priority device is allocated as much power as it needs, then the next device gets power from what is left, and so on.
  - **Distribute evenly**: The available power is distributed among all active proportional devices based on their `Maximum Expected Load (W)`.
- **Minimum Inverter Voltage (V)**: The minimum voltage required for the inverter to operate.
- **Hysteresis (W)**: A power buffer to prevent devices from turning on and off too frequently. A device will turn on at its configured minimum power and turn off at `Minimum Power - Hysteresis`.
- **Probe Battery Assist (W)**: How much brief battery draw the probe may treat as "still free" while growing headroom, absorbing short charge dips so a probe step is not abandoned on transient battery jitter.
- **Daily Reset Time**: (Default `06:00`) The local time of day at which per-day states roll over — sticky manual overrides and the on-time / `max_on_time_per_day` accumulators reset on this "logical day" boundary instead of calendar midnight. A manual choice made late in the evening therefore survives past midnight and only clears in the morning. Set to `00:00` for the classic midnight reset. The rollover is evaluated lazily each cycle, so a boundary crossed while Home Assistant was down still resets on the first cycle after it restarts.

---

## Simulation Mode (debug)

A hidden **Simulation [DEBUG]** entry appears in the configuration menu **only when debug logging is enabled** for the integration. Add the following to your `configuration.yaml` and restart to reveal it:

```yaml
logger:
  logs:
    custom_components.sun_allocator: debug
```

Simulation lets you verify the allocation logic without sunlight or real hardware by substituting fixed values for the live sensors:

- **Enable Simulation**: Master switch. While on, the PV power/voltage readings are always replaced with the simulated values below.
- **Simulated PV Power (W)** / **Simulated PV Voltage (V)**: The synthetic panel readings (total PV power is split evenly across all configured MPPT trackers).
- **Override Consumption Sensor** + **Simulated House Consumption (W)**: When the override toggle is on, the consumption value is forced to the simulated number; when off, the real consumption sensor is read as usual.
- **Override Battery Power Sensor** + **Simulated Battery Power (W)**: Same pattern for battery power (negative = discharging).
- **Override Battery SOC Sensor** + **Simulated Battery SOC (%)**: Same pattern for SOC — useful for exercising the **Share Surplus Above SOC**, the **Battery Protection Floor SOC**, and the per-device **Start Above / Stop Below Battery SOC** features.

Each override toggle is independent: leave a toggle off to keep reading the corresponding real sensor while simulating the rest. Turn **Enable Simulation** off (or raise the log level back above debug) to return to normal operation.