"""
Unit tests for Golden Repo Index Management REST API endpoints.

Tests POST /api/admin/golden-repos/{alias}/indexes (add index)
Tests GET /api/admin/golden-repos/{alias}/indexes (get index status)

Story #594: REST API for Index Management
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch


@pytest.fixture
def test_app():
    """Create a test FastAPI app with minimal setup."""
    from code_indexer.server.app import app

    return app


@pytest.fixture
def test_client(test_app):
    """Create a test client for the app."""
    return TestClient(test_app)


@pytest.fixture
def mock_golden_repo_manager(tmp_path):
    """Mock golden repo manager."""
    manager = Mock()
    manager.golden_repos_dir = str(tmp_path / "golden-repos")
    manager.golden_repos = {
        "test-repo": Mock(
            alias="test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path=str(tmp_path / "golden-repos" / "test-repo"),
            created_at="2024-01-01T00:00:00Z",
            enable_temporal=False,
            temporal_options=None,
        )
    }
    return manager


@pytest.fixture
def mock_auth_admin():
    """Mock authentication for admin user."""
    from datetime import datetime, timezone
    from code_indexer.server.auth.user_manager import User, UserRole

    with (
        patch("code_indexer.server.auth.dependencies.jwt_manager") as mock_jwt,
        patch("code_indexer.server.auth.dependencies.user_manager") as mock_user_mgr,
    ):

        mock_jwt.validate_token.return_value = {
            "username": "admin",
            "role": "admin",
            "exp": 9999999999,
        }

        admin_user = User(
            username="admin",
            password_hash="$2b$12$test_hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )
        mock_user_mgr.get_user.return_value = admin_user

        yield {"Authorization": "Bearer fake_admin_token"}


def test_post_add_index_success(test_client, mock_golden_repo_manager, mock_auth_admin):
    """
    AC1: POST endpoint returns 202 with job_id on success.

    Test that POST /api/admin/golden-repos/{alias}/indexes with valid
    index_type creates a background job and returns 202 Accepted.
    """
    # Arrange
    mock_golden_repo_manager.add_index_to_golden_repo.return_value = "job-123"

    with patch("code_indexer.server.app.golden_repo_manager", mock_golden_repo_manager):
        # Act
        response = test_client.post(
            "/api/admin/golden-repos/test-repo/indexes",
            json={"index_type": "temporal"},
            headers=mock_auth_admin,
        )

    # Assert
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["job_id"] == "job-123"
    assert "status" in data

    # Verify Location header
    assert "Location" in response.headers
    assert response.headers["Location"] == "/api/jobs/job-123"

    # Verify manager was called correctly
    mock_golden_repo_manager.add_index_to_golden_repo.assert_called_once_with(
        alias="test-repo", index_type="temporal", submitter_username="admin"
    )


def test_get_index_status_success(
    test_client, mock_golden_repo_manager, mock_auth_admin, tmp_path
):
    """
    AC2: GET endpoint returns current index status.

    Test that GET /api/admin/golden-repos/{alias}/indexes returns
    structured JSON showing presence of all index types.
    """

    # Arrange - mock _index_exists to return True for semantic_fts only
    def mock_index_exists(golden_repo, index_type):
        if index_type == "semantic_fts":
            return True
        return False

    mock_golden_repo_manager._index_exists = mock_index_exists

    with patch("code_indexer.server.app.golden_repo_manager", mock_golden_repo_manager):
        # Act
        response = test_client.get(
            "/api/admin/golden-repos/test-repo/indexes", headers=mock_auth_admin
        )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["alias"] == "test-repo"
    assert "indexes" in data
    assert "semantic_fts" in data["indexes"]
    assert "temporal" in data["indexes"]
    assert "scip" in data["indexes"]
    assert data["indexes"]["semantic_fts"]["present"] is True
    assert data["indexes"]["temporal"]["present"] is False
    assert data["indexes"]["scip"]["present"] is False


def test_post_unknown_alias_returns_404(
    test_client, mock_golden_repo_manager, mock_auth_admin
):
    """
    AC3: POST with unknown alias returns 404.

    Test that POST to non-existent alias returns 404 Not Found.
    """
    # Arrange
    mock_golden_repo_manager.add_index_to_golden_repo.side_effect = ValueError(
        "Golden repository 'non-existent' not found"
    )

    with patch("code_indexer.server.app.golden_repo_manager", mock_golden_repo_manager):
        # Act
        response = test_client.post(
            "/api/admin/golden-repos/non-existent/indexes",
            json={"index_type": "temporal"},
            headers=mock_auth_admin,
        )

    # Assert
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data or "error" in data


def test_post_invalid_index_type_returns_400(
    test_client, mock_golden_repo_manager, mock_auth_admin
):
    """
    AC4: POST with invalid index_type returns 400.

    Test that POST with invalid index_type returns 400 Bad Request
    with descriptive error message listing valid options.
    """
    # Arrange
    mock_golden_repo_manager.add_index_to_golden_repo.side_effect = ValueError(
        "Invalid index_type: invalid. Must be one of: semantic_fts, temporal, scip"
    )

    with patch("code_indexer.server.app.golden_repo_manager", mock_golden_repo_manager):
        # Act
        response = test_client.post(
            "/api/admin/golden-repos/test-repo/indexes",
            json={"index_type": "invalid"},
            headers=mock_auth_admin,
        )

    # Assert
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data


def test_post_existing_index_returns_409(
    test_client, mock_golden_repo_manager, mock_auth_admin
):
    """
    AC5: POST for existing index returns 409 Conflict.

    Test that attempting to add an existing index type returns 409 Conflict.
    """
    # Arrange
    mock_golden_repo_manager.add_index_to_golden_repo.side_effect = ValueError(
        "Index type 'semantic_fts' already exists for golden repo 'test-repo'"
    )

    with patch("code_indexer.server.app.golden_repo_manager", mock_golden_repo_manager):
        # Act
        response = test_client.post(
            "/api/admin/golden-repos/test-repo/indexes",
            json={"index_type": "semantic_fts"},
            headers=mock_auth_admin,
        )

    # Assert
    assert response.status_code == 409
    data = response.json()
    assert "detail" in data


def test_post_without_auth_returns_401(test_client, mock_golden_repo_manager):
    """
    AC6: POST without authentication returns 401.

    Test that POST without authentication token returns 401 Unauthorized.
    """
    with patch("code_indexer.server.app.golden_repo_manager", mock_golden_repo_manager):
        # Act
        response = test_client.post(
            "/api/admin/golden-repos/test-repo/indexes", json={"index_type": "temporal"}
        )

    # Assert
    assert response.status_code == 401
