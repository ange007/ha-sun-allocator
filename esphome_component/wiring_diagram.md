# Wiring Diagram for Solar Vampire Relay

## Basic Wiring

`
+---------------+                 +------------------+                 +---------------+
|               |                 |                  |                 |               |
|  ESP8266      |                 |  Solid-State     |                 |  Load         |
|  (D1 Mini)    |                 |  Relay           |                 |  (Heater,     |
|               |                 |                  |                 |   Pump, etc.) |
|               |                 |                  |                 |               |
+-------+-------+                 +--------+---------+                 +-------+-------+
        |                                  |                                   |
        |                                  |                                   |
        |         +-------------+          |                                   |
        |         |             |          |                                   |
        +-------->+ D1    Signal+----------+                                   |
        |         |             |                                              |
        |         |             |                                              |
        +-------->+ 3.3V    VCC +--+                                           |
        |         |             |  |                                           |
        |         |             |  |                                           |
        +-------->+ GND     GND +--+----------+                                |
        |         |             |  |          |                                |
        |         +-------------+  |          |                                |
        |                          |          |                                |
        |                          |          |                                |
        |                          v          v                                v
        |                     +----+----------+--------------------------------+----+
        |                     |                                                     |
        +-------------------->+ Power Supply (5V or 12V depending on relay type)    |
                              |                                                     |
                              +-----------------------------------------------------+
`

## Components

1. **ESP8266 (D1 Mini)**
   - D1: PWM signal output to relay
   - 3.3V: Power for logic circuits
   - GND: Common ground

2. **Solid-State Relay**
   - Signal: Input from ESP8266 D1 pin
   - VCC: Power supply (usually 5V or 12V)
   - GND: Common ground
   - Load terminals: Connected to the load

3. **Power Supply**
   - Provides power to both the ESP8266 and the relay
   - Typically 5V for small relays or 12V for larger ones

4. **Load**
   - The device being controlled (water heater, pump, etc.)
   - Connected to the load terminals of the relay

## Notes

- Make sure the solid-state relay is rated for the voltage and current of your load
- Use appropriate wire gauge for the load current
- Add a fuse between the power supply and the load for safety
- Consider adding a heat sink to the solid-state relay if controlling high-power loads
- For high-power applications, consider using a separate power supply for the ESP8266 and the relay

## Alternative: Using a MOSFET for Direct PWM Control

For smaller loads or more precise control, you can use a MOSFET instead of a solid-state relay:

`
+---------------+                 +------------------+                 +---------------+
|               |                 |                  |                 |               |
|  ESP8266      |                 |  MOSFET          |                 |  Load         |
|  (D1 Mini)    |                 |  (e.g., IRLZ44N) |                 |  (Heater,     |
|               |                 |                  |                 |   Pump, etc.) |
|               |                 |                  |                 |               |
+-------+-------+                 +--------+---------+                 +-------+-------+
        |                                  |                                   |
        |                                  |                                   |
        |         +-------------+          |                                   |
        |         |             |          |                                   |
        +-------->+ D1      Gate+----------+                                   |
        |         |             |                                              |
        |         |             |          +----------------------------+      |
        |         |             |          |                            |      |
        |         |             |          v                            v      v
        +-------->+ GND   Source+----------+----------------------------+------+
        |         |             |
        |         +-------------+
        |
        |                                  +------+
        |                                  |      |
        |                                  | 10K  |
        |                                  | Pull-|
        |                                  | down |
        |                                  |      |
        |                                  +--+---+
        |                                     |
        +-------------------------------------+
`

In this setup:
- The MOSFET's Gate is connected to the D1 pin of the ESP8266
- The Source is connected to ground
- The Drain is connected to the negative terminal of the load
- A 10K pull-down resistor is added between Gate and Source for safety
- The positive terminal of the load is connected to the power supply

This configuration allows for direct PWM control of the load without the need for a separate solid-state relay.
