"""
Unit tests for semantic query API endpoint - Story 7.

Tests the semantic query functionality:
- POST /api/query (semantic query with authentication)
- Query processing with user isolation
- Repository filtering and validation
- Result formatting and background job integration
- Resource limits and error handling
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from datetime import datetime, timezone

from src.code_indexer.server.app import create_app
from src.code_indexer.server.auth.user_manager import User, UserRole


@pytest.mark.e2e
class TestSemanticQueryEndpoint:
    """Test POST /api/query endpoint for semantic search."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def mock_admin_user(self):
        """Mock admin user for authentication."""
        return User(
            username="admin",
            password_hash="$2b$12$hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def mock_normal_user(self):
        """Mock normal user for authentication."""
        return User(
            username="testuser",
            password_hash="$2b$12$hash",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

    @patch("src.code_indexer.server.auth.dependencies.jwt_manager")
    @patch("src.code_indexer.server.auth.dependencies.user_manager")
    @patch("src.code_indexer.server.app.semantic_query_manager")
    def test_semantic_query_with_valid_request(
        self,
        mock_semantic_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_normal_user,
    ):
        """Test semantic query with valid authenticated request returns 200."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_normal_user

        # Mock semantic query manager response
        mock_semantic_manager.query_user_repositories.return_value = {
            "results": [
                {
                    "file_path": "/path/to/file.py",
                    "line_number": 1,
                    "code_snippet": "def test(): pass",
                    "similarity_score": 0.85,
                    "repository_alias": "my-repo",
                }
            ],
            "total_results": 1,
            "query_metadata": {
                "query_text": "test function",
                "execution_time_ms": 100,
                "repositories_searched": 1,
                "timeout_occurred": False,
            },
        }

        # Make request
        response = client.post(
            "/api/query",
            json={"query_text": "test function", "limit": 10},
            headers={"Authorization": "Bearer test-token"},
        )

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "total_results" in data
        assert "query_metadata" in data
        assert data["total_results"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["similarity_score"] == 0.85

        # Verify semantic query manager was called correctly
        mock_semantic_manager.query_user_repositories.assert_called_once_with(
            username="testuser",
            query_text="test function",
            repository_alias=None,
            limit=10,
            min_score=None,
            file_extensions=None,
        )

    @patch("src.code_indexer.server.auth.dependencies.jwt_manager")
    @patch("src.code_indexer.server.auth.dependencies.user_manager")
    @patch("src.code_indexer.server.app.semantic_query_manager")
    def test_semantic_query_with_repository_filter(
        self,
        mock_semantic_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_normal_user,
    ):
        """Test semantic query with repository filter parameter."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_normal_user

        # Mock semantic query manager response
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

        # Make request with repository filter
        response = client.post(
            "/api/query",
            json={
                "query_text": "test",
                "repository_alias": "specific-repo",
                "limit": 5,
                "min_score": 0.7,
            },
            headers={"Authorization": "Bearer test-token"},
        )

        # Verify response
        assert response.status_code == 200

        # Verify semantic query manager was called with filters
        mock_semantic_manager.query_user_repositories.assert_called_once_with(
            username="testuser",
            query_text="test",
            repository_alias="specific-repo",
            limit=5,
            min_score=0.7,
            file_extensions=None,
        )

    @patch("src.code_indexer.server.auth.dependencies.jwt_manager")
    @patch("src.code_indexer.server.auth.dependencies.user_manager")
    @patch("src.code_indexer.server.app.semantic_query_manager")
    def test_semantic_query_as_background_job(
        self,
        mock_semantic_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_normal_user,
    ):
        """Test semantic query submitted as background job when async=true."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_normal_user

        # Mock semantic query manager job submission
        mock_semantic_manager.submit_query_job.return_value = "job-123"

        # Make request with async flag
        response = client.post(
            "/api/query",
            json={"query_text": "complex query", "async_query": True},
            headers={"Authorization": "Bearer test-token"},
        )

        # Verify response
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert "message" in data
        assert data["job_id"] == "job-123"

        # Verify background job was submitted
        mock_semantic_manager.submit_query_job.assert_called_once_with(
            username="testuser",
            query_text="complex query",
            repository_alias=None,
            limit=10,
            min_score=None,
            file_extensions=None,
        )

    def test_semantic_query_without_authentication(self, client):
        """Test semantic query without authentication returns 403."""
        response = client.post("/api/query", json={"query_text": "test"})

        assert response.status_code == 403  # FastAPI returns 403 for missing auth

    @patch("src.code_indexer.server.auth.dependencies.jwt_manager")
    @patch("src.code_indexer.server.auth.dependencies.user_manager")
    @patch("src.code_indexer.server.app.semantic_query_manager")
    def test_semantic_query_with_invalid_parameters(
        self,
        mock_semantic_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_normal_user,
    ):
        """Test semantic query with invalid parameters returns 400."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_normal_user

        # Test empty query text
        response = client.post(
            "/api/query",
            json={"query_text": ""},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422  # FastAPI validation error

    @patch("src.code_indexer.server.auth.dependencies.jwt_manager")
    @patch("src.code_indexer.server.auth.dependencies.user_manager")
    @patch("src.code_indexer.server.app.semantic_query_manager")
    def test_semantic_query_with_no_repositories(
        self,
        mock_semantic_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_normal_user,
    ):
        """Test semantic query when user has no activated repositories returns 400."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_normal_user

        # Mock semantic query manager to raise error for no repositories
        from src.code_indexer.server.query.semantic_query_manager import (
            SemanticQueryError,
        )

        mock_semantic_manager.query_user_repositories.side_effect = SemanticQueryError(
            "No activated repositories found"
        )

        # Make request
        response = client.post(
            "/api/query",
            json={"query_text": "test"},
            headers={"Authorization": "Bearer test-token"},
        )

        # Verify error response
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "No activated repositories" in data["detail"]

    @patch("src.code_indexer.server.auth.dependencies.jwt_manager")
    @patch("src.code_indexer.server.auth.dependencies.user_manager")
    @patch("src.code_indexer.server.app.semantic_query_manager")
    def test_semantic_query_with_invalid_repository(
        self,
        mock_semantic_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_normal_user,
    ):
        """Test semantic query with invalid repository alias returns 404."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_normal_user

        # Mock semantic query manager to raise error for invalid repository
        from src.code_indexer.server.query.semantic_query_manager import (
            SemanticQueryError,
        )

        mock_semantic_manager.query_user_repositories.side_effect = SemanticQueryError(
            "Repository 'invalid-repo' not found"
        )

        # Make request
        response = client.post(
            "/api/query",
            json={"query_text": "test", "repository_alias": "invalid-repo"},
            headers={"Authorization": "Bearer test-token"},
        )

        # Verify error response
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"]

    @patch("src.code_indexer.server.auth.dependencies.jwt_manager")
    @patch("src.code_indexer.server.auth.dependencies.user_manager")
    @patch("src.code_indexer.server.app.semantic_query_manager")
    def test_semantic_query_timeout_error(
        self,
        mock_semantic_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_normal_user,
    ):
        """Test semantic query timeout returns 408."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_normal_user

        # Mock semantic query manager to raise timeout error
        from src.code_indexer.server.query.semantic_query_manager import (
            SemanticQueryError,
        )

        mock_semantic_manager.query_user_repositories.side_effect = SemanticQueryError(
            "Query timed out"
        )

        # Make request
        response = client.post(
            "/api/query",
            json={"query_text": "test"},
            headers={"Authorization": "Bearer test-token"},
        )

        # Verify timeout response
        assert response.status_code == 408
        data = response.json()
        assert "detail" in data
        assert "timed out" in data["detail"]

    @patch("src.code_indexer.server.auth.dependencies.jwt_manager")
    @patch("src.code_indexer.server.auth.dependencies.user_manager")
    @patch("src.code_indexer.server.app.semantic_query_manager")
    def test_semantic_query_internal_error(
        self,
        mock_semantic_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_normal_user,
    ):
        """Test semantic query with internal error returns 500."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_normal_user

        # Mock semantic query manager to raise internal error
        mock_semantic_manager.query_user_repositories.side_effect = Exception(
            "Internal search error"
        )

        # Make request
        response = client.post(
            "/api/query",
            json={"query_text": "test"},
            headers={"Authorization": "Bearer test-token"},
        )

        # Verify error response
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "search error" in data["detail"]

    @patch("src.code_indexer.server.auth.dependencies.jwt_manager")
    @patch("src.code_indexer.server.auth.dependencies.user_manager")
    @patch("src.code_indexer.server.app.semantic_query_manager")
    def test_semantic_query_validates_limit_range(
        self,
        mock_semantic_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_normal_user,
    ):
        """Test semantic query validates limit parameter range."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_normal_user

        # Test negative limit
        response = client.post(
            "/api/query",
            json={"query_text": "test", "limit": -1},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422  # Pydantic validation error

    @patch("src.code_indexer.server.auth.dependencies.jwt_manager")
    @patch("src.code_indexer.server.auth.dependencies.user_manager")
    @patch("src.code_indexer.server.app.semantic_query_manager")
    def test_semantic_query_validates_min_score_range(
        self,
        mock_semantic_manager,
        mock_dep_user_manager,
        mock_jwt_manager,
        client,
        mock_normal_user,
    ):
        """Test semantic query validates min_score parameter range."""
        # Setup authentication
        mock_jwt_manager.validate_token.return_value = {
            "username": "testuser",
            "role": "normal_user",
        }
        mock_dep_user_manager.get_user.return_value = mock_normal_user

        # Test invalid min_score > 1.0
        response = client.post(
            "/api/query",
            json={"query_text": "test", "min_score": 1.5},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422  # Pydantic validation error
