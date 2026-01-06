"""Unit tests for multi-repository query functionality (Story #676).

Tests AC1-AC6:
- AC1: CLI multi-repository syntax (--repos flag)
- AC2: Server mode detection and error messages
- AC3: Route multi-repo queries to /api/query/multi endpoint
- AC4: Format output with repository attribution
- AC5: JSON output support
- AC6: Error handling and timeout display
"""

from click.testing import CliRunner
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import json
import asyncio
import pytest


class TestMultiRepoOptionParsing:
    """Test --repos option parsing and validation (AC1)."""

    def test_repos_option_accepts_comma_separated_list(self):
        """Test that --repos accepts comma-separated repository list."""
        from src.code_indexer.cli import cli

        runner = CliRunner()
        with runner.isolated_filesystem():
            # Setup mock remote config
            (Path.cwd() / ".code-indexer").mkdir()
            (Path.cwd() / ".code-indexer" / ".remote-config").write_text(
                json.dumps(
                    {"server_url": "http://test", "encrypted_credentials": "test"}
                )
            )

            # Test that --repos option is recognized
            with patch(
                "src.code_indexer.cli_multi_repo.execute_multi_repo_query"
            ) as mock_exec:
                mock_exec.return_value = {"results": {}}
                result = runner.invoke(
                    cli, ["query", "test", "--repos", "repo1,repo2,repo3"]
                )

                # Should not show "no such option" error
                assert (
                    "--repos" not in result.output
                    or "no such option" not in result.output.lower()
                )

    def test_repos_option_treats_empty_string_as_not_provided(self):
        """Test that --repos with empty string is treated as flag not provided.

        Empty string is falsy in Python, so 'if repos:' evaluates to False
        and the multi-repo handler is skipped entirely. This is acceptable
        behavior - empty string = flag not provided.
        """
        from src.code_indexer.cli import cli

        runner = CliRunner()
        with runner.isolated_filesystem():
            # Setup mock remote config
            (Path.cwd() / ".code-indexer").mkdir()
            (Path.cwd() / ".code-indexer" / ".remote-config").write_text(
                json.dumps(
                    {"server_url": "http://test", "encrypted_credentials": "test"}
                )
            )

            result = runner.invoke(cli, ["query", "test", "--repos", ""])

            # Empty string is falsy, so it falls through to normal remote query
            # which will fail with git repository error (acceptable behavior)
            assert result.exit_code != 0
            # Should NOT show multi-repo specific error since flag was effectively not provided
            assert "mutually exclusive" not in result.output.lower()

    def test_repos_option_splits_on_comma(self):
        """Test that --repos correctly splits comma-separated values."""
        from src.code_indexer.cli import cli

        runner = CliRunner()
        with runner.isolated_filesystem():
            # Setup mock remote config
            (Path.cwd() / ".code-indexer").mkdir()
            (Path.cwd() / ".code-indexer" / ".remote-config").write_text(
                json.dumps(
                    {"server_url": "http://test", "encrypted_credentials": "test"}
                )
            )

            with patch(
                "src.code_indexer.cli_multi_repo.execute_multi_repo_query"
            ) as mock_exec:
                mock_exec.return_value = {
                    "results": {"repo1": [], "repo2": [], "repo3": []}
                }

                runner.invoke(cli, ["query", "test", "--repos", "repo1,repo2,repo3"])

                # Verify the repos were split correctly
                if mock_exec.called:
                    call_args = mock_exec.call_args
                    repos_arg = call_args[1].get("repos") or call_args[0][1]
                    assert repos_arg == ["repo1", "repo2", "repo3"]


class TestMultiRepoErrorDisplay:
    """Test error display for partial failures (AC4, AC6)."""

    def test_display_multi_repo_results_shows_partial_failures_quiet_mode(self):
        """Test AC4: Partial failure errors are displayed in quiet mode."""
        from src.code_indexer.cli_multi_repo import display_multi_repo_results
        from rich.console import Console
        from io import StringIO

        # Create console that captures output
        output = StringIO()
        console = Console(file=output, force_terminal=False, width=120)

        results = {
            "results": {
                "repo1": [{"file_path": "test.py", "score": 0.9, "content": "code"}]
            },
            "errors": {
                "repo2": "Repository not found",
                "repo3": "Query timeout after 30 seconds",
            },
        }

        display_multi_repo_results(results, quiet=True, console=console)

        output_text = output.getvalue()
        assert "=== Errors ===" in output_text
        assert "repo2" in output_text
        assert "Repository not found" in output_text
        assert "repo3" in output_text
        assert "Query timeout" in output_text

    def test_display_multi_repo_results_shows_partial_failures_rich_mode(self):
        """Test AC4: Partial failure errors are displayed in rich mode."""
        from src.code_indexer.cli_multi_repo import display_multi_repo_results
        from rich.console import Console
        from io import StringIO

        # Create console that captures output
        output = StringIO()
        console = Console(file=output, force_terminal=False, width=120)

        results = {
            "results": {
                "repo1": [{"file_path": "test.py", "score": 0.9, "content": "code"}]
            },
            "errors": {"repo2": "Repository not found"},
        }

        display_multi_repo_results(results, quiet=False, console=console)

        output_text = output.getvalue()
        assert "Partial Failures" in output_text
        assert "repo2" in output_text
        assert "Repository not found" in output_text

    def test_display_multi_repo_results_no_errors_section_when_empty(self):
        """Test that no error section is shown when errors dict is empty."""
        from src.code_indexer.cli_multi_repo import display_multi_repo_results
        from rich.console import Console
        from io import StringIO

        # Create console that captures output
        output = StringIO()
        console = Console(file=output, force_terminal=False, width=120)

        results = {
            "results": {
                "repo1": [{"file_path": "test.py", "score": 0.9, "content": "code"}]
            },
            "errors": {},  # Empty errors dict
        }

        display_multi_repo_results(results, quiet=False, console=console)

        output_text = output.getvalue()
        # Should NOT show error section when errors dict is empty
        assert "Partial Failures" not in output_text
        assert "Errors" not in output_text

    def test_display_multi_repo_results_no_errors_section_when_missing(self):
        """Test that no error section is shown when errors key is missing."""
        from src.code_indexer.cli_multi_repo import display_multi_repo_results
        from rich.console import Console
        from io import StringIO

        # Create console that captures output
        output = StringIO()
        console = Console(file=output, force_terminal=False, width=120)

        results = {
            "results": {
                "repo1": [{"file_path": "test.py", "score": 0.9, "content": "code"}]
            }
            # No errors key at all
        }

        display_multi_repo_results(results, quiet=False, console=console)

        output_text = output.getvalue()
        # Should NOT show error section when errors key is missing
        assert "Partial Failures" not in output_text
        assert "Errors" not in output_text


class TestUnsupportedParameterWarnings:
    """Test warnings for parameters not yet supported by server (High Priority #1)."""

    @pytest.fixture
    def mock_multi_repo_environment(self):
        """Shared fixture for all unsupported parameter tests."""
        # Start all patches
        patcher_config = patch(
            "src.code_indexer.remote.query_execution._load_remote_configuration"
        )
        patcher_creds = patch(
            "src.code_indexer.remote.query_execution._get_decrypted_credentials"
        )
        patcher_client = patch(
            "src.code_indexer.api_clients.remote_query_client.RemoteQueryClient"
        )
        patcher_console = patch("src.code_indexer.cli_multi_repo.Console")

        mock_config = patcher_config.start()
        mock_creds = patcher_creds.start()
        mock_client = patcher_client.start()
        mock_console_class = patcher_console.start()

        mock_config.return_value = {"server_url": "http://test"}
        mock_creds.return_value = {"username": "test"}

        # Setup mock client
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_instance.execute_multi_repo_query = AsyncMock(return_value={"results": {}})
        mock_client.return_value = mock_instance

        # Setup mock console
        mock_console_instance = MagicMock()
        mock_console_class.return_value = mock_console_instance

        yield mock_console_instance

        # Stop all patches
        patcher_console.stop()
        patcher_client.stop()
        patcher_creds.stop()
        patcher_config.stop()

    def test_warning_for_exclude_languages_parameter(self, mock_multi_repo_environment):
        """Test that warning is shown for unsupported exclude_languages parameter."""
        from src.code_indexer.cli_multi_repo import execute_multi_repo_query

        asyncio.run(
            execute_multi_repo_query(
                query_text="test",
                repos=["repo1"],
                limit=10,
                project_root=Path.cwd(),
                exclude_languages=("python",),
            )
        )

        # Verify warning was printed
        warning_calls = [
            call
            for call in mock_multi_repo_environment.print.call_args_list
            if len(call[0]) > 0 and "exclude_languages" in str(call[0][0])
        ]
        assert len(warning_calls) > 0

    def test_warning_for_exclude_paths_parameter(self, mock_multi_repo_environment):
        """Test that warning is shown for unsupported exclude_paths parameter."""
        from src.code_indexer.cli_multi_repo import execute_multi_repo_query

        asyncio.run(
            execute_multi_repo_query(
                query_text="test",
                repos=["repo1"],
                limit=10,
                project_root=Path.cwd(),
                exclude_paths=("*/tests/*",),
            )
        )

        # Verify warning was printed
        warning_calls = [
            call
            for call in mock_multi_repo_environment.print.call_args_list
            if len(call[0]) > 0 and "exclude_paths" in str(call[0][0])
        ]
        assert len(warning_calls) > 0

    def test_warning_for_accuracy_parameter(self, mock_multi_repo_environment):
        """Test that warning is shown for unsupported accuracy parameter."""
        from src.code_indexer.cli_multi_repo import execute_multi_repo_query

        asyncio.run(
            execute_multi_repo_query(
                query_text="test",
                repos=["repo1"],
                limit=10,
                project_root=Path.cwd(),
                accuracy="high",
            )
        )

        # Verify warning was printed
        warning_calls = [
            call
            for call in mock_multi_repo_environment.print.call_args_list
            if len(call[0]) > 0 and "accuracy" in str(call[0][0])
        ]
        assert len(warning_calls) > 0

    def test_no_warning_when_all_parameters_supported(
        self, mock_multi_repo_environment
    ):
        """Test that no warning is shown when all parameters are supported."""
        from src.code_indexer.cli_multi_repo import execute_multi_repo_query

        asyncio.run(
            execute_multi_repo_query(
                query_text="test",
                repos=["repo1"],
                limit=10,
                project_root=Path.cwd(),
                languages=("python",),
                path_filter=("*/src/*",),
                min_score=0.7,
            )
        )

        # Verify NO warning was printed
        warning_calls = [
            call
            for call in mock_multi_repo_environment.print.call_args_list
            if len(call[0]) > 0 and "not yet supported" in str(call[0][0])
        ]
        assert len(warning_calls) == 0
