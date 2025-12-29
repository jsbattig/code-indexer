"""
Integration tests for Git Remote Operations REST endpoints (Story #630 - F4).

Tests 3 git remote operations:
- POST /api/v1/repos/{alias}/git/push
- POST /api/v1/repos/{alias}/git/pull
- POST /api/v1/repos/{alias}/git/fetch

Uses REAL GitOperationsService with actual git command execution.
NO MOCKING of git operations.
"""

import subprocess
from pathlib import Path

import pytest


@pytest.mark.skip(reason="Requires SSH access to git@github.com:jsbattig/txt-db.git")
def test_git_push_real_remote(client, activated_repo, test_repo_dir: Path):
    """
    Integration test: POST /api/v1/repos/{alias}/git/push

    Tests pushing commits to real remote repository.
    NOTE: Skipped by default to avoid unwanted pushes.
    """
    # Setup: Create test commit
    test_file = test_repo_dir / "push_test.txt"
    test_file.write_text("content to push")
    subprocess.run(["git", "add", "push_test.txt"], cwd=test_repo_dir, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Test commit for push"],
        cwd=test_repo_dir,
        check=True
    )

    try:
        # Execute: Call REST endpoint to push
        response = client.post(
            f"/api/v1/repos/{activated_repo}/git/push",
            json={"remote": "origin"}
        )

        # Verify: Check HTTP response
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "pushed_commits" in data

    finally:
        # Cleanup: Reset local repo (remote will need manual cleanup)
        subprocess.run(["git", "reset", "--hard", "HEAD~1"], cwd=test_repo_dir, capture_output=True)


def test_git_pull_real_remote(client, activated_repo, test_repo_dir: Path):
    """
    Integration test: POST /api/v1/repos/{alias}/git/pull

    Tests pulling updates from real remote repository.
    """
    # Execute: Call REST endpoint to pull
    response = client.post(
        f"/api/v1/repos/{activated_repo}/git/pull",
        json={"remote": "origin"}
    )

    # Verify: Check HTTP response
    assert response.status_code == 200
    data = response.json()
    assert "success" in data
    assert "updated_files" in data
    assert "conflicts" in data
    assert isinstance(data["conflicts"], list)


def test_git_fetch_real_remote(client, activated_repo, test_repo_dir: Path):
    """
    Integration test: POST /api/v1/repos/{alias}/git/fetch

    Tests fetching updates from real remote repository.
    """
    # Execute: Call REST endpoint to fetch
    response = client.post(
        f"/api/v1/repos/{activated_repo}/git/fetch",
        json={"remote": "origin"}
    )

    # Verify: Check HTTP response
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "fetched_refs" in data
    assert isinstance(data["fetched_refs"], list)
