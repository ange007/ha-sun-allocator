"""Constants for the Sun Allocator integration."""

DOMAIN = "sun_allocator"

# Service constants
SERVICE_SET_RELAY_MODE = "set_relay_mode"
SERVICE_SET_RELAY_POWER = "set_relay_power"

# Relay modes
RELAY_MODE_OFF = "Off"
RELAY_MODE_ON = "On"
RELAY_MODE_PROPORTIONAL = "Proportional"

# --- Configuration Keys ---
# These constants are used as keys in configuration dictionaries.

# Solar panel configuration keys
CONF_PV_POWER = "pv_power"
CONF_PV_VOLTAGE = "pv_voltage"
CONF_CONSUMPTION = "consumption"
CONF_BATTERY_POWER = "battery_power"
CONF_BATTERY_POWER_REVERSED = "battery_power_reversed"
CONF_PANEL_VMP = "vmp"
CONF_PANEL_IMP = "imp"
CONF_PANEL_VOC = "voc"
CONF_PANEL_ISC = "isc"
CONF_PANEL_COUNT = "panel_count"
CONF_PANEL_CONFIGURATION = "panel_configuration"

# Device configuration keys
CONF_DEVICES = "devices"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_ENTITY = "device_entity"
CONF_ESPHOME_MODE_SELECT_ENTITY = "esphome_mode_select_entity"
CONF_DEVICE_ENTITY_FRIENDLY_NAME = "device_entity_friendly_name"
CONF_AUTO_CONTROL_ENABLED = "auto_control_enabled"
CONF_DEVICE_MIN_EXCESS_POWER = "min_excess_power"
CONF_DEVICE_MIN_ON_TIME = "min_on_time"
CONF_DEVICE_TYPE = "device_type"
CONF_DEVICE_MIN_EXPECTED_W = "min_expected_w"
CONF_DEVICE_MAX_EXPECTED_W = "max_expected_w"
CONF_DEVICE_DEBOUNCE_TIME = "debounce_time"
CONF_DEVICE_PRIORITY = "priority"

# Scheduling constants
CONF_DEVICE_SCHEDULE_ENABLED = "schedule_enabled"
CONF_START_TIME = "start_time"
CONF_END_TIME = "end_time"
CONF_DAYS_OF_WEEK = "days_of_week"

# Advanced settings constants
CONF_ADVANCED_SETTINGS_ENABLED = "advanced_settings_enabled"
CONF_RESERVE_BATTERY_POWER = "reserve_battery_power"
CONF_INVERTER_SELF_CONSUMPTION = "inverter_self_consumption"
CONF_DEVICE_ALLOCATION_STRATEGY = "device_allocation_strategy"
CONF_MIN_INVERTER_VOLTAGE = "min_inverter_voltage"
CONF_RAMP_UP_STEP = "ramp_up_step"
CONF_RAMP_DOWN_STEP = "ramp_down_step"
CONF_RAMP_DEADBAND = "ramp_deadband"
CONF_HYSTERESIS_W = "hysteresis_w"
CONF_CURVE_FACTOR_K = "curve_factor_k"
CONF_EFFICIENCY_CORRECTION_FACTOR = "efficiency_correction_factor"

# Temperature compensation constants
CONF_TEMPERATURE_COMPENSATION_ENABLED = "temperature_compensation_enabled"
CONF_TEMPERATURE_SENSOR = "temperature_sensor"
CONF_TEMP_COEFFICIENT_VOC = "temp_coefficient_voc"
CONF_TEMP_COEFFICIENT_PMAX = "temp_coefficient_pmax"

# --- Default & Internal Values ---
# These constants define default values for settings and internal algorithm parameters.

DEFAULT_DEBOUNCE_TIME = 15
DEFAULT_HYSTERESIS_W = 40.0

# Internal MPPT algorithm constants (not user-configurable)
INTERNAL_CURVE_FACTOR_K = 0.2
INTERNAL_EFFICIENCY_CORRECTION_FACTOR = 1.05

# Proportional strategy options
STRATEGY_FILL_ONE_BY_ONE = "fill"
STRATEGY_DISTRIBUTE_EVENLY = "distribute"

# Other internal constants
PASSIVE_CHARGING_THRESHOLD_W = 50
MAX_BRIGHTNESS = 255
MIN_BRIGHTNESS = 0
MAX_PERCENTAGE = 100
MIN_PERCENTAGE = 0

# --- Static Options & Keys ---
# These constants are for lists of options, dictionary keys, etc.

# Dictionary keys for temperature compensation
KEY_TEMP_DIFF = "temp_diff"
KEY_VOC_COEF = "voc_coef"
KEY_PMAX_COEF = "pmax_coef"

# Device type options
DEVICE_TYPE_NONE = "none"
DEVICE_TYPE_STANDARD = "standard"
DEVICE_TYPE_CUSTOM = "custom"
DEVICE_TYPE_CLIMATE = "climate"

# Panel configuration options
PANEL_CONFIG_SERIES = "series"
PANEL_CONFIG_PARALLEL = "parallel"
PANEL_CONFIG_PARALLEL_SERIES = "parallel-series"

# Days of week
DAY_MONDAY = "monday"
DAY_TUESDAY = "tuesday"
DAY_WEDNESDAY = "wednesday"
DAY_THURSDAY = "thursday"
DAY_FRIDAY = "friday"
DAY_SATURDAY = "saturday"
DAY_SUNDAY = "sunday"
DAYS_OF_WEEK = [
    DAY_MONDAY,
    DAY_TUESDAY,
    DAY_WEDNESDAY,
    DAY_THURSDAY,
    DAY_FRIDAY,
    DAY_SATURDAY,
    DAY_SUNDAY,
]

# Power distribution dictionary keys
CONF_POWER_ALLOCATION = "power_allocation"
CONF_POWER_DISTRIBUTION = "power_distribution"

# Dispatcher signal names
SIGNAL_POWER_DISTRIBUTION_UPDATED = "sunallocator_power_distribution_updated"

# Configuration flow steps
STEP_USER = "user"
STEP_DEVICES = "devices"
STEP_DEVICE_CONFIG = "device_config"
STEP_DEVICE_NAME_TYPE = "device_name_type"
STEP_DEVICE_SELECTION = "device_selection"
STEP_DEVICE_BASIC_SETTINGS = "device_basic_settings"
STEP_DEVICE_SCHEDULE = "device_schedule"
STEP_MAIN_MENU = "main_menu"
STEP_SETTINGS = "settings"
STEP_MANAGE_DEVICES = "manage_devices"
STEP_TEMPERATURE_COMPENSATION = "temperature_compensation"
STEP_ADVANCED_SETTINGS = "advanced_settings"
STEP_CONFIRM_REMOVE = "confirm_remove"

# Configuration flow actions
ACTION_ADD = "add"
ACTION_EDIT = "edit"
ACTION_REMOVE = "remove"
ACTION_SETTINGS = "settings"
ACTION_ADD_DEVICE = "add_device"
ACTION_MANAGE_DEVICES = "manage_devices"
ACTION_FINISH = "finish"
ACTION_BACK = "back"

# Configuration field constants
CONF_ACTION = "action"
CONF_CONFIRM = "confirm"

# UI constants
NONE_OPTION = "None"

# Sensor naming constants
SENSOR_NAME_PREFIX = "SunAllocator"
SENSOR_ID_PREFIX = "sunallocator"
SENSOR_EXCESS_SUFFIX = "excess"
SENSOR_MAX_POWER_SUFFIX = "max_power"
SENSOR_CURRENT_MAX_POWER_SUFFIX = "current_max_power"
SENSOR_USAGE_PERCENT_SUFFIX = "usage_percent"
SENSOR_POWER_DISTRIBUTION_SUFFIX = "power_distribution"

# Temperature compensation defaults
DEFAULT_STANDARD_TEMPERATURE = 25.0
DEFAULT_VOC_COEFFICIENT = -0.3
DEFAULT_PMAX_COEFFICIENT = -0.4

# Entity state constants
STATE_ON = "on"
STATE_OFF = "off"

# Home Assistant domain constants
DOMAIN_LIGHT = "light"
DOMAIN_SWITCH = "switch"
DOMAIN_SELECT = "select"
DOMAIN_INPUT_BOOLEAN = "input_boolean"
DOMAIN_AUTOMATION = "automation"
DOMAIN_SCRIPT = "script"
DOMAIN_CLIMATE = "climate"

# Dictionary keys for debug info
KEY_PMAX = "pmax"
KEY_ENERGY_HARVESTING_POSSIBLE = "energy_harvesting_possible"
KEY_MIN_SYSTEM_VOLTAGE = "min_system_voltage"
KEY_LIGHT_FACTOR = "light_factor"
KEY_RELATIVE_VOLTAGE = "relative_voltage"
KEY_VOC_RATIO = "voc_ratio"
KEY_CALCULATION_REASON = "calculation_reason"
