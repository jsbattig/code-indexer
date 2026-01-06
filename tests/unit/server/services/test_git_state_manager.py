"""
Unit tests for GitStateManager service.

Tests git state management operations for SCIP self-healing:
- Pre-refresh clearing workflow (AC2)
- Error handling (AC8)

Story #659: Git State Management for SCIP Self-Healing with PR Workflow
"""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.code_indexer.server.services.git_state_manager import (
    GitStateManager,
    GitStateError,
)


class TestGitStateManagerPreRefreshClearing:
    """Tests for pre-refresh clearing workflow (AC2)."""

    def test_clear_repo_before_refresh_with_uncommitted_changes(self, tmp_path):
        """AC2: Clear uncommitted changes before git pull."""
        # ARRANGE: Create mock config with feature enabled
        config = Mock(enable_pr_creation=True, default_branch="main")
        manager = GitStateManager(config=config)

        # Mock git commands to simulate dirty repository
        with patch(
            "src.code_indexer.server.services.git_state_manager.run_git_command"
        ) as mock_git:
            # First call: git status --porcelain (shows dirty state)
            # Second call: git reset --hard HEAD
            # Third call: git clean -fd
            # Fourth call: git status --porcelain (shows clean state)
            mock_git.side_effect = [
                Mock(stdout="M  modified_file.txt\n?? untracked.txt\n"),  # Dirty
                Mock(stdout=""),  # reset success
                Mock(stdout=""),  # clean success
                Mock(stdout=""),  # Clean
            ]

            # ACT
            result = manager.clear_repo_before_refresh(tmp_path)

            # ASSERT
            assert result.was_dirty is True
            assert result.files_cleared == 2  # modified_file.txt + untracked.txt
            assert mock_git.call_count == 4

            # Verify git reset --hard HEAD was called
            reset_call = [c for c in mock_git.call_args_list if "reset" in str(c)]
            assert len(reset_call) == 1
            assert "--hard" in reset_call[0][0][0]
            assert "HEAD" in reset_call[0][0][0]

            # Verify git clean -fd was called
            clean_call = [c for c in mock_git.call_args_list if "clean" in str(c)]
            assert len(clean_call) == 1
            assert "-fd" in clean_call[0][0][0]

    def test_clear_repo_before_refresh_already_clean(self, tmp_path):
        """AC2: Skip clearing if repository already clean."""
        # ARRANGE
        config = Mock(enable_pr_creation=True)
        manager = GitStateManager(config=config)

        with patch(
            "src.code_indexer.server.services.git_state_manager.run_git_command"
        ) as mock_git:
            # git status --porcelain returns empty (clean)
            mock_git.return_value = Mock(stdout="")

            # ACT
            result = manager.clear_repo_before_refresh(tmp_path)

            # ASSERT
            assert result.was_dirty is False
            assert result.files_cleared == 0
            # Only one status check, no reset/clean needed
            assert mock_git.call_count == 1

    def test_clear_repo_before_refresh_git_reset_fails(self, tmp_path):
        """AC8: Handle git reset --hard failure gracefully."""
        # ARRANGE
        config = Mock(enable_pr_creation=True)
        manager = GitStateManager(config=config)

        with patch(
            "src.code_indexer.server.services.git_state_manager.run_git_command"
        ) as mock_git:
            # First call: dirty state
            # Second call: git reset fails
            mock_git.side_effect = [
                Mock(stdout="M  file.txt\n"),  # Dirty
                subprocess.CalledProcessError(
                    1, ["git", "reset"], stderr="reset error"
                ),
            ]

            # ACT & ASSERT
            with pytest.raises(GitStateError) as exc_info:
                manager.clear_repo_before_refresh(tmp_path)

            assert "git reset --hard failed" in str(exc_info.value)
            assert "reset error" in str(exc_info.value)

    def test_clear_repo_before_refresh_git_clean_fails(self, tmp_path):
        """AC8: Handle git clean -fd failure gracefully."""
        # ARRANGE
        config = Mock(enable_pr_creation=True)
        manager = GitStateManager(config=config)

        with patch(
            "src.code_indexer.server.services.git_state_manager.run_git_command"
        ) as mock_git:
            # Dirty -> reset success -> clean fails
            mock_git.side_effect = [
                Mock(stdout="M  file.txt\n"),  # Dirty
                Mock(stdout=""),  # reset success
                subprocess.CalledProcessError(
                    1, ["git", "clean"], stderr="clean error"
                ),
            ]

            # ACT & ASSERT
            with pytest.raises(GitStateError) as exc_info:
                manager.clear_repo_before_refresh(tmp_path)

            assert "git clean -fd failed" in str(exc_info.value)
            assert "clean error" in str(exc_info.value)

    def test_clear_repo_before_refresh_not_clean_after_operations(self, tmp_path):
        """AC8: Fail if repository not clean after reset/clean."""
        # ARRANGE
        config = Mock(enable_pr_creation=True)
        manager = GitStateManager(config=config)

        with patch(
            "src.code_indexer.server.services.git_state_manager.run_git_command"
        ) as mock_git:
            # Dirty -> reset -> clean -> still dirty (should never happen)
            mock_git.side_effect = [
                Mock(stdout="M  file.txt\n"),  # Initial dirty
                Mock(stdout=""),  # reset success
                Mock(stdout=""),  # clean success
                Mock(stdout="M  file.txt\n"),  # Still dirty!
            ]

            # ACT & ASSERT
            with pytest.raises(GitStateError) as exc_info:
                manager.clear_repo_before_refresh(tmp_path)

            assert "Repository not clean after reset/clean" in str(exc_info.value)


class TestTokenAuthenticator:
    """Tests for token authentication resolution (AC3)."""

    def test_resolve_token_from_environment_github(self):
        """AC3: Resolve GitHub token from GH_TOKEN environment variable."""
        from src.code_indexer.server.services.git_state_manager import (
            TokenAuthenticator,
        )

        # ARRANGE
        with patch.dict("os.environ", {"GH_TOKEN": "env_token_12345"}):
            # ACT
            token = TokenAuthenticator.resolve_token("github")

            # ASSERT
            assert token == "env_token_12345"

    def test_resolve_token_from_environment_gitlab(self):
        """AC3: Resolve GitLab token from GITLAB_TOKEN environment variable."""
        from src.code_indexer.server.services.git_state_manager import (
            TokenAuthenticator,
        )

        # ARRANGE
        with patch.dict("os.environ", {"GITLAB_TOKEN": "gitlab_token_456"}):
            # ACT
            token = TokenAuthenticator.resolve_token("gitlab")

            # ASSERT
            assert token == "gitlab_token_456"

    def test_resolve_token_not_found(self):
        """AC3: Return None if token not found."""
        from src.code_indexer.server.services.git_state_manager import (
            TokenAuthenticator,
        )

        # ARRANGE: No environment variable, no file
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("pathlib.Path.exists", return_value=False),
        ):
            # ACT
            token = TokenAuthenticator.resolve_token("github")

            # ASSERT
            assert token is None


class TestGitStateManagerPRCreation:
    """Tests for PR creation after successful SCIP fix (AC1)."""

    def test_create_pr_after_fix_github_success(self, tmp_path):
        """AC1: Create GitHub PR after successful SCIP fix."""
        # ARRANGE
        config = Mock(
            enable_pr_creation=True, default_branch="main", pr_base_branch="main"
        )
        manager = GitStateManager(config=config)

        fix_description = "Fixed missing import statement in auth.py"
        files_modified = [Path("src/auth.py"), Path("src/utils.py")]
        pr_description = "Auto-fix: Missing imports"

        # Mock git operations
        with (
            patch(
                "src.code_indexer.server.services.git_state_manager.run_git_command"
            ) as mock_git,
            patch(
                "src.code_indexer.server.services.git_state_manager.GitHubPRClient"
            ) as mock_pr_client,
            patch(
                "src.code_indexer.server.services.git_state_manager.TokenAuthenticator.resolve_token"
            ) as mock_token,
        ):
            # Setup mocks
            mock_token.return_value = "github_token_123"
            mock_git.side_effect = [
                Mock(stdout="main\n"),  # git branch --show-current (original branch)
                Mock(stdout=""),  # git checkout -b scip-fix-...
                Mock(stdout=""),  # git add files
                Mock(stdout=""),  # git commit
                Mock(stdout="abc123\n"),  # git rev-parse HEAD (get commit hash)
                Mock(stdout=""),  # git push -u origin
                Mock(stdout=""),  # git checkout main (return to original)
            ]

            mock_pr_instance = Mock()
            mock_pr_instance.create_pull_request.return_value = (
                "https://github.com/owner/repo/pull/123"
            )
            mock_pr_client.return_value = mock_pr_instance

            # ACT
            result = manager.create_pr_after_fix(
                repo_path=tmp_path,
                fix_description=fix_description,
                files_modified=files_modified,
                pr_description=pr_description,
                platform="github",
            )

            # ASSERT
            assert result.success is True
            assert result.pr_url == "https://github.com/owner/repo/pull/123"
            assert result.branch_name.startswith("scip-fix-")
            assert "main" in result.message  # Should mention returning to main branch

            # Verify PR was created with correct parameters
            mock_pr_instance.create_pull_request.assert_called_once()
            call_args = mock_pr_instance.create_pull_request.call_args
            assert call_args[1]["title"].startswith("[SCIP Auto-Fix]")
            assert fix_description in call_args[1]["body"]
            assert "src/auth.py" in call_args[1]["body"]
            assert call_args[1]["base"] == "main"

    def test_create_pr_after_fix_gitlab_success(self, tmp_path):
        """AC1: Create GitLab MR after successful SCIP fix."""
        # ARRANGE
        config = Mock(
            enable_pr_creation=True, default_branch="develop", pr_base_branch="develop"
        )
        manager = GitStateManager(config=config)

        fix_description = "Fixed type annotation error"
        files_modified = [Path("src/models.py")]
        pr_description = "Auto-fix: Type errors"

        # Mock git operations
        with (
            patch(
                "src.code_indexer.server.services.git_state_manager.run_git_command"
            ) as mock_git,
            patch(
                "src.code_indexer.server.services.git_state_manager.GitLabPRClient"
            ) as mock_mr_client,
            patch(
                "src.code_indexer.server.services.git_state_manager.TokenAuthenticator.resolve_token"
            ) as mock_token,
        ):
            mock_token.return_value = "gitlab_token_456"
            mock_git.side_effect = [
                Mock(stdout="develop\n"),  # Current branch
                Mock(stdout=""),  # Checkout new branch
                Mock(stdout=""),  # Add files
                Mock(stdout=""),  # Commit
                Mock(stdout="def456\n"),  # git rev-parse HEAD (get commit hash)
                Mock(stdout=""),  # Push
                Mock(stdout=""),  # Return to develop
            ]

            mock_mr_instance = Mock()
            mock_mr_instance.create_merge_request.return_value = (
                "https://gitlab.com/owner/repo/-/merge_requests/456"
            )
            mock_mr_client.return_value = mock_mr_instance

            # ACT
            result = manager.create_pr_after_fix(
                repo_path=tmp_path,
                fix_description=fix_description,
                files_modified=files_modified,
                pr_description=pr_description,
                platform="gitlab",
            )

            # ASSERT
            assert result.success is True
            assert result.pr_url == "https://gitlab.com/owner/repo/-/merge_requests/456"
            assert "develop" in result.message

    def test_create_pr_after_fix_github_push_failure(self, tmp_path):
        """AC8: Handle git push failure gracefully."""
        # ARRANGE
        config = Mock(enable_pr_creation=True, default_branch="main")
        manager = GitStateManager(config=config)

        with (
            patch(
                "src.code_indexer.server.services.git_state_manager.run_git_command"
            ) as mock_git,
            patch(
                "src.code_indexer.server.services.git_state_manager.TokenAuthenticator.resolve_token"
            ) as mock_token,
        ):
            mock_token.return_value = "token"
            mock_git.side_effect = [
                Mock(stdout="main\n"),  # Current branch
                Mock(stdout=""),  # Checkout
                Mock(stdout=""),  # Add
                Mock(stdout=""),  # Commit
                Mock(stdout="xyz789\n"),  # git rev-parse HEAD (get commit hash)
                subprocess.CalledProcessError(
                    1, ["git", "push"], stderr="Permission denied"
                ),
                Mock(stdout=""),  # Return to main (should still happen)
            ]

            # ACT
            result = manager.create_pr_after_fix(
                repo_path=tmp_path,
                fix_description="Fix",
                files_modified=[Path("file.py")],
                pr_description="Auto-fix",
                platform="github",
            )

            # ASSERT
            assert result.success is False
            assert "git push failed" in result.message
            assert result.pr_url is None
            # Verify we attempted to return to original branch even after failure
            assert (
                mock_git.call_count == 7
            )  # Current + Checkout + Add + Commit + RevParse + Push(fail) + ReturnToBranch

    def test_create_pr_after_fix_pr_creation_failure(self, tmp_path):
        """AC8: Handle PR creation API failure gracefully."""
        # ARRANGE
        config = Mock(enable_pr_creation=True, default_branch="main")
        manager = GitStateManager(config=config)

        with (
            patch(
                "src.code_indexer.server.services.git_state_manager.run_git_command"
            ) as mock_git,
            patch(
                "src.code_indexer.server.services.git_state_manager.GitHubPRClient"
            ) as mock_pr_client,
            patch(
                "src.code_indexer.server.services.git_state_manager.TokenAuthenticator.resolve_token"
            ) as mock_token,
        ):
            mock_token.return_value = "token"
            mock_git.side_effect = [
                Mock(stdout="main\n"),
                Mock(stdout=""),  # Checkout
                Mock(stdout=""),  # Add
                Mock(stdout=""),  # Commit
                Mock(stdout="abc999\n"),  # git rev-parse HEAD (get commit hash)
                Mock(stdout=""),  # Push
                Mock(stdout=""),  # Return to main
            ]

            # PR creation raises exception
            mock_pr_instance = Mock()
            mock_pr_instance.create_pull_request.side_effect = Exception(
                "API rate limit exceeded"
            )
            mock_pr_client.return_value = mock_pr_instance

            # ACT
            result = manager.create_pr_after_fix(
                repo_path=tmp_path,
                fix_description="Fix",
                files_modified=[Path("file.py")],
                pr_description="Auto-fix",
                platform="github",
            )

            # ASSERT
            assert result.success is False
            assert "PR creation failed" in result.message
            assert "API rate limit exceeded" in result.message
            assert result.pr_url is None

    def test_create_pr_after_fix_returns_to_original_branch(self, tmp_path):
        """AC1: Always return to original branch, even on failure."""
        # ARRANGE
        config = Mock(enable_pr_creation=True, default_branch="main")
        manager = GitStateManager(config=config)

        with (
            patch(
                "src.code_indexer.server.services.git_state_manager.run_git_command"
            ) as mock_git,
            patch(
                "src.code_indexer.server.services.git_state_manager.TokenAuthenticator.resolve_token"
            ) as mock_token,
        ):
            mock_token.return_value = "token"
            # Simulate failure during commit, but still return to original branch
            mock_git.side_effect = [
                Mock(stdout="feature-branch\n"),  # Original branch
                Mock(stdout=""),  # Checkout new branch
                Mock(stdout=""),  # Add files
                subprocess.CalledProcessError(
                    1, ["git", "commit"], stderr="Nothing to commit"
                ),
                Mock(stdout=""),  # Return to feature-branch (should still happen)
            ]

            # ACT
            result = manager.create_pr_after_fix(
                repo_path=tmp_path,
                fix_description="Fix",
                files_modified=[Path("file.py")],
                pr_description="Auto-fix",
                platform="github",
            )

            # ASSERT
            assert result.success is False
            # Verify last git call was checkout to original branch
            last_call = mock_git.call_args_list[-1]
            assert "checkout" in last_call[0][0]
            assert "feature-branch" in last_call[0][0]

    def test_create_pr_after_fix_disabled_in_config(self, tmp_path):
        """AC6: Skip PR creation if disabled in configuration."""
        # ARRANGE
        config = Mock(enable_pr_creation=False)  # Disabled!
        manager = GitStateManager(config=config)

        # ACT
        result = manager.create_pr_after_fix(
            repo_path=tmp_path,
            fix_description="Fix",
            files_modified=[Path("file.py")],
            pr_description="Auto-fix",
            platform="github",
        )

        # ASSERT
        assert result.success is True
        assert "PR creation disabled" in result.message
        assert result.pr_url is None
        assert result.branch_name is None
