"""
Integration tests for Git Branch Management REST endpoints (Story #630 - F6).

Tests 3 git branch management operations:
- POST /api/v1/repos/{alias}/git/branches
- POST /api/v1/repos/{alias}/git/branches/{name}/switch
- DELETE /api/v1/repos/{alias}/git/branches/{name}

Uses REAL GitOperationsService with actual git command execution.
NO MOCKING of git operations.
"""

import subprocess
from pathlib import Path


def test_git_branch_create_real(client, activated_repo, test_repo_dir: Path):
    """
    Integration test: POST /api/v1/repos/{alias}/git/branches

    Tests creating a real git branch.
    """
    branch_name = "test-create-branch"

    try:
        # Execute: Call REST endpoint to create branch
        response = client.post(
            f"/api/v1/repos/{activated_repo}/git/branches",
            json={"branch_name": branch_name}
        )

        # Verify: Check HTTP response
        assert response.status_code == 201  # POST creating resource returns 201 Created
        data = response.json()
        assert data["success"] is True
        assert data["created_branch"] == branch_name

        # Verify: Branch actually exists
        result = subprocess.run(
            ["git", "branch", "--list", branch_name],
            cwd=test_repo_dir,
            capture_output=True,
            text=True
        )
        assert branch_name in result.stdout

    finally:
        # Cleanup: Delete branch
        subprocess.run(
            ["git", "branch", "-D", branch_name],
            cwd=test_repo_dir,
            capture_output=True
        )


def test_git_branch_switch_real(client, activated_repo, test_repo_dir: Path):
    """
    Integration test: POST /api/v1/repos/{alias}/git/branches/{name}/switch

    Tests switching between real git branches.
    """
    # Setup: Create test branch
    branch_name = "test-switch-branch"
    subprocess.run(["git", "branch", branch_name], cwd=test_repo_dir, check=True)

    # Get current branch
    current_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=test_repo_dir,
        capture_output=True,
        text=True
    ).stdout.strip()

    try:
        # Execute: Call REST endpoint to switch branch
        response = client.post(
            f"/api/v1/repos/{activated_repo}/git/branches/{branch_name}/switch"
        )

        # Verify: Check HTTP response
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["current_branch"] == branch_name
        assert data["previous_branch"] == current_branch

        # Verify: Actually on new branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=test_repo_dir,
            capture_output=True,
            text=True
        )
        assert result.stdout.strip() == branch_name

    finally:
        # Cleanup: Switch back and delete branch
        subprocess.run(["git", "checkout", current_branch], cwd=test_repo_dir, capture_output=True)
        subprocess.run(["git", "branch", "-D", branch_name], cwd=test_repo_dir, capture_output=True)


def test_git_branch_delete_real(client, activated_repo, test_repo_dir: Path):
    """
    Integration test: DELETE /api/v1/repos/{alias}/git/branches/{name}

    Tests deleting a real git branch with confirmation token.
    """
    # Setup: Create test branch
    branch_name = "test-delete-branch"
    subprocess.run(["git", "branch", branch_name], cwd=test_repo_dir, check=True)

    try:
        # Step 1: Request confirmation token
        response = client.delete(f"/api/v1/repos/{activated_repo}/git/branches/{branch_name}")

        # Verify: Token required
        assert response.status_code == 200
        data = response.json()
        assert data["requires_confirmation"] is True
        assert "token" in data
        token = data["token"]

        # Step 2: Delete with token
        response = client.delete(
            f"/api/v1/repos/{activated_repo}/git/branches/{branch_name}?confirmation_token={token}"
        )

        # Verify: Delete succeeded
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["deleted_branch"] == branch_name

        # Verify: Branch no longer exists
        result = subprocess.run(
            ["git", "branch", "--list", branch_name],
            cwd=test_repo_dir,
            capture_output=True,
            text=True
        )
        assert branch_name not in result.stdout

    finally:
        # Cleanup: Ensure branch is deleted
        subprocess.run(
            ["git", "branch", "-D", branch_name],
            cwd=test_repo_dir,
            capture_output=True
        )
