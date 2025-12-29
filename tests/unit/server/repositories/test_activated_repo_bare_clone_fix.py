"""
Tests for bare repository handling in CoW clone (Story #636).

Tests that when golden repositories (stored as bare) are CoW cloned,
the resulting activated repositories are converted to non-bare with:
- Working tree checked out
- Dual remotes configured (origin + golden)
"""

import subprocess

import pytest

from code_indexer.server.repositories.activated_repo_manager import ActivatedRepoManager


@pytest.fixture
def bare_golden_repo(tmp_path):
    """Create a bare golden repository for testing."""
    repo_path = tmp_path / "bare-golden"
    repo_path.mkdir()

    # Initialize as bare repo with origin remote
    subprocess.run(
        ["git", "init", "--bare"],
        cwd=repo_path,
        check=True,
        capture_output=True
    )

    # Add origin remote (simulating GitHub)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:test/repo.git"],
        cwd=repo_path,
        check=True,
        capture_output=True
    )

    return str(repo_path)


def test_cow_clone_converts_bare_to_nonbare(bare_golden_repo, tmp_path):
    """Test that CoW cloning a bare repo creates a non-bare activated repo."""
    dest_path = tmp_path / "activated"

    mgr = ActivatedRepoManager()

    # Perform CoW clone
    success = mgr._clone_with_copy_on_write(bare_golden_repo, str(dest_path))

    assert success, "CoW clone should succeed"
    assert dest_path.exists(), "Activated repo should exist"

    # Check that it's NOT bare
    config_file = dest_path / "config"
    if config_file.exists():
        # If config exists at root, it might still be bare
        result = subprocess.run(
            ["git", "config", "core.bare"],
            cwd=dest_path,
            capture_output=True,
            text=True
        )
        # Should return empty or "false", not "true"
        assert result.stdout.strip() != "true", "Activated repo should not be bare"

    # Check that working tree exists (.git subdirectory)
    git_dir = dest_path / ".git"
    assert git_dir.exists(), "Activated repo should have .git directory"
    assert git_dir.is_dir(), ".git should be a directory"


def test_cow_clone_configures_dual_remotes_for_bare_repo(bare_golden_repo, tmp_path):
    """Test that CoW cloning a bare repo configures dual remotes."""
    dest_path = tmp_path / "activated"

    mgr = ActivatedRepoManager()

    # Perform CoW clone
    success = mgr._clone_with_copy_on_write(bare_golden_repo, str(dest_path))

    assert success, "CoW clone should succeed"

    # Check remotes
    result = subprocess.run(
        ["git", "remote"],
        cwd=dest_path,
        capture_output=True,
        text=True,
        check=True
    )

    remotes = result.stdout.strip().split("\n")
    assert "origin" in remotes, "Should have origin remote"
    assert "golden" in remotes, "Should have golden remote"

    # Verify origin points to GitHub
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=dest_path,
        capture_output=True,
        text=True,
        check=True
    )
    origin_url = result.stdout.strip()
    assert "github.com" in origin_url, "Origin should point to GitHub"

    # Verify golden points to local path
    result = subprocess.run(
        ["git", "remote", "get-url", "golden"],
        cwd=dest_path,
        capture_output=True,
        text=True,
        check=True
    )
    golden_url = result.stdout.strip()
    assert golden_url == bare_golden_repo, "Golden should point to golden repo path"


def test_git_status_works_after_cow_clone(bare_golden_repo, tmp_path):
    """Test that git status works in activated repo after CoW clone."""
    dest_path = tmp_path / "activated"

    mgr = ActivatedRepoManager()

    # Perform CoW clone
    success = mgr._clone_with_copy_on_write(bare_golden_repo, str(dest_path))

    assert success, "CoW clone should succeed"

    # git status should work without errors
    result = subprocess.run(
        ["git", "status"],
        cwd=dest_path,
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, f"git status should succeed, got: {result.stderr}"
    assert "fatal" not in result.stderr.lower(), "Should not have fatal errors"
