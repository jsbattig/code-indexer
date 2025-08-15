"""Tests for CLI status command payload index integration."""

from unittest.mock import Mock, patch

from code_indexer.cli import _status_impl
from code_indexer.config import Config, QdrantConfig, ConfigManager


class TestCLIStatusPayloadIndexes:
    """Tests for payload index reporting in CLI status command."""

    def setup_method(self):
        """Setup test environment."""
        self.mock_console = Mock()

        # Create a mock config
        self.mock_config = Mock(spec=Config)
        self.mock_config.qdrant = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=384,
            enable_payload_indexes=True,
            payload_indexes=[
                ("type", "keyword"),
                ("path", "text"),
                ("git_branch", "keyword"),
                ("file_mtime", "integer"),
                ("hidden_branches", "keyword"),
            ],
        )
        self.mock_config.embedding_provider = "ollama"
        self.mock_config.codebase_dir = "/tmp/test"
        self.mock_config.indexing = Mock()
        self.mock_config.indexing.max_file_size = 100000
        self.mock_config.indexing.chunk_size = 2000

        # Create mock config manager
        from pathlib import Path

        self.mock_config_manager = Mock(spec=ConfigManager)
        self.mock_config_manager.load.return_value = self.mock_config
        self.mock_config_manager.config_path = Mock()
        self.mock_config_manager.config_path.parent = Path("/tmp/test")

    def test_status_command_includes_payload_index_info_healthy(self):
        """Test that status command includes payload index information when healthy."""
        # Create mock context
        mock_ctx = Mock()
        mock_ctx.obj = {"config_manager": self.mock_config_manager}

        # Mock docker services as running
        mock_service_status = {
            "status": "running",
            "services": {
                "test_ollama": {"state": "running"},
                "test_qdrant": {"state": "running"},
            },
        }

        # Mock healthy payload index status
        mock_index_status = {
            "indexes_enabled": True,
            "total_indexes": 5,
            "expected_indexes": 5,
            "missing_indexes": [],
            "extra_indexes": [],
            "healthy": True,
            "estimated_memory_mb": 245.0,
            "indexes": [
                {"field": "type", "schema": "keyword"},
                {"field": "path", "schema": "text"},
                {"field": "git_branch", "schema": "keyword"},
                {"field": "file_mtime", "schema": "integer"},
                {"field": "hidden_branches", "schema": "keyword"},
            ],
        }

        with patch("code_indexer.cli.DockerManager") as mock_docker_manager_class:
            with patch(
                "code_indexer.cli.EmbeddingProviderFactory"
            ) as mock_embedding_factory:
                with patch("code_indexer.cli.QdrantClient") as mock_qdrant_class:
                    with patch("code_indexer.cli.Table") as mock_table_class:
                        with patch("code_indexer.cli.console", self.mock_console):
                            # Setup mocks
                            mock_docker_manager = Mock()
                            mock_docker_manager.get_service_status.return_value = (
                                mock_service_status
                            )
                            mock_docker_manager_class.return_value = mock_docker_manager

                            mock_embedding_provider = Mock()
                            mock_embedding_provider.health_check.return_value = True
                            mock_embedding_provider.get_current_model.return_value = (
                                "test-model"
                            )
                            mock_embedding_provider.get_provider_name.return_value = (
                                "ollama"
                            )
                            mock_embedding_factory.create.return_value = (
                                mock_embedding_provider
                            )

                            mock_qdrant_client = Mock()
                            mock_qdrant_client.health_check.return_value = True
                            mock_qdrant_client.resolve_collection_name.return_value = (
                                "test_collection"
                            )
                            mock_qdrant_client.get_collection_info.return_value = {
                                "status": "green"
                            }
                            mock_qdrant_client.count_points.return_value = 100
                            mock_qdrant_client.get_payload_index_status.return_value = (
                                mock_index_status
                            )
                            mock_qdrant_class.return_value = mock_qdrant_client

                            mock_table = Mock()
                            mock_table_class.return_value = mock_table

                            # This should fail until we implement the CLI integration
                            _status_impl(mock_ctx, force_docker=False)

                            # Verify that payload index status was called
                            mock_qdrant_client.get_payload_index_status.assert_called_once_with(
                                "test_collection"
                            )

                            # Verify that healthy payload index information was displayed
                            # Look for calls that include payload index information
                            table_add_row_calls = mock_table.add_row.call_args_list

                            # Should have a row for payload indexes
                            payload_index_rows = [
                                call
                                for call in table_add_row_calls
                                if any("Payload Index" in str(arg) for arg in call[0])
                            ]
                            assert (
                                len(payload_index_rows) > 0
                            ), "Status should include payload index information"

                            # Check that the healthy status is displayed
                            payload_row = payload_index_rows[0][
                                0
                            ]  # First argument (tuple of row values)
                            assert (
                                "✅" in payload_row[1]
                            ), "Should show healthy status with checkmark"
                            assert (
                                "5 indexes" in payload_row[2] or "245" in payload_row[2]
                            ), "Should show index count or memory usage"

    def test_status_command_includes_payload_index_info_unhealthy(self):
        """Test that status command shows issues when payload indexes are unhealthy."""
        # Create mock context
        mock_ctx = Mock()
        mock_ctx.obj = {"config_manager": self.mock_config_manager}

        # Mock docker services as running
        mock_service_status = {
            "status": "running",
            "services": {
                "test_ollama": {"state": "running"},
                "test_qdrant": {"state": "running"},
            },
        }

        # Mock unhealthy payload index status (missing indexes)
        mock_index_status = {
            "indexes_enabled": True,
            "total_indexes": 2,
            "expected_indexes": 5,
            "missing_indexes": ["git_branch", "file_mtime", "hidden_branches"],
            "extra_indexes": [],
            "healthy": False,
            "estimated_memory_mb": 125.0,
            "indexes": [
                {"field": "type", "schema": "keyword"},
                {"field": "path", "schema": "text"},
            ],
        }

        with patch("code_indexer.cli.DockerManager") as mock_docker_manager_class:
            with patch(
                "code_indexer.cli.EmbeddingProviderFactory"
            ) as mock_embedding_factory:
                with patch("code_indexer.cli.QdrantClient") as mock_qdrant_class:
                    with patch("code_indexer.cli.Table") as mock_table_class:
                        with patch("code_indexer.cli.console", self.mock_console):
                            # Setup mocks
                            mock_docker_manager = Mock()
                            mock_docker_manager.get_service_status.return_value = (
                                mock_service_status
                            )
                            mock_docker_manager_class.return_value = mock_docker_manager

                            mock_embedding_provider = Mock()
                            mock_embedding_provider.health_check.return_value = True
                            mock_embedding_provider.get_current_model.return_value = (
                                "test-model"
                            )
                            mock_embedding_provider.get_provider_name.return_value = (
                                "ollama"
                            )
                            mock_embedding_factory.create.return_value = (
                                mock_embedding_provider
                            )

                            mock_qdrant_client = Mock()
                            mock_qdrant_client.health_check.return_value = True
                            mock_qdrant_client.resolve_collection_name.return_value = (
                                "test_collection"
                            )
                            mock_qdrant_client.get_collection_info.return_value = {
                                "status": "green"
                            }
                            mock_qdrant_client.count_points.return_value = 100
                            mock_qdrant_client.get_payload_index_status.return_value = (
                                mock_index_status
                            )
                            mock_qdrant_class.return_value = mock_qdrant_client

                            mock_table = Mock()
                            mock_table_class.return_value = mock_table

                            # This should fail until we implement the CLI integration
                            _status_impl(mock_ctx, force_docker=False)

                            # Verify that payload index status was called
                            mock_qdrant_client.get_payload_index_status.assert_called_once_with(
                                "test_collection"
                            )

                            # Verify that unhealthy payload index information was displayed
                            table_add_row_calls = mock_table.add_row.call_args_list

                            # Should have a row for payload indexes
                            payload_index_rows = [
                                call
                                for call in table_add_row_calls
                                if any("Payload Index" in str(arg) for arg in call[0])
                            ]
                            assert (
                                len(payload_index_rows) > 0
                            ), "Status should include payload index information"

                            # Check that the unhealthy status is displayed
                            payload_row = payload_index_rows[0][
                                0
                            ]  # First argument (tuple of row values)
                            assert (
                                "⚠️" in payload_row[1] or "❌" in payload_row[1]
                            ), "Should show warning/error status"
                            assert (
                                "missing" in payload_row[2].lower()
                                or "2/5" in payload_row[2]
                            ), "Should indicate missing indexes"

    def test_status_command_handles_payload_index_error(self):
        """Test that status command handles payload index API errors gracefully."""
        # Create mock context
        mock_ctx = Mock()
        mock_ctx.obj = {"config_manager": self.mock_config_manager}

        # Mock docker services as running
        mock_service_status = {
            "status": "running",
            "services": {
                "test_ollama": {"state": "running"},
                "test_qdrant": {"state": "running"},
            },
        }

        # Mock payload index status with error
        mock_index_status = {"error": "Collection not found", "healthy": False}

        with patch("code_indexer.cli.DockerManager") as mock_docker_manager_class:
            with patch(
                "code_indexer.cli.EmbeddingProviderFactory"
            ) as mock_embedding_factory:
                with patch("code_indexer.cli.QdrantClient") as mock_qdrant_class:
                    with patch("code_indexer.cli.Table") as mock_table_class:
                        with patch("code_indexer.cli.console", self.mock_console):
                            # Setup mocks
                            mock_docker_manager = Mock()
                            mock_docker_manager.get_service_status.return_value = (
                                mock_service_status
                            )
                            mock_docker_manager_class.return_value = mock_docker_manager

                            mock_embedding_provider = Mock()
                            mock_embedding_provider.health_check.return_value = True
                            mock_embedding_provider.get_current_model.return_value = (
                                "test-model"
                            )
                            mock_embedding_provider.get_provider_name.return_value = (
                                "ollama"
                            )
                            mock_embedding_factory.create.return_value = (
                                mock_embedding_provider
                            )

                            mock_qdrant_client = Mock()
                            mock_qdrant_client.health_check.return_value = True
                            mock_qdrant_client.resolve_collection_name.return_value = (
                                "test_collection"
                            )
                            mock_qdrant_client.get_collection_info.return_value = {
                                "status": "green"
                            }
                            mock_qdrant_client.count_points.return_value = 100
                            mock_qdrant_client.get_payload_index_status.return_value = (
                                mock_index_status
                            )
                            mock_qdrant_class.return_value = mock_qdrant_client

                            mock_table = Mock()
                            mock_table_class.return_value = mock_table

                            # This should not crash even with error
                            _status_impl(mock_ctx, force_docker=False)

                            # Verify that payload index status was called
                            mock_qdrant_client.get_payload_index_status.assert_called_once_with(
                                "test_collection"
                            )

                            # Verify that error information was displayed
                            table_add_row_calls = mock_table.add_row.call_args_list

                            # Should have a row for payload indexes showing error
                            payload_index_rows = [
                                call
                                for call in table_add_row_calls
                                if any("Payload Index" in str(arg) for arg in call[0])
                            ]
                            assert (
                                len(payload_index_rows) > 0
                            ), "Status should include payload index information even on error"

                            # Check that the error status is displayed
                            payload_row = payload_index_rows[0][
                                0
                            ]  # First argument (tuple of row values)
                            assert "❌" in payload_row[1], "Should show error status"
                            assert (
                                "error" in payload_row[2].lower()
                                or "not found" in payload_row[2].lower()
                            ), "Should show error details"

    def test_status_command_skips_payload_indexes_when_qdrant_down(self):
        """Test that status command skips payload index check when Qdrant is not running."""
        # Create mock context
        mock_ctx = Mock()
        mock_ctx.obj = {"config_manager": self.mock_config_manager}

        # Mock docker services with Qdrant down
        mock_service_status = {
            "status": "running",
            "services": {
                "test_ollama": {"state": "running"},
                "test_qdrant": {"state": "exited"},  # Qdrant is not running
            },
        }

        with patch("code_indexer.cli.DockerManager") as mock_docker_manager_class:
            with patch(
                "code_indexer.cli.EmbeddingProviderFactory"
            ) as mock_embedding_factory:
                with patch("code_indexer.cli.QdrantClient") as mock_qdrant_class:
                    with patch("code_indexer.cli.Table") as mock_table_class:
                        with patch("code_indexer.cli.console", self.mock_console):
                            # Setup mocks
                            mock_docker_manager = Mock()
                            mock_docker_manager.get_service_status.return_value = (
                                mock_service_status
                            )
                            mock_docker_manager_class.return_value = mock_docker_manager

                            mock_embedding_provider = Mock()
                            mock_embedding_provider.health_check.return_value = True
                            mock_embedding_provider.get_current_model.return_value = (
                                "test-model"
                            )
                            mock_embedding_provider.get_provider_name.return_value = (
                                "ollama"
                            )
                            mock_embedding_factory.create.return_value = (
                                mock_embedding_provider
                            )

                            mock_qdrant_client = Mock()
                            mock_qdrant_client.health_check.return_value = (
                                False  # Qdrant health check fails
                            )
                            mock_qdrant_class.return_value = mock_qdrant_client

                            mock_table = Mock()
                            mock_table_class.return_value = mock_table

                            # Should not crash when Qdrant is down
                            _status_impl(mock_ctx, force_docker=False)

                            # Verify that payload index status was NOT called when Qdrant is down
                            mock_qdrant_client.get_payload_index_status.assert_not_called()

                            # Should not have payload index rows when Qdrant is down
                            table_add_row_calls = mock_table.add_row.call_args_list
                            payload_index_rows = [
                                call
                                for call in table_add_row_calls
                                if any("Payload Index" in str(arg) for arg in call[0])
                            ]
                            assert (
                                len(payload_index_rows) == 0
                            ), "Should not show payload index info when Qdrant is down"
