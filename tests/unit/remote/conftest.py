"""Pytest configuration for remote tests - event loop cleanup."""

import pytest
import asyncio


@pytest.fixture(scope="function", autouse=True)
def cleanup_event_loop():
    """Clean up event loop after each test to prevent loop pollution."""
    yield
    # Cleanup: Close any lingering event loops
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.stop()
        if not loop.is_closed():
            loop.close()
    except RuntimeError:
        # No event loop exists, which is fine
        pass

    # Create fresh event loop for next test
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
    except RuntimeError:
        pass
