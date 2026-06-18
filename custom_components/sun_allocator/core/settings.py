"""Centralized settings and advanced parameters for SunAllocator."""

# Logging
LOG_STARTUP_DEVICES = True
LOG_DEVICE_ACTIONS = True

# Journal/Audit
ENABLE_JOURNAL = True
ENABLE_AUDIT = True

# Default timing and thresholds
WATCHDOG_STALE_AFTER_MINUTES = 3
WATCHDOG_PERIOD_SECONDS = 60
# Hard cap on a single HA service call. Keeps blocking=True (needed so the
# retry/reconciliation path knows a command completed) without letting one slow
# or hung device stall the whole allocation loop indefinitely.
SERVICE_CALL_TIMEOUT_SECONDS = 30
RAMP_INTERVAL_SECONDS = 5
RAMP_UP_STEP_DEFAULT = 10.0
RAMP_DOWN_STEP_DEFAULT = 20.0
RAMP_DEADBAND_DEFAULT = 1.0
DEVICE_MAX_PERCENT_DEFAULT = 90.0

# Counter-debounce: when a debounced state change reverts back to the original
# state, this fraction of the configured debounce time must pass on the reverted
# side before the in-progress debounce is cancelled. Avoids flicker on signals
# that keep oscillating across the threshold (e.g. kettle cycling).
COUNTER_DEBOUNCE_FRACTION = 0.5

# Other advanced settings can be added here
