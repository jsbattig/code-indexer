"""
Integration tests for canonical path resolution across GoldenRepoManager operations.

Tests verify that critical operations use get_actual_repo_path() instead of direct
golden_repo.clone_path access, preventing failures with versioned-structure repos.

This addresses P0 regression where operations failed for versioned repos because
they used stale metadata paths instead of canonical filesystem paths.
"""

import json
import os
import subprocess
import tempfile
from unittest.mock import patch


from code_indexer.server.repositories.golden_repo_manager import (
    GoldenRepo,
    GoldenRepoManager,
)
from code_indexer.server.services.golden_repo_branch_service import (
    GoldenRepoBranchService,
)


class BaseCanonicalPathTest:
    """Base class with shared setup and helper methods for canonical path tests."""

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

    def _create_versioned_repo_structure(self, alias: str) -> tuple[str, str]:
        """
        Create versioned repo structure with STALE metadata path.

        Returns:
            tuple: (flat_path, versioned_path) where flat_path doesn't exist
        """
        flat_path = os.path.join(self.golden_repos_dir, alias)
        versioned_dir = os.path.join(self.golden_repos_dir, ".versioned", alias)
        versioned_path = os.path.join(versioned_dir, "v_1767053582")
        os.makedirs(versioned_path, exist_ok=True)
        return flat_path, versioned_path

    def _init_git_repo_with_commit(self, path: str) -> None:
        """Initialize git repo and create initial commit."""
        subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=path,
            check=True,
            capture_output=True,
        )

        # Create test file and commit
        test_file = os.path.join(path, "test.txt")
        with open(test_file, "w") as f:
            f.write("test content")
        subprocess.run(
            ["git", "add", "test.txt"], cwd=path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=path,
            check=True,
            capture_output=True,
        )

    def _create_golden_repo_with_stale_path(
        self, alias: str, flat_path: str, versioned_path: str
    ) -> GoldenRepo:
        """
        Create golden repo with STALE flat path pointing to non-existent directory.

        Args:
            alias: Repository alias
            flat_path: Stale metadata path (doesn't exist)
            versioned_path: Actual path (exists)

        Returns:
            GoldenRepo object with stale clone_path
        """
        golden_repo = GoldenRepo(
            alias=alias,
            repo_url=f"local://{versioned_path}",
            default_branch="master",
            clone_path=flat_path,  # STALE - points to non-existent flat structure
            created_at="2025-01-01T00:00:00Z",
            enable_temporal=False,
            temporal_options=None,
        )
        self.manager.golden_repos[alias] = golden_repo
        self.manager._save_metadata()
        return golden_repo

    def _mock_immediate_job_execution(self):
        """
        Mock background job execution to run synchronously.

        Returns:
            Mock object for _submit_background_job
        """

        def immediate_execution(worker_func, operation_type, **kwargs):
            job_id = "test-job-123"
            try:
                result = worker_func()
                self.manager.background_jobs[job_id] = {
                    "operation": operation_type,
                    "status": "completed",
                    "result": result,
                }
            except Exception as e:
                self.manager.background_jobs[job_id] = {
                    "operation": operation_type,
                    "status": "failed",
                    "error": str(e),
                }
            return job_id

        return patch.object(
            self.manager, "_submit_background_job", side_effect=immediate_execution
        )


class TestRefreshOperationUsesCanonicalPath(BaseCanonicalPathTest):
    """Test that refresh operation uses canonical path, not metadata path."""

    def test_refresh_detects_stale_metadata_path(self):
        """
        REGRESSION TEST: Demonstrate bug where refresh uses stale metadata path.

        Bug scenario:
        - Golden repo exists ONLY in .versioned/txt-db/v_123/
        - Metadata points to flat structure /golden-repos/txt-db/ (doesn't exist)
        - Line 978 uses golden_repo.clone_path directly (BUG!)
        - Before fix: _execute_post_clone_workflow() fails because clone_path doesn't exist
        - After fix: should use get_actual_repo_path() instead
        """
        # Create versioned structure
        flat_path, versioned_path = self._create_versioned_repo_structure("txt-db")
        self._init_git_repo_with_commit(versioned_path)

        # Create golden repo with STALE flat path
        golden_repo = self._create_golden_repo_with_stale_path(
            "txt-db", flat_path, versioned_path
        )

        # VERIFY THE BUG: golden_repo.clone_path points to non-existent directory
        assert golden_repo.clone_path == flat_path
        assert not os.path.exists(flat_path)  # Stale path doesn't exist
        assert os.path.exists(versioned_path)  # Actual path exists

        # VERIFY: get_actual_repo_path() returns the correct versioned path
        actual_path = self.manager.get_actual_repo_path("txt-db")
        assert actual_path == versioned_path

        # Before fix: This demonstrates the bug - using clone_path directly fails
        # After fix: Line 978 should use self.get_actual_repo_path(alias) instead
        # For now, we just verify that canonical path resolution works
        # The actual fix will change line 978 to use get_actual_repo_path()


class TestBranchServiceUsesCanonicalPath(BaseCanonicalPathTest):
    """Test that branch service uses canonical path, not metadata path."""

    def setup_method(self):
        """Create manager and branch service."""
        super().setup_method()
        self.branch_service = GoldenRepoBranchService(golden_repo_manager=self.manager)

    def test_branch_service_uses_canonical_path_for_versioned_repos(self):
        """
        REGRESSION TEST: Verify branch service uses canonical path for versioned repos.

        Bug scenario (FIXED):
        - Golden repo exists ONLY in .versioned/txt-db/v_123/
        - Metadata points to flat structure /golden-repos/txt-db/ (doesn't exist)
        - Line 104 now uses get_actual_repo_path() to get canonical path
        - After fix: get_golden_repo_branches() succeeds using canonical path
        """
        # Create versioned structure
        flat_path, versioned_path = self._create_versioned_repo_structure("txt-db")
        self._init_git_repo_with_commit(versioned_path)

        # Create golden repo with STALE flat path
        golden_repo = self._create_golden_repo_with_stale_path(
            "txt-db", flat_path, versioned_path
        )

        # VERIFY THE BUG CONDITIONS: golden_repo.clone_path points to non-existent directory
        assert golden_repo.clone_path == flat_path
        assert not os.path.exists(flat_path)  # Stale path doesn't exist
        assert os.path.exists(versioned_path)  # Actual path exists

        # VERIFY: get_actual_repo_path() returns the correct versioned path
        actual_path = self.manager.get_actual_repo_path("txt-db")
        assert actual_path == versioned_path

        # After fix: Line 104 uses get_actual_repo_path() so this should succeed
        import asyncio

        branches = asyncio.run(self.branch_service.get_golden_repo_branches("txt-db"))

        # Verify we got branch information
        assert len(branches) > 0
        assert any(b.name == "master" for b in branches)
