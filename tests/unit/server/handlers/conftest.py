"""Shared fixtures for handlers tests.

Story #680: S2 - FTS Search with Payload Control
Story #683: S5 - Multi-repo Search with Payload Control
"""

import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def temp_db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "payload_cache.db"


@pytest.fixture
async def cache(temp_db_path):
    """Create and initialize a PayloadCache instance for testing."""
    from code_indexer.server.cache.payload_cache import (
        PayloadCache,
        PayloadCacheConfig,
    )

    config = PayloadCacheConfig(preview_size_chars=2000)
    cache = PayloadCache(db_path=temp_db_path, config=config)
    await cache.initialize()
    yield cache
    await cache.close()


@pytest.fixture
async def cache_100_chars(temp_db_path):
    """Create PayloadCache with 100 char preview for easy testing (Story #683)."""
    from code_indexer.server.cache.payload_cache import (
        PayloadCache,
        PayloadCacheConfig,
    )

    config = PayloadCacheConfig(preview_size_chars=100, max_fetch_size_chars=200)
    cache = PayloadCache(db_path=temp_db_path, config=config)
    await cache.initialize()
    yield cache
    await cache.close()
