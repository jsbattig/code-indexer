"""Unit tests for admin MCP credentials CLI commands."""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from click.testing import CliRunner

from code_indexer.server.auth.user_manager import UserManager, UserRole
from code_indexer.server.auth.mcp_credential_manager import MCPCredentialManager


@pytest.fixture
def temp_users_file(tmp_path):
    """Create a temporary users file."""
    users_file = tmp_path / "users.json"
    users_file.write_text("{}")
    return str(users_file)


@pytest.fixture
def user_manager(temp_users_file):
    """Create a UserManager with test users."""
    manager = UserManager(users_file_path=temp_users_file)

    # Create admin user
    manager.create_user("admin_user", "AdminPass123!", UserRole.ADMIN)

    # Create target users for credential management
    manager.create_user("test_user", "TestPass123!", UserRole.NORMAL_USER)
    manager.create_user("another_user", "AnotherPass123!", UserRole.NORMAL_USER)

    return manager


@pytest.fixture
def mcp_credential_manager(user_manager):
    """Create an MCPCredentialManager."""
    return MCPCredentialManager(user_manager=user_manager)


@pytest.fixture
def populated_credentials(mcp_credential_manager):
    """Create test credentials for users."""
    # Create credentials for test_user
    cred1 = mcp_credential_manager.generate_credential("test_user", "Test Cred 1")
    cred2 = mcp_credential_manager.generate_credential("test_user", "Test Cred 2")

    # Create credentials for another_user
    cred3 = mcp_credential_manager.generate_credential("another_user", "Another Cred 1")

    return {"test_user": [cred1, cred2], "another_user": [cred3]}


class TestAdminMCPCredentialsListCommand:
    """Tests for 'cidx admin mcp-credentials list' command."""

    @patch(
        "code_indexer.mode_detection.command_mode_detector.CommandModeDetector.detect_mode",
        return_value="remote",
    )
    def test_list_credentials_for_user_table_format(
        self, mock_mode_detector, user_manager, populated_credentials
    ):
        """Test listing credentials for a user in table format."""
        from code_indexer.cli import cli

        runner = CliRunner()

        # Mock credential loading and API client
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

            # Configure mock to return credentials
            mock_client_instance = MagicMock()
            mock_client_instance.list_mcp_credentials = AsyncMock(
                return_value={
                    "credentials": [
                        {
                            "credential_id": "cred-id-1",
                            "client_id_prefix": "mcp_abcd",
                            "name": "Test Cred 1",
                            "created_at": "2025-12-25T10:00:00Z",
                            "last_used_at": None,
                        },
                        {
                            "credential_id": "cred-id-2",
                            "client_id_prefix": "mcp_efgh",
                            "name": "Test Cred 2",
                            "created_at": "2025-12-25T11:00:00Z",
                            "last_used_at": "2025-12-25T12:00:00Z",
                        },
                    ]
                }
            )
            mock_client_instance.close = AsyncMock()
            mock_client_instance.close = AsyncMock()
            mock_admin_client.return_value = mock_client_instance

            result = runner.invoke(
                cli, ["admin", "mcp-credentials", "list", "--user", "test_user"]
            )

            assert result.exit_code == 0
            assert "Test Cred 1" in result.output
            assert "Test Cred 2" in result.output
            assert "mcp_abcd" in result.output
            assert "mcp_efgh" in result.output

    @patch(
        "code_indexer.mode_detection.command_mode_detector.CommandModeDetector.detect_mode",
        return_value="remote",
    )
    def test_list_credentials_for_user_json_format(
        self, mock_mode_detector, user_manager, populated_credentials
    ):
        """Test listing credentials for a user in JSON format."""
        from code_indexer.cli import cli

        runner = CliRunner()

        # Mock credential loading and API client
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

            # Configure mock to return credentials
            mock_client_instance = MagicMock()
            credentials_data = [
                {
                    "credential_id": "cred-id-1",
                    "client_id_prefix": "mcp_abcd",
                    "name": "Test Cred 1",
                    "created_at": "2025-12-25T10:00:00Z",
                    "last_used_at": None,
                }
            ]
            mock_client_instance.list_mcp_credentials = AsyncMock(
                return_value={"credentials": credentials_data}
            )
            mock_client_instance.close = AsyncMock()
            mock_admin_client.return_value = mock_client_instance

            result = runner.invoke(
                cli,
                [
                    "admin",
                    "mcp-credentials",
                    "list",
                    "--user",
                    "test_user",
                    "--format",
                    "json",
                ],
            )

            assert result.exit_code == 0
            output_data = json.loads(result.output)
            assert len(output_data) == 1
            assert output_data[0]["credential_id"] == "cred-id-1"
            assert output_data[0]["name"] == "Test Cred 1"

    @patch(
        "code_indexer.mode_detection.command_mode_detector.CommandModeDetector.detect_mode",
        return_value="remote",
    )
    def test_list_credentials_user_not_found(self, mock_mode_detector):
        """Test listing credentials for non-existent user."""
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
                side_effect=Exception("User not found")
            )
            mock_client_instance.close = AsyncMock()
            mock_admin_client.return_value = mock_client_instance

            result = runner.invoke(
                cli, ["admin", "mcp-credentials", "list", "--user", "nonexistent"]
            )

            assert result.exit_code != 0
            assert (
                "User not found" in result.output
                or "not found" in result.output.lower()
            )


class TestAdminMCPCredentialsCreateCommand:
    """Tests for 'cidx admin mcp-credentials create' command."""

    @patch(
        "code_indexer.mode_detection.command_mode_detector.CommandModeDetector.detect_mode",
        return_value="remote",
    )
    def test_create_credential_for_user_table_format(
        self, mock_mode_detector, user_manager
    ):
        """Test creating a credential for a user in table format."""
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
                    "client_secret": "mcp_sec_abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                    "client_id_prefix": "mcp_1234",
                    "name": "New Credential",
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
                    "New Credential",
                ],
            )

            assert result.exit_code == 0
            assert "mcp_1234567890abcdef1234567890abcdef" in result.output  # client_id
            assert "mcp_sec_" in result.output  # client_secret
            assert "New Credential" in result.output
            assert "WARNING" in result.output or "one time" in result.output.lower()

    @patch(
        "code_indexer.mode_detection.command_mode_detector.CommandModeDetector.detect_mode",
        return_value="remote",
    )
    def test_create_credential_for_user_json_format(
        self, mock_mode_detector, user_manager
    ):
        """Test creating a credential for a user in JSON format."""
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
            credential_data = {
                "credential_id": "new-cred-id",
                "client_id": "mcp_1234567890abcdef1234567890abcdef",
                "client_secret": "mcp_sec_abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                "client_id_prefix": "mcp_1234",
                "name": "New Credential",
                "created_at": "2025-12-25T12:00:00Z",
            }
            mock_client_instance.create_mcp_credential = AsyncMock(
                return_value=credential_data
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
                    "New Credential",
                    "--format",
                    "json",
                ],
            )

            assert result.exit_code == 0
            output_data = json.loads(result.output)
            assert output_data["client_id"] == "mcp_1234567890abcdef1234567890abcdef"
            assert output_data["client_secret"].startswith("mcp_sec_")
            assert output_data["name"] == "New Credential"

    @patch(
        "code_indexer.mode_detection.command_mode_detector.CommandModeDetector.detect_mode",
        return_value="remote",
    )
    def test_create_credential_without_name(self, mock_mode_detector, user_manager):
        """Test creating a credential without providing a name."""
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
                    "client_secret": "mcp_sec_abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                    "client_id_prefix": "mcp_1234",
                    "name": None,
                    "created_at": "2025-12-25T12:00:00Z",
                }
            )
            mock_client_instance.close = AsyncMock()
            mock_admin_client.return_value = mock_client_instance

            result = runner.invoke(
                cli, ["admin", "mcp-credentials", "create", "--user", "test_user"]
            )

            assert result.exit_code == 0
            assert "mcp_1234567890abcdef1234567890abcdef" in result.output


class TestAdminMCPCredentialsRevokeCommand:
    """Tests for 'cidx admin mcp-credentials revoke' command."""

    @patch(
        "code_indexer.mode_detection.command_mode_detector.CommandModeDetector.detect_mode",
        return_value="remote",
    )
    def test_revoke_credential(
        self, mock_mode_detector, user_manager, populated_credentials
    ):
        """Test revoking a user's credential."""
        from code_indexer.cli import cli

        runner = CliRunner()

        credential_id = populated_credentials["test_user"][0]["credential_id"]

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
                    credential_id,
                ],
            )

            assert result.exit_code == 0
            assert (
                "revoked" in result.output.lower() or "success" in result.output.lower()
            )

    @patch(
        "code_indexer.mode_detection.command_mode_detector.CommandModeDetector.detect_mode",
        return_value="remote",
    )
    def test_revoke_credential_not_found(self, mock_mode_detector, user_manager):
        """Test revoking a non-existent credential."""
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
                side_effect=Exception("Credential not found")
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
                    "nonexistent-id",
                ],
            )

            assert result.exit_code != 0
            assert "not found" in result.output.lower()


class TestAdminMCPCredentialsListAllCommand:
    """Tests for 'cidx admin mcp-credentials list-all' command."""

    @patch(
        "code_indexer.mode_detection.command_mode_detector.CommandModeDetector.detect_mode",
        return_value="remote",
    )
    def test_list_all_credentials_table_format(
        self, mock_mode_detector, user_manager, populated_credentials
    ):
        """Test listing all credentials across all users in table format."""
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
                            "username": "test_user",
                            "credential_id": "cred-1",
                            "client_id_prefix": "mcp_abcd",
                            "name": "Test Cred 1",
                            "created_at": "2025-12-25T10:00:00Z",
                            "last_used_at": None,
                        },
                        {
                            "username": "test_user",
                            "credential_id": "cred-2",
                            "client_id_prefix": "mcp_efgh",
                            "name": "Test Cred 2",
                            "created_at": "2025-12-25T11:00:00Z",
                            "last_used_at": None,
                        },
                        {
                            "username": "another_user",
                            "credential_id": "cred-3",
                            "client_id_prefix": "mcp_ijkl",
                            "name": "Another Cred 1",
                            "created_at": "2025-12-25T12:00:00Z",
                            "last_used_at": None,
                        },
                    ]
                }
            )
            mock_client_instance.close = AsyncMock()
            mock_admin_client.return_value = mock_client_instance

            result = runner.invoke(cli, ["admin", "mcp-credentials", "list-all"])

            assert result.exit_code == 0
            assert "test_user" in result.output
            assert "another_user" in result.output
            assert "Test Cred 1" in result.output
            assert "Another Cred" in result.output  # Name may wrap in table

    @patch(
        "code_indexer.mode_detection.command_mode_detector.CommandModeDetector.detect_mode",
        return_value="remote",
    )
    def test_list_all_credentials_json_format(
        self, mock_mode_detector, user_manager, populated_credentials
    ):
        """Test listing all credentials across all users in JSON format."""
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
            credentials_data = [
                {
                    "username": "test_user",
                    "credential_id": "cred-1",
                    "client_id_prefix": "mcp_abcd",
                    "name": "Test Cred 1",
                    "created_at": "2025-12-25T10:00:00Z",
                    "last_used_at": None,
                },
                {
                    "username": "another_user",
                    "credential_id": "cred-3",
                    "client_id_prefix": "mcp_ijkl",
                    "name": "Another Cred 1",
                    "created_at": "2025-12-25T12:00:00Z",
                    "last_used_at": None,
                },
            ]
            mock_client_instance.list_all_mcp_credentials = AsyncMock(
                return_value={"credentials": credentials_data}
            )
            mock_client_instance.close = AsyncMock()
            mock_admin_client.return_value = mock_client_instance

            result = runner.invoke(
                cli, ["admin", "mcp-credentials", "list-all", "--format", "json"]
            )

            assert result.exit_code == 0
            output_data = json.loads(result.output)
            assert len(output_data) == 2
            assert output_data[0]["username"] == "test_user"
            assert output_data[1]["username"] == "another_user"

    @patch(
        "code_indexer.mode_detection.command_mode_detector.CommandModeDetector.detect_mode",
        return_value="remote",
    )
    def test_list_all_credentials_with_limit(
        self, mock_mode_detector, user_manager, populated_credentials
    ):
        """Test listing all credentials with limit option."""
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
                            "username": "test_user",
                            "credential_id": "cred-1",
                            "client_id_prefix": "mcp_abcd",
                            "name": "Test Cred 1",
                            "created_at": "2025-12-25T10:00:00Z",
                            "last_used_at": None,
                        }
                    ]
                }
            )
            mock_client_instance.close = AsyncMock()
            mock_admin_client.return_value = mock_client_instance

            result = runner.invoke(
                cli, ["admin", "mcp-credentials", "list-all", "--limit", "1"]
            )

            assert result.exit_code == 0
            # Verify limit was respected (only 1 credential shown)
            assert "Test Cred 1" in result.output
