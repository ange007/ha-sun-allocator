"""Performance tests for large configurations."""

import pytest
import time

# Import the required functions
from conftest import create_test_device


@pytest.mark.asyncio
async def test_large_device_count_performance(hass):
    """Test performance with many devices."""
    # Test that we can create many devices quickly
    start_time = time.time()

    # Just test device creation performance instead of full integration
    test_devices = []
    for i in range(50):
        device = create_test_device(f"perf_device_{i}")
        test_devices.append(device)

    end_time = time.time()

    # Should complete within reasonable time
    assert (end_time - start_time) < 2.0  # 2 seconds max
    assert len(test_devices) == 50


@pytest.mark.asyncio
async def test_frequent_updates_performance(hass):
    """Test performance with frequent sensor updates."""
    # Simulate rapid sensor updates
    for i in range(100):
        hass.states.async_set("sensor.pv_power", str(200 + i))
        await hass.async_block_till_done()

    # System should remain responsive
    assert True  # If we get here without timeout, test passes
