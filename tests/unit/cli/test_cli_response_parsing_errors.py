"""Tests for CLI response parsing errors - TDD for reproducing 'str' object has no attribute 'get' errors.

These tests reproduce the specific CLI parsing issues identified in manual testing
where CLI commands fail with "'str' object has no attribute 'get'" when server
APIs work correctly via curl.
"""

import pytest
from unittest.mock import AsyncMock, patch, Mock
from click.testing import CliRunner
import httpx

from src.code_indexer.cli import cli


class TestCLIResponseParsingErrors:
    """Test class to reproduce and fix CLI response parsing errors."""

    @pytest.fixture
    def cli_runner(self):
        """Create CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_project_setup(self):
        """Setup mocks for project and remote configuration."""
        with (
            patch(
                "code_indexer.mode_detection.command_mode_detector.find_project_root"
            ) as mock_find_root,
            patch(
                "code_indexer.remote.config.load_remote_configuration"
            ) as mock_load_config,
        ):
            mock_find_root.return_value = "/test/project"
            mock_load_config.return_value = {
                "server_url": "http://localhost:8096",
                "encrypted_credentials": {"username": "testuser"},
            }
            yield mock_find_root, mock_load_config

    def test_auth_status_fails_with_str_get_attribute_error(
        self, cli_runner, mock_project_setup
    ):
        """Test reproducing the 'str' object has no attribute 'get' error in auth status.

        This test reproduces the exact error where CLI tries to call .get() on a string
        response instead of a parsed JSON dictionary.
        """
        mock_find_root, mock_load_config = mock_project_setup

        # Mock auth client creation
        with patch(
            "code_indexer.api_clients.auth_client.create_auth_client"
        ) as mock_create_client:
            mock_client = AsyncMock()
            mock_create_client.return_value = mock_client

            # Mock the auth status response as string (the bug condition)
            # This simulates what happens when the API returns a raw httpx.Response
            # instead of parsed JSON
            mock_client.get_auth_status.return_value = (
                "{'authenticated': true}"  # String, not dict
            )

            result = cli_runner.invoke(cli, ["auth", "status"])

            # Should fail with AttributeError about 'str' object not having 'get'
            assert result.exit_code != 0
            # Note: This test will fail initially (TDD red phase) because the bug exists
            # The error message varies but will contain string-related attribute errors

    def test_system_health_fails_with_response_parsing_error(
        self, cli_runner, mock_project_setup
    ):
        """Test reproducing system health response parsing errors.

        This test shows the bug where system health endpoint tries to use httpx.Response
        as a dictionary, causing TypeError when setting response["response_time_ms"].
        """
        mock_find_root, mock_load_config = mock_project_setup

        # Mock the system client but let the actual implementation run with a mock response
        with (
            patch(
                "code_indexer.api_clients.system_client.create_system_client"
            ) as mock_create_client,
            patch(
                "code_indexer.api_clients.system_client.SystemAPIClient._authenticated_request"
            ) as mock_auth_request,
            patch(
                "src.code_indexer.disabled_commands.detect_current_mode"
            ) as mock_detect_mode,
        ):
            # Mock mode detection to return remote mode
            mock_detect_mode.return_value = "remote"
            # Create real SystemAPIClient instance but mock its _authenticated_request
            from src.code_indexer.api_clients.system_client import SystemAPIClient
            from pathlib import Path

            real_client = SystemAPIClient(
                server_url="http://localhost:8096",
                credentials={"username": "testuser"},
                project_root=Path("/test/project"),
            )
            mock_create_client.return_value = real_client

            # Create a mock httpx.Response that behaves like the real one
            mock_response = Mock(spec=httpx.Response)
            mock_response.json.return_value = {"status": "ok", "message": "Healthy"}
            mock_response.status_code = 200

            # This will cause the bug: check_basic_health tries to do response["response_time_ms"]
            # but response is an httpx.Response object, not a dict
            mock_auth_request.return_value = mock_response

            result = cli_runner.invoke(cli, ["system", "health"])

            # Should fail because code tries to access response["response_time_ms"]
            # on an httpx.Response object instead of a dictionary
            assert result.exit_code != 0
            assert (
                "'MockType' object does not support item assignment" in result.output
                or "'Response' object does not support item assignment" in result.output
                or "TypeError" in result.output
            )
            # This reproduces the actual bug in the system client

    def test_auth_validate_fails_with_response_type_error(
        self, cli_runner, mock_project_setup
    ):
        """Test reproducing auth validate response parsing errors."""
        mock_find_root, mock_load_config = mock_project_setup

        with patch(
            "code_indexer.api_clients.auth_client.create_auth_client"
        ) as mock_create_client:
            mock_client = AsyncMock()
            mock_create_client.return_value = mock_client

            # Mock returning wrong type (httpx.Response instead of boolean)
            mock_response = Mock(spec=httpx.Response)
            mock_response.json.return_value = {"valid": True}
            mock_response.status_code = 200

            # Bug: validate_credentials returns response object instead of boolean
            mock_client.validate_credentials.return_value = mock_response

            result = cli_runner.invoke(cli, ["auth", "validate", "--verbose"])

            # Should fail with type-related errors
            assert result.exit_code != 0
            # This will initially fail (TDD red phase) because the bug exists


class TestCorrectResponseParsing:
    """Test class demonstrating correct response parsing (TDD green phase targets)."""

    @pytest.fixture
    def cli_runner(self):
        """Create CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_project_setup(self):
        """Setup mocks for project and remote configuration."""
        with (
            patch(
                "code_indexer.mode_detection.command_mode_detector.find_project_root"
            ) as mock_find_root,
            patch(
                "code_indexer.remote.config.load_remote_configuration"
            ) as mock_load_config,
        ):
            mock_find_root.return_value = "/test/project"
            mock_load_config.return_value = {
                "server_url": "http://localhost:8096",
                "encrypted_credentials": {"username": "testuser"},
            }
            yield mock_find_root, mock_load_config

    def test_auth_status_succeeds_with_proper_json_parsing(
        self, cli_runner, mock_project_setup
    ):
        """Test that auth status works correctly when proper JSON parsing is implemented.

        This is the target behavior after fixing the bug.
        """
        mock_find_root, mock_load_config = mock_project_setup

        with patch(
            "code_indexer.api_clients.auth_client.create_auth_client"
        ) as mock_create_client:
            mock_client = AsyncMock()
            mock_create_client.return_value = mock_client

            # Mock proper AuthStatus object (correct behavior)
            from src.code_indexer.api_clients.auth_client import AuthStatus

            status = AuthStatus(
                authenticated=True,
                username="testuser",
                role="user",
                token_valid=True,
                token_expires=None,
                refresh_expires=None,
                server_url="http://localhost:8096",
                last_refreshed=None,
                permissions=["read"],
                server_reachable=True,
            )
            mock_client.get_auth_status.return_value = status

            result = cli_runner.invoke(cli, ["auth", "status"])

            # Should succeed with proper response parsing
            assert result.exit_code == 0
            assert "Authenticated: Yes" in result.output
            assert "testuser" in result.output

    def test_system_health_succeeds_with_proper_json_parsing(
        self, cli_runner, mock_project_setup
    ):
        """Test that system health works correctly when proper JSON parsing is implemented.

        This is the target behavior after fixing the bug.
        """
        mock_find_root, mock_load_config = mock_project_setup

        with (
            patch(
                "code_indexer.api_clients.system_client.create_system_client"
            ) as mock_create_client,
            patch(
                "src.code_indexer.disabled_commands.detect_current_mode"
            ) as mock_detect_mode,
        ):
            # Mock mode detection to return remote mode
            mock_detect_mode.return_value = "remote"

            mock_client = AsyncMock()
            mock_create_client.return_value = mock_client

            # Mock proper dictionary response (correct behavior)
            health_result = {
                "status": "ok",
                "message": "System is healthy",
                "response_time_ms": 45.2,
            }
            mock_client.check_basic_health.return_value = health_result

            result = cli_runner.invoke(cli, ["system", "health"])

            # Print output for debugging
            print(f"Exit code: {result.exit_code}")
            print(f"Output: {result.output}")

            # Should succeed with proper response parsing
            assert result.exit_code == 0
            assert "System Health: OK" in result.output
            assert "45.2ms" in result.output

    def test_auth_validate_succeeds_with_proper_boolean_return(
        self, cli_runner, mock_project_setup
    ):
        """Test that auth validate works correctly when proper boolean parsing is implemented.

        This is the target behavior after fixing the bug.
        """
        mock_find_root, mock_load_config = mock_project_setup

        with (
            patch(
                "code_indexer.api_clients.auth_client.create_auth_client"
            ) as mock_create_client,
            patch(
                "src.code_indexer.disabled_commands.detect_current_mode"
            ) as mock_detect_mode,
        ):
            # Mock mode detection to return remote mode
            mock_detect_mode.return_value = "remote"

            mock_client = AsyncMock()
            mock_create_client.return_value = mock_client

            # Mock proper boolean response (correct behavior)
            mock_client.validate_credentials.return_value = True

            result = cli_runner.invoke(cli, ["auth", "validate", "--verbose"])

            # Should succeed with proper response parsing
            assert result.exit_code == 0
            assert "valid" in result.output.lower()


class TestEdgeCaseResponseParsing:
    """Test edge cases in response parsing to ensure robustness."""

    @pytest.fixture
    def cli_runner(self):
        """Create CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_project_setup(self):
        """Setup mocks for project and remote configuration."""
        with (
            patch(
                "code_indexer.mode_detection.command_mode_detector.find_project_root"
            ) as mock_find_root,
            patch(
                "code_indexer.remote.config.load_remote_configuration"
            ) as mock_load_config,
        ):
            mock_find_root.return_value = "/test/project"
            mock_load_config.return_value = {
                "server_url": "http://localhost:8096",
                "encrypted_credentials": {"username": "testuser"},
            }
            yield mock_find_root, mock_load_config

    def test_system_health_handles_malformed_json_gracefully(
        self, cli_runner, mock_project_setup
    ):
        """Test that system health handles malformed JSON responses gracefully."""
        mock_find_root, mock_load_config = mock_project_setup

        with patch(
            "code_indexer.api_clients.system_client.create_system_client"
        ) as mock_create_client:
            mock_client = AsyncMock()
            mock_create_client.return_value = mock_client

            # Mock client that raises JSON parsing error
            from src.code_indexer.api_clients.base_client import APIClientError

            mock_client.check_basic_health.side_effect = APIClientError(
                "Invalid JSON response"
            )

            result = cli_runner.invoke(cli, ["system", "health"])

            # Should handle error gracefully without crashing
            assert result.exit_code != 0
            assert "error" in result.output.lower()

    def test_auth_status_handles_network_error_gracefully(
        self, cli_runner, mock_project_setup
    ):
        """Test that auth status handles network errors gracefully."""
        mock_find_root, mock_load_config = mock_project_setup

        with patch(
            "code_indexer.api_clients.auth_client.create_auth_client"
        ) as mock_create_client:
            mock_client = AsyncMock()
            mock_create_client.return_value = mock_client

            # Mock client that raises network error
            from src.code_indexer.api_clients.base_client import APIClientError

            mock_client.get_auth_status.side_effect = APIClientError(
                "Connection failed"
            )

            result = cli_runner.invoke(cli, ["auth", "status"])

            # Should handle error gracefully without crashing
            assert result.exit_code != 0
            assert "error" in result.output.lower()
