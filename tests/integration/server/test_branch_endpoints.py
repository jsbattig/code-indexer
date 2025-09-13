"""
Integration tests for branch listing API endpoints.

Tests the complete API endpoint functionality including authentication,
authorization, and real git repository operations.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from git import Repo
from code_indexer.server.app import create_app
from code_indexer.server.auth.user_manager import User


class TestBranchEndpoints:
    """Integration tests for branch listing endpoints."""

    def setup_method(self):
        """Set up test environment with real git repository and test client."""
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

        # Add commits to feature branch
        self.repo.heads["feature-x"].checkout()
        feature_file = self.temp_dir / "feature.py"
        feature_file.write_text("print('feature branch')")
        self.repo.index.add([str(feature_file)])
        self.feature_commit = self.repo.index.commit("Add feature implementation")

        # Return to master branch
        self.repo.heads.master.checkout()

        # Create FastAPI test client
        # For now, we'll test without full server initialization
        # This will be updated when we integrate with the main app
        self.test_repo_id = "test-repo-123"

        # Create test user and authentication
        self.test_user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="hashed",
            is_active=True,
        )

    def teardown_method(self):
        """Clean up test repository."""
        if hasattr(self, "temp_dir") and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    @pytest.mark.skip(
        reason="Endpoint not yet implemented - this test should fail initially"
    )
    def test_list_branches_endpoint_returns_all_branches(self):
        """Test GET /api/repositories/{repo_id}/branches returns all branches."""
        # This test will be updated once we have the actual endpoint
        # For now, we expect it to fail

        # Arrange - Mock authentication and repository access
        with patch(
            "code_indexer.server.auth.dependencies.get_current_user"
        ) as mock_get_user:
            mock_get_user.return_value = self.test_user

            # Create test client (this will need to be updated)
            client = TestClient(create_app())

            # Act
            response = client.get(
                f"/api/repositories/{self.test_repo_id}/branches",
                headers={"Authorization": "Bearer fake-token"},
            )

            # Assert
            assert response.status_code == 200
            data = response.json()

            assert "branches" in data
            assert "total" in data
            assert "current_branch" in data

            # Should return 3 branches
            assert data["total"] == 3
            assert len(data["branches"]) == 3

            # Check branch names
            branch_names = {branch["name"] for branch in data["branches"]}
            assert branch_names == {"master", "develop", "feature-x"}

            # Check current branch identification
            current_branches = [
                branch for branch in data["branches"] if branch["is_current"]
            ]
            assert len(current_branches) == 1
            assert current_branches[0]["name"] == "master"

            # Check commit information
            master_branch = next(
                branch for branch in data["branches"] if branch["name"] == "master"
            )
            assert master_branch["last_commit"]["sha"] == self.initial_commit.hexsha
            assert master_branch["last_commit"]["message"] == "Initial commit"
            assert master_branch["last_commit"]["author"] == "Test User"

    @pytest.mark.skip(reason="Endpoint not yet implemented")
    def test_list_branches_endpoint_requires_authentication(self):
        """Test that endpoint requires valid authentication."""
        # Create test client
        client = TestClient(create_app())

        # Act - Request without authentication
        response = client.get(f"/api/repositories/{self.test_repo_id}/branches")

        # Assert
        assert response.status_code == 401

    @pytest.mark.skip(reason="Endpoint not yet implemented")
    def test_list_branches_endpoint_validates_repository_access(self):
        """Test that endpoint validates user has access to repository."""
        with patch(
            "code_indexer.server.auth.dependencies.get_current_user"
        ) as mock_get_user:
            mock_get_user.return_value = self.test_user

            client = TestClient(create_app())

            # Act - Request for non-existent repository
            response = client.get(
                "/api/repositories/nonexistent-repo/branches",
                headers={"Authorization": "Bearer fake-token"},
            )

            # Assert
            assert response.status_code == 404

    @pytest.mark.skip(reason="Endpoint not yet implemented")
    def test_list_branches_endpoint_with_remote_parameter(self):
        """Test endpoint with include_remote query parameter."""
        with patch(
            "code_indexer.server.auth.dependencies.get_current_user"
        ) as mock_get_user:
            mock_get_user.return_value = self.test_user

            client = TestClient(create_app())

            # Act
            response = client.get(
                f"/api/repositories/{self.test_repo_id}/branches?include_remote=true",
                headers={"Authorization": "Bearer fake-token"},
            )

            # Assert
            assert response.status_code == 200
            data = response.json()

            # Remote tracking info should be included
            for branch in data["branches"]:
                assert "remote_tracking" in branch

    @pytest.mark.skip(reason="Endpoint not yet implemented")
    def test_list_branches_endpoint_handles_git_errors(self):
        """Test endpoint error handling for git operation failures."""
        # This will test scenarios like corrupted repositories, git command failures, etc.
        pass

    @pytest.mark.skip(reason="Endpoint not yet implemented")
    def test_list_branches_endpoint_performance_with_many_branches(self):
        """Test endpoint performance with repositories containing many branches."""
        # Create many branches for performance testing
        for i in range(20):
            branch = self.repo.create_head(f"test-branch-{i}")
            branch.checkout()
            test_file = self.temp_dir / f"test_{i}.py"
            test_file.write_text(f"print('test {i}')")
            self.repo.index.add([str(test_file)])
            self.repo.index.commit(f"Test commit {i}")

        self.repo.heads.master.checkout()

        with patch(
            "code_indexer.server.auth.dependencies.get_current_user"
        ) as mock_get_user:
            mock_get_user.return_value = self.test_user

            client = TestClient(create_app())

            # Act & Assert - Should complete within reasonable time
            import time

            start_time = time.time()

            response = client.get(
                f"/api/repositories/{self.test_repo_id}/branches",
                headers={"Authorization": "Bearer fake-token"},
            )

            end_time = time.time()

            assert response.status_code == 200
            assert end_time - start_time < 2.0  # Should complete within 2 seconds

            data = response.json()
            assert data["total"] >= 20  # Should include all created branches
