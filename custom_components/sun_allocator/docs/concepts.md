# Technical Concepts

This document explains the core concepts and calculations used by the SunAllocator component.

## Excess Power Calculation

The `sunallocator_excess_1` sensor calculates the untapped potential power that could be extracted from your solar panel. It is calculated as:

```
Excess = Maximum Possible Power at Current Voltage - Current Power Output
```

This value represents how many additional watts could be extracted from the panel at its current operating voltage. When this value is high, it indicates that your panel has significant untapped potential that could be utilized with additional loads.

## Understanding MPPT and Solar Panel Operation

Solar panels have a characteristic I-V (current-voltage) curve that determines their power output. The key points to understand:

1.  **Maximum Power Point (MPP)**: This is the optimal operating point where the product of voltage and current is maximized. It occurs at specific voltage (Vmp) and current (Imp) values.

2.  **Operating Regions**:
    *   **Below Vmp**: In this region, the panel operates with relatively constant current. As voltage increases, power increases approximately linearly.
    *   **At Vmp**: This is the optimal operating point where maximum power is produced.
    *   **Above Vmp**: In this region, current drops rapidly as voltage increases, causing power to decrease.

3.  **Excess Possible Indicator**: The `excess_possible` attribute is `true` when your panel's voltage exceeds Vmp. This indicates:
    *   The panel is operating in the constant-voltage region (above Vmp)
    *   Power output is likely less than optimal
    *   An MPPT controller could potentially increase power by reducing voltage to Vmp

4.  **Why it's usually "false"**: Most solar systems with MPPT controllers will operate at or below Vmp to maximize power, so `excess_possible` will typically be "false" during normal operation.

## MPPT-Based Maximum Power Calculation

The `current_max_power` value estimates the maximum power that could be extracted at the current voltage, based on Maximum Power Point Tracking (MPPT) principles. This helps you understand:

1.  How much power your panel could potentially produce at its current operating voltage
2.  Whether you're operating near the optimal voltage for maximum power
3.  How much additional power you could extract with optimal MPPT control

#### Technical Details of the MPPT Algorithm

SunAllocator uses an advanced model to estimate maximum possible power at any voltage:

1.  **Relative Voltage Calculation**:
    ```
    relative_voltage = pv_voltage / (vmp * panel_count)  # for series configuration
    relative_voltage = pv_voltage / vmp                  # for parallel configuration
    ```

2.  **Power Estimation Model**:
    *   For voltage below or at Vmp (relative_voltage ≤ 1.0):
        ```
        current_max_power = pmax * (relative_voltage * (1.0 - 0.1 * (1.0 - relative_voltage)))
        ```
        This polynomial approximation creates a slight upward curve as voltage approaches Vmp, matching real-world panel behavior.

    *   For voltage above Vmp (relative_voltage > 1.0):
        ```
        current_max_power = pmax * max(0, 1 - (1.5 * (relative_voltage - 1) ** 2))
        ```
        This quadratic model with a 1.5x drop rate factor reflects the rapid power decrease that occurs in real panels when voltage exceeds Vmp.

3.  **Panel Configuration**:
    The algorithm accounts for different panel arrangements:
    *   **Series**: Voltage adds up, current remains the same
    *   **Parallel**: Current adds up, voltage remains the same

![MPPT Power Curve](../../../mppt_algorithm_comparison.png)
*Comparison of power curves showing how the improved algorithm better matches real-world panel behavior*
