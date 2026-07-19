[🇬🇧 English](./esphome.md) | [🇺🇦 Українська](./esphome_uk.md)

# ESPHome Integration

SunAllocator can directly control multiple ESPHome devices to utilize excess solar energy. This integration allows you to automatically adjust the power of solid-state relays based on the available untapped potential, with priority-based power distribution.

## Multiple Device Support

SunAllocator now supports configuring and controlling multiple ESPHome devices. Key features include:

- **Add multiple devices**: Configure any number of ESPHome devices to utilize excess solar energy
- **Priority-based power distribution**: Assign priorities to devices to control which ones get power first
- **Individual device configuration**: Each device has its own settings for the controlled entity, auto-control, priority, etc.
- **Centralized management**: Manage all devices through a single configuration interface

## Configuration

When setting up the SunAllocator integration, you'll first configure your solar panel settings, then you can add and manage your ESPHome devices:

1.  **Solar Panel Configuration**:
    *   Configure your solar panel sensors, voltage/current parameters, etc. See [Detailed Configuration](./configuration.md).

2.  **Device Management**:
    *   Add, edit, or remove devices
    *   For each device, configure:
        *   **Name**: A descriptive name for the device
        *   **Entity**: Pick the controlled entity from the entity picker (see [Selecting the Entity](#selecting-the-entity) below). You no longer pick a device type or a separate mode-select entity — the control capability is chosen directly in the picker.
        *   **Auto Control Enabled**: Whether SunAllocator should automatically control this device
        *   **Min Expected Load (W)**: Device’s useful minimum. Below this threshold the device stays off (with hysteresis)
        *   **Max Expected Load (W)**: Device’s physical/logical maximum; 100% in proportional mode corresponds to this value and allocation is capped by it. Required for proportional (Dimmer) devices with auto-control enabled
        *   **Priority**: A value from 1-100 that determines which devices get power first (higher = higher priority)
        *   **Schedule Enabled**: Whether to enable time-based scheduling for this device
        *   **Start Time**: The time when the device should start operating (if scheduling is enabled)
        *   **End Time**: The time when the device should stop operating (if scheduling is enabled)
        *   **Days of Week**: The days when the device should operate (if scheduling is enabled)

> **Note**: The entity is optional. You can leave it as *None* to create a placeholder device that does not participate in any control operations (useful for planning or testing).

## Selecting the Entity

There is no longer a separate "device type" choice or a manual "ESPHome mode select" field. You simply pick the controlled entity from the device's entity picker, and the control capability is encoded in the option you choose.

An ESPHome SunAllocator relay exposes a `light` entity together with a paired `select` entity (whose options include "Off", "On" and "Proportional") on the **same** device. When you open the picker and select the relay's `light` entity, SunAllocator auto-detects the paired Proportional-capable `select` via the entity/device registry (matching on the same `device_id`). Because of that, the light appears **twice** in the picker:

*   **`Device — Entity (Switch)`** — drives the relay on/off only.
*   **`Device — Entity (Dimmer)`** — drives the relay proportionally.

Pick **(Dimmer)** for proportional control or **(Switch)** for simple on/off. The paired mode-select entity is stored automatically behind the scenes — you never select it yourself.

The same two-row behaviour applies to any native dimmable `light` (one that supports brightness): it shows both a **(Switch)** and a **(Dimmer)** option. Plain on/off entities (standard switches, `input_boolean`, etc.) appear as a single row and are controlled on/off only.

> **Note**: For proportional (Dimmer) control with auto-control enabled, you must set **Max Expected Load (W)** — 100% brightness corresponds to that value.

## Operation Modes

An ESPHome relay supports three operation modes, exposed through its paired `select` entity:

1.  **Off**: The relay is turned off completely
2.  **On**: The relay is turned on at full power
3.  **Proportional**: The relay power is adjusted proportionally to the available excess power

You do not set these modes manually during setup — SunAllocator drives the relay itself at runtime based on the capability you picked (Switch or Dimmer):

*   **Proportional (Dimmer)**: SunAllocator sets the paired `select` to "Proportional", then sets the brightness on the `light` entity to the target percentage.
*   **On/Off (Switch)**: SunAllocator sets the paired `select` to "On" or "Off".

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
2.  Proportional devices (Dimmer): target power percentage is scaled linearly to the device capability: `target% = clamp(5..90, 100 × available_excess / max_expected_w)`. Allocated watts are capped by `max_expected_w`. For an ESPHome relay, SunAllocator first sets the paired select to "Proportional", then sets the light brightness.
3.  On/Off devices (Switch): the device turns ON when active, OFF otherwise. Allocation is capped by `max_expected_w` (if set), or by a small internal fallback cap. Percent actual is reflected as 100% when ON, 0% when OFF. For an ESPHome relay, SunAllocator sets the paired select to "On" / "Off".

## Behavior with No Entity

The integration handles a device with no entity selected as follows:

-   **If a device has no entity configured** (the picker is left as *None*):
    -   The device will be effectively disabled
    -   It will still appear in the device list but will not participate in any control operations
    -   Services that target this device will log a warning but continue for other devices
    -   Auto-control will skip this device for power distribution

This lets you create placeholder devices for planning or testing.

When you do pick an ESPHome relay's `light` entity, its paired mode-select entity is detected and stored automatically, so there is no separate optional mode-select field to leave empty.

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
