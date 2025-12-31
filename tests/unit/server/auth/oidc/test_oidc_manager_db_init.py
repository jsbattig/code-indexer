"""Tests for OIDCManager database initialization."""
import pytest
import tempfile
import aiosqlite
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from code_indexer.server.auth.oidc.oidc_manager import OIDCManager
from code_indexer.server.utils.config_manager import OIDCProviderConfig


class TestOIDCManagerDbInit:
    """Test that OIDCManager initializes the database on startup."""

    @pytest.mark.asyncio
    async def test_init_db_creates_table(self):
        """Test that _init_db() creates the oidc_identity_links table."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = OIDCProviderConfig(enabled=True)

            # Mock user_manager and jwt_manager
            user_manager = MagicMock()
            jwt_manager = MagicMock()

            manager = OIDCManager(config, user_manager, jwt_manager)

            # Override db_path to use temp directory
            db_path = Path(tmpdir) / "oidc_identities.db"
            manager.db_path = str(db_path)

            # Call _init_db directly
            await manager._init_db()

            # Verify database was created
            assert db_path.exists(), "Database file was not created"

            # Verify table exists
            async with aiosqlite.connect(str(db_path)) as db:
                cursor = await db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='oidc_identity_links'"
                )
                result = await cursor.fetchone()
                assert result is not None, "oidc_identity_links table was not created"
                assert result[0] == "oidc_identity_links"
