"""
Unit tests for AutoWatchManager - Story #640.

Tests auto-watch lifecycle management for server file operations.
"""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from code_indexer.server.services.auto_watch_manager import AutoWatchManager


class TestAutoWatchManagerBasicLifecycle:
    """Test basic auto-watch start/stop lifecycle."""

    def test_start_watch_creates_watch_instance(self, tmp_path):
        """Test that start_watch creates and starts a watch instance."""
        manager = AutoWatchManager()
        repo_path = str(tmp_path)

        with patch('code_indexer.server.services.auto_watch_manager.DaemonWatchManager') as mock_daemon:
            mock_watch_instance = Mock()
            mock_watch_instance.start_watch.return_value = {"status": "success"}
            mock_daemon.return_value = mock_watch_instance

            result = manager.start_watch(repo_path, timeout=300)

            assert result["status"] == "success"
            assert manager.is_watching(repo_path) is True
            mock_watch_instance.start_watch.assert_called_once()

    def test_start_watch_resets_timeout_if_already_running(self, tmp_path):
        """Test that starting watch again resets the timeout instead of creating new instance."""
        manager = AutoWatchManager()
        repo_path = str(tmp_path)

        with patch('code_indexer.server.services.auto_watch_manager.DaemonWatchManager') as mock_daemon:
            mock_watch_instance = Mock()
            mock_watch_instance.start_watch.return_value = {"status": "success"}
            mock_daemon.return_value = mock_watch_instance

            # Start watch first time
            result1 = manager.start_watch(repo_path, timeout=300)
            first_activity = manager._watch_state[repo_path]["last_activity"]

            # Small delay to ensure time difference
            time.sleep(0.1)

            # Start watch second time
            result2 = manager.start_watch(repo_path, timeout=300)
            second_activity = manager._watch_state[repo_path]["last_activity"]

            assert result1["status"] == "success"
            assert result2["status"] == "success"
            assert result2["message"] == "Timeout reset"
            assert second_activity > first_activity

    def test_stop_watch_terminates_watch_instance(self, tmp_path):
        """Test that stop_watch properly terminates the watch instance."""
        manager = AutoWatchManager()
        repo_path = str(tmp_path)

        with patch('code_indexer.server.services.auto_watch_manager.DaemonWatchManager') as mock_daemon:
            mock_watch_instance = Mock()
            mock_watch_instance.start_watch.return_value = {"status": "success"}
            mock_watch_instance.stop_watch.return_value = {"status": "success", "stats": {}}
            mock_daemon.return_value = mock_watch_instance

            # Start then stop
            manager.start_watch(repo_path, timeout=300)
            result = manager.stop_watch(repo_path)

            assert result["status"] == "success"
            assert manager.is_watching(repo_path) is False
            mock_watch_instance.stop_watch.assert_called_once()

    def test_stop_watch_on_non_existent_watch(self, tmp_path):
        """Test stopping watch that was never started returns error."""
        manager = AutoWatchManager()
        repo_path = str(tmp_path)

        result = manager.stop_watch(repo_path)

        assert result["status"] == "error"
        assert "not running" in result["message"].lower()


class TestAutoWatchManagerTimeout:
    """Test timeout-based auto-stop functionality."""

    def test_timeout_check_stops_expired_watch(self, tmp_path):
        """Test that _check_timeouts stops watch after inactivity timeout."""
        manager = AutoWatchManager()
        repo_path = str(tmp_path)

        with patch('code_indexer.server.services.auto_watch_manager.DaemonWatchManager') as mock_daemon:
            mock_watch_instance = Mock()
            mock_watch_instance.start_watch.return_value = {"status": "success"}
            mock_watch_instance.stop_watch.return_value = {"status": "success"}
            mock_daemon.return_value = mock_watch_instance

            # Start watch with 1 second timeout
            manager.start_watch(repo_path, timeout=1)

            # Manually set last_activity to 2 seconds ago
            manager._watch_state[repo_path]["last_activity"] = datetime.now() - timedelta(seconds=2)

            # Run timeout check
            manager._check_timeouts()

            # Watch should be stopped
            assert manager.is_watching(repo_path) is False
            mock_watch_instance.stop_watch.assert_called_once()

    def test_timeout_check_keeps_active_watch(self, tmp_path):
        """Test that _check_timeouts does not stop watch within timeout period."""
        manager = AutoWatchManager()
        repo_path = str(tmp_path)

        with patch('code_indexer.server.services.auto_watch_manager.DaemonWatchManager') as mock_daemon:
            mock_watch_instance = Mock()
            mock_watch_instance.start_watch.return_value = {"status": "success"}
            mock_daemon.return_value = mock_watch_instance

            # Start watch with 300 second timeout
            manager.start_watch(repo_path, timeout=300)

            # Run timeout check immediately
            manager._check_timeouts()

            # Watch should still be running
            assert manager.is_watching(repo_path) is True
            mock_watch_instance.stop_watch.assert_not_called()

    def test_reset_timeout_updates_last_activity(self, tmp_path):
        """Test that reset_timeout updates last_activity timestamp."""
        manager = AutoWatchManager()
        repo_path = str(tmp_path)

        with patch('code_indexer.server.services.auto_watch_manager.DaemonWatchManager') as mock_daemon:
            mock_watch_instance = Mock()
            mock_watch_instance.start_watch.return_value = {"status": "success"}
            mock_daemon.return_value = mock_watch_instance

            manager.start_watch(repo_path, timeout=300)
            first_activity = manager._watch_state[repo_path]["last_activity"]

            time.sleep(0.1)

            result = manager.reset_timeout(repo_path)
            second_activity = manager._watch_state[repo_path]["last_activity"]

            assert result["status"] == "success"
            assert second_activity > first_activity

    def test_reset_timeout_on_non_existent_watch(self, tmp_path):
        """Test resetting timeout on non-existent watch returns error."""
        manager = AutoWatchManager()
        repo_path = str(tmp_path)

        result = manager.reset_timeout(repo_path)

        assert result["status"] == "error"
        assert "not running" in result["message"].lower()
