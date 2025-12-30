"""Integration tests for OIDC authentication flow.

Tests the complete OIDC authentication flow using a mock OIDC server,
including JIT provisioning, email-based auto-linking, and error handling.
"""
import pytest
from pathlib import Path
import tempfile
import shutil


@pytest.fixture
def test_users_file(tmp_path):
    """Provide a temporary users file path for testing."""
    users_file = tmp_path / "test_users.json"
    yield str(users_file)
    # Cleanup
    if users_file.exists():
        users_file.unlink()


@pytest.fixture
def oidc_test_config(mock_oidc_server, test_users_file):
    """Provide OIDC configuration for integration testing."""
    from code_indexer.server.utils.config_manager import OIDCProviderConfig

    return OIDCProviderConfig(
        enabled=True,
        provider_name="TestSSO",
        issuer_url=mock_oidc_server.base_url,
        client_id="test-client-id",
        client_secret="test-client-secret",
        enable_jit_provisioning=True,
        default_role="normal_user",
    )


@pytest.fixture
async def oidc_manager(oidc_test_config, test_users_file, tmp_path):
    """Provide an initialized OIDC manager for testing."""
    from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
    from code_indexer.server.auth.user_manager import UserManager
    from code_indexer.server.auth.jwt_manager import JWTManager

    # Create user manager
    user_manager = UserManager(users_file_path=test_users_file)
    
    # Create JWT manager
    jwt_manager = JWTManager(secret_key="test-secret-key")
    
    # Create OIDC manager with custom db path
    manager = OIDCManager(oidc_test_config, user_manager, jwt_manager)
    manager.db_path = str(tmp_path / "test_oidc.db")
    
    # Initialize (discovers metadata and creates db)
    await manager.initialize()
    
    return manager


class TestOIDCIntegration:
    """Integration tests for OIDC authentication flow."""

    @pytest.mark.asyncio
    async def test_full_oidc_flow_with_jit_provisioning(self, mock_oidc_server, oidc_manager):
        """Test complete OIDC flow: discovery -> token exchange -> userinfo -> user creation."""
        # Configure mock server response
        mock_oidc_server.set_userinfo(
            sub="new-user-12345",
            email="newuser@example.com",
            email_verified=True
        )
        
        # 1. Verify discovery metadata was loaded
        assert oidc_manager.provider is not None
        assert oidc_manager.provider._metadata is not None
        assert oidc_manager.provider._metadata.issuer == mock_oidc_server.base_url
        
        # 2. Exchange authorization code for token
        tokens = await oidc_manager.provider.exchange_code_for_token(
            code="mock-auth-code",
            code_verifier="test-verifier",
            redirect_uri="http://localhost/callback"
        )
        
        assert "access_token" in tokens
        assert tokens["access_token"] == "mock-access-token-12345"
        
        # 3. Get user info from access token
        user_info = await oidc_manager.provider.get_user_info(tokens["access_token"])
        
        assert user_info.subject == "new-user-12345"
        assert user_info.email == "newuser@example.com"
        assert user_info.email_verified is True
        
        # 4. Match or create user (JIT provisioning)
        user = await oidc_manager.match_or_create_user(user_info)
        
        assert user is not None
        # Email stored in users.json, not on User object
        assert user.username.startswith("newuser")  # Generated from email
        
        # 5. Verify OIDC identity was linked in database
        import aiosqlite
        async with aiosqlite.connect(oidc_manager.db_path) as db:
            cursor = await db.execute(
                "SELECT username, subject, email FROM oidc_identity_links WHERE subject = ?",
                ("new-user-12345",)
            )
            result = await cursor.fetchone()
        
        assert result is not None
        assert result[0] == user.username
        assert result[1] == "new-user-12345"
        assert result[2] == "newuser@example.com"

    @pytest.mark.asyncio
    async def test_email_based_auto_linking(self, mock_oidc_server, oidc_manager):
        """Test that existing user with matching email gets auto-linked to OIDC identity."""
        # 1. Create existing user with email
        from code_indexer.server.auth.user_manager import UserRole
        existing_user = oidc_manager.user_manager.create_user(
            username="existinguser",
            password="StrongPassword123!",
            role=UserRole.NORMAL_USER
        )
        
        # Manually add email to user (stored in users.json)
        users_data = oidc_manager.user_manager._load_users()
        users_data["existinguser"]["email"] = "existing@example.com"
        oidc_manager.user_manager._save_users(users_data)
        
        # 2. Configure mock server to return same email
        mock_oidc_server.set_userinfo(
            sub="different-oidc-subject-456",
            email="existing@example.com",
            email_verified=True
        )
        
        # 3. Get tokens and user info
        tokens = await oidc_manager.provider.exchange_code_for_token(
            code="mock-auth-code",
            code_verifier="test-verifier",
            redirect_uri="http://localhost/callback"
        )
        user_info = await oidc_manager.provider.get_user_info(tokens["access_token"])
        
        # 4. Match or create user (should link to existing user)
        matched_user = await oidc_manager.match_or_create_user(user_info)
        
        # Should return existing user, not create new one
        assert matched_user.username == existing_user.username
        
        # 5. Verify OIDC identity was linked
        import aiosqlite
        async with aiosqlite.connect(oidc_manager.db_path) as db:
            cursor = await db.execute(
                "SELECT username, subject FROM oidc_identity_links WHERE subject = ?",
                ("different-oidc-subject-456",)
            )
            result = await cursor.fetchone()
        
        assert result is not None
        assert result[0] == existing_user.username
        assert result[1] == "different-oidc-subject-456"

    @pytest.mark.asyncio
    async def test_returning_oidc_user(self, mock_oidc_server, oidc_manager):
        """Test that returning OIDC user (same subject) gets matched correctly."""
        # 1. First login - creates user
        mock_oidc_server.set_userinfo(
            sub="returning-user-789",
            email="returning@example.com",
            email_verified=True
        )
        
        tokens = await oidc_manager.provider.exchange_code_for_token(
            code="mock-auth-code",
            code_verifier="test-verifier",
            redirect_uri="http://localhost/callback"
        )
        user_info = await oidc_manager.provider.get_user_info(tokens["access_token"])
        first_login_user = await oidc_manager.match_or_create_user(user_info)
        
        # 2. Second login - same subject, should return same user
        tokens2 = await oidc_manager.provider.exchange_code_for_token(
            code="mock-auth-code-2",
            code_verifier="test-verifier-2",
            redirect_uri="http://localhost/callback"
        )
        user_info2 = await oidc_manager.provider.get_user_info(tokens2["access_token"])
        second_login_user = await oidc_manager.match_or_create_user(user_info2)
        
        # Should be the same user
        assert second_login_user.username == first_login_user.username
        # Same user, verified by username

    @pytest.mark.asyncio
    async def test_oidc_discovery_endpoint(self, mock_oidc_server, oidc_manager):
        """Test that OIDC discovery endpoint returns correct metadata."""
        metadata = oidc_manager.provider._metadata
        
        assert metadata.issuer == mock_oidc_server.base_url
        assert metadata.authorization_endpoint == f"{mock_oidc_server.base_url}/authorize"
        assert metadata.token_endpoint == f"{mock_oidc_server.base_url}/token"
        assert metadata.userinfo_endpoint == f"{mock_oidc_server.base_url}/userinfo"

    @pytest.mark.asyncio
    async def test_jwt_session_creation_after_oidc_login(self, mock_oidc_server, oidc_manager):
        """Test that JWT session is created correctly after OIDC login."""
        # Setup user
        mock_oidc_server.set_userinfo(
            sub="session-test-user",
            email="session@example.com",
            email_verified=True
        )
        
        # Get tokens and user info
        tokens = await oidc_manager.provider.exchange_code_for_token(
            code="mock-auth-code",
            code_verifier="test-verifier",
            redirect_uri="http://localhost/callback"
        )
        user_info = await oidc_manager.provider.get_user_info(tokens["access_token"])
        user = await oidc_manager.match_or_create_user(user_info)
        
        # Create JWT session
        jwt_token = oidc_manager.create_jwt_session(user)
        
        assert jwt_token is not None
        assert isinstance(jwt_token, str)
        
        # Verify token can be decoded
        decoded = oidc_manager.jwt_manager.validate_token(jwt_token)
        assert decoded["username"] == user.username
        assert decoded["role"] == user.role.value

    @pytest.mark.asyncio
    async def test_jit_provisioning_disabled(self, mock_oidc_server, test_users_file, tmp_path):
        """Test that JIT provisioning can be disabled."""
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.user_manager import UserManager
        from code_indexer.server.auth.jwt_manager import JWTManager

        # Create config with JIT disabled
        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url=mock_oidc_server.base_url,
            client_id="test-client",
            client_secret="test-secret",
            enable_jit_provisioning=False,  # Disabled
        )

        user_manager = UserManager(users_file_path=test_users_file)
        jwt_manager = JWTManager(secret_key="test-secret")
        
        manager = OIDCManager(config, user_manager, jwt_manager)
        manager.db_path = str(tmp_path / "test_oidc_no_jit.db")
        await manager.initialize()
        
        # Configure mock server
        mock_oidc_server.set_userinfo(
            sub="new-user-no-jit",
            email="nojit@example.com",
            email_verified=True
        )
        
        # Get tokens and user info
        tokens = await manager.provider.exchange_code_for_token(
            code="mock-auth-code",
            code_verifier="test-verifier",
            redirect_uri="http://localhost/callback"
        )
        user_info = await manager.provider.get_user_info(tokens["access_token"])
        
        # Should return None (no user created, no match found)
        user = await manager.match_or_create_user(user_info)
        assert user is None
