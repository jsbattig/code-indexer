"""
Unit tests for AdminAPIClient.get_golden_repository_branches method.
"""

from unittest.mock import AsyncMock, patch

import pytest

from code_indexer.api_clients.admin_client import AdminAPIClient


class TestAdminClientBranchesMethod:
    """Test AdminAPIClient get_golden_repository_branches method."""

    @pytest.fixture
    def admin_client(self, tmp_path):
        """Create AdminAPIClient instance."""
        return AdminAPIClient(
            server_url="https://test-server.com",
            credentials={"access_token": "test-token"},
            project_root=tmp_path,
        )

    @pytest.mark.asyncio
    async def test_get_golden_repository_branches_method_exists(self, admin_client):
        """Test that get_golden_repository_branches method exists."""
        assert hasattr(admin_client, "get_golden_repository_branches")
        assert callable(admin_client.get_golden_repository_branches)

    @pytest.mark.asyncio
    async def test_get_golden_repository_branches_calls_correct_endpoint(
        self, admin_client
    ):
        """Test that the method calls the correct API endpoint."""
        from unittest.mock import MagicMock

        with patch.object(
            admin_client, "_authenticated_request", new_callable=AsyncMock
        ) as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "repository_alias": "test-repo",
                "branches": [],
            }
            mock_request.return_value = mock_response

            result = await admin_client.get_golden_repository_branches("test-repo")

            mock_request.assert_called_once_with(
                "GET", "/api/repos/golden/test-repo/branches"
            )
            assert result["repository_alias"] == "test-repo"
