# Solar Vampire Relay ESPHome Component

This ESPHome component controls a solid-state relay based on the untapped potential data from the SolarVampire Home Assistant component. It allows you to utilize excess solar energy by dynamically adjusting power to a load.

## Features

- **Two Operation Modes**:
  - **On/Off Mode**: Simply turns the relay on or off
  - **Proportional Mode**: Adjusts the power to the relay based on the percentage of untapped potential

- **Real-time Monitoring**:
  - Connects to Home Assistant to get SolarVampire sensor values
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

- **Light Entity**: light.solar_vampire_relay - Used to manually control the relay
- **Select Entity**: select.relay_mode - Choose between Off, On, and Proportional modes
- **Sensor Entities**:
  - sensor.untapped_potential - Shows the current untapped potential from SolarVampire
  - sensor.max_power - Shows the maximum power from SolarVampire
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
- Verify that the SolarVampire sensors are available and providing data
- Check the ESPHome logs for any error messages
- Make sure the solid-state relay supports PWM control for proportional mode

## Advanced Configuration

For advanced users, you can modify the C++ code to customize the behavior of the component:

- Adjust the PWM frequency for better compatibility with your relay
- Change the minimum threshold for activation in proportional mode
- Implement custom control algorithms based on your specific needs
