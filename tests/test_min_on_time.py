from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.core import HomeAssistant, State
from homeassistant.util import dt as dt_util

from conftest import create_test_config_entry
from custom_components.sun_allocator.const import (
    DOMAIN,
    CONF_DEVICE_ID,
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_TYPE,
    CONF_AUTO_CONTROL_ENABLED,
    CONF_DEVICE_MIN_EXPECTED_W,
    CONF_DEVICE_MIN_ON_TIME,
    CONF_DEVICE_DEBOUNCE_TIME,
    DEVICE_TYPE_STANDARD,
)
from custom_components.sun_allocator.core.power_processor import process_excess_power


def _make_mock_hass() -> HomeAssistant:
    """Create a minimal Home Assistant double for allocator unit tests."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {}

    states = {}

    def get_state(entity_id):
        return states.get(entity_id)

    def set_state(entity_id, state):
        states[entity_id] = State(entity_id, state)

    hass.states = MagicMock()
    hass.states.get = get_state
    hass.states.async_set = set_state
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    def create_task(coro, *_args, **_kwargs):
        coro.close()
        return None

    hass.async_create_task = create_task
    return hass


@pytest.mark.asyncio
async def test_minimum_on_time_and_refusal_reason(freezer, monkeypatch) -> None:
    """Test minimum on-time logic and diagnostic refusal reasons."""
    hass = _make_mock_hass()
    monkeypatch.setattr(
        dt_util, "now", lambda: freezer.time_to_freeze.replace(tzinfo=dt_util.UTC)
    )

    entity_id = "switch.test_min_on_time"

    config_data = {
        "devices": [
            {
                CONF_DEVICE_ID: "test_min_on_time",
                CONF_DEVICE_ENTITY: entity_id,
                CONF_DEVICE_TYPE: DEVICE_TYPE_STANDARD,
                CONF_AUTO_CONTROL_ENABLED: True,
                CONF_DEVICE_MIN_EXPECTED_W: 10,
                CONF_DEVICE_MIN_ON_TIME: 2,
                CONF_DEVICE_DEBOUNCE_TIME: 0,
            }
        ],
    }
    config_entry = create_test_config_entry(
        extra_data=config_data,
        entry_id="test_min_on_time_entry",
    )
    hass.data[DOMAIN] = {config_entry.entry_id: {"power_allocation": {}}}
    hass.states.async_set(entity_id, "off")

    with (
        patch(
            "custom_components.sun_allocator.core.power_processor.turn_on_entity",
            new_callable=AsyncMock,
        ) as mock_turn_on,
        patch(
            "custom_components.sun_allocator.core.power_processor.turn_off_entity",
            new_callable=AsyncMock,
        ) as mock_turn_off,
    ):
        freezer.move_to(datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt_util.UTC))
        await process_excess_power(hass, config_entry, 20)

        mock_turn_on.assert_awaited_once_with(
            hass,
            entity_id,
            None,
            None,
        )
        hass.states.async_set(entity_id, "on")

        freezer.move_to(datetime(2026, 1, 1, 12, 0, 1, tzinfo=dt_util.UTC))
        await process_excess_power(hass, config_entry, 0)

        entry_data = hass.data[DOMAIN][config_entry.entry_id]
        status = entry_data["device_status"]["test_min_on_time"]
        assert entry_data["device_on_state"]["test_min_on_time"] is True
        mock_turn_off.assert_not_awaited()
        assert any(
            "Minimum on-time" in reason
            for reason in status.get("refusal_reasons", [])
        )

        freezer.move_to(datetime(2026, 1, 1, 12, 0, 3, tzinfo=dt_util.UTC))
        await process_excess_power(hass, config_entry, 0)

        mock_turn_off.assert_awaited_once_with(hass, entity_id, None)