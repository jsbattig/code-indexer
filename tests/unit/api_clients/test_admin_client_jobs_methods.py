"""Unit tests for AdminAPIClient jobs-related methods."""

import pytest

from src.code_indexer.api_clients.admin_client import AdminAPIClient


class TestAdminAPIClientJobsMethods:
    """Tests for AdminAPIClient jobs cleanup methods."""

    @pytest.mark.asyncio
    async def test_cleanup_jobs_method_exists(self):
        """Test that AdminAPIClient has cleanup_jobs method."""
        client = AdminAPIClient(
            server_url="http://test",
            credentials={"username": "admin", "password": "pass"},
            project_root="/test",
        )

        # Check method exists
        assert hasattr(
            client, "cleanup_jobs"
        ), "AdminAPIClient should have cleanup_jobs method"
        assert callable(
            getattr(client, "cleanup_jobs", None)
        ), "cleanup_jobs should be callable"
