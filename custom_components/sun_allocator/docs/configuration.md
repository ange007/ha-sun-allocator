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

### Main Sensors
- **PV Power Sensor**: (Required) The sensor that measures your solar panel power output in Watts (W).
- **PV Voltage Sensor**: (Required for MPPT mode) The sensor that measures your solar panel voltage in Volts (V). This is required if you are not using a house consumption sensor.
- **Consumption Sensor**: (Optional) The sensor that measures your total house power consumption in Watts (W). When this sensor is provided, the integration will operate in **Parallel Mode**. If not provided, it will operate in **MPPT Mode**.
- **Battery Power Sensor**: (Optional) The sensor that measures your battery power in Watts (W). This is used to determine if the battery is charging or discharging.
- **Is Battery Power Reversed?**: (Optional) Enable this if your battery power sensor shows a positive value for discharging and a negative value for charging. By default, the integration assumes negative values for discharging and positive for charging.

### Solar Panel Specifications
These values are found on the datasheet of your solar panels.

- **Vmp (Voltage at Maximum Power)**: The voltage at which a single panel produces maximum power.
- **Imp (Current at Maximum Power)**: The current at which a single panel produces maximum power.
- **Voc (Open Circuit Voltage)**: The maximum voltage a single panel can produce with no load.
- **Isc (Short Circuit Current)**: The maximum current a single panel can produce in a short-circuit condition.
- **Panel Count**: The total number of solar panels in your array.
- **Panel Configuration**: How the panels are wired together.
  - **Series**: Panels are connected end-to-end. The total voltage is the sum of the individual panel voltages, while the current remains the same.
  - **Parallel**: Panels are connected side-by-side. The total current is the sum of the individual panel currents, while the voltage remains the same.
  - **Parallel-Series**: A combination of both.

---

## Manage Devices

In this section, you can add, edit, or remove the devices (loads) that you want to control with your excess solar power.

### Device Settings
- **Device Name**: A friendly name for the device.
- **Device Type**:
  - **Standard**: An on/off device, like a switch, light, or input boolean.
  - **Custom (ESPHome)**: A device that can handle proportional power, typically a dimmer or a custom ESPHome component. This allows the integration to send a percentage of power to the device.
- **Device Entity**: The Home Assistant entity that represents your device.
- **Min Expected (W)**: (Required) The minimum power in Watts the device consumes when it's on. This is used to determine if the device is actually running.
- **Max Expected (W)**: (Required for Custom devices) The maximum power in Watts the device consumes at 100% load. This is used for proportional control.
- **Priority**: A number from 1 to 100 that determines the order in which devices are turned on. Devices with higher priority are turned on first.
- **Debounce Time (s)**: The time in seconds the system will wait before turning a device on or off. This prevents the device from rapidly switching on and off.
- **Min On-Time (s)**: The minimum time in seconds that the device must remain on before it can be turned off. This is useful for appliances like compressors or pumps that should not be cycled on and off rapidly.
- **Auto-Control**: Enable or disable automatic control for this device.
- **Enable Schedule**: Enable or disable a schedule for this device.

### Schedule Settings
If `Enable Schedule` is checked, you can define a time window and days of the week during which the device is allowed to be controlled by SunAllocator.
- **Start Time**: The time when the schedule starts.
- **End Time**: The time when the schedule ends.
- **Days of the Week**: Select the days when the schedule is active.

---

## Temperature Compensation

This feature allows the integration to adjust the solar panel's maximum power point (MPP) based on the ambient temperature, as the panel's efficiency is affected by it.

- **Temperature Sensor**: The sensor that measures the ambient temperature in Celsius (°C).
- **Voc Temp Coefficient (%/°C)**: The temperature coefficient of the open-circuit voltage (Voc), found on the panel's datasheet. It's usually a negative percentage.
- **Pmax Temp Coefficient (%/°C)**: The temperature coefficient of the maximum power (Pmax), also found on the panel's datasheet. It's also typically a negative percentage.

---

## Advanced Settings

This section allows you to fine-tune the behavior of the power allocation algorithm.

- **Reserve Battery Power (W)**: A certain amount of power to be reserved and not used by the allocator. This is useful if you want to ensure your battery is charging with a minimum power.
- **Inverter Self-Consumption (W)**: The amount of power the inverter itself consumes for its operation. This value is subtracted from the available solar power, providing a more accurate calculation of the real excess power. You can find this value in your inverter's datasheet or measure it.
- **Proportional Allocation Strategy**: Defines how power is allocated to multiple proportional devices.
  - **Fill one by one**: The highest priority device is allocated as much power as it needs, then the next device gets power from what is left, and so on.
  - **Distribute evenly**: The available power is distributed among all active proportional devices based on their `Max Expected (W)`.
- **Min Inverter Voltage**: The minimum voltage required for the inverter to operate.
- **Ramp Up Step (%)**: The percentage by which the power is increased for proportional devices in each step.
- **Ramp Down Step (%)**: The percentage by which the power is decreased for proportional devices in each step.
- **Ramp Deadband (%)**: A small range around the target power where no changes are made, to prevent oscillations.
- **Hysteresis (W)**: A power buffer to prevent devices from turning on and off too frequently. A device will turn on at its configured minimum power and turn off at `Minimum Power - Hysteresis`.