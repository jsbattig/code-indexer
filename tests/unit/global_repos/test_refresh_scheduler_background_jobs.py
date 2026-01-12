"""
Unit tests for RefreshScheduler BackgroundJobManager integration.

Tests Story #703: Refactor RefreshScheduler to use BackgroundJobManager
for job submission instead of direct execution.
"""

from unittest.mock import patch, MagicMock

import pytest

from code_indexer.global_repos.refresh_scheduler import RefreshScheduler
from code_indexer.global_repos.query_tracker import QueryTracker
from code_indexer.global_repos.cleanup_manager import CleanupManager
from code_indexer.config import ConfigManager


class TestRefreshSchedulerBackgroundJobManagerIntegration:
    """Test suite for RefreshScheduler + BackgroundJobManager integration."""

    @pytest.fixture
    def golden_repos_dir(self, tmp_path):
        """Create a golden repos directory structure."""
        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)
        return golden_repos_dir

    @pytest.fixture
    def config_mgr(self, tmp_path):
        """Create a ConfigManager instance."""
        return ConfigManager(tmp_path / ".code-indexer" / "config.json")

    @pytest.fixture
    def query_tracker(self):
        """Create a QueryTracker instance."""
        return QueryTracker()

    @pytest.fixture
    def cleanup_manager(self, query_tracker):
        """Create a CleanupManager instance."""
        return CleanupManager(query_tracker)

    @pytest.fixture
    def mock_background_job_manager(self):
        """Create a mock BackgroundJobManager."""
        manager = MagicMock()
        manager.submit_job = MagicMock(return_value="test-job-id-123")
        return manager

    def test_scheduler_accepts_background_job_manager_parameter(
        self,
        golden_repos_dir,
        config_mgr,
        query_tracker,
        cleanup_manager,
        mock_background_job_manager,
    ):
        """Test that RefreshScheduler accepts optional background_job_manager parameter."""
        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=query_tracker,
            cleanup_manager=cleanup_manager,
            background_job_manager=mock_background_job_manager,
        )

        assert scheduler.background_job_manager is mock_background_job_manager

    def test_scheduler_background_job_manager_defaults_to_none(
        self, golden_repos_dir, config_mgr, query_tracker, cleanup_manager
    ):
        """Test that BackgroundJobManager defaults to None when not provided (CLI mode)."""
        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=query_tracker,
            cleanup_manager=cleanup_manager,
        )

        assert scheduler.background_job_manager is None

    def test_submit_refresh_job_submits_to_background_job_manager(
        self,
        golden_repos_dir,
        config_mgr,
        query_tracker,
        cleanup_manager,
        mock_background_job_manager,
    ):
        """Test that _submit_refresh_job() submits job to BackgroundJobManager."""
        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=query_tracker,
            cleanup_manager=cleanup_manager,
            background_job_manager=mock_background_job_manager,
        )

        job_id = scheduler._submit_refresh_job("test-repo-global")

        assert job_id == "test-job-id-123"
        mock_background_job_manager.submit_job.assert_called_once()

    def test_submit_refresh_job_returns_none_without_background_job_manager(
        self, golden_repos_dir, config_mgr, query_tracker, cleanup_manager
    ):
        """Test that _submit_refresh_job() falls back to direct execution without BackgroundJobManager."""
        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=query_tracker,
            cleanup_manager=cleanup_manager,
        )

        with patch.object(scheduler, "_execute_refresh") as mock_execute:
            result = scheduler._submit_refresh_job("test-repo-global")

            assert result is None
            mock_execute.assert_called_once_with("test-repo-global")

    def test_submit_refresh_job_passes_correct_parameters(
        self,
        golden_repos_dir,
        config_mgr,
        query_tracker,
        cleanup_manager,
        mock_background_job_manager,
    ):
        """Test that _submit_refresh_job passes correct parameters to BackgroundJobManager."""
        from unittest.mock import ANY

        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=query_tracker,
            cleanup_manager=cleanup_manager,
            background_job_manager=mock_background_job_manager,
        )

        scheduler._submit_refresh_job("test-repo-global")

        mock_background_job_manager.submit_job.assert_called_once_with(
            operation_type="global_repo_refresh",
            func=ANY,
            submitter_username="system",
            is_admin=True,
            repo_alias="test-repo-global",
        )

    def test_submit_refresh_job_lambda_executes_correctly(
        self,
        golden_repos_dir,
        config_mgr,
        query_tracker,
        cleanup_manager,
        mock_background_job_manager,
    ):
        """Test that the submitted lambda calls _execute_refresh with correct alias."""
        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=query_tracker,
            cleanup_manager=cleanup_manager,
            background_job_manager=mock_background_job_manager,
        )

        with patch.object(
            scheduler, "_execute_refresh", return_value={"success": True}
        ) as mock_execute:
            scheduler._submit_refresh_job("test-repo-global")

            # Get the lambda that was passed
            call_args = mock_background_job_manager.submit_job.call_args
            submitted_func = call_args.kwargs["func"]

            # Execute the lambda
            submitted_func()

            # Verify _execute_refresh was called with correct alias
            mock_execute.assert_called_once_with("test-repo-global")

    def test_execute_refresh_returns_error_dict_on_exception(
        self,
        golden_repos_dir,
        config_mgr,
        query_tracker,
        cleanup_manager,
    ):
        """Test that _execute_refresh returns error dict on exception."""
        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=query_tracker,
            cleanup_manager=cleanup_manager,
        )

        with patch.object(
            scheduler.alias_manager, "read_alias", side_effect=Exception("Test error")
        ):
            result = scheduler._execute_refresh("test-repo-global")

            assert result["success"] is False
            assert result["alias"] == "test-repo-global"
            assert "error" in result
            assert "message" in result  # After HIGH-2 fix
            assert "Test error" in result["error"]


class TestGlobalReposLifecycleManagerBackgroundJobManager:
    """Test suite for GlobalReposLifecycleManager BackgroundJobManager integration."""

    def test_lifecycle_manager_accepts_background_job_manager_parameter(self, tmp_path):
        """Test that GlobalReposLifecycleManager accepts optional background_job_manager parameter."""
        from code_indexer.server.lifecycle.global_repos_lifecycle import (
            GlobalReposLifecycleManager,
        )

        mock_bjm = MagicMock()

        lifecycle_mgr = GlobalReposLifecycleManager(
            str(tmp_path / "golden_repos"),
            background_job_manager=mock_bjm,
        )

        assert lifecycle_mgr.refresh_scheduler.background_job_manager is mock_bjm

    def test_lifecycle_manager_background_job_manager_defaults_to_none(self, tmp_path):
        """Test that GlobalReposLifecycleManager defaults background_job_manager to None."""
        from code_indexer.server.lifecycle.global_repos_lifecycle import (
            GlobalReposLifecycleManager,
        )

        lifecycle_mgr = GlobalReposLifecycleManager(str(tmp_path / "golden_repos"))

        assert lifecycle_mgr.refresh_scheduler.background_job_manager is None
