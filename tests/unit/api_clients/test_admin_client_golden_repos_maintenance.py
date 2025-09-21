"""
Test AdminAPIClient golden repository maintenance functionality.

Tests the admin client's ability to list and refresh golden repositories
through the server API with real server integration. Follows Foundation #1
compliance with real server testing and minimal mocking.
"""

import asyncio
import pytest
import tempfile
from pathlib import Path
from typing import Dict, Any

from code_indexer.api_clients.admin_client import AdminAPIClient
from code_indexer.api_clients.base_client import (
    APIClientError,
    AuthenticationError,
    NetworkError,
)
from tests.infrastructure.test_cidx_server import CIDXServerTestContext


class TestAdminAPIClientGoldenReposMaintenanceRealServer:
    """Test golden repository maintenance with real CIDX server - Foundation #1 compliant."""

    @pytest.fixture
    def test_server(self):
        """Start real CIDX server for testing."""

        async def _start_server():
            context = CIDXServerTestContext()
            server = await context.__aenter__()
            server.server_url = context.base_url  # Add server_url to server object
            return server, context

        async def _stop_server(context):
            await context.__aexit__(None, None, None)

        # Start server
        loop = asyncio.get_event_loop()
        server, context = loop.run_until_complete(_start_server())

        try:
            yield server
        finally:
            # Stop server
            loop.run_until_complete(_stop_server(context))

    @pytest.fixture
    def admin_credentials(self) -> Dict[str, Any]:
        """Admin credentials for testing."""
        return {
            "username": "admin",
            "password": "admin123",
        }

    @pytest.fixture
    def user_credentials(self) -> Dict[str, Any]:
        """Regular user credentials for testing."""
        return {
            "username": "testuser",
            "password": "testpass123",
        }

    @pytest.fixture
    def temp_project_root(self):
        """Create temporary project root for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.mark.asyncio
    async def test_list_golden_repositories_success_with_admin_credentials(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test successful golden repository listing with admin credentials."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            # List golden repositories (should work even if empty)
            result = await admin_client.list_golden_repositories()

            # Verify response structure
            assert "golden_repositories" in result
            assert "total" in result
            assert isinstance(result["golden_repositories"], list)
            assert isinstance(result["total"], int)
            assert result["total"] >= 0

        finally:
            await admin_client.close()

    @pytest.mark.asyncio
    async def test_list_golden_repositories_insufficient_privileges_with_regular_user(
        self, test_server, user_credentials, temp_project_root
    ):
        """Test golden repository listing fails with insufficient privileges."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=user_credentials,  # Non-admin user
            project_root=temp_project_root,
        )

        try:
            with pytest.raises(AuthenticationError) as exc_info:
                await admin_client.list_golden_repositories()

            assert "admin role required" in str(exc_info.value).lower()

        finally:
            await admin_client.close()

    @pytest.mark.asyncio
    async def test_refresh_golden_repository_not_found(
        self, test_server, admin_credentials, temp_project_root
    ):
        """Test refresh golden repository with non-existent alias."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            with pytest.raises(APIClientError) as exc_info:
                await admin_client.refresh_golden_repository("non-existent-repo")

            assert exc_info.value.status_code == 404
            assert "not found" in str(exc_info.value).lower()

        finally:
            await admin_client.close()

    @pytest.mark.asyncio
    async def test_refresh_golden_repository_insufficient_privileges_with_regular_user(
        self, test_server, user_credentials, temp_project_root
    ):
        """Test refresh golden repository with insufficient privileges."""
        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=user_credentials,  # Non-admin user
            project_root=temp_project_root,
        )

        try:
            with pytest.raises(AuthenticationError) as exc_info:
                await admin_client.refresh_golden_repository("test-repo")

            assert "admin role required" in str(exc_info.value).lower()

        finally:
            await admin_client.close()

    @pytest.mark.asyncio
    async def test_authentication_error_with_invalid_credentials_for_list(
        self, test_server, temp_project_root
    ):
        """Test list golden repositories fails with invalid credentials."""
        invalid_credentials = {
            "username": "nonexistent",
            "password": "wrongpass",
        }

        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=invalid_credentials,
            project_root=temp_project_root,
        )

        try:
            with pytest.raises(AuthenticationError):
                await admin_client.list_golden_repositories()

        finally:
            await admin_client.close()

    @pytest.mark.asyncio
    async def test_authentication_error_with_invalid_credentials_for_refresh(
        self, test_server, temp_project_root
    ):
        """Test refresh golden repository fails with invalid credentials."""
        invalid_credentials = {
            "username": "nonexistent",
            "password": "wrongpass",
        }

        admin_client = AdminAPIClient(
            server_url=test_server.server_url,
            credentials=invalid_credentials,
            project_root=temp_project_root,
        )

        try:
            with pytest.raises(AuthenticationError):
                await admin_client.refresh_golden_repository("test-repo")

        finally:
            await admin_client.close()

    @pytest.mark.asyncio
    async def test_network_error_with_invalid_server_url_for_list(
        self, admin_credentials, temp_project_root
    ):
        """Test list golden repositories with network error handling."""
        admin_client = AdminAPIClient(
            server_url="http://nonexistent.invalid:9999",
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            with pytest.raises((NetworkError, APIClientError)):
                await admin_client.list_golden_repositories()

        finally:
            await admin_client.close()

    @pytest.mark.asyncio
    async def test_network_error_with_invalid_server_url_for_refresh(
        self, admin_credentials, temp_project_root
    ):
        """Test refresh golden repository with network error handling."""
        admin_client = AdminAPIClient(
            server_url="http://nonexistent.invalid:9999",
            credentials=admin_credentials,
            project_root=temp_project_root,
        )

        try:
            with pytest.raises((NetworkError, APIClientError)):
                await admin_client.refresh_golden_repository("test-repo")

        finally:
            await admin_client.close()


class TestAdminAPIClientMethodSignatures:
    """Test method signatures and parameter validation."""

    def test_list_golden_repositories_method_signature(self):
        """Test list_golden_repositories method signature."""
        admin_client = AdminAPIClient(
            server_url="http://localhost:8000",
            credentials={"username": "admin", "password": "admin123"},
        )

        # Method should exist and be callable
        assert hasattr(admin_client, "list_golden_repositories")
        assert callable(getattr(admin_client, "list_golden_repositories"))

        # Verify it's a coroutine function
        method = getattr(admin_client, "list_golden_repositories")
        assert asyncio.iscoroutinefunction(method)

    def test_refresh_golden_repository_method_signature(self):
        """Test refresh_golden_repository method signature."""
        admin_client = AdminAPIClient(
            server_url="http://localhost:8000",
            credentials={"username": "admin", "password": "admin123"},
        )

        # Method should exist and be callable
        assert hasattr(admin_client, "refresh_golden_repository")
        assert callable(getattr(admin_client, "refresh_golden_repository"))

        # Verify it's a coroutine function
        method = getattr(admin_client, "refresh_golden_repository")
        assert asyncio.iscoroutinefunction(method)

    def test_refresh_golden_repository_requires_alias_parameter(self):
        """Test that refresh_golden_repository requires alias parameter."""
        admin_client = AdminAPIClient(
            server_url="http://localhost:8000",
            credentials={"username": "admin", "password": "admin123"},
        )

        # Should raise TypeError if called without required alias parameter
        with pytest.raises(TypeError):
            # This should fail even after implementation if no alias provided
            asyncio.run(admin_client.refresh_golden_repository())
