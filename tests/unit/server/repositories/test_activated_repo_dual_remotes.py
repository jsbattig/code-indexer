"""
Unit tests for ActivatedRepoManager dual remote functionality (Story #636).

Tests the dual remote configuration for activated repositories:
- New activations get origin (GitHub/GitLab) + golden (local) remotes
- Legacy repos with single origin remote auto-migrate to dual remotes
- Migration is idempotent and logged
- sync_with_golden_repository() uses golden remote instead of origin
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone

import pytest

from src.code_indexer.server.repositories.activated_repo_manager import (
    ActivatedRepoManager,
    ActivatedRepoError,
    GitOperationError,
)
from src.code_indexer.server.repositories.golden_repo_manager import GoldenRepo


@pytest.mark.unit
class TestDualRemoteConfiguration:
    """Test suite for dual remote setup in new activations."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for golden and activated repos."""
        with tempfile.TemporaryDirectory() as temp_dir:
            golden_dir = os.path.join(temp_dir, "golden-repos")
            activated_dir = os.path.join(temp_dir, "activated-repos")
            os.makedirs(golden_dir)
            os.makedirs(activated_dir)
            yield {
                "root": temp_dir,
                "golden": golden_dir,
                "activated": activated_dir,
            }

    @pytest.fixture
    def real_git_repo(self, temp_dirs):
        """Create a real git repository to use as golden repo."""
        repo_path = os.path.join(temp_dirs["golden"], "test-repo")
        os.makedirs(repo_path)

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Create initial commit
        test_file = os.path.join(repo_path, "README.md")
        with open(test_file, "w") as f:
            f.write("# Test Repo\n")

        subprocess.run(
            ["git", "add", "README.md"], cwd=repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Add a remote origin (simulating GitHub URL)
        subprocess.run(
            [
                "git",
                "remote",
                "add",
                "origin",
                "git@github.com:example/test-repo.git",
            ],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        return repo_path

    @pytest.fixture
    def activated_repo_manager(self, temp_dirs, real_git_repo):
        """Create ActivatedRepoManager with real git golden repo."""
        golden_repo_manager_mock = MagicMock()
        golden_repo = GoldenRepo(
            alias="test-repo",
            repo_url="git@github.com:example/test-repo.git",
            default_branch="master",
            clone_path=real_git_repo,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        golden_repo_manager_mock.golden_repos = {"test-repo": golden_repo}

        background_job_manager_mock = MagicMock()

        return ActivatedRepoManager(
            data_dir=temp_dirs["root"],
            golden_repo_manager=golden_repo_manager_mock,
            background_job_manager=background_job_manager_mock,
        )

    def test_configure_git_structure_sets_up_dual_remotes(
        self, activated_repo_manager, real_git_repo, temp_dirs
    ):
        """
        Test that _configure_git_structure() sets up BOTH remotes for new activations.

        RED PHASE: This test should FAIL because _configure_git_structure() currently
        only sets up 'origin' pointing to local golden repo path.

        ACCEPTANCE CRITERION 1: Activated repository has dual remotes configured
        """
        # Arrange: Create destination directory for activated repo
        dest_path = os.path.join(temp_dirs["activated"], "testuser", "test-repo-clone")
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        # Copy golden repo to destination (simulating CoW clone)
        shutil.copytree(real_git_repo, dest_path)

        # Remove existing remote to simulate fresh activation
        subprocess.run(
            ["git", "remote", "remove", "origin"],
            cwd=dest_path,
            check=True,
            capture_output=True,
        )

        # Act: Call _configure_git_structure
        activated_repo_manager._configure_git_structure(real_git_repo, dest_path)

        # Assert: Verify dual remotes are configured
        result = subprocess.run(
            ["git", "remote", "-v"],
            cwd=dest_path,
            capture_output=True,
            text=True,
            check=True,
        )
        remotes_output = result.stdout

        # Should have origin pointing to GitHub URL
        assert "origin\tgit@github.com:example/test-repo.git" in remotes_output

        # Should have golden pointing to local path
        assert f"golden\t{real_git_repo}" in remotes_output

        # Verify we have exactly 2 remotes (origin and golden)
        remote_list = subprocess.run(
            ["git", "remote"],
            cwd=dest_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip().split("\n")

        assert len(remote_list) == 2
        assert "origin" in remote_list
        assert "golden" in remote_list

    def test_configure_git_structure_extracts_github_url_from_golden_repo(
        self, activated_repo_manager, real_git_repo, temp_dirs
    ):
        """
        Test that _configure_git_structure() correctly extracts GitHub URL from golden repo.

        RED PHASE: Should FAIL because current implementation doesn't extract GitHub URL.

        ACCEPTANCE CRITERION 1: origin points to GitHub URL
        """
        # Arrange
        dest_path = os.path.join(temp_dirs["activated"], "testuser", "test-clone")
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copytree(real_git_repo, dest_path)
        subprocess.run(
            ["git", "remote", "remove", "origin"],
            cwd=dest_path,
            check=True,
            capture_output=True,
        )

        # Act
        activated_repo_manager._configure_git_structure(real_git_repo, dest_path)

        # Assert: origin should point to GitHub, not local path
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=dest_path,
            capture_output=True,
            text=True,
            check=True,
        )
        origin_url = result.stdout.strip()

        assert origin_url == "git@github.com:example/test-repo.git"
        assert not origin_url.startswith("/")  # Should NOT be a local path

    def test_configure_git_structure_golden_remote_points_to_local_path(
        self, activated_repo_manager, real_git_repo, temp_dirs
    ):
        """
        Test that _configure_git_structure() sets golden remote to local golden repo path.

        RED PHASE: Should FAIL because golden remote doesn't exist yet.

        ACCEPTANCE CRITERION 1: golden points to local golden repo path
        """
        # Arrange
        dest_path = os.path.join(temp_dirs["activated"], "testuser", "test-clone-2")
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copytree(real_git_repo, dest_path)
        subprocess.run(
            ["git", "remote", "remove", "origin"],
            cwd=dest_path,
            check=True,
            capture_output=True,
        )

        # Act
        activated_repo_manager._configure_git_structure(real_git_repo, dest_path)

        # Assert: golden should point to local path
        result = subprocess.run(
            ["git", "remote", "get-url", "golden"],
            cwd=dest_path,
            capture_output=True,
            text=True,
            check=True,
        )
        golden_url = result.stdout.strip()

        assert golden_url == real_git_repo
        assert golden_url.startswith("/")  # Should be a local path


@pytest.mark.unit
class TestLegacyRemoteMigration:
    """Test suite for just-in-time migration of legacy single-remote repos."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            golden_dir = os.path.join(temp_dir, "golden-repos")
            activated_dir = os.path.join(temp_dir, "activated-repos")
            os.makedirs(golden_dir)
            os.makedirs(activated_dir)
            yield {
                "root": temp_dir,
                "golden": golden_dir,
                "activated": activated_dir,
            }

    @pytest.fixture
    def golden_repo_with_remote(self, temp_dirs):
        """Create golden repo with GitHub remote."""
        repo_path = os.path.join(temp_dirs["golden"], "golden-repo")
        os.makedirs(repo_path)

        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        test_file = os.path.join(repo_path, "README.md")
        with open(test_file, "w") as f:
            f.write("# Golden Repo\n")

        subprocess.run(
            ["git", "add", "README.md"], cwd=repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Add GitHub remote to golden repo
        subprocess.run(
            [
                "git",
                "remote",
                "add",
                "origin",
                "git@github.com:jsbattig/test-repo.git",
            ],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        return repo_path

    @pytest.fixture
    def legacy_activated_repo(self, temp_dirs, golden_repo_with_remote):
        """Create legacy activated repo with origin pointing to local path."""
        repo_path = os.path.join(temp_dirs["activated"], "admin", "legacy-repo")
        os.makedirs(os.path.dirname(repo_path), exist_ok=True)

        # Clone from golden repo
        shutil.copytree(golden_repo_with_remote, repo_path)

        # Set origin to local path (legacy behavior)
        subprocess.run(
            ["git", "remote", "remove", "origin"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", golden_repo_with_remote],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        return repo_path

    @pytest.fixture
    def activated_repo_manager(self, temp_dirs):
        """Create ActivatedRepoManager instance."""
        golden_repo_manager_mock = MagicMock()
        background_job_manager_mock = MagicMock()

        return ActivatedRepoManager(
            data_dir=temp_dirs["root"],
            golden_repo_manager=golden_repo_manager_mock,
            background_job_manager=background_job_manager_mock,
        )

    def test_detect_and_migrate_legacy_remotes_method_exists(
        self, activated_repo_manager
    ):
        """
        Test that _detect_and_migrate_legacy_remotes() method exists.

        RED PHASE: Should FAIL because method doesn't exist yet.
        """
        assert hasattr(activated_repo_manager, "_detect_and_migrate_legacy_remotes")
        assert callable(
            getattr(activated_repo_manager, "_detect_and_migrate_legacy_remotes")
        )

    def test_detect_legacy_repo_with_local_origin(
        self, activated_repo_manager, legacy_activated_repo, golden_repo_with_remote
    ):
        """
        Test that _detect_and_migrate_legacy_remotes() detects legacy configuration.

        RED PHASE: Should FAIL because method doesn't exist yet.

        ACCEPTANCE CRITERION 6 & 7: Detect legacy repos with origin=local path
        """
        # Verify legacy setup (origin points to local path)
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=legacy_activated_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        origin_url = result.stdout.strip()
        assert origin_url.startswith("/")  # Confirm it's a local path

        # Act: Detect and migrate
        migration_occurred = activated_repo_manager._detect_and_migrate_legacy_remotes(
            legacy_activated_repo, golden_repo_with_remote
        )

        # Assert: Migration should have occurred
        assert migration_occurred is True

    def test_migrate_legacy_repo_renames_origin_to_golden(
        self, activated_repo_manager, legacy_activated_repo, golden_repo_with_remote
    ):
        """
        Test that migration renames origin to golden.

        RED PHASE: Should FAIL because migration logic doesn't exist yet.

        ACCEPTANCE CRITERION 6: Create 'golden' remote pointing to local golden repo
        """
        # Act: Migrate
        activated_repo_manager._detect_and_migrate_legacy_remotes(
            legacy_activated_repo, golden_repo_with_remote
        )

        # Assert: golden remote should exist and point to local path
        result = subprocess.run(
            ["git", "remote", "get-url", "golden"],
            cwd=legacy_activated_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        golden_url = result.stdout.strip()

        assert golden_url == golden_repo_with_remote
        assert golden_url.startswith("/")

    def test_migrate_legacy_repo_sets_origin_to_github_url(
        self, activated_repo_manager, legacy_activated_repo, golden_repo_with_remote
    ):
        """
        Test that migration sets origin to GitHub URL.

        RED PHASE: Should FAIL because migration logic doesn't exist yet.

        ACCEPTANCE CRITERION 6: Migrate origin to point to GitHub URL
        """
        # Act: Migrate
        activated_repo_manager._detect_and_migrate_legacy_remotes(
            legacy_activated_repo, golden_repo_with_remote
        )

        # Assert: origin should point to GitHub URL
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=legacy_activated_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        origin_url = result.stdout.strip()

        assert origin_url == "git@github.com:jsbattig/test-repo.git"
        assert not origin_url.startswith("/")

    def test_migration_is_idempotent(
        self, activated_repo_manager, legacy_activated_repo, golden_repo_with_remote
    ):
        """
        Test that migration only runs once (idempotent).

        RED PHASE: Should FAIL because migration logic doesn't exist yet.

        ACCEPTANCE CRITERION 7: Migration only runs once per repo
        """
        # Act: Migrate twice
        first_migration = activated_repo_manager._detect_and_migrate_legacy_remotes(
            legacy_activated_repo, golden_repo_with_remote
        )
        second_migration = activated_repo_manager._detect_and_migrate_legacy_remotes(
            legacy_activated_repo, golden_repo_with_remote
        )

        # Assert: First migration should return True, second should return False
        assert first_migration is True
        assert second_migration is False

        # Verify remotes are still correctly configured after second call
        result = subprocess.run(
            ["git", "remote", "-v"],
            cwd=legacy_activated_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        remotes = result.stdout

        assert "origin\tgit@github.com:jsbattig/test-repo.git" in remotes
        assert f"golden\t{golden_repo_with_remote}" in remotes

    def test_detect_already_migrated_repo_returns_false(
        self, activated_repo_manager, temp_dirs, golden_repo_with_remote
    ):
        """
        Test that already-migrated repos are detected correctly.

        RED PHASE: Should FAIL because method doesn't exist yet.

        ACCEPTANCE CRITERION 7: Detect repos already using dual remotes
        """
        # Arrange: Create repo with dual remotes already configured
        repo_path = os.path.join(temp_dirs["activated"], "admin", "already-migrated")
        os.makedirs(os.path.dirname(repo_path), exist_ok=True)
        shutil.copytree(golden_repo_with_remote, repo_path)

        # Set up dual remotes manually
        subprocess.run(
            ["git", "remote", "remove", "origin"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "git",
                "remote",
                "add",
                "origin",
                "git@github.com:jsbattig/test-repo.git",
            ],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "remote", "add", "golden", golden_repo_with_remote],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Act: Try to migrate
        migration_occurred = activated_repo_manager._detect_and_migrate_legacy_remotes(
            repo_path, golden_repo_with_remote
        )

        # Assert: No migration should occur
        assert migration_occurred is False


@pytest.mark.unit
class TestSyncWithGoldenRemote:
    """Test that sync_with_golden_repository() uses 'golden' remote."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = os.path.join(temp_dir, "data")
            os.makedirs(data_dir)
            yield data_dir

    @pytest.fixture
    def activated_repo_manager(self, temp_dirs):
        """Create ActivatedRepoManager instance."""
        golden_repo_manager_mock = MagicMock()
        background_job_manager_mock = MagicMock()

        return ActivatedRepoManager(
            data_dir=temp_dirs,
            golden_repo_manager=golden_repo_manager_mock,
            background_job_manager=background_job_manager_mock,
        )

    @patch("subprocess.run")
    def test_sync_with_golden_repository_uses_golden_remote(
        self, mock_subprocess, activated_repo_manager, temp_dirs
    ):
        """
        Test that sync_with_golden_repository() uses 'golden' remote instead of 'origin'.

        RED PHASE: Should FAIL because sync currently uses 'git fetch origin'.

        ACCEPTANCE CRITERION 4: sync uses 'golden' remote (not 'origin')
        """
        # Arrange: Create user and repo directories
        username = "admin"
        user_alias = "test-repo"
        user_dir = os.path.join(temp_dirs, "activated-repos", username)
        repo_dir = os.path.join(user_dir, user_alias)
        os.makedirs(repo_dir, exist_ok=True)

        # Create .git directory to simulate git repo
        git_dir = os.path.join(repo_dir, ".git")
        os.makedirs(git_dir, exist_ok=True)

        # Create metadata file (required by sync_with_golden_repository)
        metadata_file = os.path.join(user_dir, f"{user_alias}_metadata.json")
        metadata = {
            "user_alias": user_alias,
            "golden_repo_alias": "test-golden",
            "current_branch": "master",
            "activated_at": "2025-01-01T00:00:00Z",
            "last_accessed": "2025-01-01T00:00:00Z",
        }
        with open(metadata_file, "w") as f:
            json.dump(metadata, f)

        # Mock subprocess responses
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = ""
        mock_subprocess.return_value.stderr = ""

        # Act: Call sync
        activated_repo_manager.sync_with_golden_repository(username, user_alias)

        # Assert: Verify 'git fetch golden' was called (not 'git fetch origin')
        fetch_calls = [
            call
            for call in mock_subprocess.call_args_list
            if len(call[0]) > 0 and "fetch" in call[0][0]
        ]

        assert len(fetch_calls) > 0, "No git fetch calls found"

        # Check that fetch uses 'golden' remote
        fetch_call = fetch_calls[0]
        assert "git" in fetch_call[0][0]
        assert "fetch" in fetch_call[0][0]
        assert "golden" in fetch_call[0][0], f"Expected 'golden' remote, got: {fetch_call[0][0]}"
        assert "origin" not in fetch_call[0][0] or "golden" in fetch_call[0][0], "Should use 'golden' not 'origin'"
