"""
Mock Git Repository Infrastructure for Integration Testing.

Provides REAL git repositories (NOT Python mocks) for testing git workflows.
Created for Story #659 AC5: Mock Repository Git Workflow Testing.

Usage:
    mock_repo = MockGitRepository()
    mock_repo.setup()
    try:
        # Run tests with real git operations
        git_manager = GitStateManager(...)
        result = git_manager.create_pr_after_fix(repo_path=mock_repo.repo_path, ...)
    finally:
        mock_repo.cleanup()

NO Python mocks (no patch, no Mock, no MagicMock) - all git operations are REAL.
"""

import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional


class MockGitRepository:
    """
    Real git repository for integration testing (NOT Python mocks).

    Creates actual git repositories with:
    - Real commits and branches
    - Real remote repository (bare repo)
    - Real tracked/untracked files
    - Real uncommitted changes

    All git operations execute via subprocess.run() with real git commands.
    """

    def __init__(self, base_path: Optional[Path] = None):
        """
        Initialize mock git repository infrastructure.

        Args:
            base_path: Base directory for mock repositories (default: /tmp/cidx-git-workflow-test)
        """
        if base_path is None:
            base_path = Path("/tmp/cidx-git-workflow-test")

        self.base_path = base_path
        self.repo_id = str(uuid.uuid4())[:8]
        self.repo_path = base_path / f"repo-{self.repo_id}"
        self.remote_path = base_path / f"remote-{self.repo_id}"

    def setup(self) -> None:
        """
        Create real git repository with commits, branches, and remote.

        Operations:
        1. Create main repository directory
        2. Initialize git repository (git init)
        3. Configure user.email and user.name
        4. Create bare remote repository
        5. Link repository to remote (git remote add origin)
        6. Create initial commit
        7. Push to remote (git push -u origin main)

        Raises:
            subprocess.CalledProcessError: If any git command fails
        """
        # Create main repository
        self.repo_path.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init"], cwd=self.repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.repo_path,
            check=True,
            capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=self.repo_path,
            check=True,
            capture_output=True
        )

        # Create remote (bare repo)
        self.remote_path.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init", "--bare"],
            cwd=self.remote_path,
            check=True,
            capture_output=True
        )

        # Link repo to remote
        subprocess.run(
            ["git", "remote", "add", "origin", str(self.remote_path)],
            cwd=self.repo_path,
            check=True,
            capture_output=True
        )

        # Create initial commit
        (self.repo_path / "README.md").write_text("# Test Repository\n")
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=self.repo_path,
            check=True,
            capture_output=True
        )

        # Rename current branch to main (handles both master and main defaults)
        subprocess.run(
            ["git", "branch", "-M", "main"],
            cwd=self.repo_path,
            check=True,
            capture_output=True
        )

        # Push to remote (establish main branch)
        subprocess.run(
            ["git", "push", "-u", "origin", "main"],
            cwd=self.repo_path,
            check=True,
            capture_output=True
        )

    def add_uncommitted_changes(self, tracked: bool = True) -> None:
        """
        Add uncommitted changes to repository (real file modifications).

        Args:
            tracked: If True, stage changes (git add). If False, leave untracked.

        Creates a new file with real content and optionally stages it.
        """
        (self.repo_path / "changes.txt").write_text(f"Uncommitted changes {uuid.uuid4()}\n")

        if tracked:
            subprocess.run(
                ["git", "add", "changes.txt"],
                cwd=self.repo_path,
                check=True,
                capture_output=True
            )

    def create_branch(self, branch_name: str) -> None:
        """
        Create and checkout real git branch.

        Args:
            branch_name: Name of branch to create

        Raises:
            subprocess.CalledProcessError: If git checkout -b fails
        """
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=self.repo_path,
            check=True,
            capture_output=True
        )

    def get_current_branch(self) -> str:
        """
        Get current branch name (real git command).

        Returns:
            Current branch name

        Raises:
            subprocess.CalledProcessError: If git command fails
        """
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True
        )
        return result.stdout.strip()

    def get_status(self) -> str:
        """
        Get repository status (real git status command).

        Returns:
            Output of git status --porcelain

        Raises:
            subprocess.CalledProcessError: If git command fails
        """
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True
        )
        return result.stdout

    def list_branches(self) -> list[str]:
        """
        List all branches (real git branch command).

        Returns:
            List of branch names

        Raises:
            subprocess.CalledProcessError: If git command fails
        """
        result = subprocess.run(
            ["git", "branch", "-a"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True
        )
        # Parse branch output (remove * and whitespace)
        branches = []
        for line in result.stdout.split("\n"):
            line = line.strip()
            if line:
                # Remove current branch indicator (*)
                branch = line.replace("*", "").strip()
                branches.append(branch)
        return branches

    def get_commit_hash(self, ref: str = "HEAD") -> str:
        """
        Get commit hash for reference (real git rev-parse command).

        Args:
            ref: Git reference (default: HEAD)

        Returns:
            Commit SHA hash

        Raises:
            subprocess.CalledProcessError: If git command fails
        """
        result = subprocess.run(
            ["git", "rev-parse", ref],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True
        )
        return result.stdout.strip()

    def cleanup(self) -> None:
        """
        Remove mock repository directories.

        Deletes both repository and remote directories (real filesystem cleanup).
        """
        shutil.rmtree(self.repo_path, ignore_errors=True)
        shutil.rmtree(self.remote_path, ignore_errors=True)
