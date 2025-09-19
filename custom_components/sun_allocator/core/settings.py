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
RAMP_INTERVAL_SECONDS = 5
RAMP_UP_STEP_DEFAULT = 10.0
RAMP_DOWN_STEP_DEFAULT = 20.0
RAMP_DEADBAND_DEFAULT = 1.0
DEVICE_MAX_PERCENT_DEFAULT = 90.0

# Other advanced settings can be added here
