"""Tests for the Sun Allocator watchdog functionality."""

from datetime import timedelta

import pytest
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
import homeassistant.util.dt as dt_util


from custom_components.sun_allocator.const import (
    DOMAIN,
    CONF_PV_POWER,
    CONF_PV_VOLTAGE,
    CONF_VMP,
    CONF_IMP,
    CONF_PANEL_COUNT,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_TYPE,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_MIN_EXPECTED_W,
    CONF_DEBOUNCE_TIME,
    CONF_MIN_INVERTER_VOLTAGE,
    DEVICE_TYPE_STANDARD,
    CONF_DEFAULT_MIN_START_W,
    CONF_HYSTERESIS_W,
    SENSOR_ID_PREFIX,
    SENSOR_EXCESS_SUFFIX,
)
from custom_components.sun_allocator import async_setup_entry, async_unload_entry
from custom_components.sun_allocator.core.watchdog import watchdog_check


@pytest.fixture
def patch_time(freezer, monkeypatch):
    """Patch time for watchdog tests."""
    monkeypatch.setattr(
        dt_util, "utcnow", lambda: freezer.time_to_freeze.replace(tzinfo=dt_util.UTC)
    )
    monkeypatch.setattr(
        dt_util, "now", lambda: freezer.time_to_freeze.replace(tzinfo=dt_util.UTC)
    )


@pytest.fixture
async def setup_watchdog_test(hass: HomeAssistant):
    """Set up the watchdog test environment."""
    await async_setup_component(hass, "switch", {})

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_PV_POWER: "sensor.test_pv_power",
            CONF_PV_VOLTAGE: "sensor.test_pv_voltage",
            CONF_VMP: 30.0,
            CONF_IMP: 10.0,
            CONF_PANEL_COUNT: 1,
            CONF_MIN_INVERTER_VOLTAGE: 10.0,
            CONF_DEFAULT_MIN_START_W: 0,
            CONF_HYSTERESIS_W: 20,
            CONF_DEVICES: [
                {
                    CONF_DEVICE_ID: "test_device",
                    CONF_DEVICE_ENTITY: "switch.test_switch",
                    CONF_DEVICE_TYPE: DEVICE_TYPE_STANDARD,
                    CONF_AUTO_CONTROL_ENABLED: True,
                    CONF_MIN_EXPECTED_W: 50,
                    CONF_DEBOUNCE_TIME: 0,
                }
            ],
        },
        entry_id="test_entry_id",
    )
    config_entry.add_to_hass(hass)

    hass.states.async_set("sensor.test_pv_power", "250")
    hass.states.async_set("sensor.test_pv_voltage", "35")
    hass.states.async_set("switch.test_switch", "on")  # Ensure it's on initially

    await async_setup_entry(hass, config_entry)
    await hass.async_block_till_done()

    yield config_entry

    # Cleanup
    await async_unload_entry(hass, config_entry)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_watchdog_enforces_off_on_stale_sensor(
    hass: HomeAssistant, freezer, setup_watchdog_test, patch_time
) -> None:
    """Test that the watchdog enforces OFF when the excess sensor is stale."""
    config_entry = setup_watchdog_test

    with patch(
        "homeassistant.core.ServiceRegistry.async_call", new_callable=AsyncMock
    ) as mock_async_call:
        # Create excess sensor to be tracked
        excess_sensor_id = (
            f"sensor.{SENSOR_ID_PREFIX}_{SENSOR_EXCESS_SUFFIX}_{config_entry.entry_id}"
        )
        hass.states.async_set(excess_sensor_id, "100")
        await hass.async_block_till_done()

        # Reset mocks as calls might have occurred during setup
        mock_async_call.reset_mock()

        # Advance time beyond watchdog_stale_after (3 minutes + some buffer)
        future_time = dt_util.utcnow() + timedelta(minutes=3, seconds=10)
        freezer.move_to(future_time)

        # Call watchdog explicitly
        await watchdog_check(hass, config_entry)
        await hass.async_block_till_done()

        # Assert that turn_off was called
        mock_async_call.assert_called_once_with(
            "switch", "turn_off", {"entity_id": "switch.test_switch"}, blocking=True
        )

        # Manually update state since we're mocking
        hass.states.async_set("switch.test_switch", "off")
        assert hass.states.get("switch.test_switch").state == "off"


@pytest.mark.asyncio
async def test_watchdog_does_not_enforce_off_on_fresh_sensor(
    hass: HomeAssistant, freezer, setup_watchdog_test, patch_time
) -> None:
    """Test that the watchdog does not enforce OFF when the excess sensor is fresh."""
    config_entry = setup_watchdog_test

    with patch(
        "homeassistant.core.ServiceRegistry.async_call", new_callable=AsyncMock
    ) as mock_async_call:
        # Ensure initial state is as expected and reset mock
        assert hass.states.get("switch.test_switch").state == "on"
        mock_async_call.reset_mock()

        future_time = dt_util.utcnow() + timedelta(minutes=2)
        freezer.move_to(future_time)
        await watchdog_check(hass, config_entry)
        await hass.async_block_till_done()

        # Assert that _enforce_all_off was NOT called
        mock_async_call.assert_not_called()


@pytest.mark.asyncio
async def test_watchdog_resets_on_sensor_update(
    hass: HomeAssistant, freezer, setup_watchdog_test, patch_time
) -> None:
    """Test that the watchdog resets when the sensor updates after being stale."""
    config_entry = setup_watchdog_test

    with patch(
        "homeassistant.core.ServiceRegistry.async_call", new_callable=AsyncMock
    ) as mock_async_call:
        # Ensure initial state is as expected and reset mock
        assert hass.states.get("switch.test_switch").state == "on"
        mock_async_call.reset_mock()

        # Advance time beyond watchdog_stale_after
        future_time = dt_util.utcnow() + timedelta(minutes=3, seconds=10)
        freezer.move_to(future_time)

        # Call watchdog explicitly
        await watchdog_check(hass, config_entry)
        await hass.async_block_till_done()

        # Assert that _enforce_all_off was called
        mock_async_call.assert_called_once_with(
            "switch", "turn_off", {"entity_id": "switch.test_switch"}, blocking=True
        )
        hass.states.async_set("switch.test_switch", "off")
        assert hass.states.get("switch.test_switch").state == "off"

        # Simulate sensor update
        mock_async_call.reset_mock()
        hass.states.async_set("sensor.test_pv_power", "260")
        hass.states.async_set("sensor.test_pv_voltage", "36")
        await hass.async_block_till_done()

        # Advance time again, watchdog should not trigger OFF
        future_time = dt_util.utcnow() + timedelta(minutes=2)
        freezer.move_to(future_time)
        await watchdog_check(hass, config_entry)
        await hass.async_block_till_done()

        mock_async_call.assert_not_called()
