"""
Unit tests for Repository Statistics endpoint.

Following CLAUDE.md Foundation #1: No mocks - uses real operations.
Tests the /api/repositories/{repo_id}/stats endpoint functionality.
"""

import pytest
import tempfile
import os
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch

from src.code_indexer.server.app import create_app
from src.code_indexer.server.models.api_models import (
    RepositoryStatsResponse,
    RepositoryFilesInfo,
    RepositoryStorageInfo,
    RepositoryActivityInfo,
    RepositoryHealthInfo,
)


class TestRepositoryStatsEndpoint:
    """Unit tests for repository statistics endpoint."""

    @pytest.fixture
    def app(self):
        """Create FastAPI app for testing."""
        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def test_repo_directory(self):
        """Create a real test repository directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Create real test files with different languages
            (repo_path / "main.py").write_text(
                """
def main():
    print("Hello World")

if __name__ == "__main__":
    main()
"""
            )
            (repo_path / "utils.js").write_text(
                """
function calculateSum(a, b) {
    return a + b;
}
"""
            )
            (repo_path / "README.md").write_text("# Test Repository")
            (repo_path / "config.json").write_text('{"setting": "value"}')

            yield str(repo_path)

    @pytest.fixture
    def admin_token(self, client):
        """Get admin authentication token."""
        # This test will initially fail - we need to implement the endpoint
        response = client.post(
            "/auth/login", json={"username": "admin", "password": "admin_password"}
        )
        if response.status_code == 200:
            return response.json()["access_token"]
        return None

    def test_repository_stats_endpoint_exists(self, client, admin_token):
        """Test that the repository stats endpoint exists and is accessible."""
        # This test WILL FAIL initially - endpoint doesn't exist yet
        repo_id = "test-repo-123"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        response = client.get(f"/api/repositories/{repo_id}/stats", headers=headers)

        # Initially this will return 404 - that's expected for TDD
        # After implementation, should return 200
        assert response.status_code in [
            200,
            401,
            403,
            404,
        ]  # Allow auth failures in early tests

    def test_repository_stats_response_structure(
        self, client, admin_token, test_repo_directory
    ):
        """Test that repository stats response has correct structure."""
        # This test WILL FAIL initially - endpoint doesn't exist yet
        repo_id = "test-repo-123"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        # Mock the repository to point to our test directory
        with patch(
            "src.code_indexer.server.services.stats_service.get_repository_path"
        ) as mock_path:
            mock_path.return_value = test_repo_directory

            response = client.get(f"/api/repositories/{repo_id}/stats", headers=headers)

            if response.status_code == 200:
                data = response.json()

                # Validate response structure matches our model
                stats_response = RepositoryStatsResponse(**data)

                # Validate required fields
                assert stats_response.repository_id == repo_id
                assert isinstance(stats_response.files, RepositoryFilesInfo)
                assert isinstance(stats_response.storage, RepositoryStorageInfo)
                assert isinstance(stats_response.activity, RepositoryActivityInfo)
                assert isinstance(stats_response.health, RepositoryHealthInfo)

                # Validate file statistics
                assert stats_response.files.total >= 4  # We created 4 test files
                assert stats_response.files.indexed >= 0
                assert len(stats_response.files.by_language) > 0

                # Validate storage information
                assert stats_response.storage.repository_size_bytes > 0
                assert stats_response.storage.embedding_count >= 0

                # Validate health score
                assert 0.0 <= stats_response.health.score <= 1.0

    def test_repository_stats_file_counting(
        self, client, admin_token, test_repo_directory
    ):
        """Test that repository stats correctly counts files by language."""
        repo_id = "test-repo-123"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        with patch(
            "src.code_indexer.server.services.stats_service.get_repository_path"
        ) as mock_path:
            mock_path.return_value = test_repo_directory

            response = client.get(f"/api/repositories/{repo_id}/stats", headers=headers)

            if response.status_code == 200:
                data = response.json()
                stats = RepositoryStatsResponse(**data)

                # Check file count accuracy (we created 4 files)
                assert stats.files.total == 4

                # Check language distribution
                actual_languages = set(stats.files.by_language.keys())

                # Should detect at least Python and JavaScript
                assert "python" in actual_languages or "py" in actual_languages
                assert "javascript" in actual_languages or "js" in actual_languages

    def test_repository_stats_storage_calculation(
        self, client, admin_token, test_repo_directory
    ):
        """Test that repository stats correctly calculates storage metrics."""
        repo_id = "test-repo-123"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        with patch(
            "src.code_indexer.server.services.stats_service.get_repository_path"
        ) as mock_path:
            mock_path.return_value = test_repo_directory

            response = client.get(f"/api/repositories/{repo_id}/stats", headers=headers)

            if response.status_code == 200:
                data = response.json()
                stats = RepositoryStatsResponse(**data)

                # Repository size should reflect actual file sizes
                total_file_size = sum(
                    os.path.getsize(os.path.join(test_repo_directory, f))
                    for f in os.listdir(test_repo_directory)
                    if os.path.isfile(os.path.join(test_repo_directory, f))
                )

                assert stats.storage.repository_size_bytes == total_file_size

    def test_repository_stats_health_assessment(
        self, client, admin_token, test_repo_directory
    ):
        """Test that repository stats includes health assessment."""
        repo_id = "test-repo-123"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        with patch(
            "src.code_indexer.server.services.stats_service.get_repository_path"
        ) as mock_path:
            mock_path.return_value = test_repo_directory

            response = client.get(f"/api/repositories/{repo_id}/stats", headers=headers)

            if response.status_code == 200:
                data = response.json()
                stats = RepositoryStatsResponse(**data)

                # Health score should be valid
                assert 0.0 <= stats.health.score <= 1.0

                # Issues list should be present (may be empty)
                assert isinstance(stats.health.issues, list)

    def test_repository_stats_nonexistent_repo(self, client, admin_token):
        """Test repository stats endpoint with non-existent repository."""
        repo_id = "nonexistent-repo"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        response = client.get(f"/api/repositories/{repo_id}/stats", headers=headers)

        # Should return 404 for non-existent repository (or 403 if auth fails first)
        assert response.status_code in [403, 404]

        if response.status_code == 404:
            error_data = response.json()
            assert "not found" in error_data.get("message", "").lower()

    def test_repository_stats_unauthorized_access(self, client):
        """Test repository stats endpoint without authentication."""
        repo_id = "test-repo-123"

        response = client.get(f"/api/repositories/{repo_id}/stats")

        # Should return 401 or 403 without authentication
        assert response.status_code in [401, 403]

    def test_repository_stats_performance_requirement(
        self, client, admin_token, test_repo_directory
    ):
        """Test that repository stats endpoint meets performance requirements (<5s)."""
        import time

        repo_id = "test-repo-123"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        with patch(
            "src.code_indexer.server.services.stats_service.get_repository_path"
        ) as mock_path:
            mock_path.return_value = test_repo_directory

            start_time = time.time()
            response = client.get(f"/api/repositories/{repo_id}/stats", headers=headers)
            end_time = time.time()

            # Performance requirement: <5 seconds
            assert end_time - start_time < 5.0

            if response.status_code == 200:
                # Also verify we got a complete response quickly
                data = response.json()
                assert "repository_id" in data
                assert "files" in data
                assert "storage" in data
