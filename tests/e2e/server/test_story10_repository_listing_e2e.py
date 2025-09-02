"""
End-to-End tests for Story 10: Repository Listing APIs.

Tests the complete repository listing functionality including:
- List available golden repositories API
- Repository details API
- Search and filtering capabilities
- Authentication and authorization
"""

import json
import os
import tempfile
import time

import pytest
import requests

from code_indexer.server.lifecycle.server_lifecycle_manager import (
    ServerLifecycleManager,
)


class TestStory10RepositoryListingE2E:
    """E2E tests for repository listing APIs."""

    @pytest.fixture(scope="class")
    def server_lifecycle(self):
        """Set up test server for the class."""
        with tempfile.TemporaryDirectory() as temp_dir:
            server_dir = os.path.join(temp_dir, "test-server")
            os.makedirs(server_dir, exist_ok=True)

            # Create test configuration
            config = {
                "server_dir": server_dir,
                "host": "127.0.0.1",
                "port": 8123,  # Use different port to avoid conflicts
                "jwt_expiration_minutes": 10,
                "log_level": "INFO",
            }

            config_file = os.path.join(server_dir, "config.json")
            with open(config_file, "w") as f:
                json.dump(config, f)

            manager = ServerLifecycleManager(server_dir)
            # Add base_url property for convenience in tests
            manager.base_url = "http://127.0.0.1:8123"
            try:
                manager.start_server()
                yield manager
            finally:
                try:
                    manager.stop_server(force=True)
                except Exception:
                    pass

    @pytest.fixture
    def auth_headers(self, server_lifecycle):
        """Get authentication headers for API requests."""
        # Login as admin (default user)
        login_data = {"username": "admin", "password": "admin123"}

        response = requests.post(
            f"{server_lifecycle.base_url}/auth/login", json=login_data, timeout=10
        )

        assert response.status_code == 200
        token_data = response.json()
        return {"Authorization": f"Bearer {token_data['access_token']}"}

    @pytest.fixture
    def golden_repo_setup(self, server_lifecycle, auth_headers):
        """Set up golden repositories for testing."""
        # Create a test golden repository
        test_repo = {
            "repo_url": "https://github.com/octocat/Hello-World.git",
            "alias": "hello-world",
            "default_branch": "master",
        }

        # Add golden repository (this is async, so we need to track the job)
        response = requests.post(
            f"{server_lifecycle.base_url}/api/admin/golden-repos",
            json=test_repo,
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 202
        job_data = response.json()
        job_id = job_data["job_id"]

        # Wait for job completion (with timeout)
        max_wait = 60  # 1 minute timeout
        waited = 0

        while waited < max_wait:
            job_response = requests.get(
                f"{server_lifecycle.base_url}/api/jobs/{job_id}",
                headers=auth_headers,
                timeout=10,
            )

            assert job_response.status_code == 200
            job_status = job_response.json()

            if job_status["status"] == "completed":
                break
            elif job_status["status"] == "failed":
                pytest.fail(f"Golden repo creation failed: {job_status['error']}")

            time.sleep(2)
            waited += 2

        if waited >= max_wait:
            pytest.fail("Golden repository creation timed out")

        return test_repo

    def test_list_available_repositories_no_activations(
        self, server_lifecycle, auth_headers, golden_repo_setup
    ):
        """Test listing available repositories when user has no activations."""
        response = requests.get(
            f"{server_lifecycle.base_url}/api/repos/available",
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 200
        data = response.json()

        # Should return the golden repository
        assert "repositories" in data
        assert len(data["repositories"]) == 1
        assert data["repositories"][0]["alias"] == "hello-world"

        # Check response metadata
        assert "total" in data
        assert data["total"] == 1

    def test_get_repository_details_existing_repo(
        self, server_lifecycle, auth_headers, golden_repo_setup
    ):
        """Test getting details for an existing golden repository."""
        response = requests.get(
            f"{server_lifecycle.base_url}/api/repos/golden/hello-world",
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 200
        data = response.json()

        # Verify required fields are present
        required_fields = [
            "alias",
            "repo_url",
            "default_branch",
            "clone_path",
            "created_at",
            "activation_status",
            "branches_list",
            "file_count",
            "index_size",
            "last_updated",
        ]

        for field in required_fields:
            assert field in data, f"Field '{field}' missing from repository details"

        # Verify specific values
        assert data["alias"] == "hello-world"
        assert data["repo_url"] == "https://github.com/octocat/Hello-World.git"
        assert data["default_branch"] == "master"
        assert data["activation_status"] == "available"  # Not activated yet

        # Verify data types
        assert isinstance(data["branches_list"], list)
        assert isinstance(data["file_count"], int)
        assert isinstance(data["index_size"], int)

    def test_get_repository_details_nonexistent_repo(
        self, server_lifecycle, auth_headers
    ):
        """Test getting details for non-existent repository returns 404."""
        response = requests.get(
            f"{server_lifecycle.base_url}/api/repos/golden/nonexistent",
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_list_available_repositories_with_search(
        self, server_lifecycle, auth_headers, golden_repo_setup
    ):
        """Test repository search functionality."""
        # Search for existing repository
        response = requests.get(
            f"{server_lifecycle.base_url}/api/repos/available?search=hello",
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["repositories"]) == 1
        assert data["repositories"][0]["alias"] == "hello-world"

        # Search for non-existing repository
        response = requests.get(
            f"{server_lifecycle.base_url}/api/repos/available?search=nonexistent",
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["repositories"]) == 0
        assert data["total"] == 0

    def test_list_available_repositories_returns_all_repos(
        self, server_lifecycle, auth_headers, golden_repo_setup
    ):
        """Test that repository listing returns all repositories without pagination."""
        # Test that all repositories are returned in a single response
        response = requests.get(
            f"{server_lifecycle.base_url}/api/repos/available",
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 200
        data = response.json()

        assert "repositories" in data
        assert "total" in data
        # Should return all available repositories in single response
        assert len(data["repositories"]) == data["total"]

    def test_repository_listing_authentication_required(self, server_lifecycle):
        """Test that repository listing requires authentication."""
        # Try without authentication
        response = requests.get(
            f"{server_lifecycle.base_url}/api/repos/available", timeout=10
        )

        assert response.status_code == 401

        # Try repository details without authentication
        response = requests.get(
            f"{server_lifecycle.base_url}/api/repos/golden/hello-world", timeout=10
        )

        assert response.status_code == 401

    def test_list_available_repositories_invalid_parameters(
        self, server_lifecycle, auth_headers
    ):
        """Test error handling for invalid query parameters."""
        # Test invalid status filter
        response = requests.get(
            f"{server_lifecycle.base_url}/api/repos/available?repo_status=invalid",
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 400
        data = response.json()
        assert "invalid status filter" in data["detail"].lower()

    def test_pagination_parameters_ignored(
        self, server_lifecycle, auth_headers, golden_repo_setup
    ):
        """Test that pagination parameters (limit/offset) are ignored if provided."""
        # Even if pagination parameters are provided in URL, they should be ignored
        # and all repositories should be returned
        response = requests.get(
            f"{server_lifecycle.base_url}/api/repos/available?limit=1&offset=10",
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 200
        data = response.json()

        # Should still return all repositories despite pagination parameters
        assert "repositories" in data
        assert "total" in data
        assert len(data["repositories"]) == data["total"]

    def test_existing_activated_repos_endpoint_still_works(
        self, server_lifecycle, auth_headers
    ):
        """Test that the existing GET /api/repos endpoint still works correctly."""
        response = requests.get(
            f"{server_lifecycle.base_url}/api/repos", headers=auth_headers, timeout=10
        )

        # Should work (return empty list since no repos are activated)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0  # No activated repositories yet
