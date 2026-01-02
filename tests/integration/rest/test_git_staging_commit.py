"""
Integration tests for Git Staging/Commit REST endpoints (Story #630 - F3).

Tests 3 git staging/commit operations:
- POST /api/v1/repos/{alias}/git/stage
- POST /api/v1/repos/{alias}/git/unstage
- POST /api/v1/repos/{alias}/git/commit

Uses REAL GitOperationsService with actual git command execution.
NO MOCKING of git operations.
"""

import subprocess
from pathlib import Path


def test_git_stage_real_files(client, activated_repo, test_repo_dir: Path):
    """
    Integration test: POST /api/v1/repos/{alias}/git/stage

    Tests staging actual files with real git add.
    """
    # Setup: Create test file
    test_file = test_repo_dir / "stage_test.txt"
    test_file.write_text("content to stage")

    try:
        # Execute: Call REST endpoint to stage file
        response = client.post(
            f"/api/v1/repos/{activated_repo}/git/stage",
            json={"file_paths": ["stage_test.txt"]},
        )

        # Verify: Check HTTP response
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "stage_test.txt" in data["staged_files"]

        # Verify: File actually staged in git
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=test_repo_dir,
            capture_output=True,
            text=True,
        )
        assert (
            "A  stage_test.txt" in result.stdout or "A stage_test.txt" in result.stdout
        )

    finally:
        # Cleanup: Unstage and remove file
        subprocess.run(
            ["git", "reset", "HEAD", "stage_test.txt"],
            cwd=test_repo_dir,
            capture_output=True,
        )
        if test_file.exists():
            test_file.unlink()


def test_git_unstage_real_files(client, activated_repo, test_repo_dir: Path):
    """
    Integration test: POST /api/v1/repos/{alias}/git/unstage

    Tests unstaging files with real git reset.
    """
    # Setup: Create and stage a file
    test_file = test_repo_dir / "unstage_test.txt"
    test_file.write_text("content to unstage")
    subprocess.run(["git", "add", "unstage_test.txt"], cwd=test_repo_dir, check=True)

    try:
        # Execute: Call REST endpoint to unstage file
        response = client.post(
            f"/api/v1/repos/{activated_repo}/git/unstage",
            json={"file_paths": ["unstage_test.txt"]},
        )

        # Verify: Check HTTP response
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "unstage_test.txt" in data["unstaged_files"]

        # Verify: File actually unstaged in git
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=test_repo_dir,
            capture_output=True,
            text=True,
        )
        assert "??" in result.stdout  # File should be untracked now

    finally:
        # Cleanup: Remove file
        if test_file.exists():
            test_file.unlink()


def test_git_commit_real_repository(
    client, activated_repo, test_repo_dir: Path, mock_user
):
    """
    Integration test: POST /api/v1/repos/{alias}/git/commit

    Tests creating actual git commits.
    """
    # Setup: Create and stage a file
    test_file = test_repo_dir / "commit_test.txt"
    test_file.write_text("content to commit")
    subprocess.run(["git", "add", "commit_test.txt"], cwd=test_repo_dir, check=True)

    try:
        # Execute: Call REST endpoint to create commit
        response = client.post(
            f"/api/v1/repos/{activated_repo}/git/commit",
            json={
                "message": "Test commit from integration test",
                "author_email": mock_user.email,
            },
        )

        # Verify: Check HTTP response
        assert response.status_code == 201  # POST creating resource returns 201 Created
        data = response.json()
        assert data["success"] is True
        assert "commit_hash" in data
        assert data["commit_hash"]  # Non-empty hash
        assert data["author"] == mock_user.email

        # Verify: Commit actually exists in git
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H"],
            cwd=test_repo_dir,
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == data["commit_hash"]

    finally:
        # Cleanup: Reset to previous commit (undo test commit)
        subprocess.run(
            ["git", "reset", "--hard", "HEAD~1"], cwd=test_repo_dir, capture_output=True
        )
        if test_file.exists():
            test_file.unlink()
