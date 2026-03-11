[🇬🇧 English](./examples.md) | [🇺🇦 Українська](./examples_uk.md)

# Examples

This file contains examples for automations, Lovelace cards, and dashboards.

## Automation Examples

### Enable Relay on Excess Power

```yaml
automation:
  - alias: "Enable relay on excess"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sun_allocator_excess_power
        above: 50
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.your_esphome_relay
```

### Enable Relay on High Usage Percentage

```yaml
automation:
  - alias: "Enable relay on high usage"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sun_allocator_usage_percent
        above: 90
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.your_esphome_relay
```

### Enable Load Based on Current Max Power

Create an automation that activates when there's significant untapped power potential:

```yaml
automation:
  - alias: "Enable load when additional power is available"
    trigger:
      - platform: template
        value_template: >
          {% set current_power = states('sensor.pv_power') | float(0) %}
          {% set max_power = states('sensor.sun_allocator_current_max_power') | float(0) %}
          {% set power_difference = max_power - current_power %}
          {{ power_difference > 100 }}
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.additional_load
```

### Time-Based Control

You can create automations to change device modes based on time of day or other conditions:

```yaml
automation:
  - alias: "Enable Water Heater During Daytime"
    trigger:
      - platform: sun
        event: sunrise
        offset: "01:00:00"
    action:
      - service: sun_allocator.set_relay_mode
        data:
          device_id: 3f7b2a1c-e8d9-4f5a-b6c7-8d9e0f1a2b3c
          mode: Proportional
          
  - alias: "Disable Water Heater at Night"
    trigger:
      - platform: sun
        event: sunset
        offset: "-00:30:00"
    action:
      - service: sun_allocator.set_relay_mode
        data:
          device_id: 3f7b2a1c-e8d9-4f5a-b6c7-8d9e0f1a2b3c
          mode: Off
```

### Service Call Examples

#### `sun_allocator.set_relay_mode`

For a specific entity:
```yaml
service: sun_allocator.set_relay_mode
data:
  entity_id: select.relay_mode_1
  mode: Proportional
```

For a specific device by its ID:
```yaml
service: sun_allocator.set_relay_mode
data:
  device_id: 3f7b2a1c-e8d9-4f5a-b6c7-8d9e0f1a2b3c
  mode: On
```

For all devices:
```yaml
service: sun_allocator.set_relay_mode
data:
  mode: Off
```

#### `sun_allocator.set_relay_power`

For a specific entity:
```yaml
service: sun_allocator.set_relay_power
data:
  entity_id: light.sun_allocator_relay
  power: 75
```

For a specific device by its ID:
```yaml
service: sun_allocator.set_relay_power
data:
  device_id: 3f7b2a1c-e8d9-4f5a-b6c7-8d9e0f1a2b3c
  power: 50
```

For all devices:
```yaml
service: sun_allocator.set_relay_power
data:
  power: 100
```

## Lovelace & Dashboard Examples

### Simple Performance Card

```yaml
type: entities
title: Solar Panel Performance
entities:
  - entity: sensor.sun_allocator_current_max_power
    name: Maximum Possible Power (W)
  - entity: sensor.pv_power
    name: Current Power (W)
  - entity: sensor.sun_allocator_usage_percent
    name: Efficiency (%)
  - type: custom:bar-card
    entity: sensor.sun_allocator_usage_percent
    title: Panel Efficiency
    max: 100
    severity:
      green: 0
      yellow: 70
      red: 90
```

### Multi-Device Control Dashboard

```yaml
type: vertical-stack
cards:
  - type: entities
    title: SunAllocator Status
    entities:
      - entity: sensor.sun_allocator_excess_power
        name: Untapped Potential (W)
      - entity: sensor.sun_allocator_current_max_power
        name: Current Max Power (W)
      - entity: sensor.sun_allocator_usage_percent
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
    entity: sensor.sun_allocator_excess_power
    min: 0
    max: 500
    severity:
      green: 0
      yellow: 100
      red: 300
```

### Power Distribution Visualization

SunAllocator provides sensors for visualizing how power is distributed among devices.

#### Power Distribution Sensors

1.  **Main Power Distribution Sensor**: `sensor.sun_allocator_power_distribution`
    *   Shows the total allocated power across all devices
    *   Provides attributes for total power, remaining power, and allocation per device

2.  **Device Power Allocation Sensors**: `sensor.sun_allocator_device_power_[device_id]`
    *   One sensor is created for each device, showing the power allocated to it.

#### Example Power Distribution Dashboard

This example uses custom cards (`bar-card` and `apexcharts-card`) which need to be installed from HACS.

```yaml
title: Sun Allocator Power Distribution
type: vertical-stack
cards:
  - type: entities
    title: Power Distribution Overview
    entities:
      - entity: sensor.sun_allocator_power_distribution
        name: Total Allocated Power
        secondary_info: last-changed
      - type: attribute
        entity: sensor.sun_allocator_power_distribution
        attribute: total_power
        name: Total Available Power
      - type: attribute
        entity: sensor.sun_allocator_power_distribution
        attribute: remaining_power
        name: Remaining Power
      - type: attribute
        entity: sensor.sun_allocator_power_distribution
        attribute: allocated_power
        name: Allocated Power
  
  - type: custom:bar-card
    title: Power Allocation
    entity: sensor.sun_allocator_power_distribution
    # ... (bar-card config) ...
    
  - type: custom:apexcharts-card
    title: Device Power Allocation
    graph_span: 24h
    header:
      show: true
      title: Device Power Allocation
      show_states: true
    series:
      # Replace these with your actual device power sensors
      - entity: sensor.sun_allocator_device_power_device1
        name: Water Heater
      - entity: sensor.sun_allocator_device_power_device2
        name: Space Heater
      - entity: sensor.sun_allocator_device_power_device3
        name: Pool Pump
```

#### Tracking Power Distribution Over Time

```yaml
type: custom:mini-graph-card
title: Power Distribution History
entities:
  - entity: sensor.sun_allocator_power_distribution
    name: Allocated Power
  - entity: sensor.sun_allocator_excess_power
    name: Available Power
hours_to_show: 24
points_per_hour: 4
line_width: 2
show:
  fill: true
  legend: true
```
