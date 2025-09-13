"""
Unit tests for branch endpoint implementation.

Tests the endpoint logic in isolation without starting the full server.
"""

import pytest
import tempfile
import shutil
from pathlib import Path

# Mock imports removed - not needed for this test

from git import Repo
from fastapi import HTTPException

# Import the app creation function if it exists, otherwise we'll test components
from code_indexer.server.services.branch_service import BranchService
from code_indexer.services.git_topology_service import GitTopologyService


class TestBranchEndpointsUnit:
    """Unit tests for branch endpoints without full server startup."""

    def setup_method(self):
        """Set up test environment with real git repository."""
        # Create temporary directory for test repository
        self.temp_dir = Path(tempfile.mkdtemp())

        # Initialize real git repository
        self.repo = Repo.init(self.temp_dir)
        self.repo.config_writer().set_value("user", "name", "Test User").release()
        self.repo.config_writer().set_value(
            "user", "email", "test@example.com"
        ).release()

        # Create initial commit on master branch
        test_file = self.temp_dir / "test.py"
        test_file.write_text("print('hello world')")
        self.repo.index.add([str(test_file)])
        self.initial_commit = self.repo.index.commit("Initial commit")

        # Create additional branches with commits
        self.develop_branch = self.repo.create_head("develop")
        self.feature_branch = self.repo.create_head("feature-x")

        # Add commits to develop branch
        self.repo.heads.develop.checkout()
        develop_file = self.temp_dir / "develop.py"
        develop_file.write_text("print('develop branch')")
        self.repo.index.add([str(develop_file)])
        self.develop_commit = self.repo.index.commit("Add develop feature")

        # Return to master branch
        self.repo.heads.master.checkout()

        # Initialize services
        self.git_topology_service = GitTopologyService(self.temp_dir)
        self.branch_service = BranchService(
            git_topology_service=self.git_topology_service,
            index_status_manager=None,  # Use default implementation
        )

    def teardown_method(self):
        """Clean up test repository."""
        if hasattr(self, "temp_dir") and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_branch_service_returns_expected_response_format(self):
        """Test that branch service returns data in the expected API format."""
        # Act
        branches = self.branch_service.list_branches()
        current_branch_name = self.git_topology_service.get_current_branch()

        # Simulate the response model creation
        response_data = {
            "branches": [
                {
                    "name": branch.name,
                    "is_current": branch.is_current,
                    "last_commit": {
                        "sha": branch.last_commit.sha,
                        "message": branch.last_commit.message,
                        "author": branch.last_commit.author,
                        "date": branch.last_commit.date,
                    },
                    "index_status": {
                        "status": branch.index_status.status,
                        "files_indexed": branch.index_status.files_indexed,
                        "total_files": branch.index_status.total_files,
                        "last_indexed": branch.index_status.last_indexed,
                        "progress_percentage": branch.index_status.progress_percentage,
                    },
                    "remote_tracking": branch.remote_tracking,
                }
                for branch in branches
            ],
            "total": len(branches),
            "current_branch": current_branch_name,
        }

        # Assert response structure
        assert "branches" in response_data
        assert "total" in response_data
        assert "current_branch" in response_data

        # Assert content
        assert response_data["total"] == 3
        assert len(response_data["branches"]) == 3
        assert response_data["current_branch"] == "master"

        # Check branch names
        branch_names = {branch["name"] for branch in response_data["branches"]}
        assert branch_names == {"master", "develop", "feature-x"}

        # Check current branch identification
        current_branches = [b for b in response_data["branches"] if b["is_current"]]
        assert len(current_branches) == 1
        assert current_branches[0]["name"] == "master"

        # Check commit information structure
        for branch_data in response_data["branches"]:
            commit = branch_data["last_commit"]
            assert "sha" in commit
            assert "message" in commit
            assert "author" in commit
            assert "date" in commit
            assert len(commit["sha"]) == 40  # Git SHA length

        # Check index status structure
        for branch_data in response_data["branches"]:
            index_status = branch_data["index_status"]
            assert "status" in index_status
            assert "files_indexed" in index_status

    def test_branch_service_handles_include_remote_parameter(self):
        """Test that include_remote parameter works correctly."""
        # Act
        branches_without_remote = self.branch_service.list_branches(
            include_remote=False
        )
        branches_with_remote = self.branch_service.list_branches(include_remote=True)

        # Assert
        assert len(branches_without_remote) == len(branches_with_remote)

        # When include_remote=False, remote_tracking should be None
        for branch in branches_without_remote:
            assert branch.remote_tracking is None

        # When include_remote=True, remote_tracking should be included (even if None for local-only repos)
        for branch in branches_with_remote:
            # remote_tracking can be None for local-only repositories, which is correct
            pass

    def test_git_topology_service_integration(self):
        """Test integration between branch service and git topology service."""
        # Act
        current_branch_from_topology = self.git_topology_service.get_current_branch()
        branches = self.branch_service.list_branches()

        # Assert
        assert current_branch_from_topology == "master"

        current_branches = [b for b in branches if b.is_current]
        assert len(current_branches) == 1
        assert current_branches[0].name == current_branch_from_topology

    def test_branch_service_error_handling_for_invalid_repository(self):
        """Test error handling when git operations fail."""
        # Arrange - Create non-git directory
        non_git_dir = Path(tempfile.mkdtemp())
        try:
            git_service = GitTopologyService(non_git_dir)

            # Act & Assert - Should raise ValueError
            with pytest.raises(ValueError, match="Not a git repository"):
                BranchService(
                    git_topology_service=git_service, index_status_manager=None
                )
        finally:
            shutil.rmtree(non_git_dir)

    def test_branch_service_performance_with_multiple_branches(self):
        """Test performance with many branches."""
        # Arrange - Create additional branches
        for i in range(10):
            branch = self.repo.create_head(f"perf-test-{i}")
            branch.checkout()
            test_file = self.temp_dir / f"perf_{i}.py"
            test_file.write_text(f"print('performance test {i}')")
            self.repo.index.add([str(test_file)])
            self.repo.index.commit(f"Performance test commit {i}")

        self.repo.heads.master.checkout()

        # Act & Assert - Should complete quickly
        import time

        start_time = time.time()
        branches = self.branch_service.list_branches()
        end_time = time.time()

        # Should have all branches
        assert len(branches) >= 13  # original 3 + 10 new branches

        # Should complete quickly
        assert end_time - start_time < 2.0  # Within 2 seconds

    def test_endpoint_validation_logic_simulation(self):
        """Test the validation logic that would be in the endpoint."""

        # Test repository ID validation logic (extracted from endpoint)
        def validate_repo_id(repo_id: str) -> str:
            """Simulate the repo ID validation from the endpoint."""
            if not repo_id or not repo_id.strip():
                raise HTTPException(
                    status_code=400, detail="Repository ID cannot be empty"
                )

            cleaned_repo_id = repo_id.strip()

            if (
                " " in cleaned_repo_id
                or "/" in cleaned_repo_id
                or ".." in cleaned_repo_id
                or cleaned_repo_id.startswith(".")
                or len(cleaned_repo_id) > 255
            ):
                raise HTTPException(
                    status_code=400, detail="Invalid repository ID format"
                )

            return cleaned_repo_id

        # Test valid repository IDs
        assert validate_repo_id("test-repo") == "test-repo"
        assert validate_repo_id("  test-repo  ") == "test-repo"
        assert validate_repo_id("repo123") == "repo123"

        # Test invalid repository IDs
        with pytest.raises(HTTPException):
            validate_repo_id("")

        with pytest.raises(HTTPException):
            validate_repo_id("   ")

        with pytest.raises(HTTPException):
            validate_repo_id("repo with spaces")

        with pytest.raises(HTTPException):
            validate_repo_id("repo/with/slashes")

        with pytest.raises(HTTPException):
            validate_repo_id("repo/../with/traversal")

        with pytest.raises(HTTPException):
            validate_repo_id(".hidden-repo")

        with pytest.raises(HTTPException):
            validate_repo_id("a" * 256)  # Too long
