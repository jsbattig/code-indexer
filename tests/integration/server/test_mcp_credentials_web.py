"""
Integration tests for MCP Credentials Web UI routes.

Tests the web UI rendering for MCP credential management pages.
Addresses Story #614 code review rejection - E2E tests for web routes.
"""

import pytest
from fastapi.testclient import TestClient

from src.code_indexer.server.app import create_app
from src.code_indexer.server.auth.user_manager import UserManager, UserRole


@pytest.fixture
def temp_users_file(tmp_path):
    """Create temporary users file for testing."""
    users_file = tmp_path / "users.json"
    return str(users_file)


@pytest.fixture
def user_manager(temp_users_file):
    """Create UserManager instance with temporary file."""
    manager = UserManager(users_file_path=temp_users_file)
    manager.seed_initial_admin()
    # Create test user
    manager.create_user("testuser", "Test123!@#Password", UserRole.NORMAL_USER)
    return manager


@pytest.fixture
def client(user_manager):
    """Create test client with session-based authentication."""
    import src.code_indexer.server.auth.dependencies as dependencies

    # Store original manager
    original_deps_user_manager = dependencies.user_manager

    # Override with test manager
    dependencies.user_manager = user_manager

    # Create app
    app = create_app()

    # Create client
    test_client = TestClient(app)

    # Login to get session
    test_client.post(
        "/user/login",
        data={"username": "testuser", "password": "Test123!@#Password"},
        follow_redirects=False,
    )

    yield test_client

    # Restore original manager
    dependencies.user_manager = original_deps_user_manager


class TestMCPCredentialsWebUI:
    """Test MCP Credentials Web UI routes."""

    def test_mcp_credentials_page_renders(self, client):
        """
        AC1: User accesses MCP Credentials page.

        Verifies:
        - GET /user/mcp-credentials returns 200
        - Page contains expected UI elements
        - Page contains generate button
        """
        response = client.get("/user/mcp-credentials")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

        # Verify page contains expected UI elements
        content = response.text
        assert "MCP Credential Management" in content
        assert "Generate New Credential" in content
        assert "mcp-credentials-list-section" in content

    def test_mcp_credentials_page_requires_auth(self, temp_users_file):
        """AC1: MCP Credentials page requires authentication."""
        import src.code_indexer.server.auth.dependencies as dependencies

        # Create fresh user manager
        manager = UserManager(users_file_path=temp_users_file)
        manager.seed_initial_admin()
        manager.create_user("testuser", "Test123!@#Password", UserRole.NORMAL_USER)

        # Store original manager
        original_deps_user_manager = dependencies.user_manager

        # Override with test manager
        dependencies.user_manager = manager

        try:
            # Create app and client WITHOUT logging in
            app = create_app()
            unauth_client = TestClient(app)

            response = unauth_client.get(
                "/user/mcp-credentials", follow_redirects=False
            )

            # Should redirect to login
            assert response.status_code == 303
            assert "/user/login" in response.headers["location"]

        finally:
            # Restore original manager
            dependencies.user_manager = original_deps_user_manager

    def test_mcp_credentials_page_shows_empty_state(self, client):
        """AC2: Page shows empty state when user has no credentials."""
        response = client.get("/user/mcp-credentials")

        assert response.status_code == 200
        content = response.text

        # Should show empty state message
        assert "No MCP credentials found" in content or "No credentials" in content

    def test_mcp_credentials_page_shows_credentials_list(self, client, user_manager):
        """
        AC2: Page shows list of credentials after generation.

        Verifies:
        - Credentials appear in the list
        - Metadata is displayed (name, client_id_prefix, created_at, last_used_at)
        - Delete button is present
        """
        from src.code_indexer.server.auth.mcp_credential_manager import (
            MCPCredentialManager,
        )

        # Generate a credential
        mcp_manager = MCPCredentialManager(user_manager=user_manager)
        result = mcp_manager.generate_credential("testuser", name="Test Web Credential")

        # Access the page
        response = client.get("/user/mcp-credentials")
        assert response.status_code == 200

        content = response.text

        # Verify credential appears in list
        assert "Test Web Credential" in content
        assert result["client_id"][:8] in content  # client_id_prefix

        # Verify action buttons present
        assert "Delete" in content or "delete" in content

    def test_partials_mcp_credentials_list_renders(self, client):
        """
        AC3: HTMX partial returns credentials list HTML.

        Verifies:
        - GET /user/partials/mcp-credentials-list returns 200
        - Returns HTML table with credentials
        """
        response = client.get("/user/partials/mcp-credentials-list")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

        content = response.text

        # Empty state: should show message or table
        # Since no credentials, should show empty message
        assert (
            "No MCP credentials" in content
            or "No credentials" in content
            or "<table" in content
        )

    def test_partials_mcp_credentials_list_shows_credentials(
        self, client, user_manager
    ):
        """
        AC3: HTMX partial shows credentials table when credentials exist.

        Verifies:
        - Partial returns HTML table
        - Table contains credential metadata
        - Table contains delete buttons
        """
        from src.code_indexer.server.auth.mcp_credential_manager import (
            MCPCredentialManager,
        )

        # Generate two credentials
        mcp_manager = MCPCredentialManager(user_manager=user_manager)
        result1 = mcp_manager.generate_credential("testuser", name="Credential 1")
        result2 = mcp_manager.generate_credential("testuser", name="Credential 2")

        # Get partial
        response = client.get("/user/partials/mcp-credentials-list")
        assert response.status_code == 200

        content = response.text

        # Should contain table
        assert "<table" in content
        assert "<thead>" in content
        assert "<tbody>" in content

        # Should contain both credentials
        assert "Credential 1" in content
        assert "Credential 2" in content

        # Should contain client_id_prefixes
        assert result1["client_id"][:8] in content
        assert result2["client_id"][:8] in content

        # Should contain delete buttons
        assert "deleteCredential" in content

    def test_partials_mcp_credentials_list_requires_auth(self, temp_users_file):
        """AC3: HTMX partial requires authentication."""
        import src.code_indexer.server.auth.dependencies as dependencies

        # Create fresh user manager
        manager = UserManager(users_file_path=temp_users_file)
        manager.seed_initial_admin()
        manager.create_user("testuser", "Test123!@#Password", UserRole.NORMAL_USER)

        # Store original manager
        original_deps_user_manager = dependencies.user_manager

        # Override with test manager
        dependencies.user_manager = manager

        try:
            # Create app and client WITHOUT logging in
            app = create_app()
            unauth_client = TestClient(app)

            response = unauth_client.get("/user/partials/mcp-credentials-list")

            # Should return 401 or redirect
            assert response.status_code == 401

        finally:
            # Restore original manager
            dependencies.user_manager = original_deps_user_manager

    def test_web_ui_integration_with_api_workflow(self, client, user_manager):
        """
        AC4: Complete web UI workflow integration.

        Verifies:
        - Page loads successfully
        - API creates credential (tested via API)
        - Partial refresh shows new credential
        - API deletes credential (tested via API)
        - Partial refresh shows empty state
        """
        # Step 1: Load page - should show empty state
        response = client.get("/user/mcp-credentials")
        assert response.status_code == 200
        assert (
            "No MCP credentials" in response.text or "No credentials" in response.text
        )

        # Step 2: Generate credential via API (simulating JavaScript call)
        api_response = client.post("/api/mcp-credentials", json={"name": "Web UI Test"})
        assert api_response.status_code == 201
        credential_id = api_response.json()["credential_id"]

        # Step 3: Refresh partial - should show credential
        partial_response = client.get("/user/partials/mcp-credentials-list")
        assert partial_response.status_code == 200
        assert "Web UI Test" in partial_response.text

        # Step 4: Delete credential via API (simulating JavaScript call)
        delete_response = client.delete(f"/api/mcp-credentials/{credential_id}")
        assert delete_response.status_code == 200

        # Step 5: Refresh partial - should show empty state
        partial_response = client.get("/user/partials/mcp-credentials-list")
        assert partial_response.status_code == 200
        assert (
            "No MCP credentials" in partial_response.text
            or "No credentials" in partial_response.text
        )
