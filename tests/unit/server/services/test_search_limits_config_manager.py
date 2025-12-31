"""
Unit tests for SearchLimitsConfigManager service.

Tests database persistence of search limits configuration.
"""

import os
import tempfile
from pathlib import Path

import pytest

from code_indexer.server.models.search_limits_config import SearchLimitsConfig
from code_indexer.server.services.search_limits_config_manager import (
    SearchLimitsConfigManager,
)


class TestSearchLimitsConfigManager:
    """Test suite for SearchLimitsConfigManager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_search_config.db"
        self.manager = SearchLimitsConfigManager(db_path=str(self.db_path))

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_database_initialization(self):
        """Test database is created with default config."""
        assert self.db_path.exists()

        # Get default config
        config = self.manager.get_config()

        assert config.max_result_size_mb == 1
        assert config.timeout_seconds == 30

    def test_get_config_returns_defaults(self):
        """Test getting config returns default values on first access."""
        config = self.manager.get_config()

        assert isinstance(config, SearchLimitsConfig)
        assert config.max_result_size_mb == 1
        assert config.timeout_seconds == 30

    def test_update_config_persists_changes(self):
        """Test updating config persists to database."""
        # Update config
        new_config = SearchLimitsConfig(max_result_size_mb=10, timeout_seconds=60)
        self.manager.update_config(new_config)

        # Retrieve and verify
        retrieved_config = self.manager.get_config()

        assert retrieved_config.max_result_size_mb == 10
        assert retrieved_config.timeout_seconds == 60

    def test_config_persists_across_instances(self):
        """Test config persists across manager instances."""
        # Update config
        new_config = SearchLimitsConfig(max_result_size_mb=25, timeout_seconds=120)
        self.manager.update_config(new_config)

        # Create new manager instance with same db
        new_manager = SearchLimitsConfigManager(db_path=str(self.db_path))

        # Verify config persisted
        retrieved_config = new_manager.get_config()

        assert retrieved_config.max_result_size_mb == 25
        assert retrieved_config.timeout_seconds == 120

    def test_multiple_updates(self):
        """Test multiple sequential updates work correctly."""
        configs = [
            SearchLimitsConfig(max_result_size_mb=5, timeout_seconds=30),
            SearchLimitsConfig(max_result_size_mb=10, timeout_seconds=60),
            SearchLimitsConfig(max_result_size_mb=50, timeout_seconds=180),
        ]

        for config in configs:
            self.manager.update_config(config)
            retrieved = self.manager.get_config()
            assert retrieved.max_result_size_mb == config.max_result_size_mb
            assert retrieved.timeout_seconds == config.timeout_seconds

    def test_thread_safety(self):
        """Test concurrent access is thread-safe."""
        import threading

        results = []

        def update_and_read():
            config = SearchLimitsConfig(max_result_size_mb=15, timeout_seconds=90)
            self.manager.update_config(config)
            retrieved = self.manager.get_config()
            results.append(retrieved)

        # Run multiple threads
        threads = [threading.Thread(target=update_and_read) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All results should be consistent
        assert len(results) == 10
        assert all(r.max_result_size_mb == 15 for r in results)
        assert all(r.timeout_seconds == 90 for r in results)

    def test_get_instance_singleton(self):
        """Test get_instance returns singleton."""
        instance1 = SearchLimitsConfigManager.get_instance(db_path=str(self.db_path))
        instance2 = SearchLimitsConfigManager.get_instance()

        assert instance1 is instance2

    def test_config_validation_on_update(self):
        """Test updating with invalid config raises validation error."""
        from pydantic import ValidationError

        # Invalid config (timeout too low)
        with pytest.raises(ValidationError):
            SearchLimitsConfig(max_result_size_mb=10, timeout_seconds=1)

        # Invalid config (size too high)
        with pytest.raises(ValidationError):
            SearchLimitsConfig(max_result_size_mb=101, timeout_seconds=30)

    def test_database_recovery_from_empty(self):
        """Test database initializes with defaults if empty."""
        # Create manager which initializes DB
        manager = SearchLimitsConfigManager(db_path=str(self.db_path))

        # Get config should return defaults
        config = manager.get_config()

        assert config.max_result_size_mb == 1
        assert config.timeout_seconds == 30
