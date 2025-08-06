# SolarVampire Home Assistant Custom Component

**Features:**
- Calculates untapped potential solar energy (excess) and % usage.
- Estimates maximum possible power at current voltage based on MPPT principles.
- Direct integration with ESPHome devices to utilize excess solar energy.
- Automatic control of loads based on available excess power.
- **Easy configuration through Home Assistant UI** - no YAML editing required.
- Multiple device support with priority-based power distribution.
- Scheduling support for time-based device control.
- Compatible with Lovelace cards and automations.

## Installation

1. Copy `custom_components/solarvampire` to your `config/custom_components` folder.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services**.
4. Click **"+ ADD INTEGRATION"**.
5. Search for **"SolarVampire"** and select it.
6. Follow the configuration wizard to set up your solar panels and devices.

## Configuration

SolarVampire uses a **graphical configuration interface** - no YAML editing required! The setup process is divided into several steps:

### Step 1: Solar Panel Configuration

Configure your solar panel parameters:
- **PV Power Sensor**: Select the sensor that measures your solar panel power output
- **PV Voltage Sensor**: Select the sensor that measures your solar panel voltage
- **Consumption Sensor** (optional): Select a sensor that measures your power consumption
- **Panel Specifications**:
  - **Vmp** (Voltage at Maximum Power): Voltage at maximum power point from panel specifications
  - **Imp** (Current at Maximum Power): Current at maximum power point from panel specifications
  - **Voc** (Open Circuit Voltage): Open circuit voltage (optional)
  - **Isc** (Short Circuit Current): Short circuit current (optional)
  - **Panel Count**: Number of solar panels in your system
  - **Panel Configuration**: How panels are connected (Series, Parallel, or Parallel-Series)

### Step 2: Device Configuration

Add and configure ESPHome devices to utilize excess solar energy:
- **Add multiple devices** with different priorities
- **Configure device types**: No Device, Standard Switch/Light, or Custom ESPHome Relay
- **Set priorities** to control which devices get power first
- **Enable scheduling** for time-based control
- **Configure auto-control** with minimum power thresholds

### Managing Your Configuration

After initial setup, you can modify your configuration:

1. Go to **Settings → Devices & Services**
2. Find your **SolarVampire** integration
3. Click the **"CONFIGURE"** button
4. Choose from the main menu:
   - **Settings**: Modify solar panel configuration and MPPT parameters
   - **Add Device**: Add new ESPHome devices
   - **Manage Devices**: Edit or remove existing devices

## Usage

- Use `sensor.solarvampire_excess_1` in Lovelace gauge or automations. This sensor shows the untapped potential power - how many additional watts could be extracted from the panel at the current voltage.
- Other available sensors: 
  - `sensor.solarvampire_max_power_1`: Rated maximum power of the panel (Vmp × Imp × panel_count)
  - `sensor.solarvampire_usage_percent_1`: Current power usage as percentage of maximum power
  - `sensor.solarvampire_current_max_power_1`: Maximum possible power at current voltage (based on MPPT principles)
- Attributes of `sensor.solarvampire_excess_1`: 
  - `pv_power`: Current power from the solar panel
  - `pv_voltage`: Current voltage from the solar panel
  - `consumption`: Current power consumption
  - `excess_possible`: Whether excess power is possible (true if voltage > Vmp). This indicates that the panel is operating in the constant-voltage region of its I-V curve, where voltage is higher than the optimal maximum power point. In this region, the panel could potentially produce more power if the voltage was reduced to Vmp through proper MPPT control.
  - `vmp`: Voltage at maximum power point (from panel specifications)
  - `imp`: Current at maximum power point (from panel specifications)
  - `panel_count`: Number of panels
  - `panel_configuration`: Panel arrangement ("series" or "parallel")
  - `pmax`: Rated maximum power (Vmp × Imp × panel_count)
  - `current_max_power`: Maximum possible power at current voltage
  - `usage_percent`: Current power usage as percentage of maximum power

### Panel Configuration

The `panel_configuration` parameter specifies how your solar panels are arranged:

- **Series Configuration** (default): In a series arrangement, voltages add up while current remains the same. This is the most common configuration for solar installations. The relative voltage is calculated as `pv_voltage / (vmp * panel_count)`.

- **Parallel Configuration**: In a parallel arrangement, currents add up while voltage remains the same across all panels. The relative voltage is calculated as `pv_voltage / vmp`.

Choosing the correct configuration is important for accurate power calculations, especially when you have multiple panels. If you're unsure, check your solar system documentation or consult with your installer.

### Excess Power Calculation

The `solarvampire_excess_1` sensor calculates the untapped potential power that could be extracted from your solar panel. It is calculated as:

```
Excess = Maximum Possible Power at Current Voltage - Current Power Output
```

This value represents how many additional watts could be extracted from the panel at its current operating voltage. When this value is high, it indicates that your panel has significant untapped potential that could be utilized with additional loads.

### Understanding MPPT and Solar Panel Operation

Solar panels have a characteristic I-V (current-voltage) curve that determines their power output. The key points to understand:

1. **Maximum Power Point (MPP)**: This is the optimal operating point where the product of voltage and current is maximized. It occurs at specific voltage (Vmp) and current (Imp) values.

2. **Operating Regions**:
   - **Below Vmp**: In this region, the panel operates with relatively constant current. As voltage increases, power increases approximately linearly.
   - **At Vmp**: This is the optimal operating point where maximum power is produced.
   - **Above Vmp**: In this region, current drops rapidly as voltage increases, causing power to decrease.

3. **Excess Possible Indicator**: The `excess_possible` attribute is `true` when your panel's voltage exceeds Vmp. This indicates:
   - The panel is operating in the constant-voltage region (above Vmp)
   - Power output is likely less than optimal
   - An MPPT controller could potentially increase power by reducing voltage to Vmp

4. **Why it's usually "false"**: Most solar systems with MPPT controllers will operate at or below Vmp to maximize power, so `excess_possible` will typically be "false" during normal operation.

### Understanding the Consumption Parameter

The `consumption` parameter is an optional configuration parameter that represents the power consumption of your system in watts. It allows you to track how much of your solar power is being used versus how much is available.

- **What it represents**: The power consumption of your system, typically measured by a separate power meter or sensor.
- **How to configure it**: Add a `consumption` parameter to your configuration pointing to a sensor that measures your current power consumption:
  ```yaml
  consumption: sensor.your_consumption_sensor
  ```
- **Current usage**: While the consumption value is stored as an attribute and displayed in the UI, it is not directly used in the excess calculation in the current version. The excess is now calculated as the difference between the maximum possible power at current voltage and the actual power output.
- **Why it shows 0**: If you haven't specified a consumption sensor or if the specified sensor is unavailable, the consumption value will default to 0.

You can still use the consumption attribute in your own automations if needed, for example to calculate the actual excess power available after your current consumption.

### MPPT-Based Maximum Power Calculation

The `current_max_power` value estimates the maximum power that could be extracted at the current voltage, based on Maximum Power Point Tracking (MPPT) principles. This helps you understand:

1. How much power your panel could potentially produce at its current operating voltage
2. Whether you're operating near the optimal voltage for maximum power
3. How much additional power you could extract with optimal MPPT control

#### Technical Details of the MPPT Algorithm

SolarVampire uses an advanced model to estimate maximum possible power at any voltage:

1. **Relative Voltage Calculation**:
   ```
   relative_voltage = pv_voltage / (vmp * panel_count)  # for series configuration
   relative_voltage = pv_voltage / vmp                  # for parallel configuration
   ```

2. **Power Estimation Model**:
   - For voltage below or at Vmp (relative_voltage ≤ 1.0):
     ```
     current_max_power = pmax * (relative_voltage * (1.0 - 0.1 * (1.0 - relative_voltage)))
     ```
     This polynomial approximation creates a slight upward curve as voltage approaches Vmp, matching real-world panel behavior.

   - For voltage above Vmp (relative_voltage > 1.0):
     ```
     current_max_power = pmax * max(0, 1 - (1.5 * (relative_voltage - 1) ** 2))
     ```
     This quadratic model with a 1.5x drop rate factor reflects the rapid power decrease that occurs in real panels when voltage exceeds Vmp.

3. **Panel Configuration**:
   The algorithm accounts for different panel arrangements:
   - **Series**: Voltage adds up, current remains the same
   - **Parallel**: Current adds up, voltage remains the same

![MPPT Power Curve](mppt_algorithm_comparison.png)
*Comparison of power curves showing how the improved algorithm better matches real-world panel behavior*

## Example Automation

```yaml
automation:
  - alias: "Enable relay on excess"
    trigger:
      - platform: numeric_state
        entity_id: sensor.solarvampire_excess_1
        above: 50
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.your_esphome_relay
```

You can also create an automation based on the usage percentage:

```yaml
automation:
  - alias: "Enable relay on high usage"
    trigger:
      - platform: numeric_state
        entity_id: sensor.solarvampire_usage_percent_1
        above: 90
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.your_esphome_relay
```

### Example Using Current Max Power

You can create an automation that activates when there's significant untapped power potential:

```yaml
automation:
  - alias: "Enable load when additional power is available"
    trigger:
      - platform: template
        value_template: >
          {% set current_power = states('sensor.pv_power_1') | float(0) %}
          {% set max_power = states('sensor.solarvampire_current_max_power_1') | float(0) %}
          {% set power_difference = max_power - current_power %}
          {{ power_difference > 100 }}
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.additional_load
```

## Example Lovelace Cards

Here's an example of a Lovelace card that displays the current max power and efficiency:

```yaml
type: entities
title: Solar Panel Performance
entities:
  - entity: sensor.solarvampire_current_max_power_1
    name: Maximum Possible Power (W)
  - entity: sensor.pv_power_1
    name: Current Power (W)
  - entity: sensor.solarvampire_usage_percent_1
    name: Efficiency (%)
  - type: custom:bar-card
    entity: sensor.solarvampire_usage_percent_1
    title: Panel Efficiency
    max: 100
    severity:
      green: 0
      yellow: 70
      red: 90
```

## ESPHome Integration

SolarVampire can directly control multiple ESPHome devices to utilize excess solar energy. This integration allows you to automatically adjust the power of solid-state relays based on the available untapped potential, with priority-based power distribution.

### Multiple Device Support

SolarVampire now supports configuring and controlling multiple ESPHome devices. Key features include:

- **Add multiple devices**: Configure any number of ESPHome devices to utilize excess solar energy
- **Priority-based power distribution**: Assign priorities to devices to control which ones get power first
- **Individual device configuration**: Each device has its own settings for relay entity, mode, auto-control, etc.
- **Centralized management**: Manage all devices through a single configuration interface

### Configuration

When setting up the SolarVampire integration, you'll first configure your solar panel settings, then you can add and manage your ESPHome devices:

1. **Solar Panel Configuration**:
   - Configure your solar panel sensors, voltage/current parameters, etc.

2. **Device Management**:
   - Add, edit, or remove ESPHome devices
   - For each device, configure:
     - **Name**: A descriptive name for the device
     - **Device Type**: Choose between No Device, Standard Switch/Light, or Custom ESPHome Relay
     - **ESPHome Relay Entity** (optional): The light entity that controls the solid-state relay
     - **ESPHome Mode Select Entity** (optional): The select entity that controls the operation mode
     - **Auto Control Enabled**: Whether SolarVampire should automatically control this device
     - **Minimum Excess Power**: The minimum excess power required to activate this device
     - **Priority**: A value from 1-100 that determines which devices get power first (higher = higher priority)
     - **Schedule Enabled**: Whether to enable time-based scheduling for this device
     - **Start Time**: The time when the device should start operating (if scheduling is enabled)
     - **End Time**: The time when the device should stop operating (if scheduling is enabled)
     - **Days of Week**: The days when the device should operate (if scheduling is enabled)
   
   > **Note**: Both the ESPHome Relay Entity and ESPHome Mode Select Entity are now optional. This allows you to create devices that only use one of these entities, or neither. For example, you could create a device that only uses the relay entity for direct power control, or a device that only uses the mode select entity to control an external system.

### Device Types

SolarVampire supports three types of devices:

1. **No Device (Placeholder)**: A placeholder entry with no actual control entities. Useful for planning or testing.

2. **Standard Switch/Light (On/Off only)**: A standard Home Assistant switch or light entity that only supports on/off control. These devices don't use a mode select entity and will be controlled directly based on the available excess power.

3. **Custom ESPHome Relay (On/Off/Proportional)**: A custom ESPHome device with both a relay entity and a mode select entity, supporting all three operation modes (Off, On, Proportional).

### Operation Modes

Each device supports three operation modes:

1. **Off**: The relay is turned off completely
2. **On**: The relay is turned on at full power
3. **Proportional**: The relay power is adjusted proportionally to the available excess power

### Scheduling

Each device can be configured with a schedule to control when it should operate:

1. **Schedule Enabled**: Toggle to enable or disable scheduling for the device
2. **Start Time**: The time when the device should start operating (e.g., "08:00")
3. **End Time**: The time when the device should stop operating (e.g., "20:00")
4. **Days of Week**: Select the days when the device should operate

When scheduling is enabled, the device will only operate during the specified time range on the selected days. Outside of this schedule, the device will be turned off automatically.

The scheduling feature supports overnight schedules (when end time is earlier than start time). For example, if you set start time to "22:00" and end time to "06:00", the device will operate from 10 PM to 6 AM the next day.

> **Note**: Scheduling is applied after auto-control. If auto-control is disabled, the device won't be controlled automatically regardless of the schedule.

### Services

SolarVampire provides two services to control ESPHome devices:

#### `solarvampire.set_relay_mode`

Sets the operation mode of one or more relays.

Parameters:
- `entity_id` (optional): The entity ID of a specific mode select entity
- `device_id` (optional): The ID of a specific device to control
- `mode`: The operation mode to set. Must be one of: `Off`, `On`, `Proportional`

If neither `entity_id` nor `device_id` is provided, the mode will be set for all configured devices.

Examples for setting relay mode:

For a specific entity:
```yaml
service: solarvampire.set_relay_mode
data:
  entity_id: select.relay_mode_1
  mode: Proportional
```

For a specific device:
```yaml
service: solarvampire.set_relay_mode
data:
  device_id: 3f7b2a1c-e8d9-4f5a-b6c7-8d9e0f1a2b3c
  mode: On
```

For all devices:
```yaml
service: solarvampire.set_relay_mode
data:
  mode: Off
```

#### `solarvampire.set_relay_power`

Sets the power level of one or more relays.

Parameters:
- `entity_id` (optional): The entity ID of a specific relay entity
- `device_id` (optional): The ID of a specific device to control
- `power`: The power level to set, as a percentage (0-100)

If neither `entity_id` nor `device_id` is provided, the power will be set for all configured devices.

Examples for setting relay power:

For a specific entity:
```yaml
service: solarvampire.set_relay_power
data:
  entity_id: light.solar_vampire_relay_1
  power: 75
```

For a specific device:
```yaml
service: solarvampire.set_relay_power
data:
  device_id: 3f7b2a1c-e8d9-4f5a-b6c7-8d9e0f1a2b3c
  power: 50
```

For all devices:
```yaml
service: solarvampire.set_relay_power
data:
  power: 100
```

### Priority-Based Power Distribution

When multiple devices are configured with auto-control enabled, SolarVampire distributes the available excess power based on device priorities:

1. Devices are sorted by priority (higher priority first)
2. The device with the highest priority gets power first
3. If there's remaining power after satisfying the highest priority device, it goes to the next device
4. This continues until all excess power is distributed or all devices are satisfied

This allows you to create a hierarchy of loads. For example:

- **Priority 100**: Critical loads (e.g., battery charging)
- **Priority 75**: Important loads (e.g., water heating)
- **Priority 50**: Useful loads (e.g., space heating)
- **Priority 25**: Optional loads (e.g., pool heating)

### Automatic Control

When auto-control is enabled for a device, SolarVampire will automatically adjust its relay power based on the available excess power:

1. If the excess power is below the device's minimum threshold, the relay is turned off
2. If the excess power is above the minimum threshold, the relay power is set proportionally
3. The power level is scaled so that the minimum threshold corresponds to 5% power, and 3 times the minimum threshold corresponds to 100% power

### Behavior with Optional Entities

The integration handles devices with missing entities as follows:

- **If a device has no relay entity configured**:
  - The device will not receive power control commands
  - Services that target this device for power control will log a warning but continue for other devices
  - Auto-control will skip this device for power distribution

- **If a device has no mode select entity configured**:
  - The device will not receive mode change commands
  - Services that target this device for mode changes will log a warning but continue for other devices
  - Auto-control will skip this device as it cannot determine the current mode

- **If a device has neither entity configured**:
  - The device will be effectively disabled
  - It will still appear in the device list but will not participate in any control operations

This flexibility allows you to create placeholder devices or devices that only use one aspect of the control system.

### ESPHome Component

To use this integration, you need ESPHome devices with solid-state relays and mode select components. You can use the provided `solar_vampire_relay.yaml` configuration as a starting point:

```yaml
# Basic ESPHome configuration
esphome:
  name: solar_vampire_relay
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
    name: "Solar Vampire Relay"
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

### Example Dashboard

Here's an example of a Lovelace card that displays the SolarVampire data and controls for multiple ESPHome devices:

```yaml
type: vertical-stack
cards:
  - type: entities
    title: Solar Vampire Status
    entities:
      - entity: sensor.solarvampire_excess_1
        name: Untapped Potential (W)
      - entity: sensor.solarvampire_current_max_power_1
        name: Current Max Power (W)
      - entity: sensor.solarvampire_usage_percent_1
        name: PV Usage (%)
  
  - type: entities
    title: Water Heater (High Priority)
    entities:
      - entity: select.water_heater_mode
        name: Mode
      - entity: light.water_heater_relay
        name: Power
  
  - type: entities
    title: Space Heater (Medium Priority)
    entities:
      - entity: select.space_heater_mode
        name: Mode
      - entity: light.space_heater_relay
        name: Power
        
  - type: entities
    title: Pool Pump (Low Priority)
    entities:
      - entity: select.pool_pump_mode
        name: Mode
      - entity: light.pool_pump_relay
        name: Power
  
  - type: gauge
    name: Untapped Potential
    entity: sensor.solarvampire_excess_1
    min: 0
    max: 500
    severity:
      green: 0
      yellow: 100
      red: 300
```

### Example Automation for Time-Based Control

You can create automations to change device modes based on time of day or other conditions:

```yaml
automation:
  - alias: "Enable Water Heater During Daytime"
    trigger:
      - platform: sun
        event: sunrise
        offset: "01:00:00"
    action:
      - service: solarvampire.set_relay_mode
        data:
          device_id: 3f7b2a1c-e8d9-4f5a-b6c7-8d9e0f1a2b3c
          mode: Proportional
          
  - alias: "Disable Water Heater at Night"
    trigger:
      - platform: sun
        event: sunset
        offset: "-00:30:00"
    action:
      - service: solarvampire.set_relay_mode
        data:
          device_id: 3f7b2a1c-e8d9-4f5a-b6c7-8d9e0f1a2b3c
          mode: Off
```

### Power Distribution Visualization

SolarVampire provides sensors for visualizing how power is distributed among devices:

#### Power Distribution Sensors

1. **Main Power Distribution Sensor**: `sensor.solarvampire_power_distribution`
   - Shows the total allocated power across all devices
   - Provides attributes for total power, remaining power, and allocation per device
   - Updates automatically when power distribution changes

2. **Device Power Allocation Sensors**: `sensor.solarvampire_device_power_[device_id]`
   - One sensor is created for each device
   - Shows the power allocated to that specific device
   - Updates automatically when power allocation changes

#### Example Lovelace Cards

You can create various visualizations using these sensors. Here's an example of a comprehensive power distribution dashboard:

```yaml
title: Solar Vampire Power Distribution
type: vertical-stack
cards:
  - type: entities
    title: Power Distribution Overview
    entities:
      - entity: sensor.solarvampire_power_distribution
        name: Total Allocated Power
        secondary_info: last-changed
      - type: attribute
        entity: sensor.solarvampire_power_distribution
        attribute: total_power
        name: Total Available Power
      - type: attribute
        entity: sensor.solarvampire_power_distribution
        attribute: remaining_power
        name: Remaining Power
      - type: attribute
        entity: sensor.solarvampire_power_distribution
        attribute: allocated_power
        name: Allocated Power
  
  - type: custom:bar-card
    title: Power Allocation
    entity: sensor.solarvampire_power_distribution
    positions:
      icon: outside
      indicator: 'off'
      name: inside
      value: inside
    severity:
      - color: '#00ba47'
        value: 0
      - color: '#f39c12'
        value: 50
      - color: '#d35400'
        value: 80
    max: 500
    min: 0
    unit_of_measurement: W
    
  - type: custom:apexcharts-card
    title: Device Power Allocation
    graph_span: 24h
    header:
      show: true
      title: Device Power Allocation
      show_states: true
    series:
      # Replace these with your actual device power sensors
      - entity: sensor.solarvampire_device_power_device1
        name: Water Heater
      - entity: sensor.solarvampire_device_power_device2
        name: Space Heater
      - entity: sensor.solarvampire_device_power_device3
        name: Pool Pump
```

> **Note**: The example above uses custom cards (`bar-card` and `apexcharts-card`) which need to be installed via HACS. You can also use standard cards like `gauge` or `history-graph` for similar visualizations.

#### Tracking Power Distribution Over Time

You can also track power distribution over time using the history graph card:

```yaml
type: custom:mini-graph-card
title: Power Distribution History
entities:
  - entity: sensor.solarvampire_power_distribution
    name: Allocated Power
  - entity: sensor.solarvampire_excess_1
    name: Available Power
hours_to_show: 24
points_per_hour: 4
line_width: 2
show:
  fill: true
  legend: true
```

This visualization helps you understand how effectively your system is utilizing the available solar power throughout the day.
