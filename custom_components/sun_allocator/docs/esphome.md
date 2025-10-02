# ESPHome Integration

SunAllocator can directly control multiple ESPHome devices to utilize excess solar energy. This integration allows you to automatically adjust the power of solid-state relays based on the available untapped potential, with priority-based power distribution.

## Multiple Device Support

SunAllocator now supports configuring and controlling multiple ESPHome devices. Key features include:

- **Add multiple devices**: Configure any number of ESPHome devices to utilize excess solar energy
- **Priority-based power distribution**: Assign priorities to devices to control which ones get power first
- **Individual device configuration**: Each device has its own settings for relay entity, mode, auto-control, etc.
- **Centralized management**: Manage all devices through a single configuration interface

## Configuration

When setting up the SunAllocator integration, you'll first configure your solar panel settings, then you can add and manage your ESPHome devices:

1.  **Solar Panel Configuration**:
    *   Configure your solar panel sensors, voltage/current parameters, etc. See [Detailed Configuration](./configuration.md).

2.  **Device Management**:
    *   Add, edit, or remove ESPHome devices
    *   For each device, configure:
        *   **Name**: A descriptive name for the device
        *   **Device Type**: Choose between No Device, Standard Switch/Light, or Custom ESPHome Relay
        *   **ESPHome Relay Entity** (optional): The light entity that controls the solid-state relay
        *   **ESPHome Mode Select Entity** (optional): The select entity that controls the operation mode
        *   **Auto Control Enabled**: Whether SunAllocator should automatically control this device
        *   **Min Expected Load (W)**: Device’s useful minimum. Below this threshold the device stays off (with hysteresis)
        *   **Max Expected Load (W)**: Device’s physical/logical maximum; 100% in proportional mode corresponds to this value and allocation is capped by it
        *   **Priority**: A value from 1-100 that determines which devices get power first (higher = higher priority)
        *   **Schedule Enabled**: Whether to enable time-based scheduling for this device
        *   **Start Time**: The time when the device should start operating (if scheduling is enabled)
        *   **End Time**: The time when the device should stop operating (if scheduling is enabled)
        *   **Days of Week**: The days when the device should operate (if scheduling is enabled)

> **Note**: Both the ESPHome Relay Entity and ESPHome Mode Select Entity are now optional. This allows you to create devices that only use one of these entities, or neither. For example, you could create a device that only uses the relay entity for direct power control, or a device that only uses the mode select entity to control an external system.

## Device Types

SunAllocator supports three types of devices:

1.  **No Device (Placeholder)**: A placeholder entry with no actual control entities. Useful for planning or testing.

2.  **Standard Switch/Light (On/Off only)**: A standard Home Assistant switch or light entity that only supports on/off control. These devices don't use a mode select entity and will be controlled directly based on the available excess power.

3.  **Custom ESPHome Relay (On/Off/Proportional)**: A custom ESPHome device with both a relay entity and a mode select entity, supporting all three operation modes (Off, On, Proportional).

## Operation Modes

Each device supports three operation modes:

1.  **Off**: The relay is turned off completely
2.  **On**: The relay is turned on at full power
3.  **Proportional**: The relay power is adjusted proportionally to the available excess power

## Scheduling

Each device can be configured with a schedule to control when it should operate:

1.  **Schedule Enabled**: Toggle to enable or disable scheduling for the device
2.  **Start Time**: The time when the device should start operating (e.g., "08:00")
3.  **End Time**: The time when the device should stop operating (e.g., "20:00")
4.  **Days of Week**: Select the days when the device should operate

When scheduling is enabled, the device will only operate during the specified time range on the selected days. Outside of this schedule, the device will be turned off automatically.

The scheduling feature supports overnight schedules (when end time is earlier than start time). For example, if you set start time to "22:00" and end time to "06:00", the device will operate from 10 PM to 6 AM the next day.

> **Note**: Scheduling is applied after auto-control. If auto-control is disabled, the device won't be controlled automatically regardless of the schedule.

## Services

SunAllocator provides two services to control ESPHome devices:

#### `sun_allocator.set_relay_mode`

Sets the operation mode of one or more relays.

Parameters:

-   `entity_id` (optional): The entity ID of a specific mode select entity
-   `device_id` (optional): The ID of a specific device to control
-   `mode`: The operation mode to set. Must be one of: `Off`, `On`, `Proportional`

If neither `entity_id` nor `device_id` is provided, the mode will be set for all configured devices.

#### `sun_allocator.set_relay_power`

Sets the power level of one or more relays.

Parameters:

-   `entity_id` (optional): The entity ID of a specific relay entity
-   `device_id` (optional): The ID of a specific device to control
-   `power`: The power level to set, as a percentage (0-100)

If neither `entity_id` nor `device_id` is provided, the power will be set for all configured devices.

See [Examples](./examples.md) for usage.

## Priority-Based Power Distribution

When multiple devices are configured with auto-control enabled, SunAllocator distributes the available excess power based on device priorities:

1.  Devices are sorted by priority (higher priority first)
2.  The device with the highest priority gets power first
3.  If there's remaining power after satisfying the highest priority device, it goes to the next device
4.  This continues until all excess power is distributed or all devices are satisfied

This allows you to create a hierarchy of loads. For example:

-   **Priority 100**: Critical loads (e.g., battery charging)
-   **Priority 75**: Important loads (e.g., water heating)
-   **Priority 50**: Useful loads (e.g., space heating)
-   **Priority 25**: Optional loads (e.g., pool heating)

## Automatic Control

When auto-control is enabled (Variant A), SunAllocator adjusts each device using expected load limits and hysteresis:

1.  Effective start threshold: the device becomes active when available excess exceeds `max(min_expected_w, Default Min Start (W))` with hysteresis. It turns on above `+H/2` and turns off below `−H/2` around that threshold.
2.  Proportional devices (Custom, mode = Proportional): target power percentage is scaled linearly to the device capability: `target% = clamp(5..90, 100 × available_excess / max_expected_w)`. Allocated watts are capped by `max_expected_w`.
3.  On/Off devices (Standard or mode = On): the device turns ON when active, OFF otherwise. Allocation is capped by `max_expected_w` (if set), or by a small internal fallback cap. Percent actual is reflected as 100% when ON, 0% when OFF.

## Behavior with Optional Entities

The integration handles devices with missing entities as follows:

-   **If a device has no relay entity configured**:
    -   The device will not receive power control commands
    -   Services that target this device for power control will log a warning but continue for other devices
    -   Auto-control will skip this device for power distribution

-   **If a device has no mode select entity configured**:
    -   The device will not receive mode change commands
    -   Services that target this device for mode changes will log a warning but continue for other devices
    -   Auto-control will skip this device as it cannot determine the current mode

-   **If a device has neither entity configured**:
    -   The device will be effectively disabled
    -   It will still appear in the device list but will not participate in any control operations

This flexibility allows you to create placeholder devices or devices that only use one aspect of the control system.

## ESPHome Component Code

To use this integration, you need ESPHome devices with solid-state relays and mode select components. You can use the provided `sun_allocator_relay.yaml` configuration as a starting point:

```yaml
# Basic ESPHome configuration
esphome:
  name: sun_allocator_relay
  platform: ESP8266
  board: d1_mini

# WiFi connection
wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password

# Enable Home Assistant API
api:
  encryption:
    key: !secret api_encryption_key

# Define the solid-state relay output
output:
  - platform: esp8266_pwm
    id: relay_output
    pin: D1
    frequency: 1000Hz

# Define a custom PWM light to control the relay
light:
  - platform: monochromatic
    name: "Sun Allocator Relay"
    output: relay_output
    id: relay_light
    restore_mode: ALWAYS_OFF

# Mode selection
select:
  - platform: template
    name: "Relay Mode"
    id: relay_mode
    options:
      - "Off"
      - "On"
      - "Proportional"
    initial_option: "Off"
    optimistic: true
```
