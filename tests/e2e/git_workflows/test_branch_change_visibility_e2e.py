"""
E2E tests for branch change visibility bug.

This test reproduces the production bug where switching branches with stored metadata
causes all files to be hidden, making the index completely unusable.

Bug scenario:
1. Index on main branch (stores branch="main" in metadata)
2. Checkout different commit (creates detached HEAD like "detached-6a649690")
3. Run `cidx index` (triggers branch change detection)
4. Result: All files hidden, queries return "No results found"

Root cause:
- GitTopologyService._get_all_tracked_files() receives synthetic branch name "detached-6a649690"
- This is not a valid git reference, so `git ls-tree` fails
- Returns empty list for unchanged_files
- Branch isolation hides ALL files not in the (empty) unchanged_files list
"""

import pytest
import subprocess
import tempfile
import shutil
from pathlib import Path


class TestBranchChangeVisibility:
    """Test suite for branch change visibility preservation."""

    @pytest.fixture
    def test_repo(self):
        """Create a test git repository with multiple branches and files."""
        repo_dir = Path(tempfile.mkdtemp(prefix="test_branch_visibility_"))

        try:
            # Initialize git repo
            subprocess.run(["git", "init"], cwd=repo_dir, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=repo_dir,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True
            )

            # Create initial files on master branch (default branch)
            (repo_dir / "file1.py").write_text("def main_function():\n    pass\n")
            (repo_dir / "file2.py").write_text("def another_function():\n    pass\n")
            (repo_dir / "file3.py").write_text("def test_function():\n    pass\n")

            subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True
            )

            # Create feature branch with modified files
            subprocess.run(
                ["git", "checkout", "-b", "feature"], cwd=repo_dir, check=True
            )
            (repo_dir / "file1.py").write_text(
                "def main_function():\n    # Modified\n    pass\n"
            )
            (repo_dir / "file4.py").write_text("def feature_function():\n    pass\n")

            subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Feature changes"], cwd=repo_dir, check=True
            )

            # Return to master for testing
            subprocess.run(["git", "checkout", "master"], cwd=repo_dir, check=True)

            yield repo_dir

        finally:
            shutil.rmtree(repo_dir, ignore_errors=True)

    def test_branch_change_preserves_file_visibility(self, test_repo):
        """
        Test that switching branches preserves file visibility in the index.

        This is the critical E2E test that reproduces the production bug:
        1. Index on master branch
        2. Switch to different commit (detached HEAD)
        3. Run cidx index (triggers branch change detection)
        4. Verify files remain visible and queryable

        Expected behavior: All files in the new branch should remain visible
        Actual bug behavior: All files hidden, queries return no results
        """
        repo_dir = test_repo

        # Step 1: Initialize and index on master branch
        result = subprocess.run(
            ["cidx", "init", "--embedding-provider", "voyage-ai"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Start services
        result = subprocess.run(
            ["cidx", "start"], cwd=repo_dir, capture_output=True, text=True
        )
        assert result.returncode == 0, f"Start failed: {result.stderr}"

        # Index on master branch
        result = subprocess.run(
            ["cidx", "index"], cwd=repo_dir, capture_output=True, text=True
        )
        assert result.returncode == 0, f"Initial index failed: {result.stderr}"

        # Verify files are visible on master
        result = subprocess.run(
            ["cidx", "query", "function", "--quiet"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Query on master failed: {result.stderr}"
        assert "No results found" not in result.stdout, "Should find results on master"
        assert len(result.stdout.strip()) > 0, "Should have query results on master"

        # Step 2: Switch to feature branch (creates detached HEAD scenario)
        # Checkout specific commit to create detached HEAD state
        get_commit_result = subprocess.run(
            ["git", "rev-parse", "feature"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        feature_commit = get_commit_result.stdout.strip()

        subprocess.run(["git", "checkout", feature_commit], cwd=repo_dir, check=True)

        # Verify we're in detached HEAD state
        branch_check = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert branch_check.stdout.strip() == "", "Should be in detached HEAD state"

        # Step 3: Run cidx index (triggers branch change detection)
        result = subprocess.run(
            ["cidx", "index"], cwd=repo_dir, capture_output=True, text=True
        )
        print(
            f"\n=== INDEX OUTPUT ===\n{result.stdout}\n{result.stderr}\n=== END ===\n"
        )
        assert (
            result.returncode == 0
        ), f"Index after branch change failed: {result.stderr}"

        # Step 4: CRITICAL TEST - Verify files remain visible
        result = subprocess.run(
            ["cidx", "query", "function", "--quiet"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )

        # THIS IS THE BUG - Currently this assertion FAILS
        assert (
            result.returncode == 0
        ), f"Query after branch change failed: {result.stderr}"
        assert (
            "No results found" not in result.stdout
        ), "BUG: All files hidden after branch change!"
        assert (
            len(result.stdout.strip()) > 0
        ), "BUG: Index completely unusable after branch change!"

        # Additional verification: Check that we can find files that exist in feature branch
        result = subprocess.run(
            ["cidx", "query", "feature_function", "--quiet"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert (
            "feature_function" in result.stdout or "file4.py" in result.stdout
        ), "Should find files from feature branch"

        # Cleanup
        subprocess.run(["cidx", "stop"], cwd=repo_dir, check=False)

    def test_reconcile_flag_on_branch_change(self, test_repo):
        """
        Test that --reconcile flag works correctly after branch change.

        Same scenario as above but using explicit --reconcile flag.
        The bug affects both `cidx index` and `cidx index --reconcile`.
        """
        repo_dir = test_repo

        # Initialize and index on master
        subprocess.run(
            ["cidx", "init", "--embedding-provider", "voyage-ai"],
            cwd=repo_dir,
            check=True,
        )
        subprocess.run(["cidx", "start"], cwd=repo_dir, check=True)
        subprocess.run(["cidx", "index"], cwd=repo_dir, check=True)

        # Switch to feature branch (detached HEAD)
        get_commit_result = subprocess.run(
            ["git", "rev-parse", "feature"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        feature_commit = get_commit_result.stdout.strip()
        subprocess.run(["git", "checkout", feature_commit], cwd=repo_dir, check=True)

        # Run reconcile
        result = subprocess.run(
            ["cidx", "index", "--reconcile"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Reconcile failed: {result.stderr}"

        # Verify files visible
        result = subprocess.run(
            ["cidx", "query", "function", "--quiet"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Query failed: {result.stderr}"
        assert (
            "No results found" not in result.stdout
        ), "BUG: --reconcile also hides all files!"

        # Cleanup
        subprocess.run(["cidx", "stop"], cwd=repo_dir, check=False)
