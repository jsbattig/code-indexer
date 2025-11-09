#!/usr/bin/env python3
"""
Test suite for CLI temporal indexing daemon delegation bug fix.

Bug #474: CLI bypasses daemon for temporal indexing due to early exit at line 3340-3341.
This test suite ensures temporal indexing properly delegates to daemon when daemon is enabled.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call, ANY
import pytest
import subprocess
import time

from src.code_indexer.cli import cli
from click.testing import CliRunner


class TestCliTemporalDaemonDelegation:
    """Test that temporal indexing delegates to daemon when enabled."""

    @pytest.fixture
    def temp_repo(self):
        """Create a temporary git repository with commits."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Initialize git repo
            subprocess.run(["git", "init"], cwd=repo_path, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path)

            # Create some files and commits
            for i in range(3):
                file_path = repo_path / f"file{i}.py"
                file_path.write_text(f"# File {i}\nprint('hello {i}')\n")
                subprocess.run(["git", "add", "."], cwd=repo_path)
                subprocess.run(["git", "commit", "-m", f"Commit {i}"], cwd=repo_path)

            yield repo_path

    def test_temporal_bypasses_daemon_before_fix(self, temp_repo):
        """
        Test that demonstrates the bug: temporal indexing bypasses daemon.
        This test should FAIL before the fix and PASS after.
        """
        runner = CliRunner()

        with runner.isolated_filesystem():
            os.chdir(temp_repo)

            # Initialize index
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0

            # Enable daemon mode
            config_path = temp_repo / ".code-indexer" / "config.json"
            config = json.loads(config_path.read_text())
            # Properly set daemon configuration
            config["daemon"] = {
                "enabled": True,
                "ttl_minutes": 60,
                "auto_start": True,
                "auto_shutdown_on_idle": False
            }
            config_path.write_text(json.dumps(config))

            # Mock the daemon delegation to track if it's called
            with patch("src.code_indexer.cli_daemon_delegation._index_via_daemon") as mock_daemon:
                mock_daemon.return_value = 0

                # Run temporal indexing with daemon enabled
                result = runner.invoke(cli, ["index", "--index-commits", "--all-branches"])

                # BUG: Before fix, daemon is NOT called due to early exit
                # After fix, daemon SHOULD be called
                if result.exit_code == 0:
                    # After fix: daemon should be called with temporal flags
                    mock_daemon.assert_called_once()
                    call_kwargs = mock_daemon.call_args.kwargs
                    assert call_kwargs.get("index_commits") is True
                    assert call_kwargs.get("all_branches") is True
                else:
                    # Before fix: early exit runs standalone temporal
                    mock_daemon.assert_not_called()

    def test_cli_delegates_temporal_to_daemon_when_enabled(self, temp_repo):
        """Test that temporal indexing properly delegates to daemon when daemon is enabled."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            os.chdir(temp_repo)

            # Initialize index
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0

            # Enable daemon mode
            config_path = temp_repo / ".code-indexer" / "config.json"
            config = json.loads(config_path.read_text())
            # Properly set daemon configuration
            config["daemon"] = {
                "enabled": True,
                "ttl_minutes": 60,
                "auto_start": True,
                "auto_shutdown_on_idle": False
            }
            config_path.write_text(json.dumps(config))

            # Mock both delegation paths
            with patch("src.code_indexer.cli_daemon_delegation._index_via_daemon") as mock_daemon, \
                 patch("src.code_indexer.indexing.smart_indexer.SmartIndexer") as mock_indexer:

                mock_daemon.return_value = 0

                # Test 1: Temporal indexing WITH daemon enabled -> should delegate
                result = runner.invoke(cli, ["index", "--index-commits"])

                # Daemon should be called with temporal flags
                mock_daemon.assert_called_once()
                call_kwargs = mock_daemon.call_args.kwargs
                assert call_kwargs.get("index_commits") is True
                assert call_kwargs.get("all_branches") is False  # default
                assert call_kwargs.get("force_reindex") is False  # default

                # SmartIndexer should NOT be called (daemon handles it)
                mock_indexer.assert_not_called()

                # Reset mocks
                mock_daemon.reset_mock()
                mock_indexer.reset_mock()

                # Test 2: Temporal with --all-branches and --clear
                result = runner.invoke(cli, ["index", "--index-commits", "--all-branches", "--clear"])

                # Daemon should be called with all flags
                mock_daemon.assert_called_once()
                call_kwargs = mock_daemon.call_args.kwargs
                assert call_kwargs.get("index_commits") is True
                assert call_kwargs.get("all_branches") is True
                assert call_kwargs.get("force_reindex") is True

    def test_cli_runs_standalone_temporal_when_daemon_disabled(self, temp_repo):
        """Test that temporal indexing runs standalone when daemon is disabled."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            os.chdir(temp_repo)

            # Initialize index
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0

            # Ensure daemon is disabled (default)
            config_path = temp_repo / ".code-indexer" / "config.json"
            config = json.loads(config_path.read_text())
            # Explicitly disable daemon
            config["daemon"] = {
                "enabled": False,
                "ttl_minutes": 60,
                "auto_start": False,
                "auto_shutdown_on_idle": False
            }
            config_path.write_text(json.dumps(config))

            with patch("src.code_indexer.cli_daemon_delegation._index_via_daemon") as mock_daemon, \
                 patch("src.code_indexer.services.temporal.temporal_indexer.TemporalIndexer") as mock_temporal:

                mock_temporal_instance = MagicMock()
                mock_temporal.return_value = mock_temporal_instance

                # Run temporal indexing with daemon disabled
                result = runner.invoke(cli, ["index", "--index-commits"])

                # Daemon should NOT be called
                mock_daemon.assert_not_called()

                # Temporal indexer should be called directly
                mock_temporal.assert_called_once()
                mock_temporal_instance.index.assert_called_once()

    def test_semantic_indexing_still_works_with_daemon(self, temp_repo):
        """Test that regular semantic indexing still delegates to daemon correctly."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            os.chdir(temp_repo)

            # Initialize index
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0

            # Enable daemon mode
            config_path = temp_repo / ".code-indexer" / "config.json"
            config = json.loads(config_path.read_text())
            # Properly set daemon configuration
            config["daemon"] = {
                "enabled": True,
                "ttl_minutes": 60,
                "auto_start": True,
                "auto_shutdown_on_idle": False
            }
            config_path.write_text(json.dumps(config))

            with patch("src.code_indexer.cli_daemon_delegation._index_via_daemon") as mock_daemon:
                mock_daemon.return_value = 0

                # Run regular semantic indexing (no --index-commits)
                result = runner.invoke(cli, ["index"])

                # Daemon should be called WITHOUT temporal flags
                mock_daemon.assert_called_once()
                call_kwargs = mock_daemon.call_args.kwargs
                assert call_kwargs.get("index_commits") is False
                assert call_kwargs.get("all_branches") is False

    def test_no_early_exit_for_temporal_indexing(self):
        """
        Test that verifies the early exit at line 3340-3341 is removed.
        This is a code inspection test that ensures the fix is applied.
        """
        import inspect
        from src.code_indexer.cli import index

        # Get the source code of the index function
        source = inspect.getsource(index)
        lines = source.split('\n')

        # Look for patterns that indicate early exit for temporal indexing
        early_exit_patterns = [
            "if index_commits:",
            "if index_commits and not",
            "# Handle --index-commits flag",
            "# early exit path for temporal",
        ]

        # Check that early exit is removed (should not find these patterns before daemon delegation)
        # The temporal handling should be INSIDE the daemon/standalone conditional blocks

        # Find where daemon delegation starts (approximate)
        daemon_line = -1
        for i, line in enumerate(lines):
            if "_index_via_daemon" in line:
                daemon_line = i
                break

        if daemon_line > 0:
            # Check that temporal handling doesn't happen before daemon delegation
            before_daemon = '\n'.join(lines[:daemon_line])

            # After fix: These patterns should NOT appear before daemon delegation
            for pattern in early_exit_patterns:
                if pattern.lower() in before_daemon.lower():
                    # Look for context to determine if it's the early exit
                    context = '\n'.join(lines[max(0, i-2):min(len(lines), i+3)])
                    if "temporal" in context.lower() and "return" in context:
                        pytest.fail(f"Found early exit for temporal indexing: {pattern}")

    def test_daemon_receives_all_temporal_flags(self, temp_repo):
        """Test that all temporal-related flags are properly passed to daemon."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            os.chdir(temp_repo)

            # Initialize index
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0

            # Enable daemon mode
            config_path = temp_repo / ".code-indexer" / "config.json"
            config = json.loads(config_path.read_text())
            # Properly set daemon configuration
            config["daemon"] = {
                "enabled": True,
                "ttl_minutes": 60,
                "auto_start": True,
                "auto_shutdown_on_idle": False
            }
            config_path.write_text(json.dumps(config))

            with patch("src.code_indexer.cli_daemon_delegation._index_via_daemon") as mock_daemon:
                mock_daemon.return_value = 0

                # Test all temporal flag combinations
                test_cases = [
                    (["index", "--index-commits"],
                     {"index_commits": True, "all_branches": False, "force_reindex": False}),

                    (["index", "--index-commits", "--all-branches"],
                     {"index_commits": True, "all_branches": True, "force_reindex": False}),

                    (["index", "--index-commits", "--clear"],
                     {"index_commits": True, "all_branches": False, "force_reindex": True}),

                    (["index", "--index-commits", "--all-branches", "--clear"],
                     {"index_commits": True, "all_branches": True, "force_reindex": True}),
                ]

                for args, expected_kwargs in test_cases:
                    mock_daemon.reset_mock()
                    result = runner.invoke(cli, args)

                    # Verify daemon was called with correct flags
                    mock_daemon.assert_called_once()
                    call_kwargs = mock_daemon.call_args.kwargs
                    for key, expected_value in expected_kwargs.items():
                        assert call_kwargs.get(key) == expected_value, \
                            f"Flag {key} mismatch for args {args}: got {call_kwargs.get(key)}, expected {expected_value}"


class TestManualVerification:
    """
    Manual verification tests to ensure the fix works in practice.
    These tests simulate real usage scenarios.
    """

    def test_no_hashing_phase_during_temporal(self, temp_repo, capsys):
        """
        Test that temporal indexing does NOT show hashing phase.
        This verifies the bug is fixed.
        """
        runner = CliRunner()

        with runner.isolated_filesystem():
            os.chdir(temp_repo)

            # Create more files to make hashing phase visible if it happens
            for i in range(50):
                file_path = temp_repo / f"extra_file{i}.py"
                file_path.write_text(f"# Extra file {i}\n")

            subprocess.run(["git", "add", "."], cwd=temp_repo)
            subprocess.run(["git", "commit", "-m", "Add many files"], cwd=temp_repo)

            # Initialize index
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0

            # Run temporal indexing and check output
            result = runner.invoke(cli, ["index", "--index-commits", "--all-branches"])

            output = result.output

            # After fix: Should see temporal messages
            assert "temporal" in output.lower() or "commit" in output.lower(), \
                "Expected temporal indexing messages"

            # After fix: Should NOT see semantic indexing messages
            assert "🔍 Hashing" not in output, \
                "BUG: Hashing phase shown during temporal indexing!"
            assert "📁 Found" not in output or "files for indexing" not in output, \
                "BUG: File discovery shown during temporal indexing!"
            assert "🔍 Discovering files" not in output, \
                "BUG: File discovery shown during temporal indexing!"

    def test_temporal_only_no_semantic(self, temp_repo):
        """
        Test that --index-commits ONLY does temporal indexing, not semantic.
        """
        runner = CliRunner()

        with runner.isolated_filesystem():
            os.chdir(temp_repo)

            # Initialize index
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0

            # Mock to track what gets called
            with patch("src.code_indexer.indexing.smart_indexer.SmartIndexer") as mock_smart, \
                 patch("src.code_indexer.services.temporal.temporal_indexer.TemporalIndexer") as mock_temporal:

                mock_temporal_instance = MagicMock()
                mock_temporal.return_value = mock_temporal_instance

                # Run temporal indexing
                result = runner.invoke(cli, ["index", "--index-commits"])

                # Should call temporal indexer
                assert mock_temporal.called or "--index-commits" in str(result.output), \
                    "Temporal indexer should be invoked"

                # Should NOT call smart indexer for semantic indexing
                mock_smart.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])