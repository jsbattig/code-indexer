"""
Unit tests for FileContentLimitsConfigManager service.

Tests database persistence of file content limits configuration.
"""

import os
import tempfile
from pathlib import Path

import pytest

from code_indexer.server.models.file_content_limits_config import FileContentLimitsConfig
from code_indexer.server.services.file_content_limits_config_manager import (
    FileContentLimitsConfigManager,
)


class TestFileContentLimitsConfigManager:
    """Test suite for FileContentLimitsConfigManager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_file_content_config.db"
        self.manager = FileContentLimitsConfigManager(db_path=str(self.db_path))

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

        assert config.max_tokens_per_request == 5000
        assert config.chars_per_token == 4

    def test_get_config_returns_defaults(self):
        """Test getting config returns default values on first access."""
        config = self.manager.get_config()

        assert isinstance(config, FileContentLimitsConfig)
        assert config.max_tokens_per_request == 5000
        assert config.chars_per_token == 4

    def test_update_config_persists_changes(self):
        """Test updating config persists to database."""
        # Update config
        new_config = FileContentLimitsConfig(max_tokens_per_request=10000, chars_per_token=3)
        self.manager.update_config(new_config)

        # Retrieve and verify
        retrieved_config = self.manager.get_config()

        assert retrieved_config.max_tokens_per_request == 10000
        assert retrieved_config.chars_per_token == 3

    def test_config_persists_across_instances(self):
        """Test config persists across manager instances."""
        # Update config
        new_config = FileContentLimitsConfig(max_tokens_per_request=15000, chars_per_token=5)
        self.manager.update_config(new_config)

        # Create new manager instance with same db
        new_manager = FileContentLimitsConfigManager(db_path=str(self.db_path))

        # Verify config persisted
        retrieved_config = new_manager.get_config()

        assert retrieved_config.max_tokens_per_request == 15000
        assert retrieved_config.chars_per_token == 5

    def test_multiple_updates(self):
        """Test multiple sequential updates work correctly."""
        configs = [
            FileContentLimitsConfig(max_tokens_per_request=5000, chars_per_token=3),
            FileContentLimitsConfig(max_tokens_per_request=10000, chars_per_token=4),
            FileContentLimitsConfig(max_tokens_per_request=20000, chars_per_token=5),
        ]

        for config in configs:
            self.manager.update_config(config)
            retrieved = self.manager.get_config()
            assert retrieved.max_tokens_per_request == config.max_tokens_per_request
            assert retrieved.chars_per_token == config.chars_per_token

    def test_thread_safety(self):
        """Test concurrent access is thread-safe."""
        import threading

        results = []

        def update_and_read():
            config = FileContentLimitsConfig(max_tokens_per_request=8000, chars_per_token=4)
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
        assert all(r.max_tokens_per_request == 8000 for r in results)
        assert all(r.chars_per_token == 4 for r in results)

    def test_get_instance_singleton(self):
        """Test get_instance returns singleton."""
        instance1 = FileContentLimitsConfigManager.get_instance(db_path=str(self.db_path))
        instance2 = FileContentLimitsConfigManager.get_instance()

        assert instance1 is instance2

    def test_config_validation_on_update(self):
        """Test updating with invalid config raises validation error."""
        from pydantic import ValidationError

        # Invalid config (tokens too low)
        with pytest.raises(ValidationError):
            invalid_config = FileContentLimitsConfig(
                max_tokens_per_request=500, chars_per_token=4
            )

        # Invalid config (tokens too high)
        with pytest.raises(ValidationError):
            invalid_config = FileContentLimitsConfig(
                max_tokens_per_request=50000, chars_per_token=4
            )

        # Invalid config (chars_per_token too low)
        with pytest.raises(ValidationError):
            invalid_config = FileContentLimitsConfig(
                max_tokens_per_request=5000, chars_per_token=2
            )

        # Invalid config (chars_per_token too high)
        with pytest.raises(ValidationError):
            invalid_config = FileContentLimitsConfig(
                max_tokens_per_request=5000, chars_per_token=6
            )

    def test_database_recovery_from_empty(self):
        """Test database initializes with defaults if empty."""
        # Create manager which initializes DB
        manager = FileContentLimitsConfigManager(db_path=str(self.db_path))

        # Get config should return defaults
        config = manager.get_config()

        assert config.max_tokens_per_request == 5000
        assert config.chars_per_token == 4
