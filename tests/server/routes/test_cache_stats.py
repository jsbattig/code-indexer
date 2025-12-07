"""
Tests for /cache/stats REST API endpoint.

Story #526: HNSW Index Cache - Cache statistics HTTP endpoint.
TDD tests written FIRST before implementation.
"""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from code_indexer.server.auth.user_manager import User, UserRole


@pytest.fixture
def test_app_with_cache_stats():
    """Create test app with cache stats route."""
    # Import main app creation function
    from code_indexer.server.app import create_app
    from code_indexer.server.auth.dependencies import get_current_user

    # Create app
    app = create_app()

    # Override auth dependency for testing
    def override_get_current_user():
        return User(
            username="testuser",
            password_hash="dummy_hash",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

    app.dependency_overrides[get_current_user] = override_get_current_user

    return TestClient(app)


@pytest.fixture
def test_app_no_auth():
    """Create test app without auth override."""
    from code_indexer.server.app import create_app

    app = create_app()
    return TestClient(app)


class TestCacheStatsEndpoint:
    """Tests for GET /cache/stats endpoint."""

    def test_cache_stats_endpoint_exists(self, test_app_with_cache_stats):
        """Test that /cache/stats endpoint exists and responds."""
        client = test_app_with_cache_stats

        response = client.get("/cache/stats")

        # Should NOT return 404
        assert response.status_code != 404, "Endpoint should exist"

    def test_cache_stats_returns_valid_structure(self, test_app_with_cache_stats):
        """Test that /cache/stats returns valid statistics structure."""
        client = test_app_with_cache_stats

        response = client.get("/cache/stats")

        assert response.status_code == 200
        data = response.json()

        # Verify expected fields exist
        assert "cached_repositories" in data
        assert "total_memory_mb" in data
        assert "hit_count" in data
        assert "miss_count" in data
        assert "eviction_count" in data
        assert "per_repository_stats" in data

        # Verify field types
        assert isinstance(data["cached_repositories"], int)
        assert isinstance(data["total_memory_mb"], (int, float))
        assert isinstance(data["hit_count"], int)
        assert isinstance(data["miss_count"], int)
        assert isinstance(data["eviction_count"], int)
        assert isinstance(data["per_repository_stats"], dict)

    def test_cache_stats_calculates_hit_ratio(self, test_app_with_cache_stats):
        """Test that /cache/stats includes hit_ratio calculation."""
        client = test_app_with_cache_stats

        response = client.get("/cache/stats")

        assert response.status_code == 200
        data = response.json()

        # Hit ratio should be present
        assert "hit_ratio" in data
        assert isinstance(data["hit_ratio"], float)

        # Hit ratio should be between 0.0 and 1.0
        assert 0.0 <= data["hit_ratio"] <= 1.0

    def test_cache_stats_requires_authentication(self, test_app_no_auth):
        """Test that /cache/stats requires authentication."""
        client = test_app_no_auth

        # Call without authentication
        response = client.get("/cache/stats")

        # Should return 401 Unauthorized or 403 Forbidden
        assert response.status_code in [
            401,
            403,
        ], "Unauthenticated request should be rejected"

    def test_cache_stats_per_repository_structure(self, test_app_with_cache_stats):
        """Test that per_repository_stats has correct structure when populated."""
        client = test_app_with_cache_stats

        response = client.get("/cache/stats")

        assert response.status_code == 200
        data = response.json()

        per_repo = data["per_repository_stats"]

        # If there are cached repositories, verify their structure
        if per_repo:
            for repo_path, stats in per_repo.items():
                assert isinstance(repo_path, str)
                assert isinstance(stats, dict)

                # Verify expected stats fields
                assert "access_count" in stats
                assert "last_accessed" in stats
                assert "created_at" in stats
                assert "ttl_remaining_seconds" in stats

                # Verify field types
                assert isinstance(stats["access_count"], int)
                assert isinstance(stats["last_accessed"], str)
                assert isinstance(stats["created_at"], str)
                assert isinstance(stats["ttl_remaining_seconds"], (int, float))

    def test_cache_stats_initial_state(self, test_app_with_cache_stats):
        """Test cache stats in initial state (before any queries)."""
        client = test_app_with_cache_stats

        response = client.get("/cache/stats")

        assert response.status_code == 200
        data = response.json()

        # Initial state should have zero or minimal values
        # (depending on whether other tests have run)
        assert data["cached_repositories"] >= 0
        assert data["hit_count"] >= 0
        assert data["miss_count"] >= 0
        assert data["eviction_count"] >= 0

    def test_cache_stats_idempotent(self, test_app_with_cache_stats):
        """Test that calling /cache/stats multiple times is idempotent."""
        client = test_app_with_cache_stats

        response1 = client.get("/cache/stats")
        response2 = client.get("/cache/stats")

        assert response1.status_code == 200
        assert response2.status_code == 200

        # Stats should be consistent (or hit_count may increment if stats access is cached)
        data1 = response1.json()
        data2 = response2.json()

        # Cached repositories count should be stable
        assert data1["cached_repositories"] == data2["cached_repositories"]
