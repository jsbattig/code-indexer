"""
Unit tests for canonical path resolution in GoldenRepoManager.

Tests the get_actual_repo_path() method that resolves metadata paths to
actual filesystem locations, handling mixed topology (flat + versioned).
"""

import json
import os
import tempfile

import pytest

from code_indexer.server.repositories.golden_repo_manager import (
    GoldenRepo,
    GoldenRepoError,
    GoldenRepoNotFoundError,
    GoldenRepoManager,
)


class TestCanonicalPathResolution:
    """Tests for get_actual_repo_path() method."""

    def setup_method(self):
        """Create temporary directory structure for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = os.path.join(self.temp_dir, "cidx-server-data")
        self.golden_repos_dir = os.path.join(self.data_dir, "golden-repos")
        os.makedirs(self.golden_repos_dir, exist_ok=True)

        # Create metadata file
        self.metadata_file = os.path.join(self.golden_repos_dir, "metadata.json")
        with open(self.metadata_file, "w") as f:
            json.dump({}, f)

        # Initialize manager
        self.manager = GoldenRepoManager(data_dir=self.data_dir)

    def teardown_method(self):
        """Clean up temporary directory."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_flat_structure_resolution(self):
        """
        Test canonical path resolution for flat structure repos.

        When metadata points to flat structure and directory exists,
        should return the metadata path.
        """
        # Create flat structure repo
        flat_path = os.path.join(self.golden_repos_dir, "test-repo")
        os.makedirs(flat_path, exist_ok=True)

        # Add golden repo with flat path
        golden_repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/user/repo.git",
            default_branch="main",
            clone_path=flat_path,
            created_at="2025-01-01T00:00:00Z",
        )
        self.manager.golden_repos["test-repo"] = golden_repo
        self.manager._save_metadata()

        # Test resolution
        actual_path = self.manager.get_actual_repo_path("test-repo")
        assert actual_path == flat_path
        assert os.path.exists(actual_path)

    def test_versioned_structure_resolution(self):
        """
        Test canonical path resolution for versioned structure repos.

        When metadata points to non-existent flat path but versioned directory exists,
        should return the versioned path.
        """
        # Create metadata pointing to non-existent flat path
        flat_path = os.path.join(self.golden_repos_dir, "txt-db")

        # Create versioned structure (actual location)
        versioned_dir = os.path.join(self.golden_repos_dir, ".versioned", "txt-db")
        versioned_path = os.path.join(versioned_dir, "v_1767053582")
        os.makedirs(versioned_path, exist_ok=True)

        # Add golden repo with flat path (but repo is actually in versioned)
        golden_repo = GoldenRepo(
            alias="txt-db",
            repo_url="local://txt-db",
            default_branch="main",
            clone_path=flat_path,
            created_at="2025-01-01T00:00:00Z",
        )
        self.manager.golden_repos["txt-db"] = golden_repo
        self.manager._save_metadata()

        # Test resolution - should find versioned path
        actual_path = self.manager.get_actual_repo_path("txt-db")
        assert actual_path == versioned_path
        assert os.path.exists(actual_path)

    def test_multiple_versions_returns_latest(self):
        """
        Test canonical path resolution with multiple versioned directories.

        When multiple version directories exist, should return the one with
        highest timestamp (latest version).
        """
        # Create metadata pointing to non-existent flat path
        flat_path = os.path.join(self.golden_repos_dir, "multi-ver")

        # Create multiple versioned directories
        versioned_dir = os.path.join(self.golden_repos_dir, ".versioned", "multi-ver")
        older_version = os.path.join(versioned_dir, "v_1767053000")
        newer_version = os.path.join(versioned_dir, "v_1767053999")
        os.makedirs(older_version, exist_ok=True)
        os.makedirs(newer_version, exist_ok=True)

        # Add golden repo
        golden_repo = GoldenRepo(
            alias="multi-ver",
            repo_url="local://multi-ver",
            default_branch="main",
            clone_path=flat_path,
            created_at="2025-01-01T00:00:00Z",
        )
        self.manager.golden_repos["multi-ver"] = golden_repo
        self.manager._save_metadata()

        # Test resolution - should return newest version
        actual_path = self.manager.get_actual_repo_path("multi-ver")
        assert actual_path == newer_version
        assert os.path.exists(actual_path)

    def test_repo_not_found_raises_error(self):
        """
        Test canonical path resolution when repo doesn't exist in either location.

        When neither metadata path nor versioned path exists, should raise
        GoldenRepoNotFoundError with clear message showing both attempted paths.
        """
        # Create metadata pointing to non-existent flat path
        flat_path = os.path.join(self.golden_repos_dir, "missing-repo")

        # Add golden repo (no actual directory created)
        golden_repo = GoldenRepo(
            alias="missing-repo",
            repo_url="https://github.com/user/missing.git",
            default_branch="main",
            clone_path=flat_path,
            created_at="2025-01-01T00:00:00Z",
        )
        self.manager.golden_repos["missing-repo"] = golden_repo
        self.manager._save_metadata()

        # Test resolution - should raise error
        with pytest.raises(GoldenRepoNotFoundError) as exc_info:
            self.manager.get_actual_repo_path("missing-repo")

        error_msg = str(exc_info.value)
        assert "missing-repo" in error_msg
        assert "not found" in error_msg.lower()
        # Error should mention both attempted paths
        assert flat_path in error_msg
        assert ".versioned" in error_msg

    def test_alias_not_in_metadata_raises_error(self):
        """
        Test canonical path resolution when alias doesn't exist in metadata.

        Should raise GoldenRepoNotFoundError when alias is not registered.
        """
        with pytest.raises(GoldenRepoNotFoundError) as exc_info:
            self.manager.get_actual_repo_path("non-existent-alias")

        error_msg = str(exc_info.value)
        assert "non-existent-alias" in error_msg
        assert "not found" in error_msg.lower()

    def test_flat_structure_takes_priority_over_versioned(self):
        """
        Test that flat structure is checked first (priority order).

        When both flat and versioned paths exist, should return flat path
        since it's checked first in priority order.
        """
        # Create BOTH flat and versioned structures
        flat_path = os.path.join(self.golden_repos_dir, "dual-exists")
        os.makedirs(flat_path, exist_ok=True)

        versioned_dir = os.path.join(self.golden_repos_dir, ".versioned", "dual-exists")
        versioned_path = os.path.join(versioned_dir, "v_1767053582")
        os.makedirs(versioned_path, exist_ok=True)

        # Add golden repo with flat path
        golden_repo = GoldenRepo(
            alias="dual-exists",
            repo_url="https://github.com/user/dual.git",
            default_branch="main",
            clone_path=flat_path,
            created_at="2025-01-01T00:00:00Z",
        )
        self.manager.golden_repos["dual-exists"] = golden_repo
        self.manager._save_metadata()

        # Test resolution - should prefer flat path
        actual_path = self.manager.get_actual_repo_path("dual-exists")
        assert actual_path == flat_path
        assert ".versioned" not in actual_path

    def test_versioned_directory_no_v_subdirs_raises_error(self):
        """
        Test resolution when .versioned/{alias}/ exists but has no v_* subdirectories.

        Should raise error when versioned directory exists but contains no versions.
        """
        # Create metadata pointing to non-existent flat path
        flat_path = os.path.join(self.golden_repos_dir, "empty-versioned")

        # Create versioned directory but NO v_* subdirectories
        versioned_dir = os.path.join(self.golden_repos_dir, ".versioned", "empty-versioned")
        os.makedirs(versioned_dir, exist_ok=True)

        # Add golden repo
        golden_repo = GoldenRepo(
            alias="empty-versioned",
            repo_url="local://empty-versioned",
            default_branch="main",
            clone_path=flat_path,
            created_at="2025-01-01T00:00:00Z",
        )
        self.manager.golden_repos["empty-versioned"] = golden_repo
        self.manager._save_metadata()

        # Test resolution - should raise error (no v_* directories found)
        with pytest.raises(GoldenRepoNotFoundError) as exc_info:
            self.manager.get_actual_repo_path("empty-versioned")

        error_msg = str(exc_info.value)
        assert "empty-versioned" in error_msg
        assert "not found" in error_msg.lower()

    def test_path_traversal_with_double_dots(self):
        """
        SECURITY: Test path traversal attack using double dots.

        Alias containing '../../../etc/passwd' should be rejected to prevent
        directory traversal attacks escaping the golden repos directory.
        """
        # Attempt to use path traversal in alias
        malicious_alias = "../../../etc/passwd"

        # Should raise ValueError before filesystem access
        with pytest.raises(ValueError) as exc_info:
            self.manager.get_actual_repo_path(malicious_alias)

        error_msg = str(exc_info.value)
        assert "path traversal" in error_msg.lower() or "invalid alias" in error_msg.lower()
        assert ".." in error_msg

    def test_path_traversal_with_forward_slash(self):
        """
        SECURITY: Test path traversal attack using forward slashes.

        Alias containing 'root/../../etc/passwd' should be rejected to prevent
        directory escape attacks.
        """
        # Attempt to use path with forward slashes
        malicious_alias = "root/../../etc/passwd"

        # Should raise ValueError before filesystem access
        with pytest.raises(ValueError) as exc_info:
            self.manager.get_actual_repo_path(malicious_alias)

        error_msg = str(exc_info.value)
        assert "path traversal" in error_msg.lower() or "invalid alias" in error_msg.lower()
        assert "/" in error_msg

    def test_path_traversal_with_backslash(self):
        """
        SECURITY: Test path traversal attack using backslashes.

        Alias containing 'root\\..\\..\\etc\\passwd' should be rejected to prevent
        Windows-style directory escape attacks.
        """
        # Attempt to use path with backslashes
        malicious_alias = "root\\..\\..\\etc\\passwd"

        # Should raise ValueError before filesystem access
        with pytest.raises(ValueError) as exc_info:
            self.manager.get_actual_repo_path(malicious_alias)

        error_msg = str(exc_info.value)
        assert "path traversal" in error_msg.lower() or "invalid alias" in error_msg.lower()
        assert "\\" in error_msg or "backslash" in error_msg.lower()

    def test_malformed_version_directory_skipped(self):
        """
        SECURITY: Test graceful handling of malformed version directories.

        When version directory name is 'v_abc' instead of 'v_1234567890', should
        skip it and continue checking other versions instead of crashing.
        """
        # Create metadata pointing to non-existent flat path
        flat_path = os.path.join(self.golden_repos_dir, "malformed-ver")

        # Create versioned directory with mix of valid and malformed versions
        versioned_dir = os.path.join(self.golden_repos_dir, ".versioned", "malformed-ver")
        malformed_version = os.path.join(versioned_dir, "v_abc")  # Invalid timestamp
        valid_version = os.path.join(versioned_dir, "v_1767053582")  # Valid timestamp
        os.makedirs(malformed_version, exist_ok=True)
        os.makedirs(valid_version, exist_ok=True)

        # Add golden repo
        golden_repo = GoldenRepo(
            alias="malformed-ver",
            repo_url="local://malformed-ver",
            default_branch="main",
            clone_path=flat_path,
            created_at="2025-01-01T00:00:00Z",
        )
        self.manager.golden_repos["malformed-ver"] = golden_repo
        self.manager._save_metadata()

        # Should skip malformed version and return valid version
        actual_path = self.manager.get_actual_repo_path("malformed-ver")
        assert actual_path == valid_version
        assert os.path.exists(actual_path)

    def test_realpath_verification(self):
        """
        SECURITY: Test symlink attack prevention using realpath verification.

        If metadata path or versioned path is a symlink pointing outside
        golden_repos_dir, should be rejected to prevent sandbox escape.
        """
        # Create a directory OUTSIDE golden_repos_dir
        outside_dir = os.path.join(self.temp_dir, "outside")
        os.makedirs(outside_dir, exist_ok=True)

        # Create symlink inside golden_repos_dir pointing to outside directory
        symlink_path = os.path.join(self.golden_repos_dir, "symlink-attack")
        os.symlink(outside_dir, symlink_path)

        # Add golden repo with symlink path
        golden_repo = GoldenRepo(
            alias="symlink-attack",
            repo_url="https://github.com/user/attack.git",
            default_branch="main",
            clone_path=symlink_path,
            created_at="2025-01-01T00:00:00Z",
        )
        self.manager.golden_repos["symlink-attack"] = golden_repo
        self.manager._save_metadata()

        # Should reject symlink pointing outside golden_repos_dir
        with pytest.raises(ValueError) as exc_info:
            self.manager.get_actual_repo_path("symlink-attack")

        error_msg = str(exc_info.value)
        assert "security violation" in error_msg.lower() or "outside" in error_msg.lower()


class TestCanonicalPathIntegrationWithMigration:
    """Integration tests: canonical path resolution with migration code."""

    def setup_method(self):
        """Create temporary directory structure for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = os.path.join(self.temp_dir, "cidx-server-data")
        self.golden_repos_dir = os.path.join(self.data_dir, "golden-repos")
        os.makedirs(self.golden_repos_dir, exist_ok=True)

        # Create metadata file
        self.metadata_file = os.path.join(self.golden_repos_dir, "metadata.json")
        with open(self.metadata_file, "w") as f:
            json.dump({}, f)

        # Initialize manager
        self.manager = GoldenRepoManager(data_dir=self.data_dir)

    def teardown_method(self):
        """Clean up temporary directory."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_migration_uses_canonical_path_for_versioned_repo(self):
        """
        Test that migration code uses canonical path instead of metadata path.

        This is an integration test verifying the fix for Bug #3 and Bug #4.
        When migration tries to get GitHub URL from golden repo, it should use
        the actual filesystem path, not the stale metadata path.
        """
        # Create versioned golden repo structure
        flat_path = os.path.join(self.golden_repos_dir, "txt-db")
        versioned_dir = os.path.join(self.golden_repos_dir, ".versioned", "txt-db")
        versioned_path = os.path.join(versioned_dir, "v_1767053582")
        os.makedirs(versioned_path, exist_ok=True)

        # Initialize as git repo with remote
        import subprocess
        subprocess.run(["git", "init"], cwd=versioned_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/user/txt-db.git"],
            cwd=versioned_path,
            check=True,
            capture_output=True,
        )

        # Add golden repo with stale flat path
        golden_repo = GoldenRepo(
            alias="txt-db",
            repo_url="local://txt-db",
            default_branch="main",
            clone_path=flat_path,  # STALE - points to non-existent flat structure
            created_at="2025-01-01T00:00:00Z",
        )
        self.manager.golden_repos["txt-db"] = golden_repo
        self.manager._save_metadata()

        # Test canonical resolution
        actual_path = self.manager.get_actual_repo_path("txt-db")
        assert actual_path == versioned_path

        # Simulate migration code: get GitHub URL from CANONICAL path (not metadata path)
        # This should succeed because we're using the actual path, not the stale one
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=actual_path,  # Use canonical path, NOT golden_repo.clone_path
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert result.stdout.strip() == "https://github.com/user/txt-db.git"

    def test_migration_fails_with_stale_metadata_path(self):
        """
        Test that migration FAILS when using stale metadata path.

        This demonstrates the BUG that get_actual_repo_path() fixes.
        When using golden_repo.clone_path directly (metadata), git commands fail.
        """
        # Create versioned golden repo structure
        flat_path = os.path.join(self.golden_repos_dir, "txt-db")
        versioned_dir = os.path.join(self.golden_repos_dir, ".versioned", "txt-db")
        versioned_path = os.path.join(versioned_dir, "v_1767053582")
        os.makedirs(versioned_path, exist_ok=True)

        # Initialize as git repo
        import subprocess
        subprocess.run(["git", "init"], cwd=versioned_path, check=True, capture_output=True)

        # Add golden repo with stale flat path
        golden_repo = GoldenRepo(
            alias="txt-db",
            repo_url="local://txt-db",
            default_branch="main",
            clone_path=flat_path,  # STALE - points to non-existent flat structure
            created_at="2025-01-01T00:00:00Z",
        )
        self.manager.golden_repos["txt-db"] = golden_repo
        self.manager._save_metadata()

        # Demonstrate the bug: using metadata path directly FAILS
        # subprocess.run raises FileNotFoundError when cwd doesn't exist
        with pytest.raises(FileNotFoundError) as exc_info:
            subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=golden_repo.clone_path,  # BUG: Using stale metadata path
                capture_output=True,
                text=True,
            )

        # Error should indicate the missing directory
        error_msg = str(exc_info.value)
        assert flat_path in error_msg or "No such file or directory" in error_msg
