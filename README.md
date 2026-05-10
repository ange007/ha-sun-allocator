[🇬🇧 English](./README.md) | [🇺🇦 Українська](./README_UK.md)

# SunAllocator Home Assistant Custom Component

[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![GitHub release](https://img.shields.io/github/v/release/ange007/ha-sun-allocator)](https://github.com/ange007/ha-sun-allocator/releases)
[![License](https://img.shields.io/github/license/ange007/ha-sun-allocator)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/ange007/ha-sun-allocator/pythonpackage.yaml?branch=main)](https://github.com/ange007/ha-sun-allocator/actions)

![logo](./images/logo.png)

**SunAllocator** is a Home Assistant custom component that helps you maximize the use of your solar energy. It calculates potential excess power from your solar panels and automatically distributes it to your devices, such as water heaters or EV chargers, turning your home into a "solar vampire" that consumes all available free energy.

## Features

- Calculates available excess solar power and panel usage percentage.
- Estimates maximum possible power at the current voltage based on MPPT principles, including optional dual-MPPT aggregation.
- Automatic, priority-based control of multiple loads (switches, lights, climate entities, ESPHome relays).
- Supports both on/off and proportional (dimmer-style) device control.
- Configurable debounce, hysteresis, and minimum on-time to protect appliances from rapid cycling.
- Optional per-device actual-power or active-feedback inputs keep standard loads accounted correctly even when enabled but idle.
- Optional per-device minimum battery SOC thresholds block new starts for selected loads.
- Temperature compensation for accurate panel output estimation.
- Scheduling support: time-based windows or a Home Assistant helper entity (e.g. `input_boolean`, schedule helper).
- Climate devices: auto-detects `hvac_mode` from the entity's supported modes (`heat` → `heat_cool` → `auto`).
- Startup grace period prevents devices from being turned off immediately after they start.
- **Per-device entities** for easy automation and dashboarding (see below).
- **Auto-control toggle switch** per device — flip auto-control on/off at runtime without reconfiguring.
- **Easy configuration through Home Assistant UI** - no YAML editing required.

## Installation

1.  If you don't have it already, install [HACS](https://hacs.xyz/).
2.  Go to HACS > Integrations > and use the custom repository feature to add this repository.
3.  Search for "SunAllocator" and install it.
4.  Restart Home Assistant.
5.  Go to **Settings → Devices & Services**.
6.  Click **"+ ADD INTEGRATION"**.
7.  Search for **"SunAllocator"** and select it.
8.  Follow the configuration wizard to set up your solar panels and devices.

Alternatively, you can manually copy the `custom_components/sun_allocator` folder to your Home Assistant `config/custom_components` directory.

## Basic Configuration

SunAllocator is configured entirely through the UI. The setup wizard will guide you through these main steps:

1.  **Solar Panel Setup**: Provide your solar panel's power and voltage sensors, along with specifications from the panel's datasheet (Vmp, Imp, etc.).
2.  **Device Setup**: Add the switches, lights, or ESPHome relays you want to control with excess solar power. You can set priorities for each device.

For a detailed guide on all configuration options, please see the [**Detailed Configuration documentation**](./docs/configuration.md).

## Usage

### Hub-level sensors

The integration creates several sensors to monitor your solar array:

-   `sensor.sun_allocator_excess_power`: The currently available solar headroom. In MPPT-only mode this is mainly untapped panel potential; with a consumption sensor it also reflects PV power that is already being produced but is not needed by the current loads.
-   `sensor.sun_allocator_current_max_power`: The estimated maximum power your panels could produce at the current voltage. When PV1/PV2 are configured, this aggregates both MPPT inputs.
-   `sensor.sun_allocator_usage_percent`: The current power usage as a percentage of the maximum possible power.
-   `sensor.sun_allocator_power_distribution`: The total power currently allocated to all your controlled devices, plus per-device diagnostic attributes (`allocation_w`, `allocation_percent`, `device_meta`, `reasons`).

### Per-device entities

For every configured device the integration also creates:

-   `sensor.sun_allocator_<device_name>_power` — current allocated power in W.
-   `sensor.sun_allocator_<device_name>_power_percent` — proportional duty as %.
-   `sensor.sun_allocator_<device_name>_device_status` — ENUM sensor with one of: `active`, `idle`, `insufficient_power`, `debouncing_on`, `debouncing_off`, `auto_control_off`, `manual_override`, `filtered`, `trying_on`, `trying_off`, `failed_on`.
-   `switch.sun_allocator_<device_name>_auto_control` — runtime toggle for that device's auto-control. State persists across Home Assistant restarts (`RestoreEntity` + config sync). Turning it off immediately stops auto-control without removing the device from the config, and can optionally send an immediate `off` command to the underlying entity.

When `Actual Power Sensor`, `Active Feedback Binary Sensor`, or `Minimum Battery SOC` are configured, the per-device power and status sensors also expose extra diagnostic attributes for measured draw, feedback source, and battery gating.

### Example Automations

Turn on a switch when there is more than 50W of excess power available:

```yaml
automation:
  - alias: "Turn on Device with Solar Excess"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sun_allocator_excess_power
        above: 50
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.your_device
```

Disable auto-control for a device overnight using the per-device toggle:

```yaml
automation:
  - alias: "Pause Heater Auto-Control at Night"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.sun_allocator_heater_auto_control
  - alias: "Resume Heater Auto-Control in the Morning"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.sun_allocator_heater_auto_control
```

For more complex automations and Lovelace dashboard examples, check out the [**Examples documentation**](./docs/examples.md).

## Documentation

-   [**Detailed Configuration**](./docs/configuration.md): A full guide to all configuration options.
-   [**Technical Concepts**](./docs/concepts.md): An explanation of the solar power concepts and calculations used.
-   [**ESPHome Integration**](./docs/esphome.md): How to set up and control ESPHome devices.
-   [**Examples**](./docs/examples.md): Lovelace card and automation examples.
-   [**Architecture**](./docs/architecture.md): Internal module layout, data flow, and storage layout (for contributors).