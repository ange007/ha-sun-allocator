# SunAllocator Home Assistant Custom Component

![logo](./custom_components/sun_allocator/icons/logo.png)

**SunAllocator** is a Home Assistant custom component that helps you maximize the use of your solar energy. It calculates potential excess power from your solar panels and automatically distributes it to your devices, such as water heaters or EV chargers, turning your home into a "solar vampire" that consumes all available free energy.

## Features

- Calculates untapped potential solar energy (excess) and panel usage percentage.
- Estimates maximum possible power at the current voltage based on MPPT principles.
- Direct integration with ESPHome devices and standard switches to utilize excess solar energy.
- Automatic, priority-based control of multiple loads.
- **Easy configuration through Home Assistant UI** - no YAML editing required.
- Scheduling support for time-based device control.
- Provides sensors for easy integration with Lovelace dashboards and automations.

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

For a detailed guide on all configuration options, please see the [**Detailed Configuration documentation**](./custom_components/sun_allocator/docs/configuration.md).

## Usage

The integration creates several sensors to monitor your solar array:

-   `sensor.sunallocator_excess_1`: The untapped potential power available. Use this to trigger your automations.
-   `sensor.sunallocator_current_max_power_1`: The estimated maximum power your panels could produce at the current voltage.
-   `sensor.sunallocator_usage_percent_1`: The current power usage as a percentage of the maximum possible power.
-   `sensor.sunallocator_power_distribution_1`: The total power currently allocated to all your controlled devices.

### Example Automation

Here is a simple automation that turns on a switch when there is more than 50W of excess power available.

```yaml
automation:
  - alias: "Turn on Device with Solar Excess"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sunallocator_excess_1
        above: 50
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.your_device
```

For more complex automations and Lovelace dashboard examples, check out the [**Examples documentation**](./custom_components/sun_allocator/docs/examples.md).

## Documentation

-   [**Detailed Configuration**](./custom_components/sun_allocator/docs/configuration.md): A full guide to all configuration options.
-   [**Technical Concepts**](./custom_components/sun_allocator/docs/concepts.md): An explanation of the solar power concepts and calculations used.
-   [**ESPHome Integration**](./custom_components/sun_allocator/docs/esphome.md): How to set up and control ESPHome devices.
-   [**Examples**](./custom_components/sun_allocator/docs/examples.md): Lovelace card and automation examples.