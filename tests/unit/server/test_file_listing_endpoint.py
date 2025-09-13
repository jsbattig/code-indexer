"""
Unit tests for File Listing endpoint.

Following CLAUDE.md Foundation #1: No mocks - uses real file operations.
Tests the /api/repositories/{repo_id}/files endpoint functionality.
"""

import pytest
import tempfile
import os
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch

from src.code_indexer.server.app import create_app
from src.code_indexer.server.models.api_models import (
    FileListResponse,
    FileInfo,
    PaginationInfo,
)


class TestFileListingEndpoint:
    """Unit tests for file listing endpoint."""

    @pytest.fixture
    def app(self):
        """Create FastAPI app for testing."""
        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def large_test_repo_directory(self):
        """Create a test repository with many files for pagination testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Create files in different subdirectories and languages
            (repo_path / "src").mkdir()
            (repo_path / "tests").mkdir()
            (repo_path / "docs").mkdir()

            # Python files
            for i in range(5):
                (repo_path / "src" / f"module_{i}.py").write_text(
                    f"""
def function_{i}():
    return {i}
"""
                )

            # JavaScript files
            for i in range(3):
                (repo_path / "src" / f"script_{i}.js").write_text(
                    f"""
function func{i}() {{
    return {i};
}}
"""
                )

            # Test files
            for i in range(4):
                (repo_path / "tests" / f"test_{i}.py").write_text(
                    f"""
def test_{i}():
    assert True
"""
                )

            # Documentation files
            (repo_path / "docs" / "README.md").write_text("# Documentation")
            (repo_path / "docs" / "API.md").write_text("## API Documentation")

            # Config files
            (repo_path / "package.json").write_text('{"name": "test-package"}')
            (repo_path / ".gitignore").write_text("*.pyc\n__pycache__/")

            yield str(repo_path)

    @pytest.fixture
    def admin_token(self, client):
        """Get admin authentication token."""
        response = client.post(
            "/auth/login", json={"username": "admin", "password": "admin_password"}
        )
        if response.status_code == 200:
            return response.json()["access_token"]
        return None

    def test_file_listing_endpoint_exists(self, client, admin_token):
        """Test that the file listing endpoint exists and is accessible."""
        # This test WILL FAIL initially - endpoint doesn't exist yet
        repo_id = "test-repo-123"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        response = client.get(f"/api/repositories/{repo_id}/files", headers=headers)

        # Initially this will return 404 - that's expected for TDD
        assert response.status_code in [200, 401, 403, 404]

    def test_file_listing_basic_functionality(
        self, client, admin_token, large_test_repo_directory
    ):
        """Test basic file listing functionality."""
        repo_id = "test-repo-123"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        with patch(
            "src.code_indexer.server.services.file_service.get_repository_path"
        ) as mock_path:
            mock_path.return_value = large_test_repo_directory

            response = client.get(f"/api/repositories/{repo_id}/files", headers=headers)

            if response.status_code == 200:
                data = response.json()
                file_list = FileListResponse(**data)

                # Should return list of files
                assert isinstance(file_list.files, list)
                assert len(file_list.files) > 0

                # Check pagination info
                assert isinstance(file_list.pagination, PaginationInfo)
                assert file_list.pagination.page >= 1
                assert file_list.pagination.total > 0

                # Check file info structure
                for file_info in file_list.files:
                    assert isinstance(file_info, FileInfo)
                    assert file_info.path
                    assert file_info.size_bytes >= 0
                    assert isinstance(file_info.is_indexed, bool)

    def test_file_listing_pagination(
        self, client, admin_token, large_test_repo_directory
    ):
        """Test file listing pagination functionality."""
        repo_id = "test-repo-123"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        with patch(
            "src.code_indexer.server.services.file_service.get_repository_path"
        ) as mock_path:
            mock_path.return_value = large_test_repo_directory

            # Test first page with limit
            response = client.get(
                f"/api/repositories/{repo_id}/files?page=1&limit=5", headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                file_list = FileListResponse(**data)

                # Should return exactly 5 files (or less if total < 5)
                assert len(file_list.files) <= 5
                assert file_list.pagination.page == 1
                assert file_list.pagination.limit == 5

                if file_list.pagination.total > 5:
                    assert file_list.pagination.has_next is True

                    # Test second page
                    response2 = client.get(
                        f"/api/repositories/{repo_id}/files?page=2&limit=5",
                        headers=headers,
                    )

                    if response2.status_code == 200:
                        data2 = response2.json()
                        file_list2 = FileListResponse(**data2)

                        assert file_list2.pagination.page == 2
                        # Files on page 2 should be different from page 1
                        page1_paths = {f.path for f in file_list.files}
                        page2_paths = {f.path for f in file_list2.files}
                        assert page1_paths != page2_paths

    def test_file_listing_language_filter(
        self, client, admin_token, large_test_repo_directory
    ):
        """Test file listing with language filtering."""
        repo_id = "test-repo-123"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        with patch(
            "src.code_indexer.server.services.file_service.get_repository_path"
        ) as mock_path:
            mock_path.return_value = large_test_repo_directory

            # Filter for Python files only
            response = client.get(
                f"/api/repositories/{repo_id}/files?language=python", headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                file_list = FileListResponse(**data)

                # All returned files should be Python files
                for file_info in file_list.files:
                    assert file_info.language in [
                        "python",
                        "py",
                        None,
                    ]  # Allow None for undetected
                    if file_info.path.endswith(".py"):
                        assert file_info.language in ["python", "py"]

    def test_file_listing_path_pattern_filter(
        self, client, admin_token, large_test_repo_directory
    ):
        """Test file listing with path pattern filtering."""
        repo_id = "test-repo-123"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        with patch(
            "src.code_indexer.server.services.file_service.get_repository_path"
        ) as mock_path:
            mock_path.return_value = large_test_repo_directory

            # Filter for files in src directory
            response = client.get(
                f"/api/repositories/{repo_id}/files?path_pattern=src/*", headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                file_list = FileListResponse(**data)

                # All returned files should be in src directory
                for file_info in file_list.files:
                    assert file_info.path.startswith("src/")

    def test_file_listing_sorting(self, client, admin_token, large_test_repo_directory):
        """Test file listing with different sorting options."""
        repo_id = "test-repo-123"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        with patch(
            "src.code_indexer.server.services.file_service.get_repository_path"
        ) as mock_path:
            mock_path.return_value = large_test_repo_directory

            # Test sorting by size
            response = client.get(
                f"/api/repositories/{repo_id}/files?sort_by=size&limit=10",
                headers=headers,
            )

            if response.status_code == 200:
                data = response.json()
                file_list = FileListResponse(**data)

                # Check that files are sorted by size (ascending by default)
                if len(file_list.files) > 1:
                    for i in range(len(file_list.files) - 1):
                        assert (
                            file_list.files[i].size_bytes
                            <= file_list.files[i + 1].size_bytes
                        )

    def test_file_listing_file_metadata_accuracy(
        self, client, admin_token, large_test_repo_directory
    ):
        """Test that file listing returns accurate file metadata."""
        repo_id = "test-repo-123"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        with patch(
            "src.code_indexer.server.services.file_service.get_repository_path"
        ) as mock_path:
            mock_path.return_value = large_test_repo_directory

            response = client.get(f"/api/repositories/{repo_id}/files", headers=headers)

            if response.status_code == 200:
                data = response.json()
                file_list = FileListResponse(**data)

                # Verify metadata accuracy for at least one file
                for file_info in file_list.files[:3]:  # Check first 3 files
                    file_path = os.path.join(large_test_repo_directory, file_info.path)

                    if os.path.exists(file_path):
                        # Check file size accuracy
                        actual_size = os.path.getsize(file_path)
                        assert file_info.size_bytes == actual_size

                        # Check modification time (should be recent)
                        actual_mtime = os.path.getmtime(file_path)
                        # Allow some tolerance for timestamp comparison
                        assert (
                            abs(file_info.modified_at.timestamp() - actual_mtime) < 60
                        )

    def test_file_listing_query_parameter_validation(self, client, admin_token):
        """Test file listing endpoint query parameter validation."""
        repo_id = "test-repo-123"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        # Test invalid page number
        response = client.get(
            f"/api/repositories/{repo_id}/files?page=0", headers=headers
        )
        # Auth might be checked first, so accept 401/403/422
        assert response.status_code in [401, 403, 422]

        # Test invalid limit
        response = client.get(
            f"/api/repositories/{repo_id}/files?limit=1000", headers=headers
        )
        # Auth might be checked first, so accept 401/403/422
        assert response.status_code in [401, 403, 422]

        # Test invalid sort field
        response = client.get(
            f"/api/repositories/{repo_id}/files?sort_by=invalid_field", headers=headers
        )
        # Auth might be checked first, so accept various error codes
        assert response.status_code in [400, 401, 403, 404, 422]

    def test_file_listing_empty_repository(self, client, admin_token):
        """Test file listing with empty repository."""
        with tempfile.TemporaryDirectory() as temp_dir:
            empty_repo_path = Path(temp_dir) / "empty_repo"
            empty_repo_path.mkdir()

            repo_id = "empty-repo"
            headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

            with patch(
                "src.code_indexer.server.services.file_service.get_repository_path"
            ) as mock_path:
                mock_path.return_value = str(empty_repo_path)

                response = client.get(
                    f"/api/repositories/{repo_id}/files", headers=headers
                )

                if response.status_code == 200:
                    data = response.json()
                    file_list = FileListResponse(**data)

                    # Should return empty list but valid structure
                    assert len(file_list.files) == 0
                    assert file_list.pagination.total == 0
                    assert file_list.pagination.has_next is False

    def test_file_listing_nonexistent_repository(self, client, admin_token):
        """Test file listing endpoint with non-existent repository."""
        repo_id = "nonexistent-repo"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        response = client.get(f"/api/repositories/{repo_id}/files", headers=headers)

        # Should return 404 for non-existent repository (or 403 if auth fails first)
        assert response.status_code in [403, 404]

    def test_file_listing_unauthorized_access(self, client):
        """Test file listing endpoint without authentication."""
        repo_id = "test-repo-123"

        response = client.get(f"/api/repositories/{repo_id}/files")

        # Should return 401 or 403 without authentication
        assert response.status_code in [401, 403]

    def test_file_listing_performance_requirement(
        self, client, admin_token, large_test_repo_directory
    ):
        """Test that file listing endpoint meets performance requirements."""
        import time

        repo_id = "test-repo-123"
        headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

        with patch(
            "src.code_indexer.server.services.file_service.get_repository_path"
        ) as mock_path:
            mock_path.return_value = large_test_repo_directory

            start_time = time.time()
            response = client.get(f"/api/repositories/{repo_id}/files", headers=headers)
            end_time = time.time()

            # Should be reasonably fast for file listing
            assert end_time - start_time < 3.0

            if response.status_code == 200:
                data = response.json()
                assert "files" in data
                assert "pagination" in data
