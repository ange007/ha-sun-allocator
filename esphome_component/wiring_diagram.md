# Wiring Diagram for Sun Allocator Relay

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


---

## ESP32‑C3 DevKitM‑1 pin‑out (recommended for SSR)

- Safe/general‑purpose GPIOs for outputs: GPIO4, GPIO5, GPIO6, GPIO7
- Avoid using strapping/boot pins and the UART0 pins for outputs if possible (GPIO9/GPIO10 on some boards)
- Default examples in this repo use:
  - Single‑channel: GPIO4
  - 4‑channel: GPIO4, GPIO5, GPIO6, GPIO7

## Wemos D1 mini pin‑out (ESP8266)

- Good PWM pins: D1 (GPIO5), D2 (GPIO4), D6 (GPIO12), D7 (GPIO13)
- Default 4‑channel mapping in the example file:
  - CH1 → D1 (GPIO5)
  - CH2 → D2 (GPIO4)
  - CH3 → D6 (GPIO12)
  - CH4 → D7 (GPIO13)

## ESP‑01(S) pin‑out and boot notes

- Usable GPIOs: GPIO0 and GPIO2 only.
- Both are bootstrapping pins and must be HIGH at boot (pull-ups to 3.3 V required).
- Avoid connecting SSR inputs that pull these pins low at reset; prefer GPIO2 for single-channel builds.
- For 2-channel builds (GPIO2 + GPIO0):
  - Use a transistor/driver stage if SSR input current is non-trivial; keep boot pins high.
  - Ensure the input network does not sink current at boot (use proper base/gate resistors and pull-ups).
- Recovery note: pulling GPIO0 low at reset forces flashing mode; design hardware so device remains recoverable.

Example mappings:
- Single-channel: CH1 → GPIO2
- Two-channel: CH1 → GPIO2, CH2 → GPIO0

## Multi‑channel wiring

- Each channel is an independent output → SSR input pair
- Keep all SSR inputs referenced to ESP GND (common ground)
- For 4‑channel builds, consider powering the SSR input side separately if the required input current per channel is high; tie grounds together

## AC vs DC SSR (control method)

- AC zero‑cross SSR:
  - Use slow_pwm in ESPHome with period 1.0–2.0 s (see example YAMLs for ESP32‑C3)
  - This modulates the averaged power safely across mains half‑cycles
- DC SSR / MOSFET driver:
  - Use fast PWM (esp8266_pwm on ESP8266, ledc on ESP32) at ~1 kHz (see example YAMLs)

## Safety and best practices

- Mains AC is dangerous — use proper enclosures, fuses, RCD/RCBO, and adequate heatsinking for SSRs
- Verify SSR input current; add a transistor driver if ESP pin cannot source enough current
- Use appropriately rated wires and terminal blocks; derate SSRs (heatsink!) for continuous loads
- Provide strain relief and isolation distances between low‑voltage and mains wiring
