"""
Integration tests for blocking unsupported operations on composite repositories.

Tests that API endpoints properly return 400 errors for operations that are
not supported on composite repositories while allowing them on single repos.
"""

import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from datetime import datetime

from code_indexer.server.app import create_app
from code_indexer.server.models.activated_repository import ActivatedRepository


@pytest.fixture
def app_with_repos(tmp_path: Path):
    """Create FastAPI app with test repositories."""
    # Create test directory structure
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    activated_repos_dir = data_dir / "activated-repos"
    activated_repos_dir.mkdir()

    # Create user directory
    user_dir = activated_repos_dir / "testuser"
    user_dir.mkdir()

    # Create composite repository
    composite_repo_dir = user_dir / "composite-repo"
    composite_repo_dir.mkdir()
    composite_config_dir = composite_repo_dir / ".code-indexer"
    composite_config_dir.mkdir()

    composite_config = {"proxy_mode": True, "embedding_provider": "voyage-ai"}

    composite_config_file = composite_config_dir / "config.json"
    composite_config_file.write_text(json.dumps(composite_config, indent=2))

    # Create single repository
    single_repo_dir = user_dir / "single-repo"
    single_repo_dir.mkdir()
    single_config_dir = single_repo_dir / ".code-indexer"
    single_config_dir.mkdir()

    single_config = {"proxy_mode": False, "embedding_provider": "voyage-ai"}

    single_config_file = single_config_dir / "config.json"
    single_config_file.write_text(json.dumps(single_config, indent=2))

    # Create metadata files
    composite_metadata = ActivatedRepository(
        user_alias="composite-repo",
        username="testuser",
        path=composite_repo_dir,
        activated_at=datetime.now(),
        last_accessed=datetime.now(),
        is_composite=True,
        golden_repo_aliases=["repo1", "repo2"],
    )

    single_metadata = ActivatedRepository(
        user_alias="single-repo",
        username="testuser",
        path=single_repo_dir,
        activated_at=datetime.now(),
        last_accessed=datetime.now(),
        golden_repo_alias="test-golden-repo",
        current_branch="main",
    )

    composite_metadata_file = composite_repo_dir / ".cidx-metadata.json"
    composite_metadata_file.write_text(
        json.dumps(composite_metadata.to_dict(), indent=2)
    )

    single_metadata_file = single_repo_dir / ".cidx-metadata.json"
    single_metadata_file.write_text(json.dumps(single_metadata.to_dict(), indent=2))

    # Create app with test configuration
    app = create_app()

    # Override activated repo manager data directory
    from code_indexer.server.repositories import activated_repo_manager as arm_module

    arm_module.activated_repo_manager.activated_repos_dir = activated_repos_dir

    yield app


@pytest.fixture
def test_client(app_with_repos):
    """Create test client with authentication."""
    return TestClient(app_with_repos)


@pytest.fixture
def auth_headers():
    """Create authentication headers for test requests."""
    # Note: In real tests, this would use proper authentication
    # For now, we'll assume the endpoint is accessible
    return {}


class TestBlockedOperationsOnCompositeRepos:
    """Test suite for blocked operations on composite repositories."""

    def test_branch_switch_returns_400_for_composite_repo(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test that branch switch endpoint returns 400 for composite repos."""
        response = test_client.put(
            "/api/repos/composite-repo/branch",
            json={"branch_name": "feature-branch", "create": False},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert (
            "Branch operations are not supported for composite repositories"
            in response.json()["detail"]
        )

    def test_branch_list_returns_400_for_composite_repo(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test that branch list endpoint returns 400 for composite repos."""
        response = test_client.get(
            "/api/repositories/composite-repo/branches",
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert (
            "Branch operations are not supported for composite repositories"
            in response.json()["detail"]
        )

    def test_sync_returns_400_for_composite_repo(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test that sync endpoint returns 400 for composite repos."""
        response = test_client.put(
            "/api/repos/composite-repo/sync",
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert (
            "Sync is not supported for composite repositories"
            in response.json()["detail"]
        )

    def test_branch_switch_works_for_single_repo(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test that branch switch endpoint works for single repos."""
        # This will fail with different error (e.g., branch not found, git error)
        # but it should NOT return 400 with "not supported for composite" message
        response = test_client.put(
            "/api/repos/single-repo/branch",
            json={"branch_name": "feature-branch", "create": False},
            headers=auth_headers,
        )

        # Should not be blocked as composite repo operation
        # It may fail for other reasons, but not with composite repo error
        if response.status_code == 400:
            assert (
                "composite repositories"
                not in response.json().get("detail", "").lower()
            )

    def test_branch_list_works_for_single_repo(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test that branch list endpoint works for single repos."""
        response = test_client.get(
            "/api/repositories/single-repo/branches",
            headers=auth_headers,
        )

        # Should not be blocked as composite repo operation
        if response.status_code == 400:
            assert (
                "composite repositories"
                not in response.json().get("detail", "").lower()
            )

    def test_sync_works_for_single_repo(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test that sync endpoint works for single repos."""
        response = test_client.put(
            "/api/repos/single-repo/sync",
            headers=auth_headers,
        )

        # Should not be blocked as composite repo operation
        if response.status_code == 400:
            assert (
                "composite repositories"
                not in response.json().get("detail", "").lower()
            )

    def test_error_response_format_is_correct(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test that error response format matches FastAPI HTTPException format."""
        response = test_client.put(
            "/api/repos/composite-repo/branch",
            json={"branch_name": "test", "create": False},
            headers=auth_headers,
        )

        assert response.status_code == 400
        response_data = response.json()
        assert "detail" in response_data
        assert isinstance(response_data["detail"], str)

    def test_validation_happens_before_operation_attempt(
        self, test_client: TestClient, auth_headers: dict
    ):
        """Test that validation happens early (before attempting git operations)."""
        # If validation happens early, we should get consistent 400 error
        # regardless of repository state (e.g., no git repo, no branches, etc.)

        response = test_client.put(
            "/api/repos/composite-repo/branch",
            json={"branch_name": "any-branch", "create": False},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "composite repositories" in response.json()["detail"].lower()

        # Try sync as well
        response = test_client.put(
            "/api/repos/composite-repo/sync",
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "composite repositories" in response.json()["detail"].lower()
