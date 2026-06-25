[🇬🇧 English](./configuration.md) | [🇺🇦 Українська](./configuration_uk.md)

# Detailed Configuration

SunAllocator is configured through the Home Assistant UI. This document provides a detailed explanation of all the configuration parameters.

After initial setup, you can modify your configuration by going to **Settings → Devices & Services**, finding your **SunAllocator** integration, and clicking the **"CONFIGURE"** button.

This will open a menu with the following options:
- **Settings**: Modify main solar panel and battery configuration.
- **Manage Devices**: Add, edit, or remove devices.
- **Temperature Compensation**: Configure temperature-based adjustments for solar panel output.
- **Advanced Settings**: Fine-tune the algorithm for power calculation and distribution.

---

## Settings

This section covers the primary sensors and the physical characteristics of your solar array.

### Hub-level Sensors

- **Number of MPPT trackers**: How many independent MPPT trackers your inverter exposes. Choose 1 for a single-tracker setup, or 2–4 for dual/multi-MPPT inverters (Deye, Growatt, Goodwe, etc.). Each tracker is configured separately on the next step.
- **Consumption Sensor**: (Optional) The sensor that measures your total house power consumption in Watts (W). When provided, it *refines* the excess calculation — the available power is additionally bounded by your real measured consumption, which is more accurate. It is not a separate mode; see [Concepts → Calculate Excess Power](concepts.md#step-1--calculate-excess-power).
- **Battery Power Sensor**: (Optional) The sensor that measures your battery power in Watts (W). Used to determine if the battery is charging or discharging.
- **Is Battery Power Reversed?**: (Optional) Enable this if your battery power sensor shows a positive value for discharging and a negative value for charging. By default, the integration assumes negative values for discharging and positive for charging.
- **Battery SOC Sensor**: (Optional) The sensor that reports the battery state of charge in percent (%). Required for the per-device **Minimum Battery SOC** gate and for the **Share Surplus Above SOC** charge-priority feature below. If left empty, both SOC-based features are disabled (fail-open).
- **Share Surplus Above SOC (%)**: (Optional, `0` = disabled) Battery charge-priority threshold. **Below** this SOC the battery takes absolute charge priority — the **Reserve Battery Power** value (see Advanced Settings) is effectively forced to unlimited, so no surplus is released to devices and the battery charges as fast as possible. **At or above** this SOC the configured **Reserve Battery Power** applies as usual: the battery keeps that many watts and the remaining surplus is shared with your devices. Requires both the **Battery SOC Sensor** and a non-zero **Reserve Battery Power** to share anything. Fail-open: if the SOC sensor is unavailable the threshold is ignored and the plain reserve applies.

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

### Device Settings
- **Device Name**: A friendly name for the device.
- **Device Type**:
  - **Standard**: A simple on/off device. Supported entity domains:
    - `switch`, `input_boolean` — controlled via `turn_on` / `turn_off`
    - `light` — controlled via `turn_on` (at full brightness) / `turn_off`
    - `climate` (thermostat, heat pump) — controlled via `set_hvac_mode`. When selecting the device entity, the dropdown shows each available HVAC mode as a separate option (e.g., "Thermostat — heat", "Thermostat — cool"). Simply pick the desired mode — the integration stores it automatically.
    - `automation`, `script` — triggered via `turn_on` / `turn_off`
  - **Custom (ESPHome)**: A device with proportional power support. How it works depends on the entity type:
    - `light` — true proportional control: brightness is adjusted as a percentage of available power
    - `switch`, `input_boolean`, `automation`, `script` — on/off only; the integration tracks the power allocation internally but the device itself receives only on or off commands
    - `climate` — same as Standard: pick the desired HVAC mode from the entity dropdown. The integration calls `set_hvac_mode` with the selected mode to turn on and `set_hvac_mode` with `off` to turn off.
- **Device Entity**: The Home Assistant entity that represents your device.
- **Min Expected (W)**: (Required) The minimum power in Watts the device consumes when it's on. This is used to determine if the device is actually running.
- **Max Expected (W)**: (Required for Custom devices) The maximum power in Watts the device consumes at 100% load. This is used for proportional control.
- **Min Excess Power (W)**: (Optional) The minimum amount of excess solar power that must be available before this device is considered for activation.
- **Priority**: A number from 1 to 100 that determines the order in which devices are turned on. Devices with higher priority are turned on first.
- **Debounce Time (s)**: The time in seconds the system will wait before turning a device on or off. This prevents the device from rapidly switching on and off.
- **Min On-Time (s)**: The minimum time in seconds that the device must remain on before it can be turned off. This is useful for appliances like compressors or pumps that should not be cycled on and off rapidly. When a device is turned on, a **startup grace period** is also applied (configurable in Advanced Settings), during which the device will not be turned off even if solar power drops below the threshold.
- **Max On Time Per Day (min)**: (Optional, `0` = unlimited) Caps the device's total runtime per calendar day. Once the budget is reached the device is turned off and blocked from starting again until the next day.
- **Auto-Control**: Enable or disable automatic control for this device.
- **Turn Off When Auto-Control Disabled**: (Optional) When enabled, flipping this device's auto-control switch off (or disabling auto-control in config) sends an explicit turn-off command. When disabled, the device is simply left in its current state.
- **Enable Schedule**: Enable or disable a schedule for this device.

#### Device gating (optional)

These optional fields add extra conditions that must be satisfied before a device is allowed to start. They stack independently — every configured gate must pass.

- **Minimum Battery SOC (%)**: Block new starts for this device until the battery reaches this charge level. Sticky hysteresis is applied over the range `[min, min + 2%]` so the device does not rapidly cycle around the threshold. Only *new* starts are gated — a device already running is never turned off by this gate. Failure behaviour depends on *why* SOC is missing:
  - **No hub Battery SOC Sensor configured at all** → **fail-open**: the gate is ignored and the device may start. A per-device minimum is meaningless without a sensor, so a forgotten hub config never permanently blocks a device.
  - **Sensor configured but currently unavailable** → **fail-safe**: the start is blocked (and stays sticky until the sensor returns and SOC climbs back above the recovery threshold). The charge cannot be verified, so the battery is protected. This is the opposite of the hub-level sharing feature, because here the gate exists to protect the battery.
- **Usable Condition Template**: (Optional) An arbitrary Jinja2 template evaluated to gate device usability beyond the schedule — e.g. `{{ states('sensor.tank_temp') | float < 60 }}` to only run a heater while the tank is below 60 °C. The device is considered usable only when the template renders to a truthy value (`true`, `on`, `1`, etc.).

#### Actual power feedback (optional)

- **Actual Power Sensor**: (Optional) A sensor reporting the device's real power draw in Watts. When set, the allocator subtracts the device's *actual* consumption from the remaining power budget instead of its declared **Min Expected (W)**, giving a more accurate budget for the rest of the devices.
- **Active Power Threshold (W)**: (Default 10 W) Used together with the **Actual Power Sensor**. A device commanded ON but drawing **below** this threshold reports the `idle` status instead of `active` (e.g. a boiler that has reached temperature and stopped drawing power).

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
| `sensor.sun_allocator_<device>_device_status` | ENUM status (`active`, `idle`, `insufficient_power`, `debouncing_on`/`off`, `auto_control_off`, `manual_override`, `filtered`, `trying_on`/`off`, `failed_on`). `idle` = commanded ON but drawing below the **Active Power Threshold**. |
| `switch.sun_allocator_<device>_auto_control` | Runtime auto-control toggle. State persists across restarts. |

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

This section allows you to fine-tune the behavior of the power allocation algorithm.

- **Reserve Battery Power (W)**: A certain amount of power to be reserved and not used by the allocator. This is useful if you want to ensure your battery is charging with a minimum power. This reserve is the watt-budget modulated by the hub-level **Share Surplus Above SOC** threshold: below the threshold it is effectively unlimited (battery first), at/above it the configured value applies and the rest is shared with devices.
- **Inverter Self-Consumption (W)**: The amount of power the inverter itself consumes for its operation. This value is subtracted from the available solar power, providing a more accurate calculation of the real excess power. You can find this value in your inverter's datasheet or measure it.
- **Proportional Allocation Strategy**: Defines how power is allocated to multiple proportional devices.
  - **Fill one by one**: The highest priority device is allocated as much power as it needs, then the next device gets power from what is left, and so on.
  - **Distribute evenly**: The available power is distributed among all active proportional devices based on their `Max Expected (W)`.
- **Min Inverter Voltage**: The minimum voltage required for the inverter to operate.
- **Ramp Up Step (%)**: The percentage by which the power is increased for proportional devices in each step.
- **Ramp Down Step (%)**: The percentage by which the power is decreased for proportional devices in each step.
- **Ramp Deadband (%)**: A small range around the target power where no changes are made, to prevent oscillations.
- **Hysteresis (W)**: A power buffer to prevent devices from turning on and off too frequently. A device will turn on at its configured minimum power and turn off at `Minimum Power - Hysteresis`.
- **Battery Discharge Tolerance (W)**: (Default `20`) How much battery discharge is tolerated before excess is forced to `0`. Brief battery oscillations within this band (typical inverter self-draw jitter) are treated as neutral, so a device covered mostly by solar is not switched off by minor dips into the battery. Discharge beyond the tolerance still blocks excess. Set to `0` for strict behaviour (any discharge blocks excess); increase (e.g. `50`–`100` W) if your battery oscillates more.
- **Startup Grace Period (s)**: The time in seconds after a device is first turned on during which it will not be turned off, even if solar power drops below the threshold. This gives devices time to ramp up to their operating power before the allocator can decide to turn them off.

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
- **Override Battery SOC Sensor** + **Simulated Battery SOC (%)**: Same pattern for SOC — useful for exercising the **Share Surplus Above SOC** and per-device **Minimum Battery SOC** features.

Each override toggle is independent: leave a toggle off to keep reading the corresponding real sensor while simulating the rest. Turn **Enable Simulation** off (or raise the log level back above debug) to return to normal operation.