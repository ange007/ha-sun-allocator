import pytest
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.sun_allocator import async_setup_entry, async_unload_entry
from custom_components.sun_allocator.const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_DEVICE_ID,
    ACTION_MANAGE_DEVICES,
    ACTION_REMOVE,
    CONF_CONFIRM,
)

from conftest import create_test_config_entry
from tests.const import MOCK_DEVICES


@pytest.mark.asyncio
async def test_device_removal(hass: HomeAssistant):
    """Test that removing a device also removes it from the device registry."""
    # Setup the component with a mock config entry
    config_entry = create_test_config_entry(
        {
            CONF_DEVICES: MOCK_DEVICES,
        }
    )

    hass.config_entries._entries[config_entry.entry_id] = config_entry

    await async_setup_entry(hass, config_entry)
    await hass.async_block_till_done()

    # Get the device registry
    device_registry = dr.async_get(hass)

    # Get the device we want to remove
    device_id_to_remove = MOCK_DEVICES[0][CONF_DEVICE_ID]
    device_entry = device_registry.async_get_device(
        identifiers={(DOMAIN, device_id_to_remove)}
    )
    assert device_entry is not None

    # Start the options flow
    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    # Go to the manage devices step
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"action": ACTION_MANAGE_DEVICES}
    )

    # Select the device to remove and the "remove" action
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"action": ACTION_REMOVE, CONF_DEVICE_ID: device_id_to_remove},
    )

    # Confirm the removal
    with patch(
        "custom_components.sun_allocator.config.async_get_options_flow",
        return_value=True,
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={CONF_CONFIRM: True}
        )
        await hass.async_block_till_done()

    # Check that the device is gone from the registry
    device_entry = device_registry.async_get_device(
        identifiers={(DOMAIN, device_id_to_remove)}
    )
    assert device_entry is None

    # Unload the config entry
    await async_unload_entry(hass, config_entry)
    await hass.async_block_till_done()
