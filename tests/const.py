MOCK_CONFIG_WITH_DEVICES = {
    "pv_power": "sensor.pv_power",
    "pv_voltage": "sensor.pv_voltage",
    "consumption": "sensor.consumption",
    "battery_power": "sensor.battery_power",
    "battery_power_reversed": False,
    "vmp": 30.0,
    "imp": 8.0,
    "voc": 36.0,
    "isc": 9.0,
    "panel_count": 1,
    "panel_configuration": "series",
    "devices": [
        {
            "device_id": "test_device_1",
            "device_name": "Test Device 1",
            "device_entity": "switch.test_switch_1",
            "priority": 50,
            "min_expected_w": 10,
            "max_expected_w": 100,
            "debounce_time": 30,
            "auto_control_enabled": True,
            "schedule_enabled": False,
        }
    ],
}
