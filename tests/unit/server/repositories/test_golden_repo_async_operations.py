"""
Unit tests for async golden repository operations.

Tests the async refactoring of golden repository operations:
- refresh_golden_repo returns job_id instead of Dict
- add_golden_repo returns job_id and submits background job
- remove_golden_repo returns job_id and submits background job
"""

import json
import os
import tempfile
from unittest.mock import patch, MagicMock, Mock

import pytest

from src.code_indexer.server.repositories.golden_repo_manager import (
    GoldenRepoManager,
    GoldenRepoError,
    ResourceLimitError,
)
from src.code_indexer.server.repositories.background_jobs import BackgroundJobManager


class TestGoldenRepoAsyncOperations:
    """Test suite for async golden repository operations."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def mock_background_job_manager(self):
        """Create mock BackgroundJobManager."""
        mock_manager = MagicMock(spec=BackgroundJobManager)
        mock_manager.submit_job.return_value = "test-job-id-12345"
        return mock_manager

    @pytest.fixture
    def golden_repo_manager(self, temp_data_dir, mock_background_job_manager):
        """Create GoldenRepoManager instance with mocked background job manager."""
        manager = GoldenRepoManager(data_dir=temp_data_dir)
        manager.background_job_manager = mock_background_job_manager
        return manager

    @pytest.fixture
    def manager_with_existing_repo(self, golden_repo_manager):
        """Create manager with an existing golden repo."""
        # Create metadata for existing repo
        golden_repos_dir = golden_repo_manager.golden_repos_dir
        clone_path = os.path.join(golden_repos_dir, "test-repo")
        os.makedirs(clone_path, exist_ok=True)

        # Add repo to manager
        from src.code_indexer.server.repositories.golden_repo_manager import GoldenRepo
        from datetime import datetime, timezone

        golden_repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path=clone_path,
            created_at=datetime.now(timezone.utc).isoformat(),
            enable_temporal=False,
            temporal_options=None,
        )
        golden_repo_manager.golden_repos["test-repo"] = golden_repo
        golden_repo_manager._save_metadata()

        return golden_repo_manager

    # Test refresh_golden_repo
    def test_refresh_golden_repo_returns_job_id(self, manager_with_existing_repo):
        """Test that refresh_golden_repo returns a job_id string."""
        # Mock git operations
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            result = manager_with_existing_repo.refresh_golden_repo("test-repo")

            # Should return job_id string, not Dict
            assert isinstance(result, str)
            assert result == "test-job-id-12345"

    def test_refresh_golden_repo_submits_background_job(
        self, manager_with_existing_repo
    ):
        """Test that refresh_golden_repo submits job to BackgroundJobManager."""
        # Mock git operations
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            manager_with_existing_repo.refresh_golden_repo("test-repo")

            # Verify job was submitted
            manager_with_existing_repo.background_job_manager.submit_job.assert_called_once()

            # Verify job parameters
            call_args = (
                manager_with_existing_repo.background_job_manager.submit_job.call_args
            )
            assert call_args[1]["operation_type"] == "refresh_golden_repo"
            assert call_args[1]["submitter_username"] == "admin"
            assert call_args[1]["is_admin"] is True

    def test_refresh_golden_repo_validates_before_job_submission(
        self, golden_repo_manager
    ):
        """Test that refresh_golden_repo validates repo exists before submitting job."""
        with pytest.raises(
            GoldenRepoError, match="Golden repository 'nonexistent' not found"
        ):
            golden_repo_manager.refresh_golden_repo("nonexistent")

        # Job should NOT have been submitted
        golden_repo_manager.background_job_manager.submit_job.assert_not_called()

    # Test add_golden_repo
    def test_add_golden_repo_returns_job_id(self, golden_repo_manager):
        """Test that add_golden_repo returns a job_id string."""
        with patch.object(
            golden_repo_manager, "_validate_git_repository"
        ) as mock_validate:
            mock_validate.return_value = True

            # Mock clone and workflow
            with patch.object(golden_repo_manager, "_clone_repository") as mock_clone:
                mock_clone.return_value = "/path/to/cloned/repo"
                with patch.object(golden_repo_manager, "_execute_post_clone_workflow"):
                    with patch.object(
                        golden_repo_manager, "_get_repository_size"
                    ) as mock_size:
                        mock_size.return_value = 1000  # Small repo

                        result = golden_repo_manager.add_golden_repo(
                            repo_url="https://github.com/test/new-repo.git",
                            alias="new-repo",
                        )

                        # Should return job_id string, not Dict
                        assert isinstance(result, str)
                        assert result == "test-job-id-12345"

    def test_add_golden_repo_submits_background_job(self, golden_repo_manager):
        """Test that add_golden_repo submits job to BackgroundJobManager."""
        with patch.object(
            golden_repo_manager, "_validate_git_repository"
        ) as mock_validate:
            mock_validate.return_value = True

            # Mock clone and workflow
            with patch.object(golden_repo_manager, "_clone_repository") as mock_clone:
                mock_clone.return_value = "/path/to/cloned/repo"
                with patch.object(golden_repo_manager, "_execute_post_clone_workflow"):
                    with patch.object(
                        golden_repo_manager, "_get_repository_size"
                    ) as mock_size:
                        mock_size.return_value = 1000  # Small repo

                        golden_repo_manager.add_golden_repo(
                            repo_url="https://github.com/test/new-repo.git",
                            alias="new-repo",
                        )

                        # Verify job was submitted
                        golden_repo_manager.background_job_manager.submit_job.assert_called_once()

                        # Verify job parameters
                        call_args = (
                            golden_repo_manager.background_job_manager.submit_job.call_args
                        )
                        assert call_args[1]["operation_type"] == "add_golden_repo"
                        assert call_args[1]["submitter_username"] == "admin"
                        assert call_args[1]["is_admin"] is True

    def test_add_golden_repo_validates_before_job_submission(self, golden_repo_manager):
        """Test that add_golden_repo validates limits/duplicates before submitting job."""
        # Manually add a repo to test duplicate alias validation
        from src.code_indexer.server.repositories.golden_repo_manager import GoldenRepo
        from datetime import datetime, timezone

        golden_repo = GoldenRepo(
            alias="duplicate",
            repo_url="https://github.com/test/repo1.git",
            default_branch="main",
            clone_path="/path/to/repo1",
            created_at=datetime.now(timezone.utc).isoformat(),
            enable_temporal=False,
            temporal_options=None,
        )
        golden_repo_manager.golden_repos["duplicate"] = golden_repo

        # Try to add duplicate - should fail validation before job submission
        with patch.object(
            golden_repo_manager, "_validate_git_repository"
        ) as mock_validate:
            mock_validate.return_value = True

            with pytest.raises(
                GoldenRepoError,
                match="Golden repository alias 'duplicate' already exists",
            ):
                golden_repo_manager.add_golden_repo(
                    repo_url="https://github.com/test/repo2.git",
                    alias="duplicate",
                )

            # Job should NOT have been submitted
            golden_repo_manager.background_job_manager.submit_job.assert_not_called()

    def test_add_golden_repo_validates_max_repos_limit(self, golden_repo_manager):
        """Test that add_golden_repo validates MAX_GOLDEN_REPOS limit before job submission."""
        # Fill up to max
        for i in range(GoldenRepoManager.MAX_GOLDEN_REPOS):
            from src.code_indexer.server.repositories.golden_repo_manager import (
                GoldenRepo,
            )
            from datetime import datetime, timezone

            golden_repo = GoldenRepo(
                alias=f"repo-{i}",
                repo_url=f"https://github.com/test/repo{i}.git",
                default_branch="main",
                clone_path=f"/path/to/repo{i}",
                created_at=datetime.now(timezone.utc).isoformat(),
                enable_temporal=False,
                temporal_options=None,
            )
            golden_repo_manager.golden_repos[f"repo-{i}"] = golden_repo

        # Try to add one more - should fail validation
        with patch.object(
            golden_repo_manager, "_validate_git_repository"
        ) as mock_validate:
            mock_validate.return_value = True

            with pytest.raises(
                ResourceLimitError,
                match=f"Maximum of {GoldenRepoManager.MAX_GOLDEN_REPOS} golden repositories allowed",
            ):
                golden_repo_manager.add_golden_repo(
                    repo_url="https://github.com/test/overflow.git",
                    alias="overflow",
                )

            # Job should NOT have been submitted
            golden_repo_manager.background_job_manager.submit_job.assert_not_called()

    # Test remove_golden_repo
    def test_remove_golden_repo_returns_job_id(self, manager_with_existing_repo):
        """Test that remove_golden_repo returns a job_id string."""
        result = manager_with_existing_repo.remove_golden_repo("test-repo")

        # Should return job_id string, not Dict
        assert isinstance(result, str)
        assert result == "test-job-id-12345"

    def test_remove_golden_repo_submits_background_job(
        self, manager_with_existing_repo
    ):
        """Test that remove_golden_repo submits job to BackgroundJobManager."""
        manager_with_existing_repo.remove_golden_repo("test-repo")

        # Verify job was submitted
        manager_with_existing_repo.background_job_manager.submit_job.assert_called_once()

        # Verify job parameters
        call_args = (
            manager_with_existing_repo.background_job_manager.submit_job.call_args
        )
        assert call_args[1]["operation_type"] == "remove_golden_repo"
        assert call_args[1]["submitter_username"] == "admin"
        assert call_args[1]["is_admin"] is True

    def test_remove_golden_repo_validates_before_job_submission(
        self, golden_repo_manager
    ):
        """Test that remove_golden_repo validates repo exists before submitting job."""
        with pytest.raises(
            GoldenRepoError, match="Golden repository 'nonexistent' not found"
        ):
            golden_repo_manager.remove_golden_repo("nonexistent")

        # Job should NOT have been submitted
        golden_repo_manager.background_job_manager.submit_job.assert_not_called()

    # Test background worker execution
    def test_refresh_golden_repo_background_worker_callable(
        self, manager_with_existing_repo
    ):
        """Test that refresh_golden_repo submits a callable with no args."""
        # Mock git operations
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            manager_with_existing_repo.refresh_golden_repo("test-repo")

            # Get the func argument passed to submit_job
            call_args = (
                manager_with_existing_repo.background_job_manager.submit_job.call_args
            )
            func = call_args[1]["func"]

            # Verify it's callable
            assert callable(func)

            # Verify it takes no arguments (wrapper pattern)
            import inspect

            sig = inspect.signature(func)
            assert len(sig.parameters) == 0

    def test_add_golden_repo_background_worker_callable(self, golden_repo_manager):
        """Test that add_golden_repo submits a callable with no args."""
        with patch.object(
            golden_repo_manager, "_validate_git_repository"
        ) as mock_validate:
            mock_validate.return_value = True

            # Mock clone and workflow
            with patch.object(golden_repo_manager, "_clone_repository") as mock_clone:
                mock_clone.return_value = "/path/to/cloned/repo"
                with patch.object(golden_repo_manager, "_execute_post_clone_workflow"):
                    with patch.object(
                        golden_repo_manager, "_get_repository_size"
                    ) as mock_size:
                        mock_size.return_value = 1000  # Small repo

                        golden_repo_manager.add_golden_repo(
                            repo_url="https://github.com/test/new-repo.git",
                            alias="new-repo",
                        )

                        # Get the func argument passed to submit_job
                        call_args = (
                            golden_repo_manager.background_job_manager.submit_job.call_args
                        )
                        func = call_args[1]["func"]

                        # Verify it's callable
                        assert callable(func)

                        # Verify it takes no arguments (wrapper pattern)
                        import inspect

                        sig = inspect.signature(func)
                        assert len(sig.parameters) == 0

    def test_remove_golden_repo_background_worker_callable(
        self, manager_with_existing_repo
    ):
        """Test that remove_golden_repo submits a callable with no args."""
        manager_with_existing_repo.remove_golden_repo("test-repo")

        # Get the func argument passed to submit_job
        call_args = (
            manager_with_existing_repo.background_job_manager.submit_job.call_args
        )
        func = call_args[1]["func"]

        # Verify it's callable
        assert callable(func)

        # Verify it takes no arguments (wrapper pattern)
        import inspect

        sig = inspect.signature(func)
        assert len(sig.parameters) == 0

    # Test Anti-Fallback Rule compliance (MESSI Rule 2)
    def test_remove_golden_repo_cleanup_failure_raises_exception(
        self, manager_with_existing_repo
    ):
        """Test that cleanup failures cause operation to fail (Anti-Fallback rule compliance).

        Per MESSI Rule 2 (Anti-Fallback): "Graceful failure over forced success"
        When cleanup fails, the operation MUST fail with clear error, not report "success with warnings".
        """
        # Mock cleanup to fail
        with patch.object(
            manager_with_existing_repo, "_cleanup_repository_files"
        ) as mock_cleanup:
            mock_cleanup.return_value = False  # Cleanup failed

            # Get the background worker function
            manager_with_existing_repo.remove_golden_repo("test-repo")
            call_args = (
                manager_with_existing_repo.background_job_manager.submit_job.call_args
            )
            background_worker = call_args[1]["func"]

            # Execute background worker - should raise GitOperationError when cleanup fails
            from src.code_indexer.server.repositories.golden_repo_manager import (
                GitOperationError,
            )

            with pytest.raises(
                GitOperationError, match="cleanup incomplete|Resource leak"
            ):
                background_worker()

    def test_remove_golden_repo_cleanup_success_no_exception(
        self, manager_with_existing_repo
    ):
        """Test that successful cleanup completes without exception."""
        # Mock cleanup to succeed
        with patch.object(
            manager_with_existing_repo, "_cleanup_repository_files"
        ) as mock_cleanup:
            mock_cleanup.return_value = True  # Cleanup succeeded

            # Get the background worker function
            manager_with_existing_repo.remove_golden_repo("test-repo")
            call_args = (
                manager_with_existing_repo.background_job_manager.submit_job.call_args
            )
            background_worker = call_args[1]["func"]

            # Execute background worker - should complete successfully
            result = background_worker()

            # Verify success
            assert result["success"] is True
            assert "removed successfully" in result["message"]
            assert "warnings" not in result  # No warnings for successful cleanup

    # Test Audit Trail (submitter_username parameter)
    def test_add_golden_repo_passes_username_to_job_manager(self, golden_repo_manager):
        """Verify actual username is passed to background job manager."""
        with patch.object(
            golden_repo_manager, "_validate_git_repository"
        ) as mock_validate:
            mock_validate.return_value = True

            golden_repo_manager.add_golden_repo(
                repo_url="https://github.com/test/repo.git",
                alias="test-repo",
                submitter_username="alice",
            )

            # Verify submit_job was called with correct username
            golden_repo_manager.background_job_manager.submit_job.assert_called_once()
            call_kwargs = (
                golden_repo_manager.background_job_manager.submit_job.call_args[1]
            )
            assert call_kwargs["submitter_username"] == "alice"
            assert call_kwargs["is_admin"] is True

    def test_remove_golden_repo_passes_username_to_job_manager(
        self, manager_with_existing_repo
    ):
        """Verify actual username is passed to background job manager for removal."""
        manager_with_existing_repo.remove_golden_repo(
            "test-repo", submitter_username="bob"
        )

        # Verify submit_job was called with correct username
        call_kwargs = (
            manager_with_existing_repo.background_job_manager.submit_job.call_args[1]
        )
        assert call_kwargs["submitter_username"] == "bob"
        assert call_kwargs["is_admin"] is True

    def test_refresh_golden_repo_passes_username_to_job_manager(
        self, manager_with_existing_repo
    ):
        """Verify actual username is passed to background job manager for refresh."""
        manager_with_existing_repo.refresh_golden_repo(
            "test-repo", submitter_username="charlie"
        )

        # Verify submit_job was called with correct username
        call_kwargs = (
            manager_with_existing_repo.background_job_manager.submit_job.call_args[1]
        )
        assert call_kwargs["submitter_username"] == "charlie"
        assert call_kwargs["is_admin"] is True

    def test_add_golden_repo_default_username_is_admin(self, golden_repo_manager):
        """Verify default username is 'admin' when not specified."""
        with patch.object(
            golden_repo_manager, "_validate_git_repository"
        ) as mock_validate:
            mock_validate.return_value = True

            # Call without submitter_username parameter
            golden_repo_manager.add_golden_repo(
                repo_url="https://github.com/test/repo.git", alias="test-repo"
            )

            # Verify default username is "admin"
            call_kwargs = (
                golden_repo_manager.background_job_manager.submit_job.call_args[1]
            )
            assert call_kwargs["submitter_username"] == "admin"

    def test_remove_golden_repo_default_username_is_admin(
        self, manager_with_existing_repo
    ):
        """Verify default username is 'admin' when not specified."""
        # Call without submitter_username parameter
        manager_with_existing_repo.remove_golden_repo("test-repo")

        # Verify default username is "admin"
        call_kwargs = (
            manager_with_existing_repo.background_job_manager.submit_job.call_args[1]
        )
        assert call_kwargs["submitter_username"] == "admin"

    def test_refresh_golden_repo_default_username_is_admin(
        self, manager_with_existing_repo
    ):
        """Verify default username is 'admin' when not specified."""
        # Call without submitter_username parameter
        manager_with_existing_repo.refresh_golden_repo("test-repo")

        # Verify default username is "admin"
        call_kwargs = (
            manager_with_existing_repo.background_job_manager.submit_job.call_args[1]
        )
        assert call_kwargs["submitter_username"] == "admin"
