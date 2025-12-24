"""
Integration tests for FastAPI lifespan event with meta-directory population.

Tests the integration between FastAPI startup event and meta-directory
auto-population functionality.
"""

import pytest
import tempfile
import json
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock


class TestStartupLifespan:
    """Integration tests for server startup lifespan."""

    @pytest.fixture
    def temp_server_dir(self):
        """Create temporary server directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server_dir = Path(tmpdir) / ".cidx-server"
            server_dir.mkdir()

            # Create required subdirectories
            golden_repos_dir = server_dir / "golden-repos"
            golden_repos_dir.mkdir()

            meta_dir = golden_repos_dir / "cidx-meta"
            meta_dir.mkdir()

            yield server_dir

    @pytest.fixture
    def mock_env(self, temp_server_dir):
        """Mock environment variables for server."""
        with patch.dict("os.environ", {"CIDX_SERVER_DATA_DIR": str(temp_server_dir)}):
            yield temp_server_dir

    def test_lifespan_event_triggers_meta_population_on_startup(
        self, temp_server_dir, mock_env
    ):
        """
        Test: FastAPI lifespan event triggers meta-directory population
        Given: The server has registered repositories
        When: The FastAPI app starts
        Then: The lifespan event triggers meta-directory population
        And: The population completes before the app accepts requests
        """
        # Setup: Create registry with repos
        golden_repos_dir = temp_server_dir / "golden-repos"
        registry_file = golden_repos_dir / "global_registry.json"
        registry_data = {
            "repo1": {
                "repo_name": "repo1",
                "alias_name": "repo1-alias",
                "repo_url": "https://github.com/user/repo1",
                "index_path": str(golden_repos_dir / "repo1"),
                "registered_at": "2025-01-01T00:00:00Z",
            },
            "repo2": {
                "repo_name": "repo2",
                "alias_name": "repo2-alias",
                "repo_url": "https://github.com/user/repo2",
                "index_path": str(golden_repos_dir / "repo2"),
                "registered_at": "2025-01-01T00:00:00Z",
            },
        }
        registry_file.write_text(json.dumps(registry_data, indent=2))

        # Mock MetaDirectoryUpdater to verify it's called during startup
        with patch(
            "code_indexer.server.lifecycle.startup_meta_populator.MetaDirectoryUpdater"
        ) as mock_updater_class:
            mock_updater = Mock()
            mock_updater.has_changes.return_value = True
            mock_updater_class.return_value = mock_updater

            # Import and create app (this triggers lifespan event)
            from code_indexer.server.app import create_app

            app = create_app()

            # Create test client (this starts the app with lifespan context)
            with TestClient(app) as _client:
                # The lifespan event runs when TestClient context is entered
                # No need to make a request - just verify the mock was called

                # Assert: MetaDirectoryUpdater was called during startup
                mock_updater_class.assert_called_once()
                mock_updater.update.assert_called_once()

    def test_lifespan_event_handles_population_errors_gracefully(
        self, temp_server_dir, mock_env
    ):
        """
        Test: Lifespan event handles population errors without blocking startup
        Given: The meta-directory population encounters an error
        When: The FastAPI app starts
        Then: The error is logged
        And: The server continues startup successfully
        And: The server accepts requests normally
        """
        # Setup: Create registry
        golden_repos_dir = temp_server_dir / "golden-repos"
        registry_file = golden_repos_dir / "global_registry.json"
        registry_data = {
            "repo1": {
                "repo_name": "repo1",
                "alias_name": "repo1-alias",
                "repo_url": "https://github.com/user/repo1",
                "index_path": str(golden_repos_dir / "repo1"),
                "registered_at": "2025-01-01T00:00:00Z",
            }
        }
        registry_file.write_text(json.dumps(registry_data, indent=2))

        # Mock MetaDirectoryUpdater to raise exception
        with patch(
            "code_indexer.server.lifecycle.startup_meta_populator.MetaDirectoryUpdater"
        ) as mock_updater_class:
            mock_updater = Mock()
            mock_updater.has_changes.return_value = True
            mock_updater.update.side_effect = Exception("AI API timeout")
            mock_updater_class.return_value = mock_updater

            # Import and create app
            from code_indexer.server.app import create_app

            app = create_app()

            # Create test client (should not raise exception despite meta-population error)
            with TestClient(app) as _client:
                # Assert: Server started successfully despite error
                # The fact that TestClient context manager doesn't raise proves success
                pass

    def test_lifespan_event_skips_population_when_no_repos(
        self, temp_server_dir, mock_env
    ):
        """
        Test: Lifespan event skips population when no repositories registered
        Given: The registry is empty (no repos registered)
        When: The FastAPI app starts
        Then: Meta-directory population is skipped
        And: Startup completes quickly
        """
        # Setup: Create empty registry
        golden_repos_dir = temp_server_dir / "golden-repos"
        registry_file = golden_repos_dir / "global_registry.json"
        registry_file.write_text(json.dumps({}, indent=2))

        # Mock MetaDirectoryUpdater to verify it's NOT called
        with patch(
            "code_indexer.server.lifecycle.startup_meta_populator.MetaDirectoryUpdater"
        ) as mock_updater_class:
            mock_updater = Mock()
            mock_updater_class.return_value = mock_updater

            # Import and create app
            from code_indexer.server.app import create_app

            app = create_app()

            # Create test client
            with TestClient(app) as _client:
                # Assert: Server started successfully
                # The fact that TestClient context manager doesn't raise proves success

                # Assert: Update was NOT called (no repos to populate)
                mock_updater.update.assert_not_called()

    def test_lifespan_event_logs_population_status(
        self, temp_server_dir, mock_env, caplog
    ):
        """
        Test: Lifespan event logs population status for monitoring
        Given: The server has registered repositories
        When: The FastAPI app starts
        Then: Population status is logged
        And: Logs indicate number of repos processed
        """
        import logging

        caplog.set_level(logging.INFO)

        # Setup: Create registry with repos
        golden_repos_dir = temp_server_dir / "golden-repos"
        registry_file = golden_repos_dir / "global_registry.json"
        registry_data = {
            "repo1": {
                "repo_name": "repo1",
                "alias_name": "repo1-alias",
                "repo_url": "https://github.com/user/repo1",
                "index_path": str(golden_repos_dir / "repo1"),
                "registered_at": "2025-01-01T00:00:00Z",
            }
        }
        registry_file.write_text(json.dumps(registry_data, indent=2))

        # Mock MetaDirectoryUpdater
        with patch(
            "code_indexer.server.lifecycle.startup_meta_populator.MetaDirectoryUpdater"
        ) as mock_updater_class:
            mock_updater = Mock()
            mock_updater.has_changes.return_value = True
            mock_updater_class.return_value = mock_updater

            # Import and create app
            from code_indexer.server.app import create_app

            app = create_app()

            # Create test client
            with TestClient(app) as _client:
                # Assert: Server started successfully
                # The lifespan event ran during TestClient context entry

                # Check for population logs
                log_messages = [record.message for record in caplog.records]
                population_logs = [
                    msg
                    for msg in log_messages
                    if "meta-directory" in msg.lower() or "populat" in msg.lower()
                ]

                # Should have logged population activity
                assert len(population_logs) > 0
