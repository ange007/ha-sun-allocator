"""Tests for the per-device ``check_usable_template`` gate in ``_filter_device``.

The template is an AND-condition layered on top of the schedule: it is evaluated
only after the schedule check passes, it acts as a hard gate (a running device is
turned off immediately when the template turns falsy), and a broken template
fails open (the device is treated as usable, with a warning).
"""

from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from homeassistant.exceptions import TemplateError

from custom_components.sun_allocator.const import (
    CONF_DEVICE_ENTITY,
    CONF_DEVICE_NAME,
    CONF_DEVICE_CHECK_USABLE_TEMPLATE,
)
from custom_components.sun_allocator.core import power_processor as pp


def _device(template, entity="switch.heater"):
    return {
        CONF_DEVICE_NAME: "heater",
        CONF_DEVICE_ENTITY: entity,
        CONF_DEVICE_CHECK_USABLE_TEMPLATE: template,
    }


def _hass_with_state(state="off"):
    hass = MagicMock()
    state_obj = MagicMock()
    state_obj.state = state
    hass.states.get.return_value = state_obj
    return hass


def _patch_template(render_value=None, raise_error=False):
    """Patch the module-level Template so async_render returns/raises as needed."""
    tmpl_instance = MagicMock()
    if raise_error:
        tmpl_instance.async_render.side_effect = TemplateError(Exception("boom"))
    else:
        tmpl_instance.async_render.return_value = render_value
    return patch.object(pp, "Template", return_value=tmpl_instance)


@pytest.mark.asyncio
async def test_template_truthy_passes():
    """Truthy template → device is usable (filter returns None)."""
    hass = _hass_with_state("off")
    with patch.object(pp, "is_device_in_schedule", return_value=True), \
         _patch_template(render_value=True), \
         patch.object(pp, "turn_off_entity", new_callable=AsyncMock) as mock_off:
        result = await pp._filter_device(hass, _device("{{ true }}"), None)

    assert result is None
    mock_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_template_falsy_blocks_and_device_off_no_command():
    """Falsy template with an already-off device → blocked, but no redundant turn-off."""
    hass = _hass_with_state("off")
    with patch.object(pp, "is_device_in_schedule", return_value=True), \
         _patch_template(render_value=False), \
         patch.object(pp, "turn_off_entity", new_callable=AsyncMock) as mock_off:
        result = await pp._filter_device(hass, _device("{{ false }}"), None)

    assert result == "Not usable (template)"
    mock_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_template_falsy_turns_off_running_device():
    """Hard gate: a running device is turned off immediately when template goes falsy."""
    hass = _hass_with_state("on")
    with patch.object(pp, "is_device_in_schedule", return_value=True), \
         _patch_template(render_value=False), \
         patch.object(pp, "turn_off_entity", new_callable=AsyncMock) as mock_off:
        result = await pp._filter_device(hass, _device("{{ false }}"), None)

    assert result == "Not usable (template)"
    mock_off.assert_awaited_once()
    assert mock_off.await_args.args[1] == "switch.heater"


@pytest.mark.asyncio
async def test_broken_template_fails_open():
    """A template that raises is treated as usable (fail-open), not as a block."""
    hass = _hass_with_state("off")
    with patch.object(pp, "is_device_in_schedule", return_value=True), \
         _patch_template(raise_error=True), \
         patch.object(pp, "turn_off_entity", new_callable=AsyncMock) as mock_off:
        result = await pp._filter_device(hass, _device("{{ bad syntax"), None)

    assert result is None
    mock_off.assert_not_awaited()


@pytest.mark.asyncio
async def test_template_not_evaluated_outside_schedule():
    """Schedule is checked first — outside it, the template is never rendered."""
    hass = _hass_with_state("off")
    with patch.object(pp, "is_device_in_schedule", return_value=False), \
         _patch_template(render_value=True) as mock_tmpl, \
         patch.object(pp, "turn_off_entity", new_callable=AsyncMock):
        result = await pp._filter_device(hass, _device("{{ true }}"), None)

    assert result == "Outside of schedule"
    mock_tmpl.assert_not_called()
