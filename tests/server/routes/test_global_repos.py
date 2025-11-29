"""
Tests for REST API global repos endpoints.

TDD tests written FIRST before implementation.
"""

import json
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def temp_golden_repos_dir():
    """Create temporary golden repos directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        golden_dir = Path(tmpdir) / "golden-repos"
        golden_dir.mkdir(parents=True)
        (golden_dir / "aliases").mkdir()

        # Create test registry
        test_repos = {
            "test-repo-global": {
                "repo_name": "test-repo",
                "alias_name": "test-repo-global",
                "repo_url": "https://github.com/test/repo.git",
                "index_path": "/path/to/test-repo",
                "created_at": "2025-01-01T00:00:00+00:00",
                "last_refresh": "2025-01-01T12:00:00+00:00",
            }
        }

        registry_file = golden_dir / "global_registry.json"
        registry_file.write_text(json.dumps(test_repos, indent=2))

        yield str(golden_dir)


@pytest.fixture
def test_app_with_global_routes(temp_golden_repos_dir, monkeypatch):
    """Create test app with global routes configured."""
    # Set golden repos directory environment variable
    monkeypatch.setenv("GOLDEN_REPOS_DIR", temp_golden_repos_dir)

    # Import after monkeypatch to pick up environment
    from code_indexer.server.global_routes.routes import router, set_golden_repos_dir
    from fastapi import FastAPI
    from code_indexer.server.auth.user_manager import User, UserRole
    from datetime import datetime, timezone

    # Set the golden repos directory
    set_golden_repos_dir(temp_golden_repos_dir)

    # Create test app
    app = FastAPI()
    app.include_router(router)

    # Add auth dependency override for testing
    from code_indexer.server.auth.dependencies import get_current_user

    def override_get_current_user():
        return User(
            username="testuser",
            password_hash="dummy_hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )

    app.dependency_overrides[get_current_user] = override_get_current_user

    return TestClient(app)


class TestListGlobalRepos:
    """Tests for GET /global/repos endpoint."""

    def test_get_global_repos_returns_list(self, test_app_with_global_routes):
        """Test that GET /global/repos returns list of repos."""
        client = test_app_with_global_routes

        response = client.get("/global/repos")

        assert response.status_code == 200
        data = response.json()

        assert "repos" in data
        assert isinstance(data["repos"], list)
        assert len(data["repos"]) == 1

        repo = data["repos"][0]
        assert repo["alias"] == "test-repo-global"
        assert repo["repo_name"] == "test-repo"

    def test_get_global_repos_requires_authentication(self):
        """Test that endpoint requires authentication."""
        # Create app without auth override
        from code_indexer.server.global_routes.routes import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get("/global/repos")

        assert response.status_code == 401


class TestGetRepoStatus:
    """Tests for GET /global/repos/{alias}/status endpoint."""

    def test_get_repo_status_returns_metadata(self, test_app_with_global_routes):
        """Test that GET /global/repos/{alias}/status returns repo metadata."""
        client = test_app_with_global_routes

        response = client.get("/global/repos/test-repo-global/status")

        assert response.status_code == 200
        data = response.json()

        assert data["alias"] == "test-repo-global"
        assert data["repo_name"] == "test-repo"
        assert data["url"] == "https://github.com/test/repo.git"
        assert "last_refresh" in data

    def test_get_repo_status_404_for_nonexistent(self, test_app_with_global_routes):
        """Test that GET /global/repos/{alias}/status returns 404 for non-existent repo."""
        client = test_app_with_global_routes

        response = client.get("/global/repos/nonexistent-global/status")

        assert response.status_code == 404
        data = response.json()

        assert "detail" in data
        assert "nonexistent-global" in data["detail"]


class TestGetGlobalConfig:
    """Tests for GET /global/config endpoint."""

    def test_get_config_returns_interval(
        self, test_app_with_global_routes, temp_golden_repos_dir
    ):
        """Test that GET /global/config returns refresh interval."""
        # Create config file
        config_file = Path(temp_golden_repos_dir) / "global_config.json"
        config_file.write_text(json.dumps({"refresh_interval": 3600}))

        client = test_app_with_global_routes

        response = client.get("/global/config")

        assert response.status_code == 200
        data = response.json()

        assert "refresh_interval" in data
        assert data["refresh_interval"] == 3600

    def test_get_config_returns_default_if_not_exists(
        self, test_app_with_global_routes
    ):
        """Test that GET /global/config returns default config if file doesn't exist."""
        client = test_app_with_global_routes

        response = client.get("/global/config")

        assert response.status_code == 200
        data = response.json()

        assert "refresh_interval" in data
        assert data["refresh_interval"] == 3600  # Default


class TestUpdateGlobalConfig:
    """Tests for PUT /global/config endpoint."""

    def test_put_config_updates_interval(
        self, test_app_with_global_routes, temp_golden_repos_dir
    ):
        """Test that PUT /global/config updates refresh interval."""
        client = test_app_with_global_routes

        response = client.put("/global/config", json={"refresh_interval": 7200})

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "updated"

        # Verify config was saved
        config_file = Path(temp_golden_repos_dir) / "global_config.json"
        with open(config_file, "r") as f:
            config = json.load(f)

        assert config["refresh_interval"] == 7200

    def test_put_config_400_for_invalid_interval(self, test_app_with_global_routes):
        """Test that PUT /global/config returns 422 for invalid interval (Pydantic validation)."""
        client = test_app_with_global_routes

        # Test with interval < 60
        response = client.put("/global/config", json={"refresh_interval": 30})

        # Pydantic validation returns 422, not 400
        assert response.status_code == 422
        data = response.json()

        assert "detail" in data

    def test_put_config_validates_minimum_values(self, test_app_with_global_routes):
        """Test various invalid values for refresh interval."""
        client = test_app_with_global_routes

        invalid_values = [0, -100, 59, 30]

        for value in invalid_values:
            response = client.put("/global/config", json={"refresh_interval": value})

            # Pydantic validation returns 422 for invalid values
            assert response.status_code == 422, f"Expected 422 for value {value}"

    def test_put_config_accepts_valid_values(self, test_app_with_global_routes):
        """Test that valid values are accepted."""
        client = test_app_with_global_routes

        valid_values = [60, 3600, 86400]

        for value in valid_values:
            response = client.put("/global/config", json={"refresh_interval": value})

            assert response.status_code == 200, f"Expected 200 for value {value}"


class TestErrorParity:
    """Tests for error response consistency."""

    def test_repo_not_found_error_format(self, test_app_with_global_routes):
        """Test that repo not found error has consistent format."""
        client = test_app_with_global_routes

        response = client.get("/global/repos/missing-global/status")

        assert response.status_code == 404
        data = response.json()

        assert "detail" in data
        assert isinstance(data["detail"], str)
        assert "not found" in data["detail"].lower()

    def test_invalid_config_error_format(self, test_app_with_global_routes):
        """Test that invalid config error has consistent format."""
        client = test_app_with_global_routes

        response = client.put("/global/config", json={"refresh_interval": 30})

        # Pydantic validation returns 422
        assert response.status_code == 422
        data = response.json()

        assert "detail" in data
        assert isinstance(
            data["detail"], (str, list)
        )  # Pydantic returns list of validation errors
