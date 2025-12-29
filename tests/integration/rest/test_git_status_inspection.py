"""
Integration tests for Git Status/Inspection REST endpoints (Story #630 - F2).

Tests 3 git status/inspection operations:
- GET /api/v1/repos/{alias}/git/status
- GET /api/v1/repos/{alias}/git/diff
- GET /api/v1/repos/{alias}/git/log

Uses REAL GitOperationsService with actual git command execution.
NO MOCKING of git operations.
"""

from pathlib import Path


def test_git_status_real_repository(client, activated_repo, test_repo_dir: Path):
    """
    Integration test: GET /api/v1/repos/{alias}/git/status

    Tests with REAL GitOperationsService and actual git repository.
    Verifies detection of untracked files.
    """
    # Setup: Create untracked file
    test_file = test_repo_dir / "test_untracked.txt"
    test_file.write_text("untracked content")

    try:
        # Execute: Call REST endpoint
        response = client.get(f"/api/v1/repos/{activated_repo}/git/status")

        # Verify: Check HTTP response
        assert response.status_code == 200
        data = response.json()

        # Verify: Untracked file appears in response
        assert "untracked" in data
        assert "test_untracked.txt" in data["untracked"]

    finally:
        # Cleanup: Remove test file
        if test_file.exists():
            test_file.unlink()


def test_git_diff_real_repository(client, activated_repo, test_repo_dir: Path):
    """
    Integration test: GET /api/v1/repos/{alias}/git/diff

    Tests with REAL git diff output for modified files.
    """
    # Setup: Modify existing file
    readme_path = test_repo_dir / "README.md"
    original_content = readme_path.read_text() if readme_path.exists() else ""

    if readme_path.exists():
        readme_path.write_text(original_content + "\n# Test modification\n")
    else:
        readme_path.write_text("# Test file\n")

    try:
        # Execute: Call REST endpoint
        response = client.get(f"/api/v1/repos/{activated_repo}/git/diff")

        # Verify: Check HTTP response
        assert response.status_code == 200
        data = response.json()

        # Verify: Diff shows changes
        assert "diff_text" in data
        assert "files_changed" in data
        assert data["files_changed"] >= 1
        assert "README.md" in data["diff_text"] or "Test" in data["diff_text"]

    finally:
        # Cleanup: Restore original content
        if original_content:
            readme_path.write_text(original_content)
        elif readme_path.exists():
            readme_path.unlink()


def test_git_log_real_repository(client, activated_repo, test_repo_dir: Path):
    """
    Integration test: GET /api/v1/repos/{alias}/git/log

    Tests with REAL git commit history.
    """
    # Execute: Call REST endpoint with limit
    response = client.get(
        f"/api/v1/repos/{activated_repo}/git/log",
        params={"limit": 5}
    )

    # Verify: Check HTTP response
    assert response.status_code == 200
    data = response.json()

    # Verify: Commits list exists
    assert "commits" in data
    assert isinstance(data["commits"], list)
    assert len(data["commits"]) <= 5

    # Verify: Commit structure
    if data["commits"]:
        commit = data["commits"][0]
        assert "commit_hash" in commit
        assert "author" in commit
        assert "date" in commit
        assert "message" in commit
