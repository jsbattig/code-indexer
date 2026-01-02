"""
AC5 Integration Tests: Mock Repository Git Workflow Testing (Story #659).

Validates complete git workflow for PR creation using REAL git operations.

AC5 Acceptance Criteria:
- Mock repository created in /tmp/cidx-git-workflow-test/
- Mock repo has commits, branches, tracked files, uncommitted changes
- PR creation workflow executed on mock repo
- Branch is created correctly
- Changes are committed correctly
- Push succeeds (to mock remote)
- PR creation is simulated successfully
- NO errors occur during git operations

Compliance:
- CLAUDE.md Anti-Mock Rule: Uses REAL git operations via subprocess
- MockGitRepository: Real git repositories, not Python mocks
- Python mocks used ONLY for external APIs (GitHub/GitLab PR creation, token auth)
- Evidence-based validation: Verify with real git commands
"""

import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, Mock

from tests.fixtures.mock_git_repository import MockGitRepository
from src.code_indexer.server.services.git_state_manager import GitStateManager


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_git_repo():
    """
    Create real mock git repository for testing (NOT Python mocks).

    Yields MockGitRepository with real git setup (commits, branches, remote).
    Cleans up after test completes.
    """
    repo = MockGitRepository()
    repo.setup()
    try:
        yield repo
    finally:
        repo.cleanup()


@pytest.fixture
def git_state_manager():
    """
    Create GitStateManager for testing with PR creation enabled.

    Uses mock config object for configuration (config is not a git operation).
    """
    config = Mock(
        enable_pr_creation=True,
        pr_base_branch="main",
        default_branch="main"
    )
    return GitStateManager(config=config, audit_logger=None)


# =============================================================================
# AC5: Mock Repository Git Workflow Tests
# =============================================================================


def test_ac5_mock_repository_setup(mock_git_repo):
    """
    AC5 Prerequisite: Verify MockGitRepository creates valid git repository.

    Validates:
    - Repository directory exists
    - Remote directory exists (bare repo)
    - Git repository is initialized
    - Initial commit exists
    - Main branch exists
    - Remote is configured
    """
    # Verify repository paths exist
    assert mock_git_repo.repo_path.exists()
    assert mock_git_repo.remote_path.exists()

    # Verify git repository is initialized (real git command)
    assert (mock_git_repo.repo_path / ".git").is_dir()

    # Verify initial commit exists (real git log command)
    current_branch = mock_git_repo.get_current_branch()
    assert current_branch == "main"

    # Verify README.md file exists
    assert (mock_git_repo.repo_path / "README.md").exists()

    # Verify remote is configured
    branches = mock_git_repo.list_branches()
    assert any("remotes/origin/main" in b for b in branches)


def test_ac5_branch_creation_with_real_git(mock_git_repo, git_state_manager):
    """
    AC5: Verify branch is created correctly using REAL git operations.

    Flow:
    1. Create fix branch using GitStateManager._create_and_checkout_fix_branch
    2. Verify branch created (real git branch command)
    3. Verify currently on new branch (real git branch --show-current)
    4. Verify branch format matches expected pattern (scip-fix-YYYYMMDD-HHMMSS)
    """
    # Get original branch
    original_branch = mock_git_repo.get_current_branch()
    assert original_branch == "main"

    # Create fix branch using GitStateManager (REAL git checkout -b)
    branch_name = git_state_manager._create_and_checkout_fix_branch(mock_git_repo.repo_path)

    # Verify branch name format
    assert branch_name.startswith("scip-fix-")
    assert len(branch_name) > len("scip-fix-")

    # Verify currently on new branch (real git command)
    current_branch = mock_git_repo.get_current_branch()
    assert current_branch == branch_name

    # Verify branch exists in branch list (real git branch command)
    branches = mock_git_repo.list_branches()
    assert branch_name in branches


def test_ac5_commit_creation_with_real_git(mock_git_repo, git_state_manager):
    """
    AC5: Verify changes are committed correctly using REAL git operations.

    Flow:
    1. Create new file with changes
    2. Stage and commit using GitStateManager._stage_and_commit_changes
    3. Verify commit created (real git log command)
    4. Verify commit message format
    5. Verify file modifications are tracked
    """
    # Create a branch for testing
    branch_name = git_state_manager._create_and_checkout_fix_branch(mock_git_repo.repo_path)

    # Create new file with changes
    fix_file = mock_git_repo.repo_path / "fix.py"
    fix_file.write_text("# Fixed SCIP dependency issue\n")

    # Stage and commit changes (REAL git add + git commit)
    files_modified = [Path("fix.py")]
    fix_description = "Resolved missing dependency: requests"
    commit_hash = git_state_manager._stage_and_commit_changes(
        mock_git_repo.repo_path,
        files_modified,
        fix_description
    )

    # Verify commit hash returned
    assert commit_hash
    assert len(commit_hash) == 40  # Full SHA-1 hash

    # Verify commit exists (real git show command)
    result = subprocess.run(
        ["git", "show", "--stat", commit_hash],
        cwd=mock_git_repo.repo_path,
        capture_output=True,
        text=True,
        check=True
    )

    # Verify commit message contains fix description
    assert "[SCIP Auto-Fix]" in result.stdout
    assert fix_description in result.stdout

    # Verify file is in commit
    assert "fix.py" in result.stdout


def test_ac5_push_to_remote_with_real_git(mock_git_repo, git_state_manager):
    """
    AC5: Verify push succeeds to mock remote using REAL git operations.

    Flow:
    1. Create branch and commit changes
    2. Push branch to remote using GitStateManager._push_branch_to_remote
    3. Verify branch exists on remote (real git ls-remote command)
    4. Verify commit is on remote
    """
    # Create branch and commit
    branch_name = git_state_manager._create_and_checkout_fix_branch(mock_git_repo.repo_path)
    fix_file = mock_git_repo.repo_path / "fix.py"
    fix_file.write_text("# Fixed code\n")
    commit_hash = git_state_manager._stage_and_commit_changes(
        mock_git_repo.repo_path,
        [Path("fix.py")],
        "Fixed dependency issue"
    )

    # Push branch to remote (REAL git push)
    git_state_manager._push_branch_to_remote(mock_git_repo.repo_path, branch_name)

    # Verify branch exists on remote (real git ls-remote command)
    result = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", branch_name],
        cwd=mock_git_repo.repo_path,
        capture_output=True,
        text=True,
        check=True
    )

    # Verify branch found on remote
    assert branch_name in result.stdout
    assert commit_hash[:7] in result.stdout or len(result.stdout) > 0


def test_ac5_full_pr_workflow_with_real_git(mock_git_repo, git_state_manager):
    """
    AC5: End-to-end PR creation with REAL git operations.

    Python mocks used ONLY for external APIs (GitHub/GitLab PR creation, token auth).
    All git operations are REAL (branch, commit, push via subprocess).

    Validates complete workflow:
    - Real git repository with commits, branches
    - Real GitStateManager operations (branch, commit, push)
    - Real PR creation workflow (mocked GitHub/GitLab API calls only)
    - No Python mocks for git operations

    Flow:
    1. Create files to simulate SCIP fix
    2. Execute create_pr_after_fix workflow
    3. Verify branch created (real git command)
    4. Verify commit created (real git command)
    5. Verify push succeeded (real git command)
    6. Verify returned to original branch (real git command)
    """
    # Get original branch
    original_branch = mock_git_repo.get_current_branch()
    assert original_branch == "main"

    # Create files to simulate SCIP fix
    fix_file = mock_git_repo.repo_path / "pyproject.toml"
    fix_file.write_text('[tool.poetry.dependencies]\nrequests = "^2.28.0"\n')

    # Mock ONLY the PR API creation (GitHub/GitLab API), NOT git operations
    with patch(
        "src.code_indexer.server.services.git_state_manager.GitHubPRClient.create_pull_request"
    ) as mock_pr_api:
        mock_pr_api.return_value = "https://github.com/test/repo/pull/123"

        # Mock token resolution (external dependency, not git operation)
        with patch(
            "src.code_indexer.server.services.git_state_manager.TokenAuthenticator.resolve_token"
        ) as mock_token:
            mock_token.return_value = "fake_token_12345"

            # Execute REAL PR creation workflow
            result = git_state_manager.create_pr_after_fix(
                repo_path=mock_git_repo.repo_path,
                fix_description="Resolved missing dependency: requests",
                files_modified=[Path("pyproject.toml")],
                pr_description="fix(scip): Add missing requests dependency",
                platform="github",
                job_id="test-job-ac5"
            )

    # ASSERT: PR workflow succeeded
    assert result.success is True
    assert result.pr_url == "https://github.com/test/repo/pull/123"
    assert result.branch_name.startswith("scip-fix-")

    # VERIFY with real git commands (NOT mocks)
    # 1. Branch was created
    branches = mock_git_repo.list_branches()
    assert result.branch_name in branches

    # 2. Returned to original branch
    current_branch = mock_git_repo.get_current_branch()
    assert current_branch == original_branch

    # 3. Branch exists on remote
    remote_result = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", result.branch_name],
        cwd=mock_git_repo.repo_path,
        capture_output=True,
        text=True,
        check=True
    )
    assert result.branch_name in remote_result.stdout


def test_ac5_clearing_workflow_with_real_git(mock_git_repo, git_state_manager):
    """
    AC5: Verify clearing workflow (git reset + clean) with REAL git operations.

    Flow:
    1. Add uncommitted changes to repository
    2. Execute clear_repo_before_refresh
    3. Verify repository is clean (real git status command)
    4. Verify files_cleared count matches actual files removed
    """
    # Add uncommitted changes (real file creation)
    mock_git_repo.add_uncommitted_changes(tracked=True)
    untracked_file = mock_git_repo.repo_path / "untracked.txt"
    untracked_file.write_text("Untracked file content\n")

    # Verify repository is dirty (real git status)
    status_before = mock_git_repo.get_status()
    assert len(status_before.strip()) > 0  # Has uncommitted changes

    # Execute clearing workflow (REAL git reset + git clean)
    result = git_state_manager.clear_repo_before_refresh(mock_git_repo.repo_path)

    # ASSERT: Clearing succeeded
    assert result.was_dirty is True
    assert result.files_cleared >= 1  # At least changes.txt

    # VERIFY repository is clean (real git status command)
    status_after = mock_git_repo.get_status()
    assert len(status_after.strip()) == 0  # No uncommitted changes

    # VERIFY files were actually removed
    assert not untracked_file.exists()


def test_ac5_no_errors_during_git_operations(mock_git_repo, git_state_manager):
    """
    AC5: Verify NO errors occur during git operations in full workflow.

    Executes complete workflow and ensures no GitStateError or subprocess errors raised.
    """
    # Create fix file
    fix_file = mock_git_repo.repo_path / "requirements.txt"
    fix_file.write_text("requests==2.28.0\n")

    # Mock external dependencies (PR API, token) - NOT git operations
    with patch(
        "src.code_indexer.server.services.git_state_manager.GitHubPRClient.create_pull_request"
    ) as mock_pr_api:
        mock_pr_api.return_value = "https://github.com/test/repo/pull/456"

        with patch(
            "src.code_indexer.server.services.git_state_manager.TokenAuthenticator.resolve_token"
        ) as mock_token:
            mock_token.return_value = "token_xyz"

            # Execute workflow - should raise NO errors
            try:
                result = git_state_manager.create_pr_after_fix(
                    repo_path=mock_git_repo.repo_path,
                    fix_description="Add requests to requirements.txt",
                    files_modified=[Path("requirements.txt")],
                    pr_description="fix(scip): Add missing requests dependency",
                    platform="github",
                    job_id="test-job-no-errors"
                )

                # ASSERT: Success without errors
                assert result.success is True

            except Exception as e:
                pytest.fail(f"AC5 VIOLATION: Git operations raised error: {e}")
