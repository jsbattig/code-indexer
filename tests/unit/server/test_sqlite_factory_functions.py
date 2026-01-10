"""
Unit tests for SQLite factory functions in Story #702 migration.

Tests verify that factory functions create managers with SQLite backend
and use the correct database path (server_dir/data/cidx_server.db).

Story #702: Migrate Central JSON Files to SQLite
"""

from pathlib import Path
from unittest.mock import Mock, patch
import pytest


class TestTokenManagerFactoryFunction:
    """Tests for _get_token_manager() in web/routes.py (Issue #1)."""

    def test_token_manager_uses_correct_database_path(self, tmp_path: Path) -> None:
        """
        Given _get_token_manager() factory function
        When called
        Then it creates CITokenManager with db_path=server_dir/data/cidx_server.db
        """
        # Setup: Mock the config service
        mock_config_manager = Mock()
        mock_config_manager.server_dir = tmp_path
        mock_config_service = Mock()
        mock_config_service.config_manager = mock_config_manager

        # Patch where the name is used (in routes module), not where it's defined
        with patch(
            "code_indexer.server.services.config_service.get_config_service",
            return_value=mock_config_service,
        ):
            with patch(
                "code_indexer.server.web.routes.CITokenManager"
            ) as mock_manager_class:
                # Import and call the factory function
                from code_indexer.server.web.routes import _get_token_manager

                _get_token_manager()

                # Verify CITokenManager was instantiated with correct params
                mock_manager_class.assert_called_once()
                call_kwargs = mock_manager_class.call_args[1]

                assert call_kwargs["server_dir_path"] == str(tmp_path)
                assert call_kwargs["use_sqlite"] is True
                expected_db_path = str(tmp_path / "data" / "cidx_server.db")
                assert call_kwargs["db_path"] == expected_db_path


class TestTokenAuthenticatorSqliteUsage:
    """Tests for TokenAuthenticator.resolve_token() in git_state_manager.py (Issue #2)."""

    def test_resolve_token_uses_sqlite_backend(self, tmp_path: Path) -> None:
        """
        Given TokenAuthenticator.resolve_token() is called
        When no environment variable is set
        Then it creates CITokenManager with use_sqlite=True and correct db_path
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema

        # Setup: Create database with test token
        server_dir = tmp_path / ".cidx-server"
        server_dir.mkdir(parents=True)
        db_path = server_dir / "data" / "cidx_server.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        # Mock Path.home() to return tmp_path so server_dir calculation works
        with patch("pathlib.Path.home", return_value=tmp_path):
            # Clear environment variables
            with patch.dict("os.environ", {}, clear=True):
                with patch(
                    "code_indexer.server.services.ci_token_manager.CITokenManager"
                ) as mock_manager_class:
                    # Setup mock to return None (no token found)
                    mock_instance = Mock()
                    mock_instance.get_token.return_value = None
                    mock_manager_class.return_value = mock_instance

                    # Import and call resolve_token
                    from code_indexer.server.services.git_state_manager import (
                        TokenAuthenticator,
                    )

                    TokenAuthenticator.resolve_token("github")

                    # Verify CITokenManager was created with SQLite params
                    mock_manager_class.assert_called_once()
                    call_kwargs = mock_manager_class.call_args[1]

                    assert call_kwargs["use_sqlite"] is True
                    assert "data" in call_kwargs["db_path"]
                    assert "cidx_server.db" in call_kwargs["db_path"]


class TestSSHKeyManagerFactoryFunction:
    """Tests for _get_ssh_key_manager() factory in web/routes.py (Issue #3)."""

    def test_ssh_key_manager_uses_sqlite_backend(self, tmp_path: Path) -> None:
        """
        Given _get_ssh_key_manager() factory function
        When called
        Then it creates SSHKeyManager with use_sqlite=True and correct db_path
        """
        # Setup: Mock the config service
        mock_config_manager = Mock()
        mock_config_manager.server_dir = tmp_path
        mock_config_service = Mock()
        mock_config_service.config_manager = mock_config_manager

        with patch(
            "code_indexer.server.services.config_service.get_config_service",
            return_value=mock_config_service,
        ):
            with patch(
                "code_indexer.server.services.ssh_key_manager.SSHKeyManager"
            ) as mock_manager_class:
                # Import and call the factory function
                from code_indexer.server.web.routes import _get_ssh_key_manager

                _get_ssh_key_manager()

                # Verify SSHKeyManager was instantiated with correct params
                mock_manager_class.assert_called_once()
                call_kwargs = mock_manager_class.call_args[1]

                assert call_kwargs["use_sqlite"] is True
                expected_db_path = tmp_path / "data" / "cidx_server.db"
                assert call_kwargs["db_path"] == expected_db_path
                assert call_kwargs["metadata_dir"] == tmp_path / "data" / "ssh_keys"


class TestSSHKeysRouterFactoryFunction:
    """Tests for get_ssh_key_manager() in routers/ssh_keys.py (Issue #3)."""

    def test_ssh_keys_router_uses_sqlite_backend(self, tmp_path: Path) -> None:
        """
        Given get_ssh_key_manager() in ssh_keys router
        When called
        Then it creates SSHKeyManager with use_sqlite=True and correct db_path
        """
        pytest.skip("Placeholder - implementation will be tested after fix")


class TestMCPSSHKeyManagerFactory:
    """Tests for get_ssh_key_manager() in mcp/handlers.py (Issue #3)."""

    def test_mcp_ssh_key_manager_uses_sqlite_backend(self, tmp_path: Path) -> None:
        """
        Given get_ssh_key_manager() in MCP handlers
        When called
        Then it creates SSHKeyManager with use_sqlite=True and correct db_path
        """
        # Setup mock config service
        mock_config_manager = Mock()
        mock_config_manager.server_dir = tmp_path
        mock_config_service = Mock()
        mock_config_service.config_manager = mock_config_manager

        with patch(
            "code_indexer.server.services.config_service.get_config_service",
            return_value=mock_config_service,
        ):
            with patch(
                "code_indexer.server.services.ssh_key_manager.SSHKeyManager"
            ) as mock_manager_class:
                # Reset the singleton
                import code_indexer.server.mcp.handlers as handlers_module

                handlers_module._ssh_key_manager = None

                # Import and call the factory function
                from code_indexer.server.mcp.handlers import get_ssh_key_manager

                get_ssh_key_manager()

                # Verify SSHKeyManager was instantiated with correct params
                mock_manager_class.assert_called_once()
                call_kwargs = mock_manager_class.call_args[1]

                assert call_kwargs["use_sqlite"] is True
                expected_db_path = tmp_path / "data" / "cidx_server.db"
                assert call_kwargs["db_path"] == expected_db_path


class TestSyncJobManagerFactoryFunction:
    """Tests for create_sync_job_manager() in jobs/manager.py (Issue #4)."""

    def test_sync_job_manager_uses_sqlite_backend(self, tmp_path: Path) -> None:
        """
        Given create_sync_job_manager() factory function
        When called
        Then it creates SyncJobManager with use_sqlite=True and correct db_path
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema

        # Setup: Create the database
        server_dir = tmp_path / ".cidx-server"
        server_dir.mkdir(parents=True)
        db_path = server_dir / "data" / "cidx_server.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        with patch(
            "code_indexer.server.jobs.manager.SyncJobManager"
        ) as mock_manager_class:
            mock_manager_class.return_value = Mock()

            # Call the factory
            from code_indexer.server.jobs.manager import create_sync_job_manager

            create_sync_job_manager(server_dir_path=str(server_dir))

            # Verify SyncJobManager was created with SQLite params
            mock_manager_class.assert_called_once()
            call_kwargs = mock_manager_class.call_args[1]

            assert call_kwargs["use_sqlite"] is True
            assert call_kwargs["db_path"] == str(db_path)


class TestCommitterResolutionServiceSSHKeyManager:
    """Tests for SSHKeyManager in CommitterResolutionService (Issue #3)."""

    def test_committer_resolution_uses_sqlite_ssh_key_manager(
        self, tmp_path: Path
    ) -> None:
        """
        Given CommitterResolutionService created without explicit ssh_key_manager
        When it creates a default SSHKeyManager
        Then it should use SQLite backend
        """
        pytest.skip("Placeholder - requires injecting SSHKeyManager with SQLite config")


class TestMigrationOrchestratorSSHKeyManager:
    """Tests for SSHKeyManager in MigrationOrchestrator (Issue #3)."""

    def test_migration_orchestrator_uses_sqlite_ssh_key_manager(
        self, tmp_path: Path
    ) -> None:
        """
        Given MigrationOrchestrator is created
        When it initializes SSHKeyManager
        Then it should use SQLite backend
        """
        pytest.skip("Placeholder - requires modifying MigrationOrchestrator")
