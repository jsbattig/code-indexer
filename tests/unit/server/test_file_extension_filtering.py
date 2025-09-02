"""
Unit tests for file extension filtering in semantic queries - TDD implementation.

Tests the file_extensions parameter functionality:
- Request validation for file_extensions parameter
- Filtering results by specified file extensions
- Validation of file extension format (must start with dot)
- Error handling for invalid file extensions
- Integration with existing semantic query functionality
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from datetime import datetime, timezone

from src.code_indexer.server.app import create_app
from src.code_indexer.server.auth.user_manager import User, UserRole


class TestFileExtensionFiltering:
    """Test file extension filtering in semantic queries."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def mock_user(self):
        """Mock authenticated user."""
        return User(
            username="testuser",
            password_hash="$2b$12$hash",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

    @patch("src.code_indexer.server.auth.dependencies.jwt_manager")
    @patch("src.code_indexer.server.auth.dependencies.user_manager")
    @patch("src.code_indexer.server.app.semantic_query_manager")
    def test_semantic_query_with_file_extensions_parameter(
        self,
        mock_semantic_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_user,
    ):
        """Test semantic query accepts file_extensions parameter."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_user

        # Mock response with mixed file types (should be filtered to only .py files)
        mock_semantic_manager.query_user_repositories.return_value = {
            "results": [
                {
                    "file_path": "/repo/src/main.py",
                    "line_number": 1,
                    "code_snippet": "def main(): pass",
                    "similarity_score": 0.95,
                    "repository_alias": "my-repo",
                },
            ],
            "total_results": 1,
            "query_metadata": {
                "query_text": "main function",
                "execution_time_ms": 100,
                "repositories_searched": 1,
                "timeout_occurred": False,
            },
        }

        # Make request with file_extensions parameter
        response = client.post(
            "/api/query",
            json={
                "query_text": "main function",
                "file_extensions": [".py", ".js"],
                "limit": 10,
            },
            headers={"Authorization": "Bearer test-token"},
        )

        # Should succeed with 200
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert data["total_results"] == 1

        # Verify semantic query manager was called with file_extensions parameter
        mock_semantic_manager.query_user_repositories.assert_called_once_with(
            username="testuser",
            query_text="main function",
            repository_alias=None,
            limit=10,
            min_score=None,
            file_extensions=[".py", ".js"],  # This parameter should be passed through
        )

    @patch("src.code_indexer.server.auth.dependencies.jwt_manager")
    @patch("src.code_indexer.server.auth.dependencies.user_manager")
    @patch("src.code_indexer.server.app.semantic_query_manager")
    def test_semantic_query_filters_results_by_file_extensions(
        self,
        mock_semantic_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_user,
    ):
        """Test semantic query manager properly filters results by file extensions."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_user

        # Mock response should only contain .py files (filtered from larger set)
        mock_semantic_manager.query_user_repositories.return_value = {
            "results": [
                {
                    "file_path": "/repo/src/utils.py",
                    "line_number": 5,
                    "code_snippet": "class Utils: pass",
                    "similarity_score": 0.88,
                    "repository_alias": "my-repo",
                },
                {
                    "file_path": "/repo/lib/helper.py",
                    "line_number": 10,
                    "code_snippet": "def helper(): return True",
                    "similarity_score": 0.82,
                    "repository_alias": "my-repo",
                },
            ],
            "total_results": 2,
            "query_metadata": {
                "query_text": "class helper",
                "execution_time_ms": 150,
                "repositories_searched": 1,
                "timeout_occurred": False,
            },
        }

        # Request only .py files
        response = client.post(
            "/api/query",
            json={
                "query_text": "class helper",
                "file_extensions": [".py"],
                "limit": 10,
            },
            headers={"Authorization": "Bearer test-token"},
        )

        # Verify response contains only .py files
        assert response.status_code == 200
        data = response.json()
        assert data["total_results"] == 2

        # All results should be .py files
        for result in data["results"]:
            assert result["file_path"].endswith(".py")

    @patch("src.code_indexer.server.auth.dependencies.jwt_manager")
    @patch("src.code_indexer.server.auth.dependencies.user_manager")
    def test_semantic_query_validates_file_extension_format(
        self, mock_dep_user_manager, mock_jwt_manager, client, mock_user
    ):
        """Test semantic query validates file extensions start with dot."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_user

        # Request with invalid file extension format (missing dot)
        response = client.post(
            "/api/query",
            json={
                "query_text": "test",
                "file_extensions": ["py", "js"],  # Invalid - missing dots
                "limit": 10,
            },
            headers={"Authorization": "Bearer test-token"},
        )

        # Should fail validation
        assert response.status_code == 422  # Pydantic validation error
        data = response.json()
        assert "detail" in data

    @patch("src.code_indexer.server.auth.dependencies.jwt_manager")
    @patch("src.code_indexer.server.auth.dependencies.user_manager")
    def test_semantic_query_validates_file_extension_characters(
        self, mock_dep_user_manager, mock_jwt_manager, client, mock_user
    ):
        """Test semantic query validates file extensions contain valid characters."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_user

        # Request with invalid characters in file extension
        response = client.post(
            "/api/query",
            json={
                "query_text": "test",
                "file_extensions": [".py!", ".js*"],  # Invalid characters
                "limit": 10,
            },
            headers={"Authorization": "Bearer test-token"},
        )

        # Should fail validation
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @patch("src.code_indexer.server.auth.dependencies.jwt_manager")
    @patch("src.code_indexer.server.auth.dependencies.user_manager")
    @patch("src.code_indexer.server.app.semantic_query_manager")
    def test_semantic_query_with_empty_file_extensions_list(
        self,
        mock_semantic_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_user,
    ):
        """Test semantic query with empty file_extensions list behaves like no filter."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_user

        mock_semantic_manager.query_user_repositories.return_value = {
            "results": [],
            "total_results": 0,
            "query_metadata": {
                "query_text": "test",
                "execution_time_ms": 50,
                "repositories_searched": 1,
                "timeout_occurred": False,
            },
        }

        # Request with empty file_extensions list
        response = client.post(
            "/api/query",
            json={
                "query_text": "test",
                "file_extensions": [],  # Empty list
                "limit": 10,
            },
            headers={"Authorization": "Bearer test-token"},
        )

        # Should succeed and pass None (no filtering)
        assert response.status_code == 200
        mock_semantic_manager.query_user_repositories.assert_called_once_with(
            username="testuser",
            query_text="test",
            repository_alias=None,
            limit=10,
            min_score=None,
            file_extensions=None,  # Empty list should be converted to None
        )

    @patch("src.code_indexer.server.auth.dependencies.jwt_manager")
    @patch("src.code_indexer.server.auth.dependencies.user_manager")
    @patch("src.code_indexer.server.app.semantic_query_manager")
    def test_semantic_query_without_file_extensions_parameter(
        self,
        mock_semantic_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_user,
    ):
        """Test semantic query without file_extensions parameter (backward compatibility)."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_user

        mock_semantic_manager.query_user_repositories.return_value = {
            "results": [],
            "total_results": 0,
            "query_metadata": {
                "query_text": "test",
                "execution_time_ms": 50,
                "repositories_searched": 1,
                "timeout_occurred": False,
            },
        }

        # Request without file_extensions parameter (existing behavior)
        response = client.post(
            "/api/query",
            json={"query_text": "test", "limit": 10},
            headers={"Authorization": "Bearer test-token"},
        )

        # Should succeed and pass None for file_extensions
        assert response.status_code == 200
        mock_semantic_manager.query_user_repositories.assert_called_once_with(
            username="testuser",
            query_text="test",
            repository_alias=None,
            limit=10,
            min_score=None,
            file_extensions=None,  # Should default to None for backward compatibility
        )

    @patch("src.code_indexer.server.auth.dependencies.jwt_manager")
    @patch("src.code_indexer.server.auth.dependencies.user_manager")
    @patch("src.code_indexer.server.app.semantic_query_manager")
    def test_semantic_query_async_with_file_extensions(
        self,
        mock_semantic_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_user,
    ):
        """Test async semantic query with file_extensions parameter."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_user

        # Mock job submission
        mock_semantic_manager.submit_query_job.return_value = "job-456"

        # Request async query with file_extensions
        response = client.post(
            "/api/query",
            json={
                "query_text": "async test",
                "file_extensions": [".py", ".ts"],
                "async_query": True,
                "limit": 15,
            },
            headers={"Authorization": "Bearer test-token"},
        )

        # Should return job ID
        assert response.status_code == 202
        data = response.json()
        assert data["job_id"] == "job-456"

        # Verify job submission includes file_extensions
        mock_semantic_manager.submit_query_job.assert_called_once_with(
            username="testuser",
            query_text="async test",
            repository_alias=None,
            limit=15,
            min_score=None,
            file_extensions=[".py", ".ts"],
        )
