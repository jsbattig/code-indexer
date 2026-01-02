"""
Integration tests for GitSyncExecutor → GitStateManager clearing hook (Story #659, Priority 5).

Validates that GitStateManager.clear_repo_before_refresh is automatically called
when repository is dirty and behind remote before attempting git pull.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.code_indexer.server.git.git_sync_executor import (
    GitSyncExecutor,
    GitSyncError,
    RepositoryValidationResult,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_git_repo(tmp_path):
    """Create a temporary git repository for testing."""
    import subprocess

    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
    )

    # Create initial commit
    (repo_path / "README.md").write_text("# Test Repo")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)

    yield repo_path


@pytest.fixture
def git_sync_executor(temp_git_repo):
    """Create GitSyncExecutor for testing."""
    return GitSyncExecutor(repository_path=temp_git_repo, auto_index_on_changes=False)


# =============================================================================
# Integration Tests
# =============================================================================


def test_clearing_triggered_when_dirty_and_behind_remote(
    git_sync_executor, temp_git_repo
):
    """
    Test that clearing is triggered when repo is dirty and behind remote.

    Flow:
    1. Validation detects dirty state + behind remote
    2. GitStateManager.clear_repo_before_refresh is called BEFORE pull
    3. Clearing succeeds
    4. Pull proceeds normally
    """
    # Mock validation to simulate dirty + behind remote state
    dirty_validation = RepositoryValidationResult(
        is_valid=True,
        can_pull=False,  # Fails validation due to dirty + behind
        has_uncommitted_changes=True,
        is_detached_head=False,
        is_behind_remote=True,
        validation_errors=["Cannot pull with uncommitted changes when behind remote"],
        branch_name="main",
        commit_hash="abc123",
    )

    with patch.object(
        git_sync_executor, "validate_repository_state", return_value=dirty_validation
    ):
        with patch(
            "src.code_indexer.server.git.git_sync_executor.GitStateManager"
        ) as MockGitStateManager:
            mock_git_manager = MockGitStateManager.return_value
            mock_clear = mock_git_manager.clear_repo_before_refresh

            # After clearing, validation should pass
            clean_validation = RepositoryValidationResult(
                is_valid=True,
                can_pull=True,
                has_uncommitted_changes=False,
                is_detached_head=False,
                is_behind_remote=True,
                validation_errors=[],
                branch_name="main",
                commit_hash="abc123",
            )

            # First validation fails (dirty), second validation passes (after clearing)
            git_sync_executor.validate_repository_state.side_effect = [
                dirty_validation,
                clean_validation,
            ]

            # Mock the actual pull execution to avoid real git operations
            with patch.object(
                git_sync_executor,
                "_execute_git_pull",
                return_value="Already up to date",
            ):
                with patch.object(git_sync_executor, "create_backup") as mock_backup:
                    mock_backup.return_value = MagicMock(
                        success=True, backup_path="/tmp/backup"
                    )

                    # Act: Execute pull (should trigger clearing)
                    result = git_sync_executor.execute_pull()

    # Assert: Clearing was called with correct parameters
    mock_clear.assert_called_once()
    call_kwargs = mock_clear.call_args.kwargs
    assert "repo_path" in call_kwargs
    assert call_kwargs["repo_path"] == temp_git_repo

    # Assert: Pull succeeded after clearing
    assert result.success is True


def test_clearing_not_triggered_when_clean_and_behind_remote(
    git_sync_executor, temp_git_repo
):
    """
    Test that clearing is NOT triggered when repo is clean (even if behind remote).

    Flow:
    1. Validation shows clean state (no uncommitted changes)
    2. GitStateManager.clear_repo_before_refresh NOT called
    3. Pull proceeds normally
    """
    # Mock validation to simulate clean + behind remote state
    clean_validation = RepositoryValidationResult(
        is_valid=True,
        can_pull=True,  # Can pull normally
        has_uncommitted_changes=False,
        is_detached_head=False,
        is_behind_remote=True,
        validation_errors=[],
        branch_name="main",
        commit_hash="abc123",
    )

    with patch.object(
        git_sync_executor, "validate_repository_state", return_value=clean_validation
    ):
        with patch(
            "src.code_indexer.server.git.git_sync_executor.GitStateManager"
        ) as MockGitStateManager:
            mock_git_manager = MockGitStateManager.return_value
            mock_clear = mock_git_manager.clear_repo_before_refresh

            # Mock the actual pull execution
            with patch.object(
                git_sync_executor,
                "_execute_git_pull",
                return_value="Already up to date",
            ):
                with patch.object(git_sync_executor, "create_backup") as mock_backup:
                    mock_backup.return_value = MagicMock(
                        success=True, backup_path="/tmp/backup"
                    )

                    # Act: Execute pull
                    result = git_sync_executor.execute_pull()

    # Assert: Clearing NOT called (repo was clean)
    mock_clear.assert_not_called()

    # Assert: Pull succeeded normally
    assert result.success is True


def test_clearing_not_triggered_when_dirty_but_not_behind_remote(
    git_sync_executor, temp_git_repo
):
    """
    Test that clearing is NOT triggered when repo is dirty but NOT behind remote.

    Flow:
    1. Validation shows dirty state but not behind remote
    2. GitStateManager.clear_repo_before_refresh NOT called
    3. Pull may proceed or fail based on validation, but clearing not involved
    """
    # Mock validation to simulate dirty but not behind remote
    dirty_not_behind_validation = RepositoryValidationResult(
        is_valid=True,
        can_pull=True,  # Can pull (dirty but up-to-date with remote)
        has_uncommitted_changes=True,
        is_detached_head=False,
        is_behind_remote=False,
        validation_errors=[],
        branch_name="main",
        commit_hash="abc123",
    )

    with patch.object(
        git_sync_executor,
        "validate_repository_state",
        return_value=dirty_not_behind_validation,
    ):
        with patch(
            "src.code_indexer.server.git.git_sync_executor.GitStateManager"
        ) as MockGitStateManager:
            mock_git_manager = MockGitStateManager.return_value
            mock_clear = mock_git_manager.clear_repo_before_refresh

            # Mock the actual pull execution
            with patch.object(
                git_sync_executor,
                "_execute_git_pull",
                return_value="Already up to date",
            ):
                with patch.object(git_sync_executor, "create_backup") as mock_backup:
                    mock_backup.return_value = MagicMock(
                        success=True, backup_path="/tmp/backup"
                    )

                    # Act: Execute pull
                    result = git_sync_executor.execute_pull()

    # Assert: Clearing NOT called (not behind remote)
    mock_clear.assert_not_called()

    # Assert: Pull succeeded
    assert result.success is True


def test_clearing_error_does_not_block_pull_retry(git_sync_executor, temp_git_repo):
    """
    Test that errors during clearing do NOT permanently block pull operation.

    Flow:
    1. Validation detects dirty + behind remote
    2. GitStateManager.clear_repo_before_refresh raises exception
    3. Error is logged but not propagated
    4. Validation failure still prevents pull (dirty state persists)
    5. GitSyncError raised with appropriate error code
    """
    # Mock validation to simulate dirty + behind remote state (persistent)
    dirty_validation = RepositoryValidationResult(
        is_valid=True,
        can_pull=False,
        has_uncommitted_changes=True,
        is_detached_head=False,
        is_behind_remote=True,
        validation_errors=["Cannot pull with uncommitted changes when behind remote"],
        branch_name="main",
        commit_hash="abc123",
    )

    with patch.object(
        git_sync_executor, "validate_repository_state", return_value=dirty_validation
    ):
        with patch(
            "src.code_indexer.server.git.git_sync_executor.GitStateManager"
        ) as MockGitStateManager:
            mock_git_manager = MockGitStateManager.return_value
            mock_git_manager.clear_repo_before_refresh.side_effect = Exception(
                "Git reset failed: disk full"
            )

            # Act & Assert: Pull fails with validation error (not clearing error)
            with pytest.raises(GitSyncError) as exc_info:
                git_sync_executor.execute_pull()

            # Assert: Error is validation failure, not clearing failure
            assert exc_info.value.error_code == "VALIDATION_FAILED"
            assert "Repository not ready for pull" in str(exc_info.value)
