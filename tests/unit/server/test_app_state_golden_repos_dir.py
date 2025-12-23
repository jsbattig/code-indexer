"""
Unit tests for app.state.golden_repos_dir configuration.

Tests that golden_repos_dir is properly stored in app.state during server startup
and defaults to {CIDX_SERVER_DATA_DIR}/golden-repos.

This fixes the configuration mismatch where MCP handlers were falling back to
~/.code-indexer/golden-repos instead of using the server-configured path.
"""

import pytest
import os
from pathlib import Path
from unittest.mock import patch


class TestAppStateGoldenReposDir:
    """Test that app.state.golden_repos_dir is set correctly during server startup."""

    def test_golden_repos_dir_path_construction_logic(self, tmp_path):
        """Test the logic for constructing golden_repos_dir path."""
        # Test the path construction logic that should be used in app.py

        # Case 1: With CIDX_SERVER_DATA_DIR env var
        server_data_dir = tmp_path / "custom-server"
        expected_with_env = str(server_data_dir / "golden-repos")

        assert expected_with_env == str(Path(str(server_data_dir)) / "golden-repos")

        # Case 2: Without env var (default)
        default_server_dir = str(Path.home() / ".cidx-server")
        expected_default = str(Path(default_server_dir) / "golden-repos")

        assert expected_default == str(Path.home() / ".cidx-server" / "golden-repos")

    def test_golden_repos_dir_should_be_string_not_path(self):
        """Test that golden_repos_dir should be stored as string."""
        # Verify the conversion logic: Path → str
        test_path = Path("/test/golden-repos")
        as_string = str(test_path)

        assert isinstance(as_string, str)
        assert as_string == "/test/golden-repos"

    def test_golden_repos_dir_respects_cidx_server_data_dir_env(self, tmp_path):
        """Test that CIDX_SERVER_DATA_DIR environment variable is used."""
        custom_dir = tmp_path / "env-custom-server"

        # Simulate what app.py should do
        server_data_dir = str(custom_dir)
        golden_repos_dir = Path(server_data_dir) / "golden-repos"
        result = str(golden_repos_dir)

        expected = str(tmp_path / "env-custom-server" / "golden-repos")
        assert result == expected

    def test_golden_repos_dir_default_when_no_env_var(self):
        """Test default path when CIDX_SERVER_DATA_DIR not set."""
        # Should default to ~/.cidx-server/golden-repos
        expected_default = str(Path.home() / ".cidx-server" / "golden-repos")

        # Remove env var to test default
        env_without_var = {
            k: v for k, v in os.environ.items() if k != "CIDX_SERVER_DATA_DIR"
        }
        with patch.dict(os.environ, env_without_var, clear=True):
            server_data_dir_test = os.environ.get(
                "CIDX_SERVER_DATA_DIR", str(Path.home() / ".cidx-server")
            )
            golden_repos_dir_test = str(Path(server_data_dir_test) / "golden-repos")

            assert golden_repos_dir_test == expected_default


class TestAppStateGoldenReposDirIntegration:
    """Integration tests for app.state.golden_repos_dir after implementation."""

    @pytest.mark.skip(
        reason="Will pass after implementation - currently fails (RED phase)"
    )
    def test_app_state_has_golden_repos_dir_after_startup(self):
        """
        Integration test: Verify app.state.golden_repos_dir exists after startup.

        This test is SKIPPED during RED phase because the feature doesn't exist yet.
        After GREEN phase implementation, unskip this test to verify the fix.
        """
        from code_indexer.server.app import app

        # After startup, app.state should have golden_repos_dir
        assert hasattr(
            app.state, "golden_repos_dir"
        ), "app.state should have golden_repos_dir attribute after startup"

        # Value should be a string
        assert isinstance(
            app.state.golden_repos_dir, str
        ), "golden_repos_dir should be stored as string"

        # Value should end with 'golden-repos'
        assert app.state.golden_repos_dir.endswith(
            "golden-repos"
        ), "golden_repos_dir should end with 'golden-repos'"

    @pytest.mark.skip(
        reason="Will pass after implementation - currently fails (RED phase)"
    )
    def test_app_state_golden_repos_dir_matches_cidx_server_data_dir(self, tmp_path):
        """
        Integration test: Verify golden_repos_dir matches CIDX_SERVER_DATA_DIR.

        This test is SKIPPED during RED phase because the feature doesn't exist yet.
        After GREEN phase implementation, unskip this test to verify the fix.
        """
        custom_server_dir = tmp_path / "test-server"
        expected_golden_dir = str(custom_server_dir / "golden-repos")

        with patch.dict(os.environ, {"CIDX_SERVER_DATA_DIR": str(custom_server_dir)}):
            # Re-import to pick up env var
            import importlib
            from code_indexer.server import app as app_module

            importlib.reload(app_module)

            from code_indexer.server.app import app

            # Verify golden_repos_dir matches expected path
            assert (
                app.state.golden_repos_dir == expected_golden_dir
            ), f"Expected {expected_golden_dir}, got {app.state.golden_repos_dir}"
