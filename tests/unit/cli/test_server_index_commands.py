"""Unit tests for server index management CLI commands."""

from unittest.mock import patch, MagicMock, AsyncMock

from click.testing import CliRunner

from code_indexer.cli import cli


class TestServerAddIndexCommand:
    """Test suite for cidx server add-index command."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_add_index_command_success(self):
        """Test cidx server add-index returns job_id on success (AC1)."""
        with (
            patch(
                "code_indexer.remote.config.RemoteConfig"
            ) as mock_remote_config_class,
            patch(
                "code_indexer.api_clients.admin_client.AdminAPIClient"
            ) as mock_client_class,
        ):
            # Mock RemoteConfig
            mock_remote_config = MagicMock()
            mock_remote_config.server_url = "http://test-server:8000"
            mock_decrypted_creds = MagicMock()
            mock_decrypted_creds.username = "admin"
            mock_decrypted_creds.password = "test"
            mock_remote_config.get_decrypted_credentials.return_value = (
                mock_decrypted_creds
            )
            mock_remote_config_class.return_value = mock_remote_config

            # Mock AdminAPIClient
            mock_client = MagicMock()
            mock_client.add_index_to_golden_repo = AsyncMock(
                return_value={"job_id": "test-job-123", "status": "pending"}
            )
            mock_client_class.return_value = mock_client

            result = self.runner.invoke(
                cli, ["server", "add-index", "my-repo", "temporal"]
            )

            assert result.exit_code == 0
            assert "test-job-123" in result.output

    def test_add_index_command_alias_not_found(self):
        """Test cidx server add-index handles 404 alias not found (AC4)."""
        with (
            patch(
                "code_indexer.remote.config.RemoteConfig"
            ) as mock_remote_config_class,
            patch(
                "code_indexer.api_clients.admin_client.AdminAPIClient"
            ) as mock_client_class,
        ):
            # Mock RemoteConfig
            mock_remote_config = MagicMock()
            mock_remote_config.server_url = "http://test-server:8000"
            mock_decrypted_creds = MagicMock()
            mock_decrypted_creds.username = "admin"
            mock_decrypted_creds.password = "test"
            mock_remote_config.get_decrypted_credentials.return_value = (
                mock_decrypted_creds
            )
            mock_remote_config_class.return_value = mock_remote_config

            # Mock AdminAPIClient to raise APIClientError with 404
            from code_indexer.api_clients.base_client import APIClientError

            mock_client = MagicMock()
            mock_client.add_index_to_golden_repo = AsyncMock(
                side_effect=APIClientError(
                    "Golden repository 'non-existent' not found", 404
                )
            )
            mock_client_class.return_value = mock_client

            result = self.runner.invoke(
                cli, ["server", "add-index", "non-existent", "temporal"]
            )

            assert result.exit_code == 1
            assert "not found" in result.output.lower()
            assert "non-existent" in result.output

    def test_add_index_command_quiet_mode(self):
        """Test cidx server add-index --quiet outputs only job_id (AC3)."""
        with (
            patch(
                "code_indexer.remote.config.RemoteConfig"
            ) as mock_remote_config_class,
            patch(
                "code_indexer.api_clients.admin_client.AdminAPIClient"
            ) as mock_client_class,
        ):
            # Mock RemoteConfig
            mock_remote_config = MagicMock()
            mock_remote_config.server_url = "http://test-server:8000"
            mock_decrypted_creds = MagicMock()
            mock_decrypted_creds.username = "admin"
            mock_decrypted_creds.password = "test"
            mock_remote_config.get_decrypted_credentials.return_value = (
                mock_decrypted_creds
            )
            mock_remote_config_class.return_value = mock_remote_config

            # Mock AdminAPIClient
            mock_client = MagicMock()
            mock_client.add_index_to_golden_repo = AsyncMock(
                return_value={"job_id": "test-job-456", "status": "pending"}
            )
            mock_client_class.return_value = mock_client

            result = self.runner.invoke(
                cli, ["server", "add-index", "my-repo", "temporal", "--quiet"]
            )

            assert result.exit_code == 0
            assert "test-job-456" in result.output
            # In quiet mode, output should be minimal - just the job_id
            assert result.output.strip() == "test-job-456"

    def test_add_index_with_wait_polls_until_completion(self):
        """Test cidx server add-index --wait polls until job completes (AC2)."""
        with (
            patch(
                "code_indexer.remote.config.RemoteConfig"
            ) as mock_remote_config_class,
            patch(
                "code_indexer.api_clients.admin_client.AdminAPIClient"
            ) as mock_client_class,
            patch("time.sleep"),  # Mock time.sleep to speed up test
        ):
            # Mock RemoteConfig
            mock_remote_config = MagicMock()
            mock_remote_config.server_url = "http://test-server:8000"
            mock_decrypted_creds = MagicMock()
            mock_decrypted_creds.username = "admin"
            mock_decrypted_creds.password = "test"
            mock_remote_config.get_decrypted_credentials.return_value = (
                mock_decrypted_creds
            )
            mock_remote_config_class.return_value = mock_remote_config

            # Mock AdminAPIClient
            mock_client = MagicMock()
            mock_client.add_index_to_golden_repo = AsyncMock(
                return_value={"job_id": "test-job-789", "status": "pending"}
            )

            # Simulate job progression: pending -> running -> completed
            mock_client.get_job_status = AsyncMock(
                side_effect=[
                    {"job_id": "test-job-789", "status": "pending", "progress": 0},
                    {"job_id": "test-job-789", "status": "running", "progress": 50},
                    {"job_id": "test-job-789", "status": "completed", "progress": 100},
                ]
            )
            mock_client_class.return_value = mock_client

            result = self.runner.invoke(
                cli, ["server", "add-index", "my-repo", "temporal", "--wait"]
            )

            assert result.exit_code == 0
            assert "temporal" in result.output
            assert "my-repo" in result.output
            # Should have called get_job_status 3 times
            assert mock_client.get_job_status.call_count == 3

    def test_add_index_command_index_exists(self):
        """Test cidx server add-index handles 409 index already exists (AC6)."""
        with (
            patch(
                "code_indexer.remote.config.RemoteConfig"
            ) as mock_remote_config_class,
            patch(
                "code_indexer.api_clients.admin_client.AdminAPIClient"
            ) as mock_client_class,
        ):
            # Mock RemoteConfig
            mock_remote_config = MagicMock()
            mock_remote_config.server_url = "http://test-server:8000"
            mock_decrypted_creds = MagicMock()
            mock_decrypted_creds.username = "admin"
            mock_decrypted_creds.password = "test"
            mock_remote_config.get_decrypted_credentials.return_value = (
                mock_decrypted_creds
            )
            mock_remote_config_class.return_value = mock_remote_config

            # Mock AdminAPIClient to raise APIClientError with 409
            from code_indexer.api_clients.base_client import APIClientError

            mock_client = MagicMock()
            mock_client.add_index_to_golden_repo = AsyncMock(
                side_effect=APIClientError(
                    "Index type 'semantic_fts' already exists for 'my-repo'", 409
                )
            )
            mock_client_class.return_value = mock_client

            result = self.runner.invoke(
                cli, ["server", "add-index", "my-repo", "semantic_fts"]
            )

            assert result.exit_code == 1
            assert "already exists" in result.output.lower()

    def test_add_index_with_wait_handles_job_failure(self):
        """Test AC2: --wait handles job failure correctly."""
        with (
            patch(
                "code_indexer.remote.config.RemoteConfig"
            ) as mock_remote_config_class,
            patch(
                "code_indexer.api_clients.admin_client.AdminAPIClient"
            ) as mock_client_class,
            patch("time.sleep"),  # Mock time.sleep to speed up test
        ):
            # Mock RemoteConfig
            mock_remote_config = MagicMock()
            mock_remote_config.server_url = "http://test-server:8000"
            mock_decrypted_creds = MagicMock()
            mock_decrypted_creds.username = "admin"
            mock_decrypted_creds.password = "test"
            mock_remote_config.get_decrypted_credentials.return_value = (
                mock_decrypted_creds
            )
            mock_remote_config_class.return_value = mock_remote_config

            # Mock AdminAPIClient
            mock_client = MagicMock()
            mock_client.add_index_to_golden_repo = AsyncMock(
                return_value={"job_id": "test-job-fail-123", "status": "pending"}
            )

            # Simulate job progression: pending -> running -> failed
            mock_client.get_job_status = AsyncMock(
                side_effect=[
                    {"job_id": "test-job-fail-123", "status": "pending", "progress": 0},
                    {"job_id": "test-job-fail-123", "status": "running", "progress": 50},
                    {
                        "job_id": "test-job-fail-123",
                        "status": "failed",
                        "progress": 50,
                        "error": "Git clone failed: repository not accessible",
                    },
                ]
            )
            mock_client_class.return_value = mock_client

            result = self.runner.invoke(
                cli, ["server", "add-index", "my-repo", "temporal", "--wait"]
            )

            assert result.exit_code == 1
            assert "failed" in result.output.lower()
            assert "Git clone failed" in result.output or "repository not accessible" in result.output

    def test_add_index_with_wait_handles_timeout(self):
        """Test AC2: --wait respects timeout parameter."""
        with (
            patch(
                "code_indexer.remote.config.RemoteConfig"
            ) as mock_remote_config_class,
            patch(
                "code_indexer.api_clients.admin_client.AdminAPIClient"
            ) as mock_client_class,
        ):
            # Mock RemoteConfig
            mock_remote_config = MagicMock()
            mock_remote_config.server_url = "http://test-server:8000"
            mock_decrypted_creds = MagicMock()
            mock_decrypted_creds.username = "admin"
            mock_decrypted_creds.password = "test"
            mock_remote_config.get_decrypted_credentials.return_value = (
                mock_decrypted_creds
            )
            mock_remote_config_class.return_value = mock_remote_config

            # Mock AdminAPIClient
            mock_client = MagicMock()
            mock_client.add_index_to_golden_repo = AsyncMock(
                return_value={"job_id": "test-job-timeout-123", "status": "pending"}
            )

            # Simulate job stuck in running state (never completes)
            mock_client.get_job_status = AsyncMock(
                return_value={
                    "job_id": "test-job-timeout-123",
                    "status": "running",
                    "progress": 50,
                }
            )
            mock_client_class.return_value = mock_client

            # Use a very short timeout (1 second) to make test fast
            result = self.runner.invoke(
                cli,
                ["server", "add-index", "my-repo", "temporal", "--wait", "--timeout", "1"],
            )

            assert result.exit_code == 2
            assert "timeout" in result.output.lower()

    def test_add_index_command_invalid_index_type(self):
        """Test AC5: Invalid index_type returns 400 with friendly error."""
        with (
            patch(
                "code_indexer.remote.config.RemoteConfig"
            ) as mock_remote_config_class,
            patch(
                "code_indexer.api_clients.admin_client.AdminAPIClient"
            ) as mock_client_class,
        ):
            # Mock RemoteConfig
            mock_remote_config = MagicMock()
            mock_remote_config.server_url = "http://test-server:8000"
            mock_decrypted_creds = MagicMock()
            mock_decrypted_creds.username = "admin"
            mock_decrypted_creds.password = "test"
            mock_remote_config.get_decrypted_credentials.return_value = (
                mock_decrypted_creds
            )
            mock_remote_config_class.return_value = mock_remote_config

            # Mock AdminAPIClient to raise APIClientError with 400
            from code_indexer.api_clients.base_client import APIClientError

            mock_client = MagicMock()
            mock_client.add_index_to_golden_repo = AsyncMock(
                side_effect=APIClientError(
                    "Invalid request: index_type must be one of: semantic_fts, temporal, scip",
                    400,
                )
            )
            mock_client_class.return_value = mock_client

            # Note: click.Choice validates at CLI level, but we test API error handling too
            result = self.runner.invoke(
                cli, ["server", "add-index", "my-repo", "semantic_fts"]
            )

            assert result.exit_code == 1
            assert "invalid" in result.output.lower() or "error" in result.output.lower()

    def test_add_index_command_not_authenticated(self):
        """Test AC7: Command requires authentication."""
        with patch(
            "code_indexer.remote.config.RemoteConfig"
        ) as mock_remote_config_class:
            # Mock RemoteConfig to return None credentials (not authenticated)
            mock_remote_config = MagicMock()
            mock_remote_config.server_url = "http://test-server:8000"
            mock_remote_config.get_decrypted_credentials.return_value = None
            mock_remote_config_class.return_value = mock_remote_config

            result = self.runner.invoke(
                cli, ["server", "add-index", "my-repo", "temporal"]
            )

            assert result.exit_code == 1
            assert "not authenticated" in result.output.lower() or "login" in result.output.lower()


class TestServerListIndexesCommand:
    """Test suite for cidx server list-indexes command."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_list_indexes_command_success(self):
        """Test cidx server list-indexes displays index status (AC8)."""
        with (
            patch(
                "code_indexer.remote.config.RemoteConfig"
            ) as mock_remote_config_class,
            patch(
                "code_indexer.api_clients.admin_client.AdminAPIClient"
            ) as mock_client_class,
        ):
            # Mock RemoteConfig
            mock_remote_config = MagicMock()
            mock_remote_config.server_url = "http://test-server:8000"
            mock_decrypted_creds = MagicMock()
            mock_decrypted_creds.username = "admin"
            mock_decrypted_creds.password = "test"
            mock_remote_config.get_decrypted_credentials.return_value = (
                mock_decrypted_creds
            )
            mock_remote_config_class.return_value = mock_remote_config

            # Mock AdminAPIClient
            mock_client = MagicMock()
            mock_client.get_golden_repo_indexes = AsyncMock(
                return_value={
                    "alias": "my-repo",
                    "indexes": {
                        "semantic_fts": {"present": True},
                        "temporal": {"present": False},
                        "scip": {"present": False},
                    },
                }
            )
            mock_client_class.return_value = mock_client

            result = self.runner.invoke(cli, ["server", "list-indexes", "my-repo"])

            assert result.exit_code == 0
            assert "my-repo" in result.output
            assert "semantic_fts" in result.output
            assert "temporal" in result.output
            assert "scip" in result.output


class TestAdminAPIClientJobStatus:
    """Test suite for AdminAPIClient.get_job_status method."""

    async def test_get_job_status_success(self):
        """Test AdminAPIClient.get_job_status returns job status for valid job_id."""
        from code_indexer.api_clients.admin_client import AdminAPIClient

        # Create client
        client = AdminAPIClient(
            server_url="http://test-server:8000",
            credentials={"username": "admin", "password": "test"},
            project_root=None,
        )

        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "job_id": "test-job-123",
            "status": "completed",
            "progress": 100,
        }

        # Assign AsyncMock to _authenticated_request
        client._authenticated_request = AsyncMock(return_value=mock_response)

        # Call get_job_status
        result = await client.get_job_status("test-job-123")

        assert result["job_id"] == "test-job-123"
        assert result["status"] == "completed"
        assert result["progress"] == 100
        client._authenticated_request.assert_called_once_with(
            "GET", "/api/jobs/test-job-123/status"
        )
