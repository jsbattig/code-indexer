"""Tests for OIDC manager implementation."""
import pytest


class TestOIDCManager:
    """Test OIDC manager class."""

    def test_oidc_manager_initialization(self):
        """Test that OIDCManager can be initialized with dependencies."""
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig

        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
            client_id="test-client-id",
            client_secret="test-client-secret",
        )

        # Mock dependencies
        user_manager = None  # Will mock properly later
        jwt_manager = None  # Will mock properly later

        manager = OIDCManager(config, user_manager, jwt_manager)

        assert manager.config == config
        assert manager.user_manager is user_manager
        assert manager.jwt_manager is jwt_manager
        assert manager.provider is None  # Not initialized yet

    @pytest.mark.asyncio
    async def test_oidc_manager_initialize_creates_provider(self, monkeypatch):
        """Test that initialize() creates and initializes OIDC provider when enabled."""
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig

        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
            client_id="test-client-id",
            client_secret="test-client-secret",
        )

        manager = OIDCManager(config, None, None)

        # Mock HTTP response for discovery
        mock_response = {
            "issuer": "https://example.com",
            "authorization_endpoint": "https://example.com/authorize",
            "token_endpoint": "https://example.com/token",
        }

        async def mock_get(*args, **kwargs):
            class MockResponse:
                def json(self):
                    return mock_response

                def raise_for_status(self):
                    pass  # No error for success case

            return MockResponse()

        # Mock httpx.AsyncClient
        import httpx

        class MockAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, *args, **kwargs):
                return await mock_get(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", lambda: MockAsyncClient())

        # Initialize manager
        await manager.initialize()

        # Verify provider was created and initialized
        assert manager.provider is not None
        assert manager.provider.config == config
        assert manager.provider._metadata is not None
        assert manager.provider._metadata.issuer == "https://example.com"

    def test_is_enabled_returns_true_when_configured(self):
        """Test that is_enabled() returns True when OIDC is enabled and provider initialized."""
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import OIDCProvider
        from code_indexer.server.utils.config_manager import OIDCProviderConfig

        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
        )

        manager = OIDCManager(config, None, None)
        manager.provider = OIDCProvider(config)

        assert manager.is_enabled() is True

    def test_is_enabled_returns_false_when_disabled(self):
        """Test that is_enabled() returns False when OIDC is disabled."""
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig

        config = OIDCProviderConfig(enabled=False)

        manager = OIDCManager(config, None, None)

        assert manager.is_enabled() is False

    def test_is_enabled_returns_false_when_provider_not_initialized(self):
        """Test that is_enabled() returns False when provider is None."""
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig

        config = OIDCProviderConfig(enabled=True)

        manager = OIDCManager(config, None, None)

        assert manager.is_enabled() is False

    def test_create_jwt_session_returns_token(self):
        """Test that create_jwt_session() creates a JWT token for the user."""
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.jwt_manager import JWTManager
        from code_indexer.server.auth.user_manager import User, UserRole
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from datetime import datetime, timezone

        config = OIDCProviderConfig(enabled=True)
        jwt_manager = JWTManager(secret_key="test-secret", token_expiration_minutes=10)

        manager = OIDCManager(config, None, jwt_manager)

        # Create test user
        user = User(
            username="testuser",
            password_hash="dummy",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

        # Create JWT session
        token = manager.create_jwt_session(user)

        # Verify token is valid
        assert isinstance(token, str)
        assert len(token) > 0

        # Verify token can be decoded
        payload = jwt_manager.validate_token(token)
        assert payload["username"] == "testuser"
        assert payload["role"] == "normal_user"

    def test_oidc_manager_has_db_path(self):
        """Test that OIDCManager initializes with database path."""
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig

        config = OIDCProviderConfig(enabled=True)
        manager = OIDCManager(config, None, None)

        assert hasattr(manager, "db_path")
        assert isinstance(manager.db_path, str)
        assert "oauth.db" in manager.db_path  # Uses existing OAuth database

    @pytest.mark.asyncio
    async def test_init_db_creates_schema(self, tmp_path):
        """Test that _init_db() creates the oidc_identities database schema."""
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        import aiosqlite

        config = OIDCProviderConfig(enabled=True)
        manager = OIDCManager(config, None, None)

        # Use temporary database path
        manager.db_path = str(tmp_path / "test_oidc_identities.db")

        # Initialize database
        await manager._init_db()

        # Verify table exists
        async with aiosqlite.connect(manager.db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='oidc_identity_links'"
            )
            result = await cursor.fetchone()
            assert result is not None
            assert result[0] == "oidc_identity_links"

    @pytest.mark.asyncio
    async def test_link_oidc_identity_stores_in_database(self, tmp_path):
        """Test that link_oidc_identity() stores identity link in database."""
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from datetime import datetime, timezone
        import aiosqlite

        config = OIDCProviderConfig(enabled=True)
        manager = OIDCManager(config, None, None)
        manager.db_path = str(tmp_path / "test_oidc_identities.db")

        # Initialize database
        await manager._init_db()

        # Link OIDC identity
        await manager.link_oidc_identity(
            username="testuser",
            subject="oidc-subject-123",
            email="test@example.com"
        )

        # Verify data was stored
        async with aiosqlite.connect(manager.db_path) as db:
            cursor = await db.execute(
                "SELECT username, subject, email FROM oidc_identity_links WHERE username = ?",
                ("testuser",)
            )
            result = await cursor.fetchone()
            assert result is not None
            assert result[0] == "testuser"
            assert result[1] == "oidc-subject-123"
            assert result[2] == "test@example.com"

    @pytest.mark.asyncio
    async def test_match_or_create_user_returns_existing_user_by_subject(self, tmp_path):
        """Test that match_or_create_user() returns existing user when subject exists."""
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import OIDCUserInfo
        from code_indexer.server.auth.user_manager import User, UserRole
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from datetime import datetime, timezone
        from unittest.mock import Mock

        config = OIDCProviderConfig(enabled=True)

        # Mock user_manager
        user_manager = Mock()
        existing_user = User(
            username="testuser",
            password_hash="dummy",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )
        user_manager.get_user.return_value = existing_user

        manager = OIDCManager(config, user_manager, None)
        manager.db_path = str(tmp_path / "test_oidc_identities.db")

        # Initialize database and link identity
        await manager._init_db()
        await manager.link_oidc_identity(
            username="testuser",
            subject="oidc-subject-123",
            email="test@example.com"
        )

        # Create user info with same subject
        user_info = OIDCUserInfo(
            subject="oidc-subject-123",
            email="test@example.com",
            email_verified=True,
        )

        # Match user by subject
        user = await manager.match_or_create_user(user_info)

        # Verify existing user is returned
        assert user.username == "testuser"
        assert user.role == UserRole.NORMAL_USER
        user_manager.get_user.assert_called_once_with("testuser")

    @pytest.mark.asyncio
    async def test_match_or_create_user_links_existing_user_by_email(self, tmp_path):
        """Test that match_or_create_user() auto-links existing user by verified email."""
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import OIDCUserInfo
        from code_indexer.server.auth.user_manager import User, UserRole
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from datetime import datetime, timezone
        from unittest.mock import Mock
        import aiosqlite

        config = OIDCProviderConfig(enabled=True)

        # Mock user_manager
        user_manager = Mock()
        existing_user = User(
            username="testuser",
            password_hash="dummy",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )
        user_manager.get_user_by_email.return_value = existing_user

        manager = OIDCManager(config, user_manager, None)
        manager.db_path = str(tmp_path / "test_oidc_identities.db")

        # Initialize database (no existing identity link)
        await manager._init_db()

        # Create user info with verified email
        user_info = OIDCUserInfo(
            subject="new-oidc-subject-456",
            email="test@example.com",
            email_verified=True,
        )

        # Match user by email
        user = await manager.match_or_create_user(user_info)

        # Verify existing user is returned
        assert user.username == "testuser"
        assert user.role == UserRole.NORMAL_USER
        user_manager.get_user_by_email.assert_called_once_with("test@example.com")

        # Verify identity link was created
        async with aiosqlite.connect(manager.db_path) as db:
            cursor = await db.execute(
                "SELECT username, subject, email FROM oidc_identity_links WHERE subject = ?",
                ("new-oidc-subject-456",)
            )
            result = await cursor.fetchone()
            assert result is not None
            assert result[0] == "testuser"
            assert result[1] == "new-oidc-subject-456"
            assert result[2] == "test@example.com"

    @pytest.mark.asyncio
    async def test_match_or_create_user_creates_new_user_via_jit(self, tmp_path):
        """Test that match_or_create_user() creates new user via JIT provisioning."""
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import OIDCUserInfo
        from code_indexer.server.auth.user_manager import User, UserRole
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from datetime import datetime, timezone
        from unittest.mock import Mock
        import aiosqlite

        config = OIDCProviderConfig(
            enabled=True,
            enable_jit_provisioning=True,
            default_role="normal_user"
        )

        # Mock user_manager
        user_manager = Mock()
        user_manager.get_user_by_email.return_value = None  # No existing user by email

        # Mock create_oidc_user to return a new user
        new_user = User(
            username="newuser",
            password_hash="",  # No password for OIDC-only user
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )
        user_manager.create_oidc_user.return_value = new_user

        manager = OIDCManager(config, user_manager, None)
        manager.db_path = str(tmp_path / "test_oidc_identities.db")

        # Initialize database
        await manager._init_db()

        # Create user info for new user
        user_info = OIDCUserInfo(
            subject="brand-new-subject-789",
            email="newuser@example.com",
            email_verified=True,
        )

        # Create user via JIT provisioning
        user = await manager.match_or_create_user(user_info)

        # Verify new user was created
        assert user.username == "newuser"
        assert user.role == UserRole.NORMAL_USER
        user_manager.create_oidc_user.assert_called_once()

        # Verify identity link was created
        async with aiosqlite.connect(manager.db_path) as db:
            cursor = await db.execute(
                "SELECT username, subject, email FROM oidc_identity_links WHERE subject = ?",
                ("brand-new-subject-789",)
            )
            result = await cursor.fetchone()
            assert result is not None
            assert result[0] == "newuser"
            assert result[1] == "brand-new-subject-789"
            assert result[2] == "newuser@example.com"

    @pytest.mark.asyncio
    async def test_initialize_calls_init_db(self, monkeypatch, tmp_path):
        """Test that initialize() calls _init_db() to create database schema."""
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        import aiosqlite

        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
            client_id="test-client-id",
            client_secret="test-client-secret",
        )

        manager = OIDCManager(config, None, None)
        manager.db_path = str(tmp_path / "test_oidc_identities.db")

        # Mock HTTP response for discovery
        mock_response = {
            "issuer": "https://example.com",
            "authorization_endpoint": "https://example.com/authorize",
            "token_endpoint": "https://example.com/token",
        }

        async def mock_get(*args, **kwargs):
            class MockResponse:
                def json(self):
                    return mock_response

                def raise_for_status(self):
                    pass  # No error for success case

            return MockResponse()

        # Mock httpx.AsyncClient
        import httpx

        class MockAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, *args, **kwargs):
                return await mock_get(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", lambda: MockAsyncClient())

        # Initialize manager (should call _init_db)
        await manager.initialize()

        # Verify database was initialized by checking table exists
        async with aiosqlite.connect(manager.db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='oidc_identity_links'"
            )
            result = await cursor.fetchone()
            assert result is not None, "oidc_identity_links table should exist after initialize()"
            assert result[0] == "oidc_identity_links"
    @pytest.mark.asyncio
    async def test_match_or_create_user_handles_stale_oidc_link(self, tmp_path, monkeypatch):
        """Test that match_or_create_user handles stale OIDC links gracefully."""
        import aiosqlite
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import OIDCUserInfo
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from code_indexer.server.auth.user_manager import UserRole

        # Create test config with JIT provisioning enabled
        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
            client_id="test-client-id",
            client_secret="test-client-secret",
            enable_jit_provisioning=True,
            default_role="normal_user",
        )

        # Mock user manager
        class MockUserManager:
            def __init__(self):
                self.users = {}
                self.oidc_users_created = []

            def get_user(self, username):
                return self.users.get(username)

            def get_user_by_email(self, email):
                return None

            def create_oidc_user(self, username, role, email, oidc_identity):
                class MockUser:
                    pass
                user = MockUser()
                user.username = username
                user.role = role
                user.email = email
                self.users[username] = user
                self.oidc_users_created.append(username)
                return user

        user_manager = MockUserManager()

        # Create manager with test database
        db_path = tmp_path / "test_oidc.db"
        manager = OIDCManager(config, user_manager, None)
        manager.db_path = str(db_path)

        # Initialize database
        await manager._init_db()

        # Create a stale OIDC link (points to deleted user)
        from datetime import datetime, timezone
        async with aiosqlite.connect(manager.db_path) as db:
            await db.execute(
                "INSERT INTO oidc_identity_links (subject, username, email, linked_at) VALUES (?, ?, ?, ?)",
                ("test-subject-123", "deleteduser", "test@example.com", datetime.now(timezone.utc).isoformat())
            )
            await db.commit()

        # Create user info for SSO login
        user_info = OIDCUserInfo(
            subject="test-subject-123",
            email="test@example.com",
            email_verified=True,
        )

        # Call match_or_create_user - should handle stale link gracefully
        result_user = await manager.match_or_create_user(user_info)

        # Should have created a new user via JIT provisioning
        assert result_user is not None
        assert result_user.username == "test"  # From email prefix
        assert len(user_manager.oidc_users_created) == 1

        # Verify stale link was deleted
        async with aiosqlite.connect(manager.db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM oidc_identity_links WHERE username = ?",
                ("deleteduser",)
            )
            count = (await cursor.fetchone())[0]
            assert count == 0, "Stale OIDC link should have been deleted"

        # Verify new link was created for new user
        async with aiosqlite.connect(manager.db_path) as db:
            cursor = await db.execute(
                "SELECT username FROM oidc_identity_links WHERE subject = ?",
                ("test-subject-123",)
            )
            result = await cursor.fetchone()
            assert result is not None
            assert result[0] == "test", "New OIDC link should point to new user"
