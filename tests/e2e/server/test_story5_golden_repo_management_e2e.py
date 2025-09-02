"""
E2E tests for Story 5: Golden Repository Management.

Tests the complete flow of golden repository management through the API endpoints:
- Adding golden repositories
- Listing golden repositories
- Removing golden repositories
- Authentication and authorization
- Error handling
"""

import tempfile
import subprocess
import os
import time

import pytest
from fastapi.testclient import TestClient

from src.code_indexer.server.app import create_app
from src.code_indexer.server.repositories.golden_repo_manager import GoldenRepoManager


class TestGoldenRepoManagementE2E:
    """E2E tests for golden repository management functionality."""

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

        return repo_path

    @pytest.fixture
    def golden_repo_manager(self):
        """Create golden repository manager with temporary data directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield GoldenRepoManager(data_dir=temp_dir)

    @pytest.fixture(scope="class")
    def admin_token(self, client):
        """Get admin authentication token."""
        # Login with default admin credentials
        login_data = {"username": "admin", "password": "admin"}
        response = client.post("/auth/login", json=login_data)
        assert response.status_code == 200

        data = response.json()
        return data["access_token"]

    @pytest.fixture
    def auth_headers(self, admin_token):
        """Get authentication headers for admin."""
        return {"Authorization": f"Bearer {admin_token}"}

    @pytest.fixture
    def valid_repo_url(self, test_repo_path):
        """Valid git repository URL for testing."""
        return test_repo_path

    def test_health_check(self, client):
        """Test that the server is running."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_admin_authentication_required(self, client):
        """Test that admin authentication is required for golden repo endpoints."""
        # Test without authentication
        response = client.get("/api/admin/golden-repos")
        assert (
            response.status_code == 403
        )  # FastAPI HTTPBearer returns 403 when no token

        # Test with invalid token
        headers = {"Authorization": "Bearer invalid-token"}
        response = client.get("/api/admin/golden-repos", headers=headers)
        assert response.status_code == 401

    def test_list_golden_repos_empty(self, client, auth_headers):
        """Test listing golden repositories when none exist."""
        response = client.get("/api/admin/golden-repos", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["golden_repositories"] == []
        assert data["total"] == 0

    def test_add_golden_repo_success(
        self, client, auth_headers, valid_repo_url, golden_repo_manager, monkeypatch
    ):
        """Test successfully adding a golden repository."""
        # Use real golden repo manager with test setup
        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", golden_repo_manager
        )

        repo_data = {
            "repo_url": valid_repo_url,
            "alias": "hello-world",
            "default_branch": "master",  # git init creates master branch by default
        }

        response = client.post(
            "/api/admin/golden-repos", json=repo_data, headers=auth_headers
        )

        # Should now return 202 (background job started) instead of 201
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert "hello-world" in data["message"]
        assert "addition started" in data["message"]

        # Wait for background job to complete
        job_id = data["job_id"]
        max_wait_time = 60  # 60 seconds timeout
        wait_interval = 2  # Check every 2 seconds
        elapsed_time = 0

        while elapsed_time < max_wait_time:
            job_response = client.get(f"/api/jobs/{job_id}", headers=auth_headers)
            assert job_response.status_code == 200
            job_data = job_response.json()

            if job_data["status"] == "completed":
                break
            elif job_data["status"] == "failed":
                pytest.fail(
                    f"Background job failed: {job_data.get('error', 'Unknown error')}"
                )

            time.sleep(wait_interval)
            elapsed_time += wait_interval

        if elapsed_time >= max_wait_time:
            pytest.fail(
                f"Background job {job_id} did not complete within {max_wait_time} seconds"
            )

        # Verify repository was actually cloned
        clone_path = os.path.join(golden_repo_manager.golden_repos_dir, "hello-world")
        assert os.path.exists(clone_path)
        assert os.path.exists(os.path.join(clone_path, "README.md"))
        assert os.path.exists(os.path.join(clone_path, "main.py"))

        # CRITICAL: Verify workflow execution actually happened
        self._verify_workflow_execution(clone_path)

    def test_add_golden_repo_invalid_url_format(self, client, auth_headers):
        """Test adding golden repository with invalid URL format."""
        repo_data = {
            "repo_url": "not-a-valid-url",
            "alias": "invalid-repo",
            "default_branch": "main",
        }

        response = client.post(
            "/api/admin/golden-repos", json=repo_data, headers=auth_headers
        )
        assert response.status_code == 422  # Validation error

    def test_add_golden_repo_invalid_alias(self, client, auth_headers, valid_repo_url):
        """Test adding golden repository with invalid alias."""
        repo_data = {
            "repo_url": valid_repo_url,
            "alias": "invalid alias with spaces!@#",
            "default_branch": "main",
        }

        response = client.post(
            "/api/admin/golden-repos", json=repo_data, headers=auth_headers
        )
        assert response.status_code == 422  # Validation error

    def test_add_golden_repo_duplicate_alias(
        self, client, auth_headers, valid_repo_url, golden_repo_manager, monkeypatch
    ):
        """Test adding golden repository with duplicate alias."""
        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", golden_repo_manager
        )

        repo_data = {
            "repo_url": valid_repo_url,
            "alias": "duplicate-test",
            "default_branch": "master",
        }

        # Add repository first time - should succeed
        response = client.post(
            "/api/admin/golden-repos", json=repo_data, headers=auth_headers
        )
        assert response.status_code == 202

        # Wait for first job to complete
        job_data = response.json()
        self._wait_for_job_completion(client, auth_headers, job_data["job_id"])

        # Try to add same alias again - should fail during job execution
        response = client.post(
            "/api/admin/golden-repos", json=repo_data, headers=auth_headers
        )
        assert response.status_code == 202  # Job is submitted successfully

        # But the job should fail with duplicate alias error
        job_data = response.json()
        job_id = job_data["job_id"]
        max_wait_time = 60
        wait_interval = 2
        elapsed_time = 0

        while elapsed_time < max_wait_time:
            job_response = client.get(f"/api/jobs/{job_id}", headers=auth_headers)
            assert job_response.status_code == 200
            job_status = job_response.json()

            if job_status["status"] == "failed":
                assert job_status["error"] and "already exists" in job_status["error"]
                break
            elif job_status["status"] == "completed":
                pytest.fail(
                    "Expected job to fail with duplicate alias, but it completed successfully"
                )

            time.sleep(wait_interval)
            elapsed_time += wait_interval

        if elapsed_time >= max_wait_time:
            pytest.fail(f"Job {job_id} did not complete within {max_wait_time} seconds")

    def test_add_golden_repo_invalid_git_url(
        self, client, auth_headers, golden_repo_manager, monkeypatch
    ):
        """Test adding golden repository with invalid git URL."""
        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", golden_repo_manager
        )

        repo_data = {
            "repo_url": "https://definitely-not-a-real-git-url-12345.com/repo.git",
            "alias": "invalid-repo",
            "default_branch": "main",
        }

        response = client.post(
            "/api/admin/golden-repos", json=repo_data, headers=auth_headers
        )
        # Job submission should succeed, but job execution should fail
        assert response.status_code == 202

        # Wait for job to fail
        job_data = response.json()
        job_id = job_data["job_id"]
        max_wait_time = 60
        wait_interval = 2
        elapsed_time = 0

        while elapsed_time < max_wait_time:
            job_response = client.get(f"/api/jobs/{job_id}", headers=auth_headers)
            assert job_response.status_code == 200
            job_status = job_response.json()

            if job_status["status"] == "failed":
                assert (
                    job_status["error"]
                    and "Invalid or inaccessible" in job_status["error"]
                )
                break
            elif job_status["status"] == "completed":
                pytest.fail(
                    "Expected job to fail with invalid git URL, but it completed successfully"
                )

            time.sleep(wait_interval)
            elapsed_time += wait_interval

        if elapsed_time >= max_wait_time:
            pytest.fail(f"Job {job_id} did not complete within {max_wait_time} seconds")

    def test_add_golden_repo_exceeds_limit(
        self, client, auth_headers, valid_repo_url, golden_repo_manager, monkeypatch
    ):
        """Test adding golden repository exceeds resource limit."""
        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", golden_repo_manager
        )

        # Temporarily reduce the limit to test this quickly
        original_limit = golden_repo_manager.MAX_GOLDEN_REPOS
        golden_repo_manager.MAX_GOLDEN_REPOS = 2

        try:
            # Add first repository - should succeed
            repo_data1 = {
                "repo_url": valid_repo_url,
                "alias": "limit-test-1",
                "default_branch": "master",
            }
            response = client.post(
                "/api/admin/golden-repos", json=repo_data1, headers=auth_headers
            )
            assert response.status_code == 202
            job_data1 = response.json()
            self._wait_for_job_completion(client, auth_headers, job_data1["job_id"])

            # Add second repository - should succeed
            repo_data2 = {
                "repo_url": valid_repo_url,
                "alias": "limit-test-2",
                "default_branch": "master",
            }
            response = client.post(
                "/api/admin/golden-repos", json=repo_data2, headers=auth_headers
            )
            assert response.status_code == 202
            job_data2 = response.json()
            self._wait_for_job_completion(client, auth_headers, job_data2["job_id"])

            # Try to add third repository - should fail with limit exceeded
            repo_data3 = {
                "repo_url": valid_repo_url,
                "alias": "limit-test-3",
                "default_branch": "master",
            }
            response = client.post(
                "/api/admin/golden-repos", json=repo_data3, headers=auth_headers
            )
            # Job submission should succeed, but job execution should fail
            assert response.status_code == 202

            # Wait for job to fail with limit exceeded
            job_data3 = response.json()
            job_id = job_data3["job_id"]
            max_wait_time = 60
            wait_interval = 2
            elapsed_time = 0

            while elapsed_time < max_wait_time:
                job_response = client.get(f"/api/jobs/{job_id}", headers=auth_headers)
                assert job_response.status_code == 200
                job_status = job_response.json()

                if job_status["status"] == "failed":
                    assert job_status["error"] and "Maximum" in job_status["error"]
                    break
                elif job_status["status"] == "completed":
                    pytest.fail(
                        "Expected job to fail with limit exceeded, but it completed successfully"
                    )

                time.sleep(wait_interval)
                elapsed_time += wait_interval

            if elapsed_time >= max_wait_time:
                pytest.fail(
                    f"Job {job_id} did not complete within {max_wait_time} seconds"
                )
        finally:
            # Restore original limit
            golden_repo_manager.MAX_GOLDEN_REPOS = original_limit

    def test_list_golden_repos_with_data(
        self, client, auth_headers, valid_repo_url, golden_repo_manager, monkeypatch
    ):
        """Test listing golden repositories with existing data."""
        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", golden_repo_manager
        )

        # Add some real repositories first
        repo_data1 = {
            "repo_url": valid_repo_url,
            "alias": "list-test-1",
            "default_branch": "master",
        }
        response = client.post(
            "/api/admin/golden-repos", json=repo_data1, headers=auth_headers
        )
        assert response.status_code == 202
        job_data1 = response.json()
        self._wait_for_job_completion(client, auth_headers, job_data1["job_id"])

        repo_data2 = {
            "repo_url": valid_repo_url,
            "alias": "list-test-2",
            "default_branch": "master",
        }
        response = client.post(
            "/api/admin/golden-repos", json=repo_data2, headers=auth_headers
        )
        assert response.status_code == 202
        job_data2 = response.json()
        self._wait_for_job_completion(client, auth_headers, job_data2["job_id"])

        # Now test listing
        response = client.get("/api/admin/golden-repos", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["total"] >= 2  # May have repos from other tests
        repo_aliases = [repo["alias"] for repo in data["golden_repositories"]]
        assert "list-test-1" in repo_aliases
        assert "list-test-2" in repo_aliases

    def test_remove_golden_repo_success(
        self, client, auth_headers, valid_repo_url, golden_repo_manager, monkeypatch
    ):
        """Test successfully removing a golden repository."""
        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", golden_repo_manager
        )

        # First add a repository to remove
        repo_data = {
            "repo_url": valid_repo_url,
            "alias": "remove-test",
            "default_branch": "master",
        }
        response = client.post(
            "/api/admin/golden-repos", json=repo_data, headers=auth_headers
        )
        assert response.status_code == 202
        job_data = response.json()
        self._wait_for_job_completion(client, auth_headers, job_data["job_id"])

        # Verify it exists
        clone_path = os.path.join(golden_repo_manager.golden_repos_dir, "remove-test")
        assert os.path.exists(clone_path)

        # Now remove it
        response = client.delete(
            "/api/admin/golden-repos/remove-test", headers=auth_headers
        )
        assert response.status_code == 200

        data = response.json()
        assert "remove-test" in data["message"]
        assert "removed successfully" in data["message"]

        # Verify it was actually removed from filesystem
        assert not os.path.exists(clone_path)

    def test_remove_golden_repo_not_found(
        self, client, auth_headers, golden_repo_manager, monkeypatch
    ):
        """Test removing non-existent golden repository."""
        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", golden_repo_manager
        )

        response = client.delete(
            "/api/admin/golden-repos/nonexistent", headers=auth_headers
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_complete_golden_repo_workflow(
        self, client, auth_headers, valid_repo_url, golden_repo_manager, monkeypatch
    ):
        """Test complete workflow: add, list, remove golden repository."""
        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", golden_repo_manager
        )

        # Step 1: Add golden repository
        repo_data = {
            "repo_url": valid_repo_url,
            "alias": "workflow-test",
            "default_branch": "master",
        }

        add_response = client.post(
            "/api/admin/golden-repos", json=repo_data, headers=auth_headers
        )
        # Should return 202 (background job started)
        assert add_response.status_code == 202
        job_data = add_response.json()
        assert "job_id" in job_data

        # Wait for background job to complete
        job_id = job_data["job_id"]
        self._wait_for_job_completion(client, auth_headers, job_id)

        # Verify clone path exists
        clone_path = os.path.join(golden_repo_manager.golden_repos_dir, "workflow-test")
        assert os.path.exists(clone_path)
        assert os.path.exists(os.path.join(clone_path, "README.md"))

        # CRITICAL: Verify workflow execution actually happened
        self._verify_workflow_execution(clone_path)

        # Step 2: List golden repositories (should include new one)
        list_response = client.get("/api/admin/golden-repos", headers=auth_headers)
        assert list_response.status_code == 200

        data = list_response.json()
        repo_aliases = [repo["alias"] for repo in data["golden_repositories"]]
        assert "workflow-test" in repo_aliases

        # Find our specific repo
        workflow_repo = next(
            repo
            for repo in data["golden_repositories"]
            if repo["alias"] == "workflow-test"
        )
        assert workflow_repo["repo_url"] == valid_repo_url
        assert workflow_repo["default_branch"] == "master"

        # Step 3: Remove golden repository
        remove_response = client.delete(
            "/api/admin/golden-repos/workflow-test", headers=auth_headers
        )
        assert remove_response.status_code == 200

        # Verify it was actually removed
        assert not os.path.exists(clone_path)

        # Verify it's no longer in the list
        list_response = client.get("/api/admin/golden-repos", headers=auth_headers)
        data = list_response.json()
        repo_aliases = [repo["alias"] for repo in data["golden_repositories"]]
        assert "workflow-test" not in repo_aliases

    def test_refresh_golden_repo_success(
        self, client, auth_headers, valid_repo_url, golden_repo_manager, monkeypatch
    ):
        """Test successfully refreshing a golden repository."""
        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", golden_repo_manager
        )

        # First add a repository to refresh
        repo_data = {
            "repo_url": valid_repo_url,
            "alias": "refresh-test",
            "default_branch": "master",
        }
        add_response = client.post(
            "/api/admin/golden-repos", json=repo_data, headers=auth_headers
        )
        assert add_response.status_code == 202
        job_data = add_response.json()
        self._wait_for_job_completion(client, auth_headers, job_data["job_id"])

        # Verify it exists
        clone_path = os.path.join(golden_repo_manager.golden_repos_dir, "refresh-test")
        assert os.path.exists(clone_path)

        # Now refresh it
        refresh_response = client.post(
            "/api/admin/golden-repos/refresh-test/refresh", headers=auth_headers
        )
        assert refresh_response.status_code == 202

        refresh_job_data = refresh_response.json()
        assert "job_id" in refresh_job_data
        assert "refresh-test" in refresh_job_data["message"]
        assert "refresh started" in refresh_job_data["message"]

        # Wait for refresh job to complete
        refresh_job_id = refresh_job_data["job_id"]
        self._wait_for_job_completion(client, auth_headers, refresh_job_id)

        # Verify repository still exists after refresh
        assert os.path.exists(clone_path)

    def test_refresh_golden_repo_not_found(
        self, client, auth_headers, golden_repo_manager, monkeypatch
    ):
        """Test refreshing non-existent golden repository."""
        monkeypatch.setattr(
            "src.code_indexer.server.app.golden_repo_manager", golden_repo_manager
        )

        response = client.post(
            "/api/admin/golden-repos/nonexistent/refresh", headers=auth_headers
        )
        # Job submission should succeed, but job execution should fail
        assert response.status_code == 202

        # Wait for job to fail
        job_data = response.json()
        job_id = job_data["job_id"]
        max_wait_time = 60
        wait_interval = 2
        elapsed_time = 0

        while elapsed_time < max_wait_time:
            job_response = client.get(f"/api/jobs/{job_id}", headers=auth_headers)
            assert job_response.status_code == 200
            job_status = job_response.json()

            if job_status["status"] == "failed":
                assert job_status["error"] and "not found" in job_status["error"]
                break
            elif job_status["status"] == "completed":
                pytest.fail(
                    "Expected job to fail with non-existent repo, but it completed successfully"
                )

            time.sleep(wait_interval)
            elapsed_time += wait_interval

        if elapsed_time >= max_wait_time:
            pytest.fail(f"Job {job_id} did not complete within {max_wait_time} seconds")

    def test_request_validation_edge_cases(self, client, auth_headers):
        """Test edge cases in request validation."""
        # Empty repo URL
        repo_data = {"repo_url": "", "alias": "test-repo", "default_branch": "main"}
        response = client.post(
            "/api/admin/golden-repos", json=repo_data, headers=auth_headers
        )
        assert response.status_code == 422

        # Empty alias
        repo_data = {
            "repo_url": "https://github.com/test/repo.git",
            "alias": "",
            "default_branch": "main",
        }
        response = client.post(
            "/api/admin/golden-repos", json=repo_data, headers=auth_headers
        )
        assert response.status_code == 422

        # Empty branch name
        repo_data = {
            "repo_url": "https://github.com/test/repo.git",
            "alias": "test-repo",
            "default_branch": "",
        }
        response = client.post(
            "/api/admin/golden-repos", json=repo_data, headers=auth_headers
        )
        assert response.status_code == 422

    def test_non_admin_user_access_denied(self, client):
        """Test that non-admin users cannot access golden repo endpoints."""
        # This would require creating a non-admin user and getting their token
        # For now, we test with no authentication (401) and invalid token (401)

        # Test POST endpoint
        repo_data = {
            "repo_url": "https://github.com/test/repo.git",
            "alias": "test-repo",
            "default_branch": "main",
        }
        response = client.post("/api/admin/golden-repos", json=repo_data)
        assert (
            response.status_code == 403
        )  # FastAPI HTTPBearer returns 403 when no token

        # Test GET endpoint
        response = client.get("/api/admin/golden-repos")
        assert (
            response.status_code == 403
        )  # FastAPI HTTPBearer returns 403 when no token

        # Test DELETE endpoint
        response = client.delete("/api/admin/golden-repos/test-repo")
        assert (
            response.status_code == 403
        )  # FastAPI HTTPBearer returns 403 when no token

    def _wait_for_job_completion(self, client, auth_headers, job_id, max_wait_time=60):
        """Wait for a background job to complete."""
        wait_interval = 2
        elapsed_time = 0

        while elapsed_time < max_wait_time:
            job_response = client.get(f"/api/jobs/{job_id}", headers=auth_headers)
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
            f"Background job {job_id} did not complete within {max_wait_time} seconds"
        )

    def _verify_workflow_execution(self, clone_path):
        """Verify that the post-clone workflow was actually executed."""
        # Check that cidx initialization happened
        cidx_config_path = os.path.join(clone_path, ".cidx-config.yaml")
        assert os.path.exists(
            cidx_config_path
        ), f"cidx config file not found at {cidx_config_path} - workflow did not execute"

        # Check that the configuration contains voyage-ai embedding provider
        with open(cidx_config_path, "r") as f:
            config_content = f.read()
            assert (
                "voyage-ai" in config_content
            ), "voyage-ai embedding provider not configured - workflow did not execute properly"

        # Check that indexing created the necessary files/directories
        # This is a more comprehensive check than just file cloning
        qdrant_data_dir = os.path.join(clone_path, ".cidx-local", "qdrant_data")
        if not os.path.exists(qdrant_data_dir):
            # If qdrant data dir doesn't exist, the workflow didn't complete indexing
            pytest.fail(
                f"Qdrant data directory not found at {qdrant_data_dir} - indexing did not complete"
            )
