"""
E2E tests for Story 6: Repository Activation System.

Tests the complete flow of repository activation through the API endpoints:
- Activating repositories for users (power users and admins)
- Listing activated repositories
- Deactivating repositories
- Branch switching
- Authentication and authorization
- Background job integration
- Copy-on-write cloning
"""

import tempfile
import subprocess
import os
import time
import json

import pytest
from fastapi.testclient import TestClient

from src.code_indexer.server.app import create_app
from src.code_indexer.server.repositories.golden_repo_manager import GoldenRepoManager
from src.code_indexer.server.repositories.activated_repo_manager import (
    ActivatedRepoManager,
)


class TestRepoActivationE2E:
    """E2E tests for repository activation functionality."""

    @pytest.fixture(scope="class")
    def app(self):
        """Create FastAPI app for testing."""
        return create_app()

    @pytest.fixture(scope="class")
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture(scope="class")
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture(scope="class")
    def test_repo_path(self, temp_data_dir):
        """Create a real test git repository for E2E testing."""
        repo_path = os.path.join(temp_data_dir, "test_repo")

        # Create a real git repository with content
        os.makedirs(repo_path)
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )

        # Add some test files
        with open(os.path.join(repo_path, "README.md"), "w") as f:
            f.write("# Test Repository\n\nThis is a test repository for E2E testing.\n")

        with open(os.path.join(repo_path, "main.py"), "w") as f:
            f.write(
                "#!/usr/bin/env python3\n\ndef main():\n    print('Hello, World!')\n\nif __name__ == '__main__':\n    main()\n"
            )

        # Add and commit files
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True
        )

        # Create a feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature-branch"], cwd=repo_path, check=True
        )
        with open(os.path.join(repo_path, "feature.py"), "w") as f:
            f.write("# Feature implementation\nprint('Feature code')\n")
        subprocess.run(["git", "add", "feature.py"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add feature"], cwd=repo_path, check=True
        )

        # Switch back to master
        subprocess.run(["git", "checkout", "master"], cwd=repo_path, check=True)

        return repo_path

    @pytest.fixture(scope="class")
    def golden_repo_manager(self, temp_data_dir):
        """Create golden repository manager with temporary data directory."""
        return GoldenRepoManager(data_dir=temp_data_dir)

    @pytest.fixture(scope="class")
    def activated_repo_manager(self, temp_data_dir, golden_repo_manager):
        """Create activated repository manager with temporary data directory."""
        return ActivatedRepoManager(
            data_dir=temp_data_dir, golden_repo_manager=golden_repo_manager
        )

    @pytest.fixture(scope="class")
    def admin_token(self, client):
        """Get admin authentication token."""
        # Login with default admin credentials
        login_data = {"username": "admin", "password": "admin"}
        response = client.post("/auth/login", json=login_data)
        assert response.status_code == 200

        data = response.json()
        return data["access_token"]

    @pytest.fixture(scope="class")
    def power_user_token(self, client, admin_token):
        """Create and get power user authentication token."""
        # Create power user
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        user_data = {
            "username": "poweruser",
            "password": "password123!",
            "role": "power_user",
        }

        response = client.post(
            "/api/admin/users", json=user_data, headers=admin_headers
        )
        assert response.status_code == 201

        # Login as power user
        login_data = {"username": "poweruser", "password": "password123!"}
        response = client.post("/auth/login", json=login_data)
        assert response.status_code == 200

        data = response.json()
        return data["access_token"]

    @pytest.fixture(scope="class")
    def normal_user_token(self, client, admin_token):
        """Create and get normal user authentication token."""
        # Create normal user
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        user_data = {
            "username": "normaluser",
            "password": "password123!",
            "role": "normal_user",
        }

        response = client.post(
            "/api/admin/users", json=user_data, headers=admin_headers
        )
        assert response.status_code == 201

        # Login as normal user
        login_data = {"username": "normaluser", "password": "password123!"}
        response = client.post("/auth/login", json=login_data)
        assert response.status_code == 200

        data = response.json()
        return data["access_token"]

    @pytest.fixture
    def admin_headers(self, admin_token):
        """Get authentication headers for admin."""
        return {"Authorization": f"Bearer {admin_token}"}

    @pytest.fixture
    def power_user_headers(self, power_user_token):
        """Get authentication headers for power user."""
        return {"Authorization": f"Bearer {power_user_token}"}

    @pytest.fixture
    def normal_user_headers(self, normal_user_token):
        """Get authentication headers for normal user."""
        return {"Authorization": f"Bearer {normal_user_token}"}

    @pytest.fixture
    def golden_repo_setup(
        self, client, admin_headers, test_repo_path, golden_repo_manager, monkeypatch
    ):
        """Setup a golden repository for testing."""
        # Use real golden repo manager with test setup
        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", golden_repo_manager
        )

        repo_data = {
            "repo_url": test_repo_path,
            "alias": "test-repo",
            "default_branch": "master",
        }

        # Add golden repository
        response = client.post(
            "/api/admin/golden-repos", json=repo_data, headers=admin_headers
        )
        assert response.status_code == 202

        # Wait for background job to complete
        data = response.json()
        job_id = data["job_id"]
        self._wait_for_job_completion(client, job_id, admin_headers)

        return "test-repo"

    def _wait_for_job_completion(self, client, job_id, headers, max_wait=60):
        """Wait for a background job to complete."""
        elapsed_time = 0
        wait_interval = 2

        while elapsed_time < max_wait:
            job_response = client.get(f"/api/jobs/{job_id}", headers=headers)
            assert job_response.status_code == 200
            job_data = job_response.json()

            if job_data["status"] == "completed":
                return job_data
            elif job_data["status"] == "failed":
                pytest.fail(
                    f"Background job failed: {job_data.get('error', 'Unknown error')}"
                )

            time.sleep(wait_interval)
            elapsed_time += wait_interval

        pytest.fail(
            f"Background job {job_id} did not complete within {max_wait} seconds"
        )

    def test_health_check(self, client):
        """Test that the server is running."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_list_activated_repos_empty(self, client, power_user_headers):
        """Test listing activated repositories when none exist."""
        response = client.get("/api/repos", headers=power_user_headers)
        assert response.status_code == 200

        data = response.json()
        assert data == []

    def test_activate_repo_requires_power_user(
        self, client, normal_user_headers, golden_repo_setup
    ):
        """Test that repository activation requires power user or admin role."""
        # Normal users should not be able to activate repositories
        activation_data = {"golden_repo_alias": golden_repo_setup}

        response = client.post(
            "/api/repos/activate", json=activation_data, headers=normal_user_headers
        )
        assert response.status_code == 403

    def test_activate_repository_success_power_user(
        self,
        client,
        power_user_headers,
        golden_repo_setup,
        activated_repo_manager,
        monkeypatch,
    ):
        """Test successful repository activation by power user."""
        # Use real activated repo manager with test setup
        monkeypatch.setattr(
            "src.code_indexer.server.app.activated_repo_manager", activated_repo_manager
        )

        activation_data = {
            "golden_repo_alias": golden_repo_setup,
            "user_alias": "my-test-repo",
        }

        response = client.post(
            "/api/repos/activate", json=activation_data, headers=power_user_headers
        )

        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert "my-test-repo" in data["message"]
        assert "poweruser" in data["message"]
        assert "activation started" in data["message"]

        # Wait for background job to complete
        job_id = data["job_id"]
        self._wait_for_job_completion(client, job_id, power_user_headers)

        # Verify repository was actually activated
        user_repos_dir = os.path.join(
            activated_repo_manager.activated_repos_dir, "poweruser"
        )
        repo_dir = os.path.join(user_repos_dir, "my-test-repo")
        metadata_file = os.path.join(user_repos_dir, "my-test-repo_metadata.json")

        assert os.path.exists(repo_dir)
        assert os.path.exists(metadata_file)
        assert os.path.exists(os.path.join(repo_dir, "README.md"))
        assert os.path.exists(os.path.join(repo_dir, "main.py"))

        # Verify metadata
        with open(metadata_file, "r") as f:
            metadata = json.load(f)
        assert metadata["user_alias"] == "my-test-repo"
        assert metadata["golden_repo_alias"] == golden_repo_setup
        assert metadata["current_branch"] == "master"

    def test_activate_repository_success_admin(
        self,
        client,
        admin_headers,
        golden_repo_setup,
        activated_repo_manager,
        monkeypatch,
    ):
        """Test successful repository activation by admin."""
        # Use real activated repo manager with test setup
        monkeypatch.setattr(
            "src.code_indexer.server.app.activated_repo_manager", activated_repo_manager
        )

        activation_data = {
            "golden_repo_alias": golden_repo_setup,
            "branch_name": "master",
        }

        response = client.post(
            "/api/repos/activate", json=activation_data, headers=admin_headers
        )

        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert (
            golden_repo_setup in data["message"]
        )  # Uses golden_repo_alias as user_alias by default
        assert "admin" in data["message"]
        assert "activation started" in data["message"]

        # Wait for background job to complete
        job_id = data["job_id"]
        self._wait_for_job_completion(client, job_id, admin_headers)

    def test_activate_repository_nonexistent_golden_repo(
        self, client, power_user_headers
    ):
        """Test activation fails when golden repository doesn't exist."""
        activation_data = {"golden_repo_alias": "nonexistent-repo"}

        response = client.post(
            "/api/repos/activate", json=activation_data, headers=power_user_headers
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_activate_repository_already_activated(
        self,
        client,
        power_user_headers,
        golden_repo_setup,
        activated_repo_manager,
        monkeypatch,
    ):
        """Test activation fails when repository already activated."""
        # Use real activated repo manager with test setup
        monkeypatch.setattr(
            "src.code_indexer.server.app.activated_repo_manager", activated_repo_manager
        )

        activation_data = {
            "golden_repo_alias": golden_repo_setup,
            "user_alias": "duplicate-repo",
        }

        # First activation
        response1 = client.post(
            "/api/repos/activate", json=activation_data, headers=power_user_headers
        )
        assert response1.status_code == 202

        job_id1 = response1.json()["job_id"]
        self._wait_for_job_completion(client, job_id1, power_user_headers)

        # Second activation should fail
        response2 = client.post(
            "/api/repos/activate", json=activation_data, headers=power_user_headers
        )
        assert response2.status_code == 400
        assert "already activated" in response2.json()["detail"]

    def test_list_activated_repositories_with_data(
        self,
        client,
        power_user_headers,
        golden_repo_setup,
        activated_repo_manager,
        monkeypatch,
    ):
        """Test listing activated repositories with existing data."""
        # Use real activated repo manager with test setup
        monkeypatch.setattr(
            "src.code_indexer.server.app.activated_repo_manager", activated_repo_manager
        )

        # Activate a repository first
        activation_data = {
            "golden_repo_alias": golden_repo_setup,
            "user_alias": "list-test-repo",
        }

        response = client.post(
            "/api/repos/activate", json=activation_data, headers=power_user_headers
        )
        assert response.status_code == 202

        job_id = response.json()["job_id"]
        self._wait_for_job_completion(client, job_id, power_user_headers)

        # List repositories
        response = client.get("/api/repos", headers=power_user_headers)
        assert response.status_code == 200

        data = response.json()
        assert len(data) >= 1

        # Find our repository
        our_repo = None
        for repo in data:
            if repo["user_alias"] == "list-test-repo":
                our_repo = repo
                break

        assert our_repo is not None
        assert our_repo["golden_repo_alias"] == golden_repo_setup
        assert our_repo["current_branch"] == "master"
        assert "activated_at" in our_repo
        assert "last_accessed" in our_repo

    def test_deactivate_repository_success(
        self,
        client,
        power_user_headers,
        golden_repo_setup,
        activated_repo_manager,
        monkeypatch,
    ):
        """Test successful repository deactivation."""
        # Use real activated repo manager with test setup
        monkeypatch.setattr(
            "src.code_indexer.server.app.activated_repo_manager", activated_repo_manager
        )

        # Activate a repository first
        activation_data = {
            "golden_repo_alias": golden_repo_setup,
            "user_alias": "deactivate-test-repo",
        }

        response = client.post(
            "/api/repos/activate", json=activation_data, headers=power_user_headers
        )
        assert response.status_code == 202

        job_id = response.json()["job_id"]
        self._wait_for_job_completion(client, job_id, power_user_headers)

        # Verify repository exists
        user_repos_dir = os.path.join(
            activated_repo_manager.activated_repos_dir, "poweruser"
        )
        repo_dir = os.path.join(user_repos_dir, "deactivate-test-repo")
        assert os.path.exists(repo_dir)

        # Deactivate repository
        response = client.delete(
            "/api/repos/deactivate-test-repo", headers=power_user_headers
        )
        assert response.status_code == 202

        data = response.json()
        assert "job_id" in data
        assert "deactivate-test-repo" in data["message"]
        assert "deactivation started" in data["message"]

        # Wait for background job to complete
        job_id = data["job_id"]
        self._wait_for_job_completion(client, job_id, power_user_headers)

        # Verify repository was removed
        assert not os.path.exists(repo_dir)

    def test_deactivate_repository_not_found(self, client, power_user_headers):
        """Test deactivation fails when repository not found."""
        response = client.delete(
            "/api/repos/nonexistent-repo", headers=power_user_headers
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_switch_branch_success(
        self,
        client,
        power_user_headers,
        golden_repo_setup,
        activated_repo_manager,
        monkeypatch,
    ):
        """Test successful branch switching."""
        # Use real activated repo manager with test setup
        monkeypatch.setattr(
            "src.code_indexer.server.app.activated_repo_manager", activated_repo_manager
        )

        # Activate a repository first
        activation_data = {
            "golden_repo_alias": golden_repo_setup,
            "user_alias": "branch-test-repo",
        }

        response = client.post(
            "/api/repos/activate", json=activation_data, headers=power_user_headers
        )
        assert response.status_code == 202

        job_id = response.json()["job_id"]
        self._wait_for_job_completion(client, job_id, power_user_headers)

        # Switch to feature branch
        branch_data = {"branch_name": "feature-branch"}
        response = client.put(
            "/api/repos/branch-test-repo/branch",
            json=branch_data,
            headers=power_user_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "feature-branch" in data["message"]
        assert "branch-test-repo" in data["message"]

        # Verify branch was actually switched
        user_repos_dir = os.path.join(
            activated_repo_manager.activated_repos_dir, "poweruser"
        )
        metadata_file = os.path.join(user_repos_dir, "branch-test-repo_metadata.json")

        with open(metadata_file, "r") as f:
            metadata = json.load(f)
        assert metadata["current_branch"] == "feature-branch"

    def test_switch_branch_repository_not_found(self, client, power_user_headers):
        """Test branch switching fails when repository not found."""
        branch_data = {"branch_name": "feature-branch"}
        response = client.put(
            "/api/repos/nonexistent-repo/branch",
            json=branch_data,
            headers=power_user_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_switch_branch_invalid_branch(
        self,
        client,
        power_user_headers,
        golden_repo_setup,
        activated_repo_manager,
        monkeypatch,
    ):
        """Test branch switching fails with invalid branch name."""
        # Use real activated repo manager with test setup
        monkeypatch.setattr(
            "src.code_indexer.server.app.activated_repo_manager", activated_repo_manager
        )

        # Activate a repository first
        activation_data = {
            "golden_repo_alias": golden_repo_setup,
            "user_alias": "invalid-branch-test-repo",
        }

        response = client.post(
            "/api/repos/activate", json=activation_data, headers=power_user_headers
        )
        assert response.status_code == 202

        job_id = response.json()["job_id"]
        self._wait_for_job_completion(client, job_id, power_user_headers)

        # Try to switch to nonexistent branch
        branch_data = {"branch_name": "nonexistent-branch"}
        response = client.put(
            "/api/repos/invalid-branch-test-repo/branch",
            json=branch_data,
            headers=power_user_headers,
        )

        assert response.status_code == 400
        assert "Failed to switch branch" in response.json()["detail"]

    def test_user_isolation(
        self,
        client,
        power_user_headers,
        admin_headers,
        golden_repo_setup,
        activated_repo_manager,
        monkeypatch,
    ):
        """Test that users can only see their own activated repositories."""
        # Use real activated repo manager with test setup
        monkeypatch.setattr(
            "src.code_indexer.server.app.activated_repo_manager", activated_repo_manager
        )

        # Power user activates a repository
        power_user_data = {
            "golden_repo_alias": golden_repo_setup,
            "user_alias": "power-user-repo",
        }
        response = client.post(
            "/api/repos/activate", json=power_user_data, headers=power_user_headers
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        self._wait_for_job_completion(client, job_id, power_user_headers)

        # Admin activates a repository
        admin_data = {
            "golden_repo_alias": golden_repo_setup,
            "user_alias": "admin-repo",
        }
        response = client.post(
            "/api/repos/activate", json=admin_data, headers=admin_headers
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        self._wait_for_job_completion(client, job_id, admin_headers)

        # Power user should only see their own repository
        response = client.get("/api/repos", headers=power_user_headers)
        assert response.status_code == 200
        power_user_repos = response.json()
        assert len(power_user_repos) == 1
        assert power_user_repos[0]["user_alias"] == "power-user-repo"

        # Admin should only see their own repository
        response = client.get("/api/repos", headers=admin_headers)
        assert response.status_code == 200
        admin_repos = response.json()
        assert len(admin_repos) == 1
        assert admin_repos[0]["user_alias"] == "admin-repo"

    def test_activation_request_validation(self, client, power_user_headers):
        """Test validation of activation request data."""
        # Test empty golden_repo_alias
        response = client.post(
            "/api/repos/activate",
            json={"golden_repo_alias": ""},
            headers=power_user_headers,
        )
        assert response.status_code == 422

        # Test whitespace-only golden_repo_alias
        response = client.post(
            "/api/repos/activate",
            json={"golden_repo_alias": "   "},
            headers=power_user_headers,
        )
        assert response.status_code == 422

        # Test empty user_alias
        response = client.post(
            "/api/repos/activate",
            json={"golden_repo_alias": "test", "user_alias": ""},
            headers=power_user_headers,
        )
        assert response.status_code == 422

    def test_branch_switch_request_validation(self, client, power_user_headers):
        """Test validation of branch switch request data."""
        # Test empty branch_name
        response = client.put(
            "/api/repos/test-repo/branch",
            json={"branch_name": ""},
            headers=power_user_headers,
        )
        assert response.status_code == 422

        # Test whitespace-only branch_name
        response = client.put(
            "/api/repos/test-repo/branch",
            json={"branch_name": "   "},
            headers=power_user_headers,
        )
        assert response.status_code == 422
