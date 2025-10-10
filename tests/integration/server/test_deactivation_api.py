"""
Integration tests for repository deactivation.

Tests complete deactivation workflow for both single and composite repositories,
including cleanup verification and error handling. Tests use direct manager calls
rather than API layer to focus on deactivation logic.
"""

import json
import shutil
import tempfile
import time
from pathlib import Path

import pytest

from code_indexer.server.repositories.activated_repo_manager import (
    ActivatedRepoManager,
    ActivatedRepoError,
)


class TestDeactivationIntegration:
    """Integration tests for repository deactivation workflow."""

    def wait_for_job(self, manager, job_id, username, timeout=30):
        """Helper method to wait for background job completion."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            job_status = manager.background_job_manager.get_job_status(job_id, username)
            if job_status and job_status["status"] in ["completed", "failed"]:
                return job_status
            time.sleep(0.1)

        raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds")

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def manager(self, temp_data_dir):
        """Create ActivatedRepoManager instance."""
        return ActivatedRepoManager(data_dir=temp_data_dir)

    @pytest.fixture
    def composite_repo(self, temp_data_dir):
        """Create composite repository structure for testing."""
        user_dir = Path(temp_data_dir) / "activated-repos" / "testuser"
        user_dir.mkdir(parents=True, exist_ok=True)

        composite_path = user_dir / "composite_test"
        composite_path.mkdir(parents=True, exist_ok=True)

        # Create .code-indexer directory with proxy config
        config_dir = composite_path / ".code-indexer"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_file = config_dir / "config.json"
        config_data = {
            "proxy_mode": True,
            "discovered_repos": ["repo_a", "repo_b", "repo_c"],
            "embedding_provider": "voyage-ai",
        }
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        # Create component repositories
        for repo_name in ["repo_a", "repo_b", "repo_c"]:
            repo_path = composite_path / repo_name
            repo_path.mkdir(parents=True, exist_ok=True)
            (repo_path / ".code-indexer").mkdir(parents=True, exist_ok=True)
            # Add some files to make it more realistic
            (repo_path / "README.md").write_text(f"# {repo_name}")

        # Create metadata file
        metadata_file = user_dir / "composite_test_metadata.json"
        metadata = {
            "user_alias": "composite_test",
            "username": "testuser",
            "path": str(composite_path),
            "is_composite": True,
            "golden_repo_aliases": ["golden_a", "golden_b", "golden_c"],
            "discovered_repos": ["repo_a", "repo_b", "repo_c"],
            "activated_at": "2024-01-01T00:00:00Z",
            "last_accessed": "2024-01-01T00:00:00Z",
        }
        with open(metadata_file, "w") as f:
            json.dump(metadata, f)

        return {
            "composite_path": composite_path,
            "metadata_file": metadata_file,
            "config_dir": config_dir,
            "component_paths": [
                composite_path / "repo_a",
                composite_path / "repo_b",
                composite_path / "repo_c",
            ],
        }

    @pytest.fixture
    def single_repo(self, temp_data_dir):
        """Create single repository structure for testing."""
        user_dir = Path(temp_data_dir) / "activated-repos" / "testuser"
        user_dir.mkdir(parents=True, exist_ok=True)

        repo_path = user_dir / "single_test"
        repo_path.mkdir(parents=True, exist_ok=True)

        # Add some files
        (repo_path / "README.md").write_text("# Single Repo")

        # Create metadata file
        metadata_file = user_dir / "single_test_metadata.json"
        metadata = {
            "user_alias": "single_test",
            "golden_repo_alias": "golden_single",
            "current_branch": "main",
            "activated_at": "2024-01-01T00:00:00Z",
            "last_accessed": "2024-01-01T00:00:00Z",
        }
        with open(metadata_file, "w") as f:
            json.dump(metadata, f)

        return {
            "repo_path": repo_path,
            "metadata_file": metadata_file,
        }

    def test_deactivate_composite_repository_complete_cleanup(
        self, manager, composite_repo
    ):
        """Test composite repository deactivation removes all resources."""
        composite_path = composite_repo["composite_path"]
        metadata_file = composite_repo["metadata_file"]
        component_paths = composite_repo["component_paths"]

        # Verify everything exists before deactivation
        assert composite_path.exists()
        assert metadata_file.exists()
        for component_path in component_paths:
            assert component_path.exists()
            assert (component_path / "README.md").exists()

        # Submit deactivation job
        job_id = manager.deactivate_repository("testuser", "composite_test")

        # Wait for job to complete
        job_status = self.wait_for_job(manager, job_id, "testuser", timeout=30)

        # Verify job succeeded
        assert job_status["status"] == "completed"
        assert job_status["result"]["success"] is True
        assert job_status["result"]["is_composite"] is True

        # Verify complete cleanup
        assert not composite_path.exists()
        assert not metadata_file.exists()

        # Verify all components removed
        for component_path in component_paths:
            assert not component_path.exists()

    def test_deactivate_single_repository_complete_cleanup(self, manager, single_repo):
        """Test single repository deactivation removes all resources."""
        repo_path = single_repo["repo_path"]
        metadata_file = single_repo["metadata_file"]

        # Verify exists before deactivation
        assert repo_path.exists()
        assert metadata_file.exists()

        # Submit deactivation job
        job_id = manager.deactivate_repository("testuser", "single_test")

        # Wait for job to complete
        job_status = self.wait_for_job(manager, job_id, "testuser", timeout=30)

        # Verify job succeeded
        assert job_status["status"] == "completed"
        assert job_status["result"]["success"] is True

        # Verify complete cleanup
        assert not repo_path.exists()
        assert not metadata_file.exists()

    def test_deactivate_nonexistent_repository_raises_error(self, manager):
        """Test deactivating nonexistent repository raises error."""
        with pytest.raises(ActivatedRepoError) as exc_info:
            manager.deactivate_repository("testuser", "nonexistent")

        assert "not found" in str(exc_info.value).lower()

    def test_deactivate_composite_with_partial_cleanup(self, manager, composite_repo):
        """Test deactivation succeeds even if some components already removed."""
        # Manually remove one component before deactivation
        component_to_remove = composite_repo["component_paths"][0]
        shutil.rmtree(component_to_remove, ignore_errors=True)

        # Verify component removed
        assert not component_to_remove.exists()

        # Deactivation should still succeed
        job_id = manager.deactivate_repository("testuser", "composite_test")

        # Wait for job to complete
        job_status = self.wait_for_job(manager, job_id, "testuser", timeout=30)

        # Verify complete cleanup
        assert job_status["status"] == "completed"
        assert job_status["result"]["success"] is True

        # Verify all remaining components removed
        composite_path = composite_repo["composite_path"]
        assert not composite_path.exists()

    def test_deactivate_is_idempotent(self, manager, composite_repo):
        """Test that deactivating already-deactivated repo raises error."""
        # First deactivation
        job_id = manager.deactivate_repository("testuser", "composite_test")
        job_status = self.wait_for_job(manager, job_id, "testuser", timeout=30)
        assert job_status["status"] == "completed"

        # Second deactivation should raise error (not found)
        with pytest.raises(ActivatedRepoError) as exc_info:
            manager.deactivate_repository("testuser", "composite_test")

        assert "not found" in str(exc_info.value).lower()
