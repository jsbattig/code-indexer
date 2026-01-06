"""
End-to-end integration tests for git workflow with REAL git operations.

Tests complete PR creation workflow using actual git commands:
- Real repository initialization
- Real commits, branches, file operations
- Real bare repository as mock remote
- Real git push operations
- NO mocking of git commands

Story #659: Git State Management for SCIP Self-Healing with PR Workflow
AC5: Mock Repository Git Workflow Testing
"""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.code_indexer.server.services.git_state_manager import (
    GitStateManager,
)


class TestGitWorkflowE2E:
    """E2E tests with REAL git operations (AC5)."""

    @pytest.fixture
    def mock_repo_with_remote(self, tmp_path):
        """
        Create a real git repository with a bare remote for testing.

        Returns tuple: (work_repo_path, bare_repo_path)
        """
        # Create bare repository (acts as remote)
        bare_repo = tmp_path / "bare_remote.git"
        bare_repo.mkdir()
        subprocess.run(
            ["git", "init", "--bare"], cwd=bare_repo, check=True, capture_output=True
        )

        # Create working repository
        work_repo = tmp_path / "work_repo"
        work_repo.mkdir()
        subprocess.run(["git", "init"], cwd=work_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=work_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=work_repo,
            check=True,
            capture_output=True,
        )

        # Add remote
        subprocess.run(
            ["git", "remote", "add", "origin", str(bare_repo)],
            cwd=work_repo,
            check=True,
            capture_output=True,
        )

        # Configure default branch
        subprocess.run(
            ["git", "checkout", "-b", "main"],
            cwd=work_repo,
            check=True,
            capture_output=True,
        )

        # Create initial commit on main branch
        initial_file = work_repo / "README.md"
        initial_file.write_text("# Test Repository\n")
        subprocess.run(
            ["git", "add", "README.md"], cwd=work_repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=work_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "push", "-u", "origin", "main"],
            cwd=work_repo,
            check=True,
            capture_output=True,
        )

        return work_repo, bare_repo

    def test_pr_creation_workflow_github_real_git(self, mock_repo_with_remote):
        """
        AC5: Test complete PR creation workflow with REAL git operations.

        Given a mock repository with real git history and remote
        When PR creation workflow executes
        Then:
        - Branch is created correctly
        - Changes are committed correctly
        - Push succeeds to mock remote
        - PR creation is simulated successfully
        - No errors occur during git operations
        - Original branch is restored
        """
        # ARRANGE
        work_repo, bare_repo = mock_repo_with_remote

        config = Mock(
            enable_pr_creation=True, default_branch="main", pr_base_branch="main"
        )
        manager = GitStateManager(config=config)

        # Create files to modify (simulating SCIP fix)
        fix_file1 = work_repo / "src" / "auth.py"
        fix_file1.parent.mkdir(parents=True, exist_ok=True)
        fix_file1.write_text("# Fixed import\nimport os\n")

        fix_file2 = work_repo / "src" / "utils.py"
        fix_file2.write_text("# Fixed type hint\nfrom typing import Optional\n")

        files_modified = [Path("src/auth.py"), Path("src/utils.py")]

        # Mock PR client to avoid real API calls
        with (
            patch(
                "code_indexer.server.services.git_state_manager.GitHubPRClient"
            ) as mock_pr_client,
            patch(
                "code_indexer.server.services.git_state_manager.TokenAuthenticator.resolve_token"
            ) as mock_token,
        ):
            mock_token.return_value = "fake_token_12345"
            mock_pr_instance = Mock()
            mock_pr_instance.create_pull_request.return_value = (
                "https://github.com/test/repo/pull/999"
            )
            mock_pr_client.return_value = mock_pr_instance

            # Verify we start on main branch
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=work_repo,
                capture_output=True,
                text=True,
                check=True,
            )
            assert result.stdout.strip() == "main"

            # ACT: Execute PR creation workflow
            pr_result = manager.create_pr_after_fix(
                repo_path=work_repo,
                fix_description="Fixed missing imports in auth module",
                files_modified=files_modified,
                pr_description="Auto-fix: Missing imports",
                platform="github",
            )

            # ASSERT: Workflow succeeded
            assert pr_result.success is True
            assert pr_result.pr_url == "https://github.com/test/repo/pull/999"
            assert pr_result.branch_name is not None
            assert pr_result.branch_name.startswith("scip-fix-")

            # Verify we returned to main branch
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=work_repo,
                capture_output=True,
                text=True,
                check=True,
            )
            assert result.stdout.strip() == "main"

            # Verify fix branch exists locally
            result = subprocess.run(
                ["git", "branch", "--list", pr_result.branch_name],
                cwd=work_repo,
                capture_output=True,
                text=True,
                check=True,
            )
            assert pr_result.branch_name in result.stdout

            # Verify fix branch was pushed to remote
            result = subprocess.run(
                ["git", "ls-remote", "origin", pr_result.branch_name],
                cwd=work_repo,
                capture_output=True,
                text=True,
                check=True,
            )
            assert pr_result.branch_name in result.stdout

            # Verify commit exists on fix branch
            subprocess.run(
                ["git", "checkout", pr_result.branch_name],
                cwd=work_repo,
                check=True,
                capture_output=True,
            )
            result = subprocess.run(
                ["git", "log", "--oneline", "-1"],
                cwd=work_repo,
                capture_output=True,
                text=True,
                check=True,
            )
            assert "[SCIP Auto-Fix]" in result.stdout

            # Verify files were committed
            result = subprocess.run(
                ["git", "show", "--name-only", "--format="],
                cwd=work_repo,
                capture_output=True,
                text=True,
                check=True,
            )
            assert "src/auth.py" in result.stdout
            assert "src/utils.py" in result.stdout

            # Cleanup: return to main
            subprocess.run(
                ["git", "checkout", "main"],
                cwd=work_repo,
                check=True,
                capture_output=True,
            )

    def test_pr_creation_workflow_uncommitted_changes(self, mock_repo_with_remote):
        """
        AC5: Test workflow handles uncommitted changes gracefully.

        Given a repository with uncommitted changes
        When PR creation workflow executes
        Then uncommitted changes should NOT interfere
        """
        # ARRANGE
        work_repo, _ = mock_repo_with_remote

        config = Mock(
            enable_pr_creation=True, default_branch="main", pr_base_branch="main"
        )
        manager = GitStateManager(config=config)

        # Create uncommitted change
        uncommitted_file = work_repo / "uncommitted.txt"
        uncommitted_file.write_text("This is uncommitted\n")

        # Create file for SCIP fix
        fix_file = work_repo / "fix.py"
        fix_file.write_text("# Fixed\n")

        # Mock PR client
        with (
            patch(
                "code_indexer.server.services.git_state_manager.GitHubPRClient"
            ) as mock_pr_client,
            patch(
                "code_indexer.server.services.git_state_manager.TokenAuthenticator.resolve_token"
            ) as mock_token,
        ):
            mock_token.return_value = "token"
            mock_pr_instance = Mock()
            mock_pr_instance.create_pull_request.return_value = (
                "https://github.com/test/repo/pull/100"
            )
            mock_pr_client.return_value = mock_pr_instance

            # ACT
            pr_result = manager.create_pr_after_fix(
                repo_path=work_repo,
                fix_description="Fix",
                files_modified=[Path("fix.py")],
                pr_description="Auto-fix",
                platform="github",
            )

            # ASSERT
            assert pr_result.success is True

            # Verify uncommitted file still exists and is uncommitted
            assert uncommitted_file.exists()
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=work_repo,
                capture_output=True,
                text=True,
                check=True,
            )
            assert "uncommitted.txt" in result.stdout

    def test_pr_creation_workflow_branch_already_exists(self, mock_repo_with_remote):
        """
        AC5: Test workflow handles existing branch name collision.

        Given a branch with similar name already exists
        When PR creation attempts to create branch
        Then workflow should handle gracefully (likely fail with clear error)
        """
        # ARRANGE
        work_repo, _ = mock_repo_with_remote

        config = Mock(
            enable_pr_creation=True, default_branch="main", pr_base_branch="main"
        )
        manager = GitStateManager(config=config)

        # Pre-create a branch that might collide
        # (Note: Actual implementation uses timestamp, so collision unlikely)
        subprocess.run(
            ["git", "checkout", "-b", "scip-fix-test"],
            cwd=work_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "checkout", "main"], cwd=work_repo, check=True, capture_output=True
        )

        fix_file = work_repo / "fix2.py"
        fix_file.write_text("# Fix\n")

        with (
            patch(
                "code_indexer.server.services.git_state_manager.GitHubPRClient"
            ) as mock_pr_client,
            patch(
                "code_indexer.server.services.git_state_manager.TokenAuthenticator.resolve_token"
            ) as mock_token,
        ):
            mock_token.return_value = "token"
            mock_pr_instance = Mock()
            mock_pr_instance.create_pull_request.return_value = (
                "https://github.com/test/repo/pull/101"
            )
            mock_pr_client.return_value = mock_pr_instance

            # ACT
            pr_result = manager.create_pr_after_fix(
                repo_path=work_repo,
                fix_description="Another fix",
                files_modified=[Path("fix2.py")],
                pr_description="Auto-fix 2",
                platform="github",
            )

            # ASSERT: Should succeed because branch name includes timestamp
            # (unlikely to collide with "scip-fix-test")
            assert pr_result.success is True
            assert pr_result.branch_name != "scip-fix-test"

    def test_clear_repo_before_refresh_real_git(self, mock_repo_with_remote):
        """
        AC5: Test pre-refresh clearing with REAL git operations.

        Given a repository with uncommitted changes and untracked files
        When clear_repo_before_refresh executes
        Then all changes should be discarded using real git commands
        """
        # ARRANGE
        work_repo, _ = mock_repo_with_remote

        config = Mock(enable_pr_creation=True)
        manager = GitStateManager(config=config)

        # Create uncommitted changes
        tracked_file = work_repo / "README.md"
        tracked_file.write_text("# Modified README\n")

        # Create untracked file
        untracked_file = work_repo / "untracked.txt"
        untracked_file.write_text("Untracked content\n")

        # Verify dirty state
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=work_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "README.md" in result.stdout
        assert "untracked.txt" in result.stdout

        # ACT
        cleanup_result = manager.clear_repo_before_refresh(work_repo)

        # ASSERT
        assert cleanup_result.was_dirty is True
        assert cleanup_result.files_cleared > 0

        # Verify clean state using real git
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=work_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == ""  # Should be completely clean

        # Verify untracked file was removed
        assert not untracked_file.exists()

        # Verify tracked file was reset
        assert tracked_file.read_text() == "# Test Repository\n"  # Original content
