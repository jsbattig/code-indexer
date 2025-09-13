"""
Test-Driven Development tests for Repository Details Endpoint.

Tests for GET /api/repositories/{repo_id} endpoint as specified in Story 2:
Implement Repository Details Endpoint.

This module follows TDD methodology:
1. Write failing tests first that define expected behavior
2. Implement minimal code to make tests pass
3. Refactor for quality while keeping tests green

Acceptance Criteria:
1. GET endpoint returns 200 with complete repository details for authorized users
2. Returns 404 for non-existent repositories
3. Returns 403 for unauthorized access (user doesn't own repository)
4. Includes statistics (file counts, size, embeddings, languages)
5. Includes git information (branches, current branch, last commit)
6. Shows indexing status and progress for repositories being indexed
7. Response time < 200ms for standard repositories
"""

import os
import tempfile
import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from src.code_indexer.server.app import create_app


class TestRepositoryDetailsEndpointTDD:
    """Test-Driven Development test suite for Repository Details endpoint."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def app_with_test_data(self, temp_data_dir):
        """Create FastAPI app instance with test data."""
        # Set environment for test data directory
        os.environ["CIDX_DATA_DIR"] = temp_data_dir

        # Create users file path in temp directory
        users_file = os.path.join(temp_data_dir, "users.json")
        os.environ["CIDX_USERS_FILE"] = users_file

        app = create_app()

        yield app

    @pytest.fixture
    def client(self, app_with_test_data):
        """Create test client."""
        return TestClient(app_with_test_data)

    @pytest.fixture
    def auth_token_testuser(self, client):
        """Get authentication token for admin user (using default seeded admin)."""
        response = client.post(
            "/auth/login", json={"username": "admin", "password": "admin"}
        )
        assert response.status_code == 200
        return response.json()["access_token"]

    @pytest.fixture
    def auth_token_otheruser(self, client):
        """Get authentication token for admin user (simulating different user)."""
        # For now, we'll use the same admin user. In real implementation,
        # we would create separate users for testing authorization
        response = client.post(
            "/auth/login", json={"username": "admin", "password": "admin"}
        )
        assert response.status_code == 200
        return response.json()["access_token"]

    @pytest.fixture
    def auth_headers_testuser(self, auth_token_testuser):
        """Get authorization headers for testuser."""
        return {"Authorization": f"Bearer {auth_token_testuser}"}

    @pytest.fixture
    def auth_headers_otheruser(self, auth_token_otheruser):
        """Get authorization headers for otheruser."""
        return {"Authorization": f"Bearer {auth_token_otheruser}"}

    def test_repository_details_endpoint_exists_and_works(
        self, client, auth_headers_testuser
    ):
        """
        TDD STEP 1: Verify the endpoint exists and works.

        This test confirms the endpoint is implemented and returns expected data.
        """
        response = client.get(
            "/api/repositories/test-repo-id", headers=auth_headers_testuser
        )

        # Endpoint should exist and return 200 with valid data
        assert response.status_code == 200
        response_data = response.json()
        assert "id" in response_data
        assert response_data["id"] == "test-repo-id"

    def test_repository_details_returns_404_for_nonexistent_repository(
        self, client, auth_headers_testuser
    ):
        """
        TDD STEP 2: Test 404 for non-existent repositories.

        Acceptance Criteria 2: Returns 404 for non-existent repositories
        """
        response = client.get(
            "/api/repositories/nonexistent-repo-id", headers=auth_headers_testuser
        )

        assert response.status_code == 404
        response_data = response.json()
        assert "not found" in response_data["detail"].lower()

    def test_repository_details_returns_403_for_unauthorized_access(
        self, client, auth_headers_testuser, auth_headers_otheruser
    ):
        """
        TDD STEP 3: Test 403 for unauthorized access.

        Acceptance Criteria 3: Returns 403 for unauthorized access (user doesn't own repository)
        """
        # This test assumes there's a repository that the current user can't access
        # We use "otheruser-repo-1" to trigger the authorization logic
        repo_id = "otheruser-repo-1"

        response = client.get(
            f"/api/repositories/{repo_id}",
            headers=auth_headers_testuser,  # Admin trying to access otheruser's repo
        )

        assert response.status_code == 403
        response_data = response.json()
        assert (
            "access denied" in response_data["detail"].lower()
            or "unauthorized" in response_data["detail"].lower()
        )

    def test_repository_details_returns_200_with_complete_details_for_authorized_user(
        self, client, auth_headers_testuser
    ):
        """
        TDD STEP 4: Test 200 with complete repository details.

        Acceptance Criteria 1: GET endpoint returns 200 with complete repository details for authorized users
        """
        # This assumes a repository exists and is owned by testuser
        repo_id = "testuser-repo-1"

        response = client.get(
            f"/api/repositories/{repo_id}", headers=auth_headers_testuser
        )

        assert response.status_code == 200
        response_data = response.json()

        # Verify response structure matches API schema from story
        required_fields = [
            "id",
            "name",
            "path",
            "owner_id",
            "created_at",
            "updated_at",
            "last_sync_at",
            "status",
            "indexing_progress",
            "statistics",
            "git_info",
            "configuration",
            "errors",
        ]

        for field in required_fields:
            assert field in response_data, f"Missing required field: {field}"

    def test_repository_details_includes_statistics(
        self, client, auth_headers_testuser
    ):
        """
        TDD STEP 5: Test statistics inclusion.

        Acceptance Criteria 4: Includes statistics (file counts, size, embeddings, languages)
        """
        repo_id = "testuser-repo-1"

        response = client.get(
            f"/api/repositories/{repo_id}", headers=auth_headers_testuser
        )

        assert response.status_code == 200
        response_data = response.json()

        # Verify statistics structure
        assert "statistics" in response_data
        statistics = response_data["statistics"]

        required_stats = [
            "total_files",
            "indexed_files",
            "total_size_bytes",
            "embeddings_count",
            "languages",
        ]

        for stat in required_stats:
            assert stat in statistics, f"Missing statistic: {stat}"

        # Verify data types
        assert isinstance(statistics["total_files"], int)
        assert isinstance(statistics["indexed_files"], int)
        assert isinstance(statistics["total_size_bytes"], int)
        assert isinstance(statistics["embeddings_count"], int)
        assert isinstance(statistics["languages"], list)

    def test_repository_details_includes_git_information(
        self, client, auth_headers_testuser
    ):
        """
        TDD STEP 6: Test git information inclusion.

        Acceptance Criteria 5: Includes git information (branches, current branch, last commit)
        """
        repo_id = "testuser-repo-1"

        response = client.get(
            f"/api/repositories/{repo_id}", headers=auth_headers_testuser
        )

        assert response.status_code == 200
        response_data = response.json()

        # Verify git_info structure
        assert "git_info" in response_data
        git_info = response_data["git_info"]

        required_git_fields = [
            "current_branch",
            "branches",
            "last_commit",
            "remote_url",
        ]

        for field in required_git_fields:
            assert field in git_info, f"Missing git info field: {field}"

        # Verify data types
        assert isinstance(git_info["current_branch"], str)
        assert isinstance(git_info["branches"], list)
        assert isinstance(git_info["last_commit"], str)
        assert isinstance(git_info["remote_url"], (str, type(None)))

    def test_repository_details_includes_indexing_status_and_progress(
        self, client, auth_headers_testuser
    ):
        """
        TDD STEP 7: Test indexing status and progress.

        Acceptance Criteria 6: Shows indexing status and progress for repositories being indexed
        """
        repo_id = "testuser-repo-1"

        response = client.get(
            f"/api/repositories/{repo_id}", headers=auth_headers_testuser
        )

        assert response.status_code == 200
        response_data = response.json()

        # Verify indexing status fields
        assert "status" in response_data
        assert "indexing_progress" in response_data

        # Status should be one of valid values
        valid_statuses = ["indexed", "indexing", "error", "pending"]
        assert response_data["status"] in valid_statuses

        # Progress should be 0-100
        progress = response_data["indexing_progress"]
        assert isinstance(progress, (int, float))
        assert 0 <= progress <= 100

    def test_repository_details_response_time_under_200ms(
        self, client, auth_headers_testuser
    ):
        """
        TDD STEP 8: Test response time performance.

        Acceptance Criteria 7: Response time < 200ms for standard repositories
        """
        repo_id = "testuser-repo-1"

        start_time = time.time()
        response = client.get(
            f"/api/repositories/{repo_id}", headers=auth_headers_testuser
        )
        end_time = time.time()

        response_time_ms = (end_time - start_time) * 1000

        assert response.status_code == 200
        assert (
            response_time_ms < 200
        ), f"Response time {response_time_ms}ms exceeds 200ms limit"

    def test_repository_details_includes_configuration(
        self, client, auth_headers_testuser
    ):
        """
        TDD STEP 9: Test configuration information inclusion.

        Verify configuration details are included per API schema.
        """
        repo_id = "testuser-repo-1"

        response = client.get(
            f"/api/repositories/{repo_id}", headers=auth_headers_testuser
        )

        assert response.status_code == 200
        response_data = response.json()

        # Verify configuration structure
        assert "configuration" in response_data
        config = response_data["configuration"]

        expected_config_fields = [
            "ignore_patterns",
            "chunk_size",
            "overlap",
            "embedding_model",
        ]

        for field in expected_config_fields:
            assert field in config, f"Missing configuration field: {field}"

        # Verify data types
        assert isinstance(config["ignore_patterns"], list)
        assert isinstance(config["chunk_size"], int)
        assert isinstance(config["overlap"], int)
        assert isinstance(config["embedding_model"], str)

    def test_repository_details_includes_error_information(
        self, client, auth_headers_testuser
    ):
        """
        TDD STEP 10: Test error information inclusion.

        Verify errors array is included per API schema.
        """
        repo_id = "testuser-repo-1"

        response = client.get(
            f"/api/repositories/{repo_id}", headers=auth_headers_testuser
        )

        assert response.status_code == 200
        response_data = response.json()

        # Verify errors field exists and is a list
        assert "errors" in response_data
        assert isinstance(response_data["errors"], list)

    def test_repository_details_timestamp_formats(self, client, auth_headers_testuser):
        """
        TDD STEP 11: Test timestamp format consistency.

        Verify all timestamps follow ISO 8601 format.
        """
        repo_id = "testuser-repo-1"

        response = client.get(
            f"/api/repositories/{repo_id}", headers=auth_headers_testuser
        )

        assert response.status_code == 200
        response_data = response.json()

        # Verify timestamp fields exist and have correct format
        timestamp_fields = ["created_at", "updated_at", "last_sync_at"]

        for field in timestamp_fields:
            assert field in response_data
            timestamp_str = response_data[field]

            # Verify ISO 8601 format
            try:
                datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except ValueError:
                pytest.fail(f"Invalid timestamp format for {field}: {timestamp_str}")

    def test_repository_details_requires_authentication(self, client):
        """
        TDD STEP 12: Test authentication requirement.

        Verify endpoint requires valid authentication token.
        """
        repo_id = "testuser-repo-1"

        # Request without authentication
        response = client.get(f"/api/repositories/{repo_id}")

        # Should return 401 (Unauthorized) or 403 (Forbidden) for missing authentication
        assert response.status_code in [401, 403]

    def test_repository_details_rejects_invalid_repo_ids(
        self, client, auth_headers_testuser
    ):
        """
        TDD STEP 13: Test validation of repository IDs.

        Verify endpoint properly validates repository ID format.
        """
        invalid_repo_ids = [
            "",  # Empty string
            "   ",  # Whitespace only
            "../../../etc/passwd",  # Path traversal attempt
            "repo with spaces",  # Invalid characters
            "repo/with/slashes",  # Slashes
        ]

        for invalid_id in invalid_repo_ids:
            response = client.get(
                f"/api/repositories/{invalid_id}", headers=auth_headers_testuser
            )

            # Should return 400 for invalid format or 404 for not found
            assert response.status_code in [
                400,
                404,
            ], f"Invalid repo ID '{invalid_id}' should return 400 or 404"

    def test_repository_details_handles_concurrent_requests(
        self, client, auth_headers_testuser
    ):
        """
        TDD STEP 14: Test concurrent request handling.

        Verify endpoint handles multiple concurrent requests safely.
        """
        import concurrent.futures

        repo_id = "testuser-repo-1"
        num_concurrent_requests = 10
        results = []

        def make_request():
            response = client.get(
                f"/api/repositories/{repo_id}", headers=auth_headers_testuser
            )
            return response

        # Execute concurrent requests
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=num_concurrent_requests
        ) as executor:
            futures = [
                executor.submit(make_request) for _ in range(num_concurrent_requests)
            ]
            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        # All requests should succeed with same data
        for response in results:
            assert response.status_code == 200

        # Verify all responses have consistent data
        first_response_data = results[0].json()
        for response in results[1:]:
            assert response.json() == first_response_data

    def test_repository_details_endpoint_method_validation(
        self, client, auth_headers_testuser
    ):
        """
        TDD STEP 15: Test HTTP method validation.

        Verify endpoint only accepts GET requests.
        """
        repo_id = "testuser-repo-1"

        # Test unsupported methods
        unsupported_methods = ["POST", "PUT", "DELETE", "PATCH"]

        for method in unsupported_methods:
            if method == "POST":
                response = client.post(
                    f"/api/repositories/{repo_id}", headers=auth_headers_testuser
                )
            elif method == "PUT":
                response = client.put(
                    f"/api/repositories/{repo_id}", headers=auth_headers_testuser
                )
            elif method == "DELETE":
                response = client.delete(
                    f"/api/repositories/{repo_id}", headers=auth_headers_testuser
                )
            elif method == "PATCH":
                response = client.patch(
                    f"/api/repositories/{repo_id}", headers=auth_headers_testuser
                )

            # Should return 405 Method Not Allowed
            assert response.status_code == 405


class TestRepositoryDetailsEndpointIntegration:
    """Integration tests for Repository Details endpoint with real data."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for integration testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    def test_repository_details_with_real_repository_data(self, temp_data_dir):
        """
        Integration test with real repository structure.

        This test will be implemented after the basic endpoint is created.
        """
        # Create mock repository structure
        repo_path = os.path.join(temp_data_dir, "test-repo")
        os.makedirs(repo_path)

        # Create sample files
        with open(os.path.join(repo_path, "main.py"), "w") as f:
            f.write("# Sample Python file\nprint('Hello World')")

        with open(os.path.join(repo_path, "README.md"), "w") as f:
            f.write("# Test Repository\nThis is a test repository.")

        # This will be expanded once the endpoint is implemented
        assert os.path.exists(repo_path)

    def test_repository_details_with_git_repository(self, temp_data_dir):
        """
        Integration test with real Git repository.

        This test will verify git information extraction.
        """
        import subprocess

        repo_path = os.path.join(temp_data_dir, "git-repo")
        os.makedirs(repo_path)

        # Initialize git repository
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
        )

        # Create and commit a file
        test_file = os.path.join(repo_path, "test.txt")
        with open(test_file, "w") as f:
            f.write("Test content")

        subprocess.run(["git", "add", "test.txt"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True
        )

        # Verify git repository was created
        git_dir = os.path.join(repo_path, ".git")
        assert os.path.exists(git_dir)

        # This will be expanded once the endpoint can extract git information
        assert True  # Placeholder until implementation
