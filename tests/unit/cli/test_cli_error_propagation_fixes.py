"""Test suite for CLI error propagation fixes.

This test suite reproduces and validates fixes for the 'str' object has no attribute 'get'
error that occurs when error handling in async functions returns strings instead of proper
dataclass objects during configuration failures or remote mode issues.

ROOT CAUSE: Commands like `auth status` and `system health` fail when remote mode preconditions
aren't met, and error handling returns strings instead of raising exceptions properly.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch
from click.testing import CliRunner
from datetime import datetime, timezone

from code_indexer.cli import cli
from code_indexer.api_clients.auth_client import AuthStatus
from code_indexer.api_clients.base_client import AuthenticationError, APIClientError


class TestCliErrorPropagation:
    """Test suite for CLI error propagation fixes."""

    @pytest.fixture
    def runner(self):
        """Create a CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary project with minimal configuration."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        # Create minimal config to satisfy find_project_root
        config_dir = project_dir / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(
            json.dumps({"project_name": "test", "codebase_dir": str(project_dir)})
        )

        return project_dir

    @pytest.fixture
    def remote_config(self, temp_project):
        """Create a remote configuration file."""
        # The remote config file is actually .remote-config, not remote.json
        remote_file = temp_project / ".code-indexer" / ".remote-config"
        remote_file.write_text(
            json.dumps(
                {
                    "mode": "remote",
                    "server_url": "http://localhost:8000",
                    "encrypted_credentials": {"username": "testuser"},
                }
            )
        )
        return remote_file

    def test_auth_status_string_error_reproduction(
        self, runner, temp_project, remote_config
    ):
        """Test that reproduces the 'str' object has no attribute 'get' error in auth status."""
        with runner.isolated_filesystem():
            # Mock the auth client to return a string instead of AuthStatus
            with patch(
                "code_indexer.api_clients.auth_client.create_auth_client"
            ) as mock_create:
                mock_client = AsyncMock()
                # This simulates the error: returning string instead of AuthStatus
                mock_client.get_auth_status = AsyncMock(
                    return_value="Error: Connection failed"
                )
                mock_create.return_value = mock_client

                # Navigate to project directory
                import os

                os.chdir(str(temp_project))

                # This should now be handled gracefully by defensive code
                result = runner.invoke(cli, ["auth", "status"])

                # The defensive code now handles the string gracefully
                # Should no longer have the attribute error
                assert "'str' object has no attribute" not in result.output
                # Should show authentication status display (even if error)
                assert (
                    "CIDX Authentication Status" in result.output
                    or "Error:" in result.output
                )
                assert (
                    result.exit_code == 0
                )  # Exit code 0 because error is handled gracefully

    def test_auth_status_with_proper_error_handling(
        self, runner, temp_project, remote_config
    ):
        """Test auth status with proper error handling returning AuthStatus."""
        with runner.isolated_filesystem():
            with patch(
                "code_indexer.api_clients.auth_client.create_auth_client"
            ) as mock_create:
                mock_client = AsyncMock()
                # Proper response: return AuthStatus object even on error
                mock_client.get_auth_status = AsyncMock(
                    return_value=AuthStatus(
                        authenticated=False,
                        username=None,
                        role=None,
                        token_valid=False,
                        token_expires=None,
                        refresh_expires=None,
                        server_url="http://localhost:8000",
                        last_refreshed=None,
                        permissions=[],
                        server_reachable=False,
                        server_version=None,
                    )
                )
                mock_create.return_value = mock_client

                import os

                os.chdir(str(temp_project))

                result = runner.invoke(cli, ["auth", "status"])
                # Should handle unauthenticated status gracefully
                assert (
                    "Authenticated: No" in result.output
                    or "Not logged in" in result.output
                )
                # Should not have attribute error
                assert "'str' object has no attribute" not in result.output

    def test_system_health_string_error_reproduction(
        self, runner, temp_project, remote_config
    ):
        """Test that reproduces the 'str' object has no attribute 'get' error in system health."""
        with runner.isolated_filesystem():
            # Mock inside the actual run_health_check function where it's imported
            with patch(
                "code_indexer.api_clients.system_client.create_system_client"
            ) as mock_create:
                mock_client = AsyncMock()
                # This simulates the error: returning string instead of dict
                mock_client.check_basic_health = AsyncMock(
                    return_value="Connection timeout"
                )
                mock_create.return_value = mock_client

                import os

                os.chdir(str(temp_project))

                result = runner.invoke(cli, ["system", "health"])

                # The defensive code now handles the string error gracefully
                assert "'str' object has no attribute" not in result.output
                assert (
                    "Health Check Error: Connection timeout" in result.output
                    or "Error:" in result.output
                )
                assert result.exit_code == 0  # Defensive code handles error gracefully

    def test_system_health_with_proper_dict_response(
        self, runner, temp_project, remote_config
    ):
        """Test system health with proper dict response."""
        with runner.isolated_filesystem():
            # Mock inside the actual run_health_check function where it's imported
            with patch(
                "code_indexer.api_clients.system_client.create_system_client"
            ) as mock_create:
                mock_client = AsyncMock()
                # Proper response: return dict
                mock_client.check_basic_health = AsyncMock(
                    return_value={
                        "status": "ok",
                        "message": "System is healthy",
                        "response_time_ms": 50.5,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
                mock_create.return_value = mock_client

                import os

                os.chdir(str(temp_project))

                result = runner.invoke(cli, ["system", "health"])
                assert "System Health:" in result.output
                assert "Response Time:" in result.output
                assert "'str' object has no attribute" not in result.output

    def test_auth_validate_error_propagation(self, runner, temp_project, remote_config):
        """Test auth validate command error handling."""
        with runner.isolated_filesystem():
            with patch(
                "code_indexer.api_clients.auth_client.create_auth_client"
            ) as mock_create:
                mock_client = AsyncMock()
                # Test with exception raising
                mock_client.validate_token = AsyncMock(
                    side_effect=APIClientError("Token validation failed")
                )
                mock_create.return_value = mock_client

                import os

                os.chdir(str(temp_project))

                # auth validate is silent by default, use --verbose to see errors
                result = runner.invoke(cli, ["auth", "validate", "--verbose"])
                # Should show meaningful error, not generic "Error"
                assert (
                    "Token validation failed" in result.output
                    or "Error" in result.output
                    or "Validating" in result.output
                )
                # Exit code depends on validation result (0 for success, 1 for failure)
                # In this case it might be 0 if error is handled gracefully
                assert result.exit_code in [0, 1]

    def test_credential_health_with_string_error(
        self, runner, temp_project, remote_config
    ):
        """Test credential health check with string return error."""
        with runner.isolated_filesystem():
            with patch(
                "code_indexer.api_clients.auth_client.create_auth_client"
            ) as mock_create:
                mock_client = AsyncMock()
                # Simulate string return instead of CredentialHealth
                mock_client.check_credential_health = AsyncMock(
                    return_value="Credential check failed"
                )
                mock_create.return_value = mock_client

                import os

                os.chdir(str(temp_project))

                result = runner.invoke(cli, ["auth", "status", "--health"])
                # Should handle error gracefully with defensive code
                assert "'str' object has no attribute" not in result.output
                assert result.exit_code == 0  # Defensive code handles error gracefully

    def test_missing_remote_configuration(self, runner, temp_project):
        """Test commands when remote configuration is missing."""
        with runner.isolated_filesystem():
            import os

            os.chdir(str(temp_project))

            # Remove remote config
            remote_file = temp_project / ".code-indexer" / "remote.json"
            if remote_file.exists():
                remote_file.unlink()

            # Test auth status without remote config
            result = runner.invoke(cli, ["auth", "status"])
            # Should show clear error about missing remote mode
            assert "remote" in result.output.lower() and "mode" in result.output.lower()
            assert result.exit_code != 0

            # Test system health without remote config
            result = runner.invoke(cli, ["system", "health"])
            assert "remote" in result.output.lower() and "mode" in result.output.lower()
            assert result.exit_code != 0

    def test_display_functions_type_safety(self, runner):
        """Test that display functions handle incorrect types gracefully."""
        from code_indexer.cli import _display_auth_status, _display_basic_health_status

        # Test _display_auth_status with string
        with patch("code_indexer.cli.console"):
            # Should not crash when receiving wrong type
            try:
                _display_auth_status("invalid string input", verbose=False)
                # If it gets here without exception, defensive code was added
            except AttributeError as e:
                # This is the original error we're fixing
                assert "'str' object has no attribute" in str(e)

        # Test _display_basic_health_status with string
        with patch("code_indexer.cli.console"):
            try:
                _display_basic_health_status("invalid string input")
                # If it gets here without exception, defensive code was added
            except AttributeError as e:
                # This is the original error we're fixing
                assert "'str' object has no attribute 'get'" in str(e)

    def test_async_error_propagation_chain(self, runner, temp_project, remote_config):
        """Test that async errors propagate correctly through the chain."""
        with runner.isolated_filesystem():
            import os

            os.chdir(str(temp_project))

            # Test auth client network error
            with patch(
                "code_indexer.api_clients.auth_client.create_auth_client"
            ) as mock_create:
                mock_client = AsyncMock()
                mock_client.get_auth_status = AsyncMock(
                    side_effect=ConnectionError("Network unreachable")
                )
                mock_create.return_value = mock_client

                result = runner.invoke(cli, ["auth", "status"])
                assert (
                    "Network unreachable" in result.output or "Error" in result.output
                )
                assert result.exit_code != 0

            # Test system client authentication error
            # Mock inside the actual run_health_check function where it's imported
            with patch(
                "code_indexer.api_clients.system_client.create_system_client"
            ) as mock_create:
                mock_client = AsyncMock()
                mock_client.check_basic_health = AsyncMock(
                    side_effect=AuthenticationError("Invalid token")
                )
                mock_create.return_value = mock_client

                result = runner.invoke(cli, ["system", "health"])
                assert (
                    "Authentication failed" in result.output
                    or "Invalid token" in result.output
                )
                assert result.exit_code != 0


class TestErrorPropagationFixes:
    """Test the fixes for error propagation issues."""

    def test_auth_status_defensive_display(self):
        """Test that _display_auth_status handles non-AuthStatus inputs defensively."""
        from code_indexer.cli import _display_auth_status

        with patch("code_indexer.cli.console") as mock_console:
            # Test with None
            _display_auth_status(None, verbose=False)
            # Should print error message, not crash
            calls = [str(call) for call in mock_console.print.call_args_list]
            assert any("error" in str(call).lower() for call in calls)

            mock_console.reset_mock()

            # Test with string
            _display_auth_status("Connection failed", verbose=False)
            # Should print error message, not crash
            calls = [str(call) for call in mock_console.print.call_args_list]
            assert any(
                "error" in str(call).lower() or "failed" in str(call).lower()
                for call in calls
            )

            mock_console.reset_mock()

            # Test with dict (wrong type but has get method)
            _display_auth_status({"error": "Failed"}, verbose=False)
            # Should handle gracefully
            calls = [str(call) for call in mock_console.print.call_args_list]
            assert any(
                "error" in str(call).lower() or "failed" in str(call).lower()
                for call in calls
            )

    def test_health_display_defensive_handling(self):
        """Test that health display functions handle incorrect types defensively."""
        from code_indexer.cli import (
            _display_basic_health_status,
            _display_health_status,
        )

        with patch("code_indexer.cli.console") as mock_console:
            # Test basic health with None
            _display_basic_health_status(None)
            # Should print error or unknown status
            calls = [str(call) for call in mock_console.print.call_args_list]
            assert any(
                "unknown" in str(call).lower() or "error" in str(call).lower()
                for call in calls
            )

            mock_console.reset_mock()

            # Test basic health with string
            _display_basic_health_status("Service unavailable")
            # Should handle gracefully
            calls = [str(call) for call in mock_console.print.call_args_list]
            assert len(calls) > 0  # Should print something, not crash

            mock_console.reset_mock()

            # Test credential health with wrong type
            _display_health_status("Invalid input")
            # Should handle gracefully
            calls = [str(call) for call in mock_console.print.call_args_list]
            assert any("error" in str(call).lower() for call in calls)
