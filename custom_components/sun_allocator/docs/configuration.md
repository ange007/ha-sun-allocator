# Detailed Configuration

SunAllocator is configured through the Home Assistant UI. This document provides a detailed explanation of all the configuration parameters.

## Step 1: Solar Panel Configuration

This is the first step of the configuration process where you define your solar panel setup.

- **PV Power Sensor**: Select the sensor that measures your solar panel power output in Watts (W). This is a mandatory field.
- **PV Voltage Sensor**: Select the sensor that measures your solar panel voltage in Volts (V). This is a mandatory field.
- **Consumption Sensor** (optional): Select a sensor that measures your total house power consumption in Watts (W). This helps in understanding the overall energy flow but is not used in the core excess power calculation.
- **Panel Specifications**: These values are found on the datasheet of your solar panels.
  - **Vmp** (Voltage at Maximum Power): The voltage at which the panel produces maximum power.
  - **Imp** (Current at Maximum Power): The current at which the panel produces maximum power.
  - **Voc** (Open Circuit Voltage): The maximum voltage the panel can produce with no load. (Optional)
  - **Isc** (Short Circuit Current): The maximum current the panel can produce in a short-circuit condition. (Optional)
  - **Panel Count**: The total number of solar panels in your array.
  - **Panel Configuration**: How the panels are wired together.
    - **Series**: Voltages of the panels add up, current stays the same. The relative voltage is calculated as `pv_voltage / (vmp * panel_count)`.
    - **Parallel**: Currents of the panels add up, voltage stays the same. The relative voltage is calculated as `pv_voltage / vmp`.
    - **Parallel-Series**: A mix of both. You should calculate the equivalent `Vmp` and `Imp` for the entire array and set panel count to 1.

### Understanding the Consumption Parameter

The `consumption` parameter is an optional configuration parameter that represents the power consumption of your system in watts. It allows you to track how much of your solar power is being used versus how much is available.

- **What it represents**: The power consumption of your system, typically measured by a separate power meter or sensor.
- **How to configure it**: Add a `consumption` parameter to your configuration pointing to a sensor that measures your current power consumption.
- **Current usage**: While the consumption value is stored as an attribute and displayed in the UI, it is not directly used in the excess calculation in the current version. The excess is now calculated as the difference between the maximum possible power at current voltage and the actual power output.
- **Why it shows 0**: If you haven't specified a consumption sensor or if the specified sensor is unavailable, the consumption value will default to 0.

You can still use the consumption attribute in your own automations if needed, for example to calculate the actual excess power available after your current consumption.

## Step 2: Device Configuration

Add and configure ESPHome devices or other switchable entities to utilize excess solar energy. You can add multiple devices, each with its own priority and settings.

See the [ESPHome Integration](./esphome.md) documentation for more details on configuring devices.

## Managing Your Configuration

After initial setup, you can modify your configuration:

1. Go to **Settings → Devices & Services**
2. Find your **SunAllocator** integration
3. Click the **"CONFIGURE"** button
4. Choose from the main menu:
   - **Settings**: Modify solar panel configuration and MPPT parameters.
   - **Add Device**: Add new devices to be controlled.
   - **Manage Devices**: Edit or remove existing devices.
