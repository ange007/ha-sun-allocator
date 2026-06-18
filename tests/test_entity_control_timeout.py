"""Tests for the service-call timeout guard in entity_control._async_call_service.

``blocking=True`` is kept (retry/reconciliation needs completion), but a slow or
hung device must not stall the allocation loop — the call is wrapped in a timeout
and both timeout and HA errors are swallowed (reconciled next cycle).
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from custom_components.sun_allocator.core import entity_control as ec


@pytest.mark.asyncio
async def test_service_call_timeout_is_swallowed(monkeypatch):
    monkeypatch.setattr(ec, "SERVICE_CALL_TIMEOUT_SECONDS", 0.05)
    hass = MagicMock()

    async def _slow(*_a, **_k):
        await asyncio.sleep(5)  # far longer than the patched timeout

    hass.services.async_call = _slow
    # Must return (not raise) despite the call exceeding the timeout.
    await ec._async_call_service(hass, "switch", "turn_on", {}, "dev")


@pytest.mark.asyncio
async def test_service_call_completes_normally(monkeypatch):
    monkeypatch.setattr(ec, "SERVICE_CALL_TIMEOUT_SECONDS", 5)
    hass = MagicMock()
    called = {}

    async def _ok(domain, service, data, blocking):
        called["args"] = (domain, service, data, blocking)

    hass.services.async_call = _ok
    await ec._async_call_service(hass, "switch", "turn_on", {"entity_id": "switch.x"}, "dev")
    assert called["args"] == ("switch", "turn_on", {"entity_id": "switch.x"}, True)


@pytest.mark.asyncio
async def test_service_call_haerror_is_swallowed(monkeypatch):
    monkeypatch.setattr(ec, "SERVICE_CALL_TIMEOUT_SECONDS", 5)
    hass = MagicMock()

    async def _boom(*_a, **_k):
        raise ec.HomeAssistantError("nope")

    hass.services.async_call = _boom
    # HA errors are logged, not raised.
    await ec._async_call_service(hass, "switch", "turn_on", {}, "dev")
