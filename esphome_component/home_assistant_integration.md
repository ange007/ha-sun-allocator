# Home Assistant Integration Guide

This guide explains how to integrate the Sun Allocator Relay ESPHome component with Home Assistant and set up automations to make the most of your excess solar energy.

## Basic Integration

After flashing your ESP device with the Sun Allocator Relay firmware, it will automatically be discovered by Home Assistant if you have the ESPHome integration installed. If not, you can add it manually:

1. Go to **Settings** > **Devices & Services**
2. Click **+ Add Integration**
3. Search for and select **ESPHome**
4. Enter the IP address of your ESP device
5. Follow the prompts to complete the setup

## Available Entities

Once integrated, you'll have the following entities in Home Assistant:

- **Light Entity**: light.sun_allocator_relay — manual/proportional brightness control
- **Select Entity**: select.sunallocator_mode — Off / On / Proportional
- **Sensor Entities**:
  - sensor.untapped_potential — Untapped potential from SunAllocator
  - sensor.max_power — Maximum power from SunAllocator
  - sensor.untapped_percentage — Percentage of untapped potential
- **Text Sensor**: sensor.relay_status — Current status and power level

## Dashboard Integration

### Basic Card

Add this card to your dashboard for basic control:

`yaml
type: entities
title: Sun Allocator Relay
entities:
  - entity: select.sunallocator_mode
  - entity: light.sun_allocator_relay
  - entity: sensor.untapped_potential
  - entity: sensor.untapped_percentage
  - entity: text_sensor.relay_status
`

### Advanced Card

For a more comprehensive view, use this card:

`yaml
type: vertical-stack
cards:
  - type: entities
    title: Sun Allocator Relay Control
    entities:
      - entity: select.relay_mode
      - entity: light.sun_allocator_relay
      - entity: text_sensor.relay_status
  
  - type: history-graph
    title: Solar Power Utilization
    hours_to_show: 24
    entities:
      - entity: sensor.untapped_potential
      - entity: sensor.max_power
      - entity: sensor.untapped_percentage
  
  - type: gauge
    name: Untapped Potential
    entity: sensor.untapped_percentage
    min: 0
    max: 100
    severity:
      green: 0
      yellow: 30
      red: 70
`

## Automation Examples

### Basic Automations

#### Enable Proportional Mode During Peak Sun Hours

`yaml
automation:
  - alias: "Enable Proportional Mode During Peak Sun Hours"
    trigger:
      - platform: time
        at: "10:00:00"
    action:
      - service: select.select_option
        target:
          entity_id: select.relay_mode
        data:
          option: "Proportional"
`

#### Turn Off Relay at Night

`yaml
automation:
  - alias: "Turn Off Relay at Night"
    trigger:
      - platform: time
        at: "18:00:00"
    action:
      - service: select.select_option
        target:
          entity_id: select.relay_mode
        data:
          option: "Off"
`

### Advanced Automations

#### Dynamic Mode Selection Based on Untapped Potential

`yaml
automation:
  - alias: "Dynamic Mode Selection Based on Untapped Potential"
    trigger:
      - platform: state
        entity_id: sensor.untapped_percentage
    condition:
      - condition: numeric_state
        entity_id: sensor.untapped_percentage
        above: 5
    action:
      - service: select.select_option
        target:
          entity_id: select.relay_mode
        data:
          option: >
            {% if states('sensor.untapped_percentage') | float > 50 %}
              On
            {% else %}
              Proportional
            {% endif %}
`

#### Notify When High Untapped Potential is Available

`yaml
automation:
  - alias: "Notify When High Untapped Potential is Available"
    trigger:
      - platform: numeric_state
        entity_id: sensor.untapped_percentage
        above: 70
        for:
          minutes: 5
    action:
      - service: notify.mobile_app
        data:
          title: "High Solar Potential Available"
          message: "{{ states('sensor.untapped_percentage') }}% untapped solar potential is available. Consider turning on additional loads."
`

#### Safety Shutdown on Overheating

If you have a temperature sensor on your load, you can add a safety automation:

`yaml
automation:
  - alias: "Safety Shutdown on Overheating"
    trigger:
      - platform: numeric_state
        entity_id: sensor.load_temperature
        above: 80  # Adjust based on your load's safe temperature
    action:
      - service: select.select_option
        target:
          entity_id: select.relay_mode
        data:
          option: "Off"
      - service: notify.mobile_app
        data:
          title: "Safety Shutdown Activated"
          message: "Sun Allocator Relay turned off due to high temperature ({{ states('sensor.load_temperature') }}�C)"
`

## Scripts

### Toggle Between Modes Based on Time of Day

`yaml
script:
  sun_allocator_auto_mode:
    alias: "Sun Allocator Auto Mode"
    sequence:
      - variables:
          current_hour: "{{ now().hour }}"
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ current_hour >= 9 and current_hour < 16 }}"
            sequence:
              - service: select.select_option
                target:
                  entity_id: select.relay_mode
                data:
                  option: "Proportional"
          - conditions:
              - condition: template
                value_template: "{{ current_hour >= 16 and current_hour < 18 }}"
            sequence:
              - service: select.select_option
                target:
                  entity_id: select.relay_mode
                data:
                  option: "On"
        default:
          - service: select.select_option
            target:
              entity_id: select.relay_mode
            data:
              option: "Off"
`

## Energy Dashboard Integration

To track the energy used by your Sun Allocator Relay, you can create a virtual power sensor:

`yaml
template:
  - sensor:
      - name: "Sun Allocator Relay Power"
        unit_of_measurement: "W"
        device_class: power
        state_class: measurement
        state: >
          {% set relay_power = states('sensor.relay_power') | float %}
          {% set max_load = 1000 %}  # Replace with your actual load power in watts
          {{ (relay_power / 100 * max_load) | round(0) }}
`

Then add this sensor to your Energy Dashboard to track how much excess solar energy you're utilizing.

## Troubleshooting

### Entity Not Available

If any of the entities are not available in Home Assistant:

1. Check that your ESP device is online and connected to your network
2. Verify that the ESPHome integration is properly set up
3. Restart the ESP device and Home Assistant
4. Check the ESPHome logs for any error messages

### Relay Not Responding

If the relay is not responding to commands:

1. Check the wiring between the ESP device and the relay
2. Verify that the relay is powered
3. Test the relay with a simple on/off command
4. Check the ESPHome logs for any error messages related to the relay output

### SunAllocator Sensors Not Updating

If the SunAllocator sensor values are not updating:

1. Verify that the SunAllocator component is properly set up in Home Assistant
2. Check that the sensor entities exist and are providing data
3. Restart Home Assistant
4. Check the Home Assistant logs for any error messages related to the SunAllocator component
