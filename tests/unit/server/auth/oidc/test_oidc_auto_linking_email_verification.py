"""Tests for OIDC auto-linking with require_email_verification configuration."""

import pytest


class TestOIDCAutoLinkingEmailVerification:
    """Test auto-linking behavior with different email verification settings."""

    @pytest.mark.asyncio
    async def test_auto_link_with_verified_email_when_verification_required(
        self, tmp_path
    ):
        """Test auto-linking works with verified email when require_email_verification=True."""
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import OIDCUserInfo
        from code_indexer.server.auth.user_manager import User, UserRole
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from datetime import datetime, timezone
        from unittest.mock import Mock
        import aiosqlite

        # Config requires email verification
        config = OIDCProviderConfig(
            enabled=True,
            require_email_verification=True,
        )

        # Mock user_manager with existing user
        user_manager = Mock()
        existing_user = User(
            username="existinguser",
            password_hash="dummy",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
            email="existing@example.com",
        )
        user_manager.get_user_by_email.return_value = existing_user

        manager = OIDCManager(config, user_manager, None)
        manager.db_path = str(tmp_path / "test_oidc.db")
        await manager._init_db()

        # User info with VERIFIED email
        user_info = OIDCUserInfo(
            subject="new-oidc-subject",
            email="existing@example.com",
            email_verified=True,  # Verified
        )

        # Should auto-link to existing user
        user = await manager.match_or_create_user(user_info)

        assert user is not None
        assert user.username == "existinguser"
        user_manager.get_user_by_email.assert_called_once_with("existing@example.com")

        # Verify identity link was created
        async with aiosqlite.connect(manager.db_path) as db:
            cursor = await db.execute(
                "SELECT username, subject FROM oidc_identity_links WHERE subject = ?",
                ("new-oidc-subject",),
            )
            result = await cursor.fetchone()
            assert result is not None
            assert result[0] == "existinguser"

    @pytest.mark.asyncio
    async def test_auto_link_skipped_with_unverified_email_when_verification_required(
        self, tmp_path
    ):
        """Test auto-linking is SKIPPED with unverified email when require_email_verification=True."""
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import OIDCUserInfo
        from code_indexer.server.auth.user_manager import User, UserRole
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from datetime import datetime, timezone
        from unittest.mock import Mock

        # Config requires email verification
        config = OIDCProviderConfig(
            enabled=True,
            require_email_verification=True,
            enable_jit_provisioning=False,  # Disable JIT to test auto-link failure
        )

        # Mock user_manager with existing user
        user_manager = Mock()
        existing_user = User(
            username="existinguser",
            password_hash="dummy",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
            email="existing@example.com",
        )
        user_manager.get_user_by_email.return_value = existing_user

        manager = OIDCManager(config, user_manager, None)
        manager.db_path = str(tmp_path / "test_oidc.db")
        await manager._init_db()

        # User info with UNVERIFIED email
        user_info = OIDCUserInfo(
            subject="new-oidc-subject",
            email="existing@example.com",
            email_verified=False,  # NOT verified
        )

        # Should NOT auto-link (verification required but email not verified)
        user = await manager.match_or_create_user(user_info)

        assert user is None  # No match, JIT disabled
        # get_user_by_email should NOT be called because verification check failed first
        user_manager.get_user_by_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_link_works_with_unverified_email_when_verification_not_required(
        self, tmp_path
    ):
        """Test auto-linking WORKS with unverified email when require_email_verification=False."""
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import OIDCUserInfo
        from code_indexer.server.auth.user_manager import User, UserRole
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from datetime import datetime, timezone
        from unittest.mock import Mock
        import aiosqlite

        # Config does NOT require email verification
        config = OIDCProviderConfig(
            enabled=True,
            require_email_verification=False,  # Don't require verification
        )

        # Mock user_manager with existing user
        user_manager = Mock()
        existing_user = User(
            username="existinguser",
            password_hash="dummy",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
            email="existing@example.com",
        )
        user_manager.get_user_by_email.return_value = existing_user

        manager = OIDCManager(config, user_manager, None)
        manager.db_path = str(tmp_path / "test_oidc.db")
        await manager._init_db()

        # User info with UNVERIFIED email
        user_info = OIDCUserInfo(
            subject="new-oidc-subject",
            email="existing@example.com",
            email_verified=False,  # NOT verified, but config allows it
        )

        # Should auto-link to existing user (verification not required)
        user = await manager.match_or_create_user(user_info)

        assert user is not None
        assert user.username == "existinguser"
        user_manager.get_user_by_email.assert_called_once_with("existing@example.com")

        # Verify identity link was created
        async with aiosqlite.connect(manager.db_path) as db:
            cursor = await db.execute(
                "SELECT username, subject FROM oidc_identity_links WHERE subject = ?",
                ("new-oidc-subject",),
            )
            result = await cursor.fetchone()
            assert result is not None
            assert result[0] == "existinguser"

    @pytest.mark.asyncio
    async def test_auto_link_with_no_email_in_userinfo(self, tmp_path):
        """Test auto-linking is skipped when no email in user info."""
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import OIDCUserInfo
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from unittest.mock import Mock

        config = OIDCProviderConfig(
            enabled=True,
            require_email_verification=False,
            enable_jit_provisioning=False,
        )

        user_manager = Mock()
        user_manager.get_user_by_email.return_value = None

        manager = OIDCManager(config, user_manager, None)
        manager.db_path = str(tmp_path / "test_oidc.db")
        await manager._init_db()

        # User info with NO email
        user_info = OIDCUserInfo(
            subject="subject-no-email",
            email=None,  # No email
            email_verified=False,
        )

        # Should return None (no auto-link, no JIT)
        user = await manager.match_or_create_user(user_info)

        assert user is None
        # get_user_by_email should NOT be called when email is None
        user_manager.get_user_by_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_link_with_empty_email_in_userinfo(self, tmp_path):
        """Test auto-linking is skipped when email is empty string."""
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.auth.oidc.oidc_provider import OIDCUserInfo
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from unittest.mock import Mock

        config = OIDCProviderConfig(
            enabled=True,
            require_email_verification=False,
            enable_jit_provisioning=False,
        )

        user_manager = Mock()
        user_manager.get_user_by_email.return_value = None

        manager = OIDCManager(config, user_manager, None)
        manager.db_path = str(tmp_path / "test_oidc.db")
        await manager._init_db()

        # User info with EMPTY email
        user_info = OIDCUserInfo(
            subject="subject-empty-email",
            email="",  # Empty string
            email_verified=False,
        )

        # Should return None (no auto-link, no JIT)
        user = await manager.match_or_create_user(user_info)

        assert user is None
        # get_user_by_email should NOT be called when email is empty
        user_manager.get_user_by_email.assert_not_called()
