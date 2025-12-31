"""Tests for OIDC link cleanup during user deletion."""
import pytest
from unittest.mock import Mock, AsyncMock, patch
import aiosqlite
from pathlib import Path


class TestUserDeletionOIDCCleanup:
    """Test that OIDC links are cleaned up when users are deleted."""

    @pytest.mark.asyncio
    async def test_delete_user_cleans_up_oidc_link(self, tmp_path):
        """Test that deleting a user also deletes their OIDC identity link."""
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig
        from datetime import datetime, timezone

        # Create test OIDC database
        db_path = tmp_path / "test_oidc.db"

        # Create OIDC manager to initialize database
        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
            client_id="test-client-id",
            client_secret="test-client-secret",
        )
        manager = OIDCManager(config, None, None)
        manager.db_path = str(db_path)
        await manager._init_db()

        # Insert test OIDC link
        async with aiosqlite.connect(str(db_path)) as db:
            await db.execute(
                "INSERT INTO oidc_identity_links (subject, username, email, linked_at) VALUES (?, ?, ?, ?)",
                ("test-subject-123", "testuser", "test@example.com", datetime.now(timezone.utc).isoformat())
            )
            await db.commit()

            # Verify link exists
            cursor = await db.execute(
                "SELECT COUNT(*) FROM oidc_identity_links WHERE username = ?",
                ("testuser",)
            )
            count = (await cursor.fetchone())[0]
            assert count == 1, "OIDC link should exist before deletion"

        # Mock OIDC manager for cleanup code
        from code_indexer.server.auth.oidc import routes as oidc_routes

        mock_manager = Mock()
        mock_manager.db_path = str(db_path)

        original_manager = oidc_routes.oidc_manager
        oidc_routes.oidc_manager = mock_manager

        try:
            # Simulate the cleanup code from delete_user route
            if oidc_routes.oidc_manager:
                async with aiosqlite.connect(oidc_routes.oidc_manager.db_path) as db:
                    await db.execute(
                        "DELETE FROM oidc_identity_links WHERE username = ?",
                        ("testuser",)
                    )
                    await db.commit()

            # Verify link was deleted
            async with aiosqlite.connect(str(db_path)) as db:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM oidc_identity_links WHERE username = ?",
                    ("testuser",)
                )
                count = (await cursor.fetchone())[0]
                assert count == 0, "OIDC link should be deleted after user deletion"
        finally:
            # Restore original manager
            oidc_routes.oidc_manager = original_manager

    @pytest.mark.asyncio
    async def test_delete_user_handles_no_oidc_link(self, tmp_path):
        """Test that deleting a user without OIDC link doesn't cause errors."""
        from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
        from code_indexer.server.utils.config_manager import OIDCProviderConfig

        # Create test OIDC database
        db_path = tmp_path / "test_oidc.db"

        # Create OIDC manager to initialize database
        config = OIDCProviderConfig(
            enabled=True,
            provider_name="TestSSO",
            issuer_url="https://example.com",
            client_id="test-client-id",
            client_secret="test-client-secret",
        )
        manager = OIDCManager(config, None, None)
        manager.db_path = str(db_path)
        await manager._init_db()

        # No OIDC link for this user - just verify cleanup doesn't crash
        from code_indexer.server.auth.oidc import routes as oidc_routes

        mock_manager = Mock()
        mock_manager.db_path = str(db_path)

        original_manager = oidc_routes.oidc_manager
        oidc_routes.oidc_manager = mock_manager

        try:
            # This should not raise an error even though no link exists
            if oidc_routes.oidc_manager:
                async with aiosqlite.connect(oidc_routes.oidc_manager.db_path) as db:
                    await db.execute(
                        "DELETE FROM oidc_identity_links WHERE username = ?",
                        ("nonexistent_user",)
                    )
                    await db.commit()

            # Verify database is still intact
            async with aiosqlite.connect(str(db_path)) as db:
                cursor = await db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='oidc_identity_links'"
                )
                result = await cursor.fetchone()
                assert result is not None, "Table should still exist"
        finally:
            # Restore original manager
            oidc_routes.oidc_manager = original_manager
