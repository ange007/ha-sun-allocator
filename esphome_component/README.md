# SunAllocator Relay ESPHome Component

This ESPHome component controls a solid-state relay based on the untapped potential data from the SunAllocator Home Assistant integration. It allows you to utilize excess solar energy by dynamically adjusting power to a load.

## Features

- **Two Operation Modes**:
  - **On/Off Mode**: Simply turns the relay on or off
  - **Proportional Mode**: Adjusts the power to the relay based on the percentage of untapped potential

- **Real-time Monitoring**:
  - Connects to Home Assistant to get SunAllocator sensor values
  - Calculates percentage of untapped potential
  - Displays current status and power level

- **Automatic Adjustment**:
  - Updates relay power every 10 seconds in proportional mode
  - Only activates when untapped potential exceeds 5%

## Hardware Requirements

- ESP8266 or ESP32 board (example uses D1 Mini)
- Solid-state relay with PWM control capability
- Power supply for the ESP board
- Wiring to connect the relay to the load

## Installation

1. Install ESPHome in your Home Assistant instance if not already installed
2. Create a new ESPHome device using the provided YAML configuration
3. Customize the configuration as needed for your specific setup
4. Flash the firmware to your ESP device
5. Connect the solid-state relay to the specified GPIO pin (default: D1)

## Configuration

The default configuration uses the following pins:
- D1: PWM output to control the solid-state relay

You can modify the configuration to use different pins or adjust other parameters:

`yaml
# Define the solid-state relay output
output:
  - platform: esp8266_pwm
    id: relay_output
    pin: D1  # Change this to your preferred GPIO pin
    frequency: 1000Hz  # Adjust PWM frequency if needed
`

## Usage

After installation, you'll have the following entities in Home Assistant:

- **Light Entity**: light.sunallocator_relay - Used to manually control the relay
- **Select Entity**: select.sunallocator_mode — Off / On / Proportional
- **Sensor Entities**:
  - sensor.untapped_potential - Shows the current untapped potential from SunAllocator
  - sensor.max_power - Shows the maximum power from SunAllocator
  - sensor.untapped_percentage - Shows the percentage of untapped potential
- **Text Sensor**: 	ext_sensor.relay_status - Shows the current status and power level

### Operation Modes

1. **Off**: The relay is turned off completely
2. **On**: The relay is turned on at full power (100%)
3. **Proportional**: The relay power is adjusted proportionally to the untapped potential percentage

In proportional mode, the relay will automatically adjust its power level every 10 seconds based on the current untapped potential. If the untapped potential is less than 5%, the relay will turn off.

## Integration with Home Assistant Automations

You can create automations in Home Assistant to control the relay mode based on various conditions:

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

## Troubleshooting

- If the relay is not responding, check the wiring and ensure the ESP device is connected to your network
- Verify that the SunAllocator sensors are available and providing data
- Check the ESPHome logs for any error messages
- Make sure the solid-state relay supports PWM control for proportional mode

## Advanced Configuration

For advanced users, you can modify the C++ code to customize the behavior of the component:

- Adjust the PWM frequency for better compatibility with your relay
- Change the minimum threshold for activation in proportional mode
- Implement custom control algorithms based on your specific needs


---

## What’s new (2025‑08)
- Added ready‑to‑use multi‑channel examples:
  - esphome_component/sun_allocator_relay_multi_d1.yaml (Wemos D1 mini, 4 channels)
  - esphome_component/sun_allocator_relay_multi_c3.yaml (ESP32‑C3 DevKitM‑1, 4 channels)
- Added ESP32‑C3 single‑channel preset: esphome_component/sun_allocator_relay_c3.yaml
- Added ESP‑01 presets:
  - esphome_component/sun_allocator_relay_esp01.yaml (single channel on GPIO2)
  - esphome_component/sun_allocator_relay_esp01_2ch.yaml (two channels on GPIO2 + GPIO0)
- Entity naming updated for better Home Assistant discovery in Sun Allocator options flow:
  - Select entity name now contains "SunAllocator" (e.g., "SunAllocator Mode"), so entity_id becomes select.sunallocator_mode (or select.sunallocator_mode_1 for multi‑channel).
- AC vs DC SSR tuning guidance added (slow_pwm vs fast PWM).

## Pin‑out quick reference
- Wemos D1 mini (ESP8266):
  - Good PWM pins: D1 (GPIO5), D2 (GPIO4), D6 (GPIO12), D7 (GPIO13)
  - Example mappings used in 4‑channel file.
- ESP32‑C3 DevKitM‑1:
  - Recommended GPIOs for outputs: GPIO4, GPIO5, GPIO6, GPIO7
  - Default single‑channel uses GPIO4.
- ESP‑01(S):
  - Usable GPIOs: GPIO0 and GPIO2 only (both must be HIGH at boot; keep pulled up).
  - Avoid loading these pins low at boot. Prefer GPIO2 for single‑channel; for 2‑channel use a transistor/driver stage if SSR input current is high.

## AC vs DC SSR (tuning)
- AC zero‑cross SSRs (most mains AC SSR):
  - Use slow_pwm with a period around 1.0–2.0 s for smooth average power control.
  - See examples: sun_allocator_relay_c3.yaml, sun_allocator_relay_multi_c3.yaml.
- DC SSR or MOSFET drivers (DC loads):
  - Use fast PWM (esp8266_pwm on ESP8266, ledc on ESP32) at ~1 kHz.
  - See examples: sun_allocator_relay.yaml, sun_allocator_relay_multi_d1.yaml.

## Choosing a YAML
- Single channel (D1 mini, DC): esphome_component/sun_allocator_relay.yaml
- Single channel (ESP32‑C3, AC by default): esphome_component/sun_allocator_relay_c3.yaml
- Single channel (ESP‑01, DC by default): esphome_component/sun_allocator_relay_esp01.yaml
- 2 channels (ESP‑01, DC by default — see boot cautions): esphome_component/sun_allocator_relay_esp01_2ch.yaml
- 4 channels (D1 mini): esphome_component/sun_allocator_relay_multi_d1.yaml
- 4 channels (ESP32‑C3): esphome_component/sun_allocator_relay_multi_c3.yaml

## Home Assistant entities
- Single‑channel examples create:
  - light.sunallocator_relay (or light.sunallocator_relay_1)
  - select.sunallocator_mode (or select.sunallocator_mode_1)
- Multi‑channel examples create per‑channel entities:
  - light.sunallocator_relay_1..4 and select.sunallocator_mode_1..4
- Modes supported by the select: Off / On / Proportional.
  - In Proportional mode, Sun Allocator integration sets brightness via standard light.turn_on, so the YAML doesn’t change brightness locally to avoid conflicts.

## Safety notes
- Mains AC is dangerous. Use proper enclosures, fuses, RCD/RCBO, and adequate heatsinking for SSRs.
- Check SSR input current requirements; some may need a transistor driver if ESP pin cannot supply enough current.
