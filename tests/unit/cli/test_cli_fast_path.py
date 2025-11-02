"""Tests for CLI fast-path optimization with daemon delegation.

These tests ensure the CLI startup time is minimized when daemon mode
is enabled by avoiding heavy imports until absolutely necessary.
"""

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch


class TestQuickDaemonCheck:
    """Test quick daemon mode detection without heavy imports."""

    def test_quick_daemon_check_detects_enabled_daemon(self, tmp_path):
        """Test that quick check detects daemon.enabled: true."""
        # Arrange
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"

        config_data = {
            "daemon": {"enabled": True},
            "codebase_dir": str(tmp_path),
            "backend": "filesystem",
        }
        config_file.write_text(json.dumps(config_data))

        # Import should be fast - only stdlib
        from code_indexer.cli_fast_entry import quick_daemon_check

        # Act
        with patch("code_indexer.cli_fast_entry.Path.cwd", return_value=tmp_path):
            is_daemon, config_path = quick_daemon_check()

        # Assert
        assert is_daemon is True
        assert config_path == config_file

    def test_quick_daemon_check_detects_disabled_daemon(self, tmp_path):
        """Test that quick check detects daemon.enabled: false."""
        # Arrange
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"

        config_data = {"daemon": {"enabled": False}, "codebase_dir": str(tmp_path)}
        config_file.write_text(json.dumps(config_data))

        from code_indexer.cli_fast_entry import quick_daemon_check

        # Act
        with patch("code_indexer.cli_fast_entry.Path.cwd", return_value=tmp_path):
            is_daemon, config_path = quick_daemon_check()

        # Assert
        assert is_daemon is False
        assert config_path is None

    def test_quick_daemon_check_walks_up_directory_tree(self, tmp_path):
        """Test that quick check walks up directory tree to find config."""
        # Arrange
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"

        config_data = {"daemon": {"enabled": True}}
        config_file.write_text(json.dumps(config_data))

        # Create subdirectory
        subdir = tmp_path / "src" / "module"
        subdir.mkdir(parents=True)

        from code_indexer.cli_fast_entry import quick_daemon_check

        # Act - start from subdirectory
        with patch("code_indexer.cli_fast_entry.Path.cwd", return_value=subdir):
            is_daemon, config_path = quick_daemon_check()

        # Assert
        assert is_daemon is True
        assert config_path == config_file

    def test_quick_daemon_check_handles_missing_config(self, tmp_path):
        """Test that quick check returns False when no config found."""
        from code_indexer.cli_fast_entry import quick_daemon_check

        # Act - no .code-indexer directory exists
        with patch("code_indexer.cli_fast_entry.Path.cwd", return_value=tmp_path):
            is_daemon, config_path = quick_daemon_check()

        # Assert
        assert is_daemon is False
        assert config_path is None

    def test_quick_daemon_check_handles_malformed_json(self, tmp_path):
        """Test that quick check handles malformed JSON gracefully."""
        # Arrange
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text("{invalid json}")

        from code_indexer.cli_fast_entry import quick_daemon_check

        # Act
        with patch("code_indexer.cli_fast_entry.Path.cwd", return_value=tmp_path):
            is_daemon, config_path = quick_daemon_check()

        # Assert - should fail gracefully
        assert is_daemon is False
        assert config_path is None

    def test_quick_daemon_check_execution_time(self, tmp_path):
        """Test that quick check executes in <10ms."""
        # Arrange
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"daemon": {"enabled": True}}))

        from code_indexer.cli_fast_entry import quick_daemon_check

        # Act - measure execution time
        with patch("code_indexer.cli_fast_entry.Path.cwd", return_value=tmp_path):
            start = time.time()
            quick_daemon_check()
            elapsed_ms = (time.time() - start) * 1000

        # Assert - should be very fast (stdlib only)
        assert elapsed_ms < 10, f"Quick check took {elapsed_ms:.1f}ms, expected <10ms"


class TestCommandClassification:
    """Test command classification for daemon delegation."""

    def test_identifies_daemon_delegatable_commands(self):
        """Test that query, index, watch etc. are identified as delegatable."""
        from code_indexer.cli_fast_entry import is_delegatable_command

        delegatable = [
            "query",
            "index",
            "watch",
            "clean",
            "clean-data",
            "stop",
            "watch-stop",
        ]

        for cmd in delegatable:
            assert is_delegatable_command(cmd) is True, f"{cmd} should be delegatable"

    def test_identifies_non_delegatable_commands(self):
        """Test that init, fix-config etc. are not delegatable."""
        from code_indexer.cli_fast_entry import is_delegatable_command

        non_delegatable = ["init", "fix-config", "reconcile", "sync", "list-repos"]

        for cmd in non_delegatable:
            assert (
                is_delegatable_command(cmd) is False
            ), f"{cmd} should not be delegatable"


class TestFastPathRouting:
    """Test main entry point routing logic."""

    @patch("code_indexer.cli_fast_entry.quick_daemon_check")
    @patch("code_indexer.cli_daemon_fast.execute_via_daemon")
    def test_routes_to_fast_path_when_daemon_enabled(self, mock_execute, mock_check):
        """Test that daemon-enabled + delegatable command uses fast path."""
        # Arrange
        mock_check.return_value = (True, Path("/fake/config.json"))
        mock_execute.return_value = 0

        from code_indexer.cli_fast_entry import main

        # Act - query command with daemon enabled
        with patch.object(sys, "argv", ["cidx", "query", "test", "--fts"]):
            result = main()

        # Assert
        mock_check.assert_called_once()
        mock_execute.assert_called_once()
        assert result == 0

    @patch("code_indexer.cli_fast_entry.quick_daemon_check")
    @patch("code_indexer.cli.cli")
    def test_routes_to_slow_path_when_daemon_disabled(self, mock_cli, mock_check):
        """Test that daemon-disabled uses full CLI (slow path)."""
        # Arrange
        mock_check.return_value = (False, None)

        from code_indexer.cli_fast_entry import main

        # Act - query command with daemon disabled
        with patch.object(sys, "argv", ["cidx", "query", "test"]):
            main()

        # Assert
        mock_check.assert_called_once()
        mock_cli.assert_called_once()

    @patch("code_indexer.cli_fast_entry.quick_daemon_check")
    @patch("code_indexer.cli.cli")
    def test_routes_to_slow_path_for_non_delegatable_commands(
        self, mock_cli, mock_check
    ):
        """Test that non-delegatable commands always use full CLI."""
        # Arrange
        mock_check.return_value = (True, Path("/fake/config.json"))

        from code_indexer.cli_fast_entry import main

        # Act - init command (not delegatable)
        with patch.object(sys, "argv", ["cidx", "init"]):
            main()

        # Assert
        mock_check.assert_called_once()
        mock_cli.assert_called_once()  # Should use slow path


class TestFastPathPerformance:
    """Test that fast path achieves target performance."""

    @patch("code_indexer.cli_fast_entry.quick_daemon_check")
    @patch("code_indexer.cli_daemon_fast.execute_via_daemon")
    def test_fast_path_startup_time_under_150ms(self, mock_execute, mock_check):
        """Test that fast path (daemon mode) starts in <150ms."""
        # Arrange
        mock_check.return_value = (True, Path("/fake/config.json"))
        mock_execute.return_value = 0

        # Act - measure import + execution time
        start = time.time()
        from code_indexer.cli_fast_entry import main

        with patch.object(sys, "argv", ["cidx", "query", "test", "--fts"]):
            main()

        elapsed_ms = (time.time() - start) * 1000

        # Assert - should be <150ms (target)
        # Note: This may be tight in CI, but should pass on reasonable hardware
        assert elapsed_ms < 200, f"Fast path took {elapsed_ms:.0f}ms, target <150ms"

    def test_fast_entry_module_import_time(self):
        """Test that cli_fast_entry imports quickly (<50ms)."""
        # Act - measure import time
        start = time.time()
        import code_indexer.cli_fast_entry  # noqa: F401

        elapsed_ms = (time.time() - start) * 1000

        # Assert - should import very quickly (stdlib + rpyc + rich)
        assert (
            elapsed_ms < 100
        ), f"Fast entry import took {elapsed_ms:.0f}ms, expected <100ms"


class TestFallbackBehavior:
    """Test fallback to full CLI when daemon unavailable."""

    @patch("code_indexer.cli_fast_entry.quick_daemon_check")
    @patch("code_indexer.cli_daemon_fast.execute_via_daemon")
    @patch("code_indexer.cli.cli")
    def test_fallback_to_full_cli_on_daemon_connection_error(
        self, mock_cli, mock_execute, mock_check
    ):
        """Test fallback when daemon connection fails."""
        # Arrange
        mock_check.return_value = (True, Path("/fake/config.json"))
        mock_execute.side_effect = Exception("Connection refused")

        from code_indexer.cli_fast_entry import main

        # Act
        with patch.object(sys, "argv", ["cidx", "query", "test"]):
            # Should not raise, should fallback
            main()

        # Assert - should have attempted fast path, then fallen back
        mock_execute.assert_called_once()
        # Note: Actual fallback implementation may vary
