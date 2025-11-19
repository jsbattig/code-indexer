"""
Unit tests for debug log path helper function.

Tests the functionality of getting debug log paths within .code-indexer/.tmp
instead of hardcoded /tmp paths.
"""

import pytest
from pathlib import Path
import tempfile
import shutil
import os

from code_indexer.utils.log_path_helper import get_debug_log_path


class TestDebugLogPath:
    """Tests for debug log path helper function."""

    def test_get_debug_log_path_creates_tmp_directory(self, tmp_path):
        """Test that get_debug_log_path creates .tmp directory if it doesn't exist."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        # .tmp should not exist yet
        tmp_dir = config_dir / ".tmp"
        assert not tmp_dir.exists()

        # Call helper
        log_path = get_debug_log_path(config_dir, "test_debug.log")

        # .tmp should now exist
        assert tmp_dir.exists()
        assert tmp_dir.is_dir()

    def test_get_debug_log_path_returns_correct_path(self, tmp_path):
        """Test that get_debug_log_path returns correct path structure."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        log_path = get_debug_log_path(config_dir, "cidx_debug.log")

        expected_path = config_dir / ".tmp" / "cidx_debug.log"
        assert log_path == expected_path

    def test_get_debug_log_path_handles_existing_tmp_directory(self, tmp_path):
        """Test that get_debug_log_path works when .tmp already exists."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()
        tmp_dir = config_dir / ".tmp"
        tmp_dir.mkdir()

        log_path = get_debug_log_path(config_dir, "cidx_vectorcalc_debug.log")

        expected_path = tmp_dir / "cidx_vectorcalc_debug.log"
        assert log_path == expected_path
        assert tmp_dir.exists()

    def test_get_debug_log_path_is_writable(self, tmp_path):
        """Test that the returned path is writable."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        log_path = get_debug_log_path(config_dir, "test_write.log")

        # Should be able to write to the path
        with open(log_path, "w") as f:
            f.write("test content\n")

        assert log_path.exists()
        assert log_path.read_text() == "test content\n"

    def test_get_debug_log_path_multiple_calls_same_name(self, tmp_path):
        """Test that multiple calls with same name return same path."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        path1 = get_debug_log_path(config_dir, "debug.log")
        path2 = get_debug_log_path(config_dir, "debug.log")

        assert path1 == path2

    def test_get_debug_log_path_different_names(self, tmp_path):
        """Test that different log names return different paths."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        path1 = get_debug_log_path(config_dir, "cidx_debug.log")
        path2 = get_debug_log_path(config_dir, "cidx_vectorcalc_debug.log")

        assert path1 != path2
        assert path1.parent == path2.parent  # Same directory
        assert path1.name == "cidx_debug.log"
        assert path2.name == "cidx_vectorcalc_debug.log"

    def test_get_debug_log_path_not_in_tmp(self, tmp_path):
        """Test that returned path is NOT hardcoded to /tmp (the bug we're fixing)."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        log_path = get_debug_log_path(config_dir, "debug.log")

        # Path should be within config_dir/.tmp, not hardcoded to /tmp/cidx_debug.log
        assert log_path.parent == config_dir / ".tmp"
        # Path should be relative to config_dir structure
        assert log_path.parent.parent == config_dir

    def test_get_debug_log_path_permissions_work_for_non_root(self, tmp_path):
        """Test that non-root users can write to debug log paths."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        log_path = get_debug_log_path(config_dir, "test_permissions.log")

        # Simulate non-root user writing
        # If this were /tmp with wrong permissions, this would fail
        try:
            with open(log_path, "a") as f:
                f.write("Test from non-root user\n")
            success = True
        except PermissionError:
            success = False

        assert success, "Should be able to write to debug log without permission errors"


class TestDebugLogPathIntegration:
    """Integration tests to verify the fix works in real scenarios."""

    def test_vector_calculation_manager_can_write_debug_logs(self, tmp_path):
        """Test that VectorCalculationManager can write debug logs to .code-indexer/.tmp."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        # This simulates what VectorCalculationManager will do
        log_path = get_debug_log_path(config_dir, "cidx_vectorcalc_debug.log")

        # Simulate debug logging
        with open(log_path, "a") as f:
            f.write(
                "VectorCalc: Processing batch abc123 with 10 chunks - STARTING API call\n"
            )
            f.flush()

        with open(log_path, "a") as f:
            f.write(
                "VectorCalc: Batch abc123 COMPLETED in 1.23s - returned 10 embeddings\n"
            )
            f.flush()

        # Verify logs were written
        assert log_path.exists()
        content = log_path.read_text()
        assert "Processing batch abc123" in content
        assert "COMPLETED" in content

    def test_temporal_indexer_can_write_debug_logs(self, tmp_path):
        """Test that temporal_indexer can write debug logs to .code-indexer/.tmp."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        # This simulates what temporal_indexer will do
        log_path = get_debug_log_path(config_dir, "cidx_debug.log")

        # Simulate debug logging
        with open(log_path, "a") as f:
            f.write(
                "Commit abc12345: Processing 3 batch(es) with 150 total chunks (max 10 concurrent)\n"
            )
            f.flush()

        with open(log_path, "a") as f:
            f.write("Commit abc12345: Wave batch 1/3 completed - 50 embeddings\n")
            f.flush()

        # Verify logs were written
        assert log_path.exists()
        content = log_path.read_text()
        assert "Processing 3 batch(es)" in content
        assert "Wave batch" in content
