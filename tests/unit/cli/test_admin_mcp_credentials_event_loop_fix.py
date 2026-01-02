"""Test for admin MCP credentials CLI event loop handling.

This test reproduces the 'Event loop is closed' error that occurs
when admin_client.close() is called via run_async() after the
main operation has already completed and closed its event loop.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from click.testing import CliRunner


class TestAdminMCPCredentialsEventLoopHandling:
    """Test that admin MCP credentials commands handle event loop properly."""

    @patch(
        "code_indexer.mode_detection.command_mode_detector.CommandModeDetector.detect_mode",
        return_value="remote",
    )
    def test_list_credentials_no_event_loop_error(self, mock_mode_detector):
        """Test that list command doesn't raise 'Event loop is closed' error."""
        from code_indexer.cli import cli

        runner = CliRunner()

        with (
            patch(
                "code_indexer.mode_detection.command_mode_detector.find_project_root",
                return_value=Path.cwd(),
            ),
            patch(
                "code_indexer.cli._load_admin_credentials",
                return_value=({"username": "admin", "password": "pass"}, "http://test"),
            ),
            patch(
                "code_indexer.api_clients.admin_client.AdminAPIClient"
            ) as mock_admin_client,
        ):

            mock_client_instance = MagicMock()
            mock_client_instance.list_mcp_credentials = AsyncMock(
                return_value={
                    "credentials": [
                        {
                            "credential_id": "cred-1",
                            "client_id_prefix": "mcp_test",
                            "name": "Test",
                            "created_at": "2025-12-25T10:00:00Z",
                            "last_used_at": None,
                        }
                    ]
                }
            )
            mock_client_instance.close = AsyncMock()
            mock_admin_client.return_value = mock_client_instance

            result = runner.invoke(
                cli, ["admin", "mcp-credentials", "list", "--user", "test_user"]
            )

            # CRITICAL: Exit code must be 0, not non-zero
            assert (
                result.exit_code == 0
            ), f"Expected exit code 0, got {result.exit_code}. Output:\n{result.output}"

            # CRITICAL: Should NOT contain "Event loop is closed" error
            assert (
                "Event loop is closed" not in result.output
            ), f"Found 'Event loop is closed' error in output:\n{result.output}"

            # CRITICAL: Should contain success output
            assert "Test" in result.output

    @patch(
        "code_indexer.mode_detection.command_mode_detector.CommandModeDetector.detect_mode",
        return_value="remote",
    )
    def test_create_credential_no_event_loop_error(self, mock_mode_detector):
        """Test that create command doesn't raise 'Event loop is closed' error."""
        from code_indexer.cli import cli

        runner = CliRunner()

        with (
            patch(
                "code_indexer.mode_detection.command_mode_detector.find_project_root",
                return_value=Path.cwd(),
            ),
            patch(
                "code_indexer.cli._load_admin_credentials",
                return_value=({"username": "admin", "password": "pass"}, "http://test"),
            ),
            patch(
                "code_indexer.api_clients.admin_client.AdminAPIClient"
            ) as mock_admin_client,
        ):

            mock_client_instance = MagicMock()
            mock_client_instance.create_mcp_credential = AsyncMock(
                return_value={
                    "credential_id": "new-cred-id",
                    "client_id": "mcp_1234567890abcdef1234567890abcdef",
                    "client_secret": "mcp_sec_secret",
                    "name": "New Cred",
                    "created_at": "2025-12-25T12:00:00Z",
                }
            )
            mock_client_instance.close = AsyncMock()
            mock_admin_client.return_value = mock_client_instance

            result = runner.invoke(
                cli,
                [
                    "admin",
                    "mcp-credentials",
                    "create",
                    "--user",
                    "test_user",
                    "--name",
                    "New Cred",
                ],
            )

            # CRITICAL: Exit code must be 0
            assert (
                result.exit_code == 0
            ), f"Expected exit code 0, got {result.exit_code}. Output:\n{result.output}"

            # CRITICAL: Should NOT contain "Event loop is closed" error
            assert (
                "Event loop is closed" not in result.output
            ), f"Found 'Event loop is closed' error in output:\n{result.output}"

            # CRITICAL: Should contain success message
            assert (
                "Created" in result.output
                or "mcp_1234567890abcdef1234567890abcdef" in result.output
            )

    @patch(
        "code_indexer.mode_detection.command_mode_detector.CommandModeDetector.detect_mode",
        return_value="remote",
    )
    def test_revoke_credential_no_event_loop_error(self, mock_mode_detector):
        """Test that revoke command doesn't raise 'Event loop is closed' error."""
        from code_indexer.cli import cli

        runner = CliRunner()

        with (
            patch(
                "code_indexer.mode_detection.command_mode_detector.find_project_root",
                return_value=Path.cwd(),
            ),
            patch(
                "code_indexer.cli._load_admin_credentials",
                return_value=({"username": "admin", "password": "pass"}, "http://test"),
            ),
            patch(
                "code_indexer.api_clients.admin_client.AdminAPIClient"
            ) as mock_admin_client,
        ):

            mock_client_instance = MagicMock()
            mock_client_instance.revoke_mcp_credential = AsyncMock(
                return_value={"success": True}
            )
            mock_client_instance.close = AsyncMock()
            mock_admin_client.return_value = mock_client_instance

            result = runner.invoke(
                cli,
                [
                    "admin",
                    "mcp-credentials",
                    "revoke",
                    "--user",
                    "test_user",
                    "--credential-id",
                    "cred-123",
                ],
            )

            # CRITICAL: Exit code must be 0
            assert (
                result.exit_code == 0
            ), f"Expected exit code 0, got {result.exit_code}. Output:\n{result.output}"

            # CRITICAL: Should NOT contain "Event loop is closed" error
            assert (
                "Event loop is closed" not in result.output
            ), f"Found 'Event loop is closed' error in output:\n{result.output}"

            # CRITICAL: Should contain success message
            assert "revoked" in result.output.lower()

    @patch(
        "code_indexer.mode_detection.command_mode_detector.CommandModeDetector.detect_mode",
        return_value="remote",
    )
    def test_list_all_credentials_no_event_loop_error(self, mock_mode_detector):
        """Test that list-all command doesn't raise 'Event loop is closed' error."""
        from code_indexer.cli import cli

        runner = CliRunner()

        with (
            patch(
                "code_indexer.mode_detection.command_mode_detector.find_project_root",
                return_value=Path.cwd(),
            ),
            patch(
                "code_indexer.cli._load_admin_credentials",
                return_value=({"username": "admin", "password": "pass"}, "http://test"),
            ),
            patch(
                "code_indexer.api_clients.admin_client.AdminAPIClient"
            ) as mock_admin_client,
        ):

            mock_client_instance = MagicMock()
            mock_client_instance.list_all_mcp_credentials = AsyncMock(
                return_value={
                    "credentials": [
                        {
                            "username": "user1",
                            "credential_id": "cred-1",
                            "client_id_prefix": "mcp_test",
                            "name": "Test",
                            "created_at": "2025-12-25T10:00:00Z",
                            "last_used_at": None,
                        }
                    ]
                }
            )
            mock_client_instance.close = AsyncMock()
            mock_admin_client.return_value = mock_client_instance

            result = runner.invoke(cli, ["admin", "mcp-credentials", "list-all"])

            # CRITICAL: Exit code must be 0
            assert (
                result.exit_code == 0
            ), f"Expected exit code 0, got {result.exit_code}. Output:\n{result.output}"

            # CRITICAL: Should NOT contain "Event loop is closed" error
            assert (
                "Event loop is closed" not in result.output
            ), f"Found 'Event loop is closed' error in output:\n{result.output}"

            # CRITICAL: Should contain credentials output
            assert "user1" in result.output or "Test" in result.output
