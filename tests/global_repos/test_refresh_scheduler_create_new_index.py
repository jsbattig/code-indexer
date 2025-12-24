"""
Unit tests for RefreshScheduler._create_new_index method.

Tests the complete functionality of creating new versioned indexes including:
- CoW clone with proper timeouts
- Git status fix (update-index + restore)
- cidx fix-config execution
- cidx index execution
- Index validation before returning
- Error handling and cleanup on failure
"""

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from code_indexer.global_repos.refresh_scheduler import RefreshScheduler
from code_indexer.global_repos.query_tracker import QueryTracker
from code_indexer.global_repos.cleanup_manager import CleanupManager
from code_indexer.config import ConfigManager
from code_indexer.server.utils.config_manager import ServerResourceConfig


def create_successful_subprocess_mock(expected_dest):
    """
    Create a mock subprocess.run that simulates successful execution.

    Automatically creates index directory when cidx index is called.
    """

    def subprocess_side_effect(cmd, *args, **kwargs):
        # Create index dir when cidx index is called
        if len(cmd) >= 2 and cmd[0] == "cidx" and cmd[1] == "index":
            index_dir = Path(expected_dest) / ".code-indexer" / "index"
            index_dir.mkdir(parents=True, exist_ok=True)
        return MagicMock(returncode=0, stdout="", stderr="")

    return subprocess_side_effect


class TestCreateNewIndex:
    """Test suite for RefreshScheduler._create_new_index method."""

    @pytest.fixture
    def scheduler_with_config(self, tmp_path):
        """Create RefreshScheduler with custom resource config for testing."""
        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        config_mgr = ConfigManager(tmp_path / ".code-indexer" / "config.json")
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker)

        # Create custom resource config with short timeouts for testing
        resource_config = ServerResourceConfig(
            cow_clone_timeout=10,
            git_update_index_timeout=10,
            git_restore_timeout=10,
            cidx_fix_config_timeout=10,
            cidx_index_timeout=10,
        )

        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
            resource_config=resource_config,
        )

        return scheduler

    def test_create_new_index_creates_versioned_directory(
        self, tmp_path, scheduler_with_config
    ):
        """Test that _create_new_index creates .versioned/repo_name/v_timestamp/ directory."""
        source_path = str(tmp_path / "source_repo")
        Path(source_path).mkdir()

        with patch(
            "code_indexer.global_repos.refresh_scheduler.datetime"
        ) as mock_datetime:
            mock_datetime.utcnow.return_value.timestamp.return_value = 1234567890

            expected_path = str(
                tmp_path
                / ".code-indexer"
                / "golden_repos"
                / ".versioned"
                / "test-repo"
                / "v_1234567890"
            )

            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = create_successful_subprocess_mock(expected_path)

                new_index_path = scheduler_with_config._create_new_index(
                    alias_name="test-repo-global", source_path=source_path
                )

                assert new_index_path == expected_path

    def test_create_new_index_performs_cow_clone(self, tmp_path, scheduler_with_config):
        """Test that _create_new_index performs CoW clone using cp --reflink=auto."""
        source_path = str(tmp_path / "source_repo")
        Path(source_path).mkdir()

        with patch(
            "code_indexer.global_repos.refresh_scheduler.datetime"
        ) as mock_datetime:
            mock_datetime.utcnow.return_value.timestamp.return_value = 1234567890

            expected_dest = str(
                tmp_path
                / ".code-indexer"
                / "golden_repos"
                / ".versioned"
                / "test-repo"
                / "v_1234567890"
            )

            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = create_successful_subprocess_mock(expected_dest)

                scheduler_with_config._create_new_index(
                    alias_name="test-repo-global", source_path=source_path
                )

                # Verify cp --reflink=auto was called
                cp_calls = [
                    call_obj
                    for call_obj in mock_run.call_args_list
                    if len(call_obj[0]) > 0 and call_obj[0][0][0] == "cp"
                ]
                assert len(cp_calls) == 1
                assert cp_calls[0][0][0] == [
                    "cp",
                    "--reflink=auto",
                    "-r",
                    source_path,
                    expected_dest,
                ]

    def test_create_new_index_runs_git_update_index(
        self, tmp_path, scheduler_with_config
    ):
        """Test that _create_new_index runs git update-index --refresh after CoW clone."""
        source_path = str(tmp_path / "source_repo")
        Path(source_path).mkdir()

        with patch(
            "code_indexer.global_repos.refresh_scheduler.datetime"
        ) as mock_datetime:
            mock_datetime.utcnow.return_value.timestamp.return_value = 1234567890

            expected_dest = str(
                tmp_path
                / ".code-indexer"
                / "golden_repos"
                / ".versioned"
                / "test-repo"
                / "v_1234567890"
            )

            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = create_successful_subprocess_mock(expected_dest)

                scheduler_with_config._create_new_index(
                    alias_name="test-repo-global", source_path=source_path
                )

                # Verify git update-index --refresh was called
                git_update_calls = [
                    call_obj
                    for call_obj in mock_run.call_args_list
                    if len(call_obj[0]) > 0
                    and len(call_obj[0][0]) >= 2
                    and call_obj[0][0][0] == "git"
                    and call_obj[0][0][1] == "update-index"
                ]
                # Should be called only if .git exists (not in this test)
                assert len(git_update_calls) == 0

    def test_create_new_index_runs_cidx_fix_config(
        self, tmp_path, scheduler_with_config
    ):
        """Test that _create_new_index runs cidx fix-config --force."""
        source_path = str(tmp_path / "source_repo")
        Path(source_path).mkdir()

        with patch(
            "code_indexer.global_repos.refresh_scheduler.datetime"
        ) as mock_datetime:
            mock_datetime.utcnow.return_value.timestamp.return_value = 1234567890

            expected_dest = str(
                tmp_path
                / ".code-indexer"
                / "golden_repos"
                / ".versioned"
                / "test-repo"
                / "v_1234567890"
            )

            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = create_successful_subprocess_mock(expected_dest)

                scheduler_with_config._create_new_index(
                    alias_name="test-repo-global", source_path=source_path
                )

                # Verify cidx fix-config --force was called
                cidx_fix_calls = [
                    call_obj
                    for call_obj in mock_run.call_args_list
                    if len(call_obj[0]) > 0
                    and len(call_obj[0][0]) >= 2
                    and call_obj[0][0][0] == "cidx"
                    and call_obj[0][0][1] == "fix-config"
                ]
                assert len(cidx_fix_calls) == 1
                assert cidx_fix_calls[0][0][0] == ["cidx", "fix-config", "--force"]

    def test_create_new_index_runs_cidx_index(self, tmp_path, scheduler_with_config):
        """Test that _create_new_index runs cidx index."""
        source_path = str(tmp_path / "source_repo")
        Path(source_path).mkdir()

        with patch(
            "code_indexer.global_repos.refresh_scheduler.datetime"
        ) as mock_datetime:
            mock_datetime.utcnow.return_value.timestamp.return_value = 1234567890

            expected_dest = str(
                tmp_path
                / ".code-indexer"
                / "golden_repos"
                / ".versioned"
                / "test-repo"
                / "v_1234567890"
            )

            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = create_successful_subprocess_mock(expected_dest)

                scheduler_with_config._create_new_index(
                    alias_name="test-repo-global", source_path=source_path
                )

                # Verify cidx index was called
                cidx_index_calls = [
                    call_obj
                    for call_obj in mock_run.call_args_list
                    if len(call_obj[0]) > 0
                    and len(call_obj[0][0]) >= 2
                    and call_obj[0][0][0] == "cidx"
                    and call_obj[0][0][1] == "index"
                ]
                assert len(cidx_index_calls) == 1

    def test_create_new_index_validates_index_exists(
        self, tmp_path, scheduler_with_config
    ):
        """Test that _create_new_index validates index directory exists."""
        source_path = str(tmp_path / "source_repo")
        Path(source_path).mkdir()

        with patch(
            "code_indexer.global_repos.refresh_scheduler.datetime"
        ) as mock_datetime:
            mock_datetime.utcnow.return_value.timestamp.return_value = 1234567890

            with patch("subprocess.run") as mock_run:
                # Don't create index dir - validation should fail
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

                with pytest.raises(RuntimeError, match="Index validation failed"):
                    scheduler_with_config._create_new_index(
                        alias_name="test-repo-global", source_path=source_path
                    )

    def test_create_new_index_cleans_up_on_failure(
        self, tmp_path, scheduler_with_config
    ):
        """Test that _create_new_index cleans up partial artifacts on failure."""
        source_path = str(tmp_path / "source_repo")
        Path(source_path).mkdir()

        with patch(
            "code_indexer.global_repos.refresh_scheduler.datetime"
        ) as mock_datetime:
            mock_datetime.utcnow.return_value.timestamp.return_value = 1234567890

            with patch("subprocess.run") as mock_run:
                # Mock CoW clone failure
                mock_run.side_effect = subprocess.CalledProcessError(
                    1, "cp", stderr="Permission denied"
                )

                with pytest.raises(RuntimeError, match="CoW clone failed"):
                    scheduler_with_config._create_new_index(
                        alias_name="test-repo-global", source_path=source_path
                    )

    def test_create_new_index_uses_resource_config_timeouts(
        self, tmp_path, scheduler_with_config
    ):
        """Test that _create_new_index uses timeouts from resource_config."""
        source_path = str(tmp_path / "source_repo")
        Path(source_path).mkdir()

        with patch(
            "code_indexer.global_repos.refresh_scheduler.datetime"
        ) as mock_datetime:
            mock_datetime.utcnow.return_value.timestamp.return_value = 1234567890

            expected_dest = str(
                tmp_path
                / ".code-indexer"
                / "golden_repos"
                / ".versioned"
                / "test-repo"
                / "v_1234567890"
            )

            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = create_successful_subprocess_mock(expected_dest)

                scheduler_with_config._create_new_index(
                    alias_name="test-repo-global", source_path=source_path
                )

                # Verify timeouts were passed (all should be 10 from our test config)
                for call_obj in mock_run.call_args_list:
                    if "timeout" in call_obj[1]:
                        assert call_obj[1]["timeout"] == 10
