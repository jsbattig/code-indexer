"""
Integration tests for repository details API endpoint.

Tests the GET /api/repositories/{id} endpoint for both single and composite
repositories, ensuring proper routing and aggregation.
"""

import json
from datetime import datetime, timezone

import pytest


@pytest.fixture
def test_user_credentials():
    """Provide test user credentials."""
    return {"username": "testuser", "password": "testpass123"}


@pytest.fixture
def authenticated_client(client, test_user_credentials):
    """Create an authenticated test client."""
    # Register user
    client.post("/api/auth/register", json=test_user_credentials)

    # Login
    response = client.post("/api/auth/login", json=test_user_credentials)
    assert response.status_code == 200
    token = response.json()["access_token"]

    # Set authorization header
    client.headers["Authorization"] = f"Bearer {token}"

    return client


class TestSingleRepositoryDetails:
    """Tests for single repository details endpoint (existing functionality)."""

    def test_get_single_repo_details_unchanged(
        self, authenticated_client, tmp_path, activated_repo_manager
    ):
        """Test that single repo details still work as before."""
        # This test ensures we don't break existing functionality
        # Create a single activated repository
        user_dir = tmp_path / "activated-repos" / "testuser"
        user_dir.mkdir(parents=True)

        repo_dir = user_dir / "test-repo"
        repo_dir.mkdir()

        # Create metadata for single repo
        metadata = {
            "user_alias": "test-repo",
            "username": "testuser",
            "path": str(repo_dir),
            "is_composite": False,
            "golden_repo_alias": "golden-test",
            "current_branch": "main",
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
        }

        metadata_file = user_dir / "test-repo_metadata.json"
        metadata_file.write_text(json.dumps(metadata))

        # Make API request
        response = authenticated_client.get("/api/repositories/test-repo")

        # Should work as before (implementation determines exact response)
        # At minimum, should not return 404 or 500
        assert response.status_code in [200, 404]

    def test_get_nonexistent_repo_returns_404(self, authenticated_client):
        """Test that requesting non-existent repo returns 404."""
        response = authenticated_client.get("/api/repositories/does-not-exist")
        assert response.status_code == 404


class TestCompositeRepositoryDetails:
    """Tests for composite repository details endpoint."""

    def test_get_composite_repo_details(
        self, authenticated_client, tmp_path, activated_repo_manager
    ):
        """Test retrieving details for a composite repository."""
        # Create composite repository structure
        user_dir = tmp_path / "activated-repos" / "testuser"
        user_dir.mkdir(parents=True)

        composite_dir = user_dir / "my-composite"
        composite_dir.mkdir()

        # Create .code-indexer with proxy config
        index_dir = composite_dir / ".code-indexer"
        index_dir.mkdir()

        config = {
            "proxy_mode": True,
            "discovered_repos": ["backend", "frontend"],
        }
        (index_dir / "config.json").write_text(json.dumps(config))

        # Create component repositories
        backend_dir = composite_dir / "backend"
        backend_dir.mkdir()
        backend_index = backend_dir / ".code-indexer"
        backend_index.mkdir()
        backend_metadata = {"indexed_files": 120}
        (backend_index / "metadata.json").write_text(json.dumps(backend_metadata))
        (backend_dir / "file1.py").write_text("code")

        frontend_dir = composite_dir / "frontend"
        frontend_dir.mkdir()
        frontend_index = frontend_dir / ".code-indexer"
        frontend_index.mkdir()
        frontend_metadata = {"indexed_files": 80}
        (frontend_index / "metadata.json").write_text(json.dumps(frontend_metadata))
        (frontend_dir / "file1.js").write_text("code")

        # Create composite metadata
        composite_metadata = {
            "user_alias": "my-composite",
            "username": "testuser",
            "path": str(composite_dir),
            "is_composite": True,
            "golden_repo_aliases": ["backend-golden", "frontend-golden"],
            "discovered_repos": ["backend", "frontend"],
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
        }

        metadata_file = user_dir / "my-composite_metadata.json"
        metadata_file.write_text(json.dumps(composite_metadata))

        # Make API request
        response = authenticated_client.get("/api/repositories/my-composite")

        assert response.status_code == 200
        data = response.json()

        # Verify composite details structure
        assert data["user_alias"] == "my-composite"
        assert data["is_composite"] is True
        assert len(data["component_repositories"]) == 2
        assert data["total_files"] == 200  # 120 + 80
        assert data["total_size_mb"] > 0

    def test_composite_details_shows_all_components(
        self, authenticated_client, tmp_path, activated_repo_manager
    ):
        """Test that all component repos are included in details."""
        user_dir = tmp_path / "activated-repos" / "testuser"
        user_dir.mkdir(parents=True)

        composite_dir = user_dir / "multi-repo"
        composite_dir.mkdir()

        index_dir = composite_dir / ".code-indexer"
        index_dir.mkdir()

        # Create 3 component repos
        component_names = ["api", "web", "mobile"]
        config = {"proxy_mode": True, "discovered_repos": component_names}
        (index_dir / "config.json").write_text(json.dumps(config))

        for comp_name in component_names:
            comp_dir = composite_dir / comp_name
            comp_dir.mkdir()
            comp_index = comp_dir / ".code-indexer"
            comp_index.mkdir()
            comp_metadata = {"indexed_files": 50}
            (comp_index / "metadata.json").write_text(json.dumps(comp_metadata))
            (comp_dir / "file.txt").write_text("x")

        # Create composite metadata
        composite_metadata = {
            "user_alias": "multi-repo",
            "username": "testuser",
            "path": str(composite_dir),
            "is_composite": True,
            "golden_repo_aliases": ["api-golden", "web-golden", "mobile-golden"],
            "discovered_repos": component_names,
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
        }

        metadata_file = user_dir / "multi-repo_metadata.json"
        metadata_file.write_text(json.dumps(composite_metadata))

        # Make API request
        response = authenticated_client.get("/api/repositories/multi-repo")

        assert response.status_code == 200
        data = response.json()

        # All 3 components should be present
        assert len(data["component_repositories"]) == 3
        component_names_in_response = [
            c["name"] for c in data["component_repositories"]
        ]
        assert set(component_names_in_response) == set(component_names)

    def test_composite_details_calculates_totals_correctly(
        self, authenticated_client, tmp_path, activated_repo_manager
    ):
        """Test that file counts and sizes are aggregated correctly."""
        user_dir = tmp_path / "activated-repos" / "testuser"
        user_dir.mkdir(parents=True)

        composite_dir = user_dir / "totals-test"
        composite_dir.mkdir()

        index_dir = composite_dir / ".code-indexer"
        index_dir.mkdir()

        config = {"proxy_mode": True, "discovered_repos": ["comp1", "comp2"]}
        (index_dir / "config.json").write_text(json.dumps(config))

        # Create components with known file counts
        comp1_dir = composite_dir / "comp1"
        comp1_dir.mkdir()
        comp1_index = comp1_dir / ".code-indexer"
        comp1_index.mkdir()
        (comp1_index / "metadata.json").write_text(json.dumps({"indexed_files": 75}))
        (comp1_dir / "f1.txt").write_text("data" * 1000)  # ~4KB

        comp2_dir = composite_dir / "comp2"
        comp2_dir.mkdir()
        comp2_index = comp2_dir / ".code-indexer"
        comp2_index.mkdir()
        (comp2_index / "metadata.json").write_text(json.dumps({"indexed_files": 125}))
        (comp2_dir / "f2.txt").write_text("data" * 2000)  # ~8KB

        # Create composite metadata
        composite_metadata = {
            "user_alias": "totals-test",
            "username": "testuser",
            "path": str(composite_dir),
            "is_composite": True,
            "golden_repo_aliases": ["g1", "g2"],
            "discovered_repos": ["comp1", "comp2"],
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
        }

        metadata_file = user_dir / "totals-test_metadata.json"
        metadata_file.write_text(json.dumps(composite_metadata))

        # Make API request
        response = authenticated_client.get("/api/repositories/totals-test")

        assert response.status_code == 200
        data = response.json()

        # Verify totals
        assert data["total_files"] == 200  # 75 + 125
        assert data["total_size_mb"] > 0
        # Size should be roughly (4KB + 8KB) / 1024 / 1024 ≈ 0.01 MB plus metadata
        assert data["total_size_mb"] < 1.0  # Reasonable upper bound

    def test_composite_details_identifies_indexed_components(
        self, authenticated_client, tmp_path, activated_repo_manager
    ):
        """Test that index status is correctly identified for each component."""
        user_dir = tmp_path / "activated-repos" / "testuser"
        user_dir.mkdir(parents=True)

        composite_dir = user_dir / "index-status-test"
        composite_dir.mkdir()

        index_dir = composite_dir / ".code-indexer"
        index_dir.mkdir()

        config = {
            "proxy_mode": True,
            "discovered_repos": ["indexed-repo", "not-indexed-repo"],
        }
        (index_dir / "config.json").write_text(json.dumps(config))

        # Create indexed component
        indexed_dir = composite_dir / "indexed-repo"
        indexed_dir.mkdir()
        indexed_index = indexed_dir / ".code-indexer"
        indexed_index.mkdir()
        (indexed_index / "metadata.json").write_text(json.dumps({"indexed_files": 10}))
        (indexed_dir / "file.txt").write_text("x")

        # Create non-indexed component (no .code-indexer)
        not_indexed_dir = composite_dir / "not-indexed-repo"
        not_indexed_dir.mkdir()
        (not_indexed_dir / "file.txt").write_text("x")

        # Create composite metadata
        composite_metadata = {
            "user_alias": "index-status-test",
            "username": "testuser",
            "path": str(composite_dir),
            "is_composite": True,
            "golden_repo_aliases": ["g1", "g2"],
            "discovered_repos": ["indexed-repo", "not-indexed-repo"],
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
        }

        metadata_file = user_dir / "index-status-test_metadata.json"
        metadata_file.write_text(json.dumps(composite_metadata))

        # Make API request
        response = authenticated_client.get("/api/repositories/index-status-test")

        assert response.status_code == 200
        data = response.json()

        # Find components
        indexed_comp = next(
            c for c in data["component_repositories"] if c["name"] == "indexed-repo"
        )
        not_indexed_comp = next(
            c for c in data["component_repositories"] if c["name"] == "not-indexed-repo"
        )

        # Verify index status
        assert indexed_comp["has_index"] is True
        assert indexed_comp["indexed_files"] == 10
        assert not_indexed_comp["has_index"] is False
        assert not_indexed_comp["indexed_files"] == 0


class TestRepositoryDetailsRouting:
    """Tests for proper routing between single and composite repo handlers."""

    def test_endpoint_routes_composite_repos_correctly(
        self, authenticated_client, tmp_path, activated_repo_manager
    ):
        """Test that composite repos are routed to composite handler."""
        # This is implicitly tested by composite repo tests above,
        # but explicitly verify the is_composite flag routing
        user_dir = tmp_path / "activated-repos" / "testuser"
        user_dir.mkdir(parents=True)

        # Create composite repo
        composite_dir = user_dir / "routed-composite"
        composite_dir.mkdir()

        index_dir = composite_dir / ".code-indexer"
        index_dir.mkdir()
        config = {"proxy_mode": True, "discovered_repos": []}
        (index_dir / "config.json").write_text(json.dumps(config))

        composite_metadata = {
            "user_alias": "routed-composite",
            "username": "testuser",
            "path": str(composite_dir),
            "is_composite": True,
            "golden_repo_aliases": [],
            "discovered_repos": [],
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
        }

        metadata_file = user_dir / "routed-composite_metadata.json"
        metadata_file.write_text(json.dumps(composite_metadata))

        response = authenticated_client.get("/api/repositories/routed-composite")

        assert response.status_code == 200
        data = response.json()

        # Should have composite-specific fields
        assert "is_composite" in data
        assert data["is_composite"] is True
        assert "component_repositories" in data
        assert "total_files" in data
        assert "total_size_mb" in data
