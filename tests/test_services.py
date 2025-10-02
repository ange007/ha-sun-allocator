"""Tests for the Sun Allocator services."""

import pytest
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sun_allocator.const import (
    DOMAIN,
    SERVICE_SET_RELAY_MODE,
    SERVICE_SET_RELAY_POWER,
    RELAY_MODE_ON,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_ENTITY,
    CONF_ESPHOME_MODE_SELECT_ENTITY,
    DOMAIN_SWITCH,
    DOMAIN_SELECT,
)


@pytest.mark.asyncio
async def test_set_relay_mode(hass: HomeAssistant) -> None:
    """Test the set_relay_mode service."""
    # Setup the component with a mock entry
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DEVICES: [
                {
                    CONF_DEVICE_ID: "test_device",
                    CONF_DEVICE_ENTITY: f"{DOMAIN_SWITCH}.test_switch",
                    CONF_ESPHOME_MODE_SELECT_ENTITY: f"{DOMAIN_SELECT}.test_select",
                }
            ]
        },
    )
    config_entry.add_to_hass(hass)

    with patch(
        "custom_components.sun_allocator.core.services.set_mode_for_entity",
        new_callable=AsyncMock,
    ) as mock_call:
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        # Verify the service is registered
        assert hass.services.has_service(DOMAIN, SERVICE_SET_RELAY_MODE)

        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_RELAY_MODE,
            {"device_id": "test_device", "mode": RELAY_MODE_ON},
            blocking=True,
        )
        await hass.async_block_till_done()

        # Verify the underlying entity was called correctly
        mock_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_relay_power(hass: HomeAssistant) -> None:
    """Test the set_relay_power service."""
    # Setup the component with a mock entry
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DEVICES: [
                {
                    CONF_DEVICE_ID: "test_device",
                    CONF_DEVICE_ENTITY: f"{DOMAIN_SWITCH}.test_switch",
                }
            ]
        },
    )
    config_entry.add_to_hass(hass)

    with patch(
        "custom_components.sun_allocator.core.services.set_power_for_entity",
        new_callable=AsyncMock,
    ) as mock_service:
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        # Verify the service is registered
        assert hass.services.has_service(DOMAIN, SERVICE_SET_RELAY_POWER)

        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_RELAY_POWER,
            {"device_id": "test_device", "power": 100},
            blocking=True,
        )
        await hass.async_block_till_done()

        # Verify the service implementation was called
        mock_service.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_relay_mode_invalid_device(hass: HomeAssistant, caplog) -> None:
    """Test the set_relay_mode service with an invalid device ID."""
    # Setup the component with a mock entry
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DEVICES: [
                {
                    CONF_DEVICE_ID: "test_device",
                    CONF_DEVICE_ENTITY: f"{DOMAIN_SWITCH}.test_switch",
                    CONF_ESPHOME_MODE_SELECT_ENTITY: f"{DOMAIN_SELECT}.test_select",
                }
            ]
        },
    )
    config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Verify the service is registered
    assert hass.services.has_service(DOMAIN, SERVICE_SET_RELAY_MODE)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_RELAY_MODE,
        {"device_id": "invalid_device", "mode": RELAY_MODE_ON},
        blocking=True,
    )
    await hass.async_block_till_done()

    # Verify that an error was logged
    assert "Config entry not found for device ID invalid_device" in caplog.text
