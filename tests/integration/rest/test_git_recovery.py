"""
Integration tests for Git Recovery Operations REST endpoints (Story #630 - F5).

Tests 3 git recovery operations:
- POST /api/v1/repos/{alias}/git/reset
- POST /api/v1/repos/{alias}/git/clean
- POST /api/v1/repos/{alias}/git/merge-abort

Uses REAL GitOperationsService with actual git command execution.
NO MOCKING of git operations.
"""

import subprocess
from pathlib import Path


def test_git_reset_hard_real_repository(client, activated_repo, test_repo_dir: Path):
    """
    Integration test: POST /api/v1/repos/{alias}/git/reset

    Tests hard reset with confirmation token system.
    """
    # Setup: Create and commit a test file
    test_file = test_repo_dir / "reset_test.txt"
    test_file.write_text("content to reset")
    subprocess.run(["git", "add", "reset_test.txt"], cwd=test_repo_dir, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Test commit for reset"],
        cwd=test_repo_dir,
        check=True
    )

    try:
        # Step 1: Request confirmation token
        response = client.post(
            f"/api/v1/repos/{activated_repo}/git/reset",
            json={"mode": "hard"}
        )

        # Verify: Token required
        assert response.status_code == 200
        data = response.json()
        assert data["requires_confirmation"] is True
        assert "token" in data
        token = data["token"]

        # Step 2: Perform reset with token
        response = client.post(
            f"/api/v1/repos/{activated_repo}/git/reset",
            json={"mode": "hard", "commit_hash": "HEAD~1", "confirmation_token": token}
        )

        # Verify: Reset succeeded
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["reset_mode"] == "hard"

        # Verify: File no longer exists
        assert not test_file.exists()

    finally:
        # Cleanup: Ensure clean state
        if test_file.exists():
            test_file.unlink()


def test_git_clean_real_untracked(client, activated_repo, test_repo_dir: Path):
    """
    Integration test: POST /api/v1/repos/{alias}/git/clean

    Tests removing untracked files with confirmation token.
    """
    # Setup: Create untracked files
    test_file1 = test_repo_dir / "clean_test1.txt"
    test_file2 = test_repo_dir / "clean_test2.txt"
    test_file1.write_text("untracked 1")
    test_file2.write_text("untracked 2")

    try:
        # Step 1: Request confirmation token
        response = client.post(f"/api/v1/repos/{activated_repo}/git/clean")

        # Verify: Token required
        assert response.status_code == 200
        data = response.json()
        assert data["requires_confirmation"] is True
        assert "token" in data
        token = data["token"]

        # Step 2: Perform clean with token
        response = client.post(
            f"/api/v1/repos/{activated_repo}/git/clean",
            json={"confirmation_token": token}
        )

        # Verify: Clean succeeded
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "removed_files" in data
        assert len(data["removed_files"]) >= 2

        # Verify: Files actually removed
        assert not test_file1.exists()
        assert not test_file2.exists()

    finally:
        # Cleanup: Remove any remaining files
        for f in [test_file1, test_file2]:
            if f.exists():
                f.unlink()


def test_git_merge_abort_real_conflict(client, activated_repo, test_repo_dir: Path):
    """
    Integration test: POST /api/v1/repos/{alias}/git/merge-abort

    Tests aborting a merge in progress.
    NOTE: This test creates a merge conflict scenario.
    """
    # Setup: Create a branch with conflicting changes
    current_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=test_repo_dir,
        capture_output=True,
        text=True
    ).stdout.strip()

    test_file = test_repo_dir / "merge_test.txt"

    try:
        # Create test branch
        subprocess.run(["git", "checkout", "-b", "test-merge-branch"], cwd=test_repo_dir, check=True)
        test_file.write_text("branch content")
        subprocess.run(["git", "add", "merge_test.txt"], cwd=test_repo_dir, check=True)
        subprocess.run(["git", "commit", "-m", "Branch commit"], cwd=test_repo_dir, check=True)

        # Switch back and create conflicting change
        subprocess.run(["git", "checkout", current_branch], cwd=test_repo_dir, check=True)
        test_file.write_text("main content")
        subprocess.run(["git", "add", "merge_test.txt"], cwd=test_repo_dir, check=True)
        subprocess.run(["git", "commit", "-m", "Main commit"], cwd=test_repo_dir, check=True)

        # Attempt merge (will conflict)
        subprocess.run(
            ["git", "merge", "test-merge-branch"],
            cwd=test_repo_dir,
            capture_output=True
        )  # Expected to fail with conflict

        # Execute: Call REST endpoint to abort merge
        response = client.post(f"/api/v1/repos/{activated_repo}/git/merge-abort")

        # Verify: Merge aborted successfully
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["aborted"] is True

        # Verify: No longer in merge state
        merge_head = test_repo_dir / ".git" / "MERGE_HEAD"
        assert not merge_head.exists()

    finally:
        # Cleanup: Delete test branch and file
        subprocess.run(["git", "merge", "--abort"], cwd=test_repo_dir, capture_output=True)
        subprocess.run(["git", "checkout", current_branch], cwd=test_repo_dir, capture_output=True)
        subprocess.run(["git", "branch", "-D", "test-merge-branch"], cwd=test_repo_dir, capture_output=True)
        subprocess.run(["git", "reset", "--hard", "HEAD~1"], cwd=test_repo_dir, capture_output=True)
        if test_file.exists():
            test_file.unlink()
