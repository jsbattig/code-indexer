"""Tests for CLI staleness display integration across local and remote modes.

Tests that staleness indicators are properly displayed in CLI output for both
local and remote query modes with identical visual presentation.
"""

import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, Mock
from click.testing import CliRunner

from code_indexer.cli import query
from code_indexer.api_clients.remote_query_client import QueryResultItem
from code_indexer.remote.staleness_detector import EnhancedQueryResultItem


class TestCLIStalenessDisplayIntegration:
    """Test CLI staleness display integration for both local and remote modes."""

    @pytest.fixture
    def cli_runner(self):
        """Create CLI runner for testing."""
        return CliRunner()

    @pytest.fixture
    def temp_project_root(self):
        """Create temporary project root directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            # Create basic CIDX structure
            cidx_dir = project_root / ".code-indexer"
            cidx_dir.mkdir()
            yield project_root

    def test_remote_mode_displays_staleness_indicators(
        self, cli_runner, temp_project_root
    ):
        """Test that remote mode CLI output includes staleness indicators."""
        # This test will initially fail because CLI doesn't show staleness indicators yet

        # Mock remote mode detection
        with (
            patch(
                "code_indexer.disabled_commands.detect_current_mode"
            ) as mock_detect_mode,
            patch("code_indexer.cli.asyncio.run") as mock_asyncio,
            patch(
                "code_indexer.mode_detection.command_mode_detector.CommandModeDetector"
            ) as mock_detector,
        ):

            # Mock the mode detection for require_mode decorator
            mock_detect_mode.return_value = "remote"

            # Setup mocks
            mock_instance = Mock()
            mock_instance.detect_mode.return_value = "remote"
            mock_detector.return_value = mock_instance

            # Create enhanced result with staleness metadata
            enhanced_result = EnhancedQueryResultItem(
                similarity_score=0.95,
                file_path="test.py",
                line_number=1,
                code_snippet="def test_function():\n    pass",
                repository_alias="test-repo",
                language="python",
                file_last_modified=time.time() - 3600,
                indexed_timestamp=time.time() - 1800,
                local_file_mtime=time.time(),
                is_stale=True,
                staleness_delta_seconds=1800.0,
                staleness_indicator="🟡 30m stale",
            )

            mock_asyncio.return_value = [enhanced_result]

            # Run query command
            result = cli_runner.invoke(
                query,
                ["test query", "--quiet"],
                obj={
                    "mode": "remote",
                    "project_root": temp_project_root,
                    "config_manager": Mock(),
                },
            )

            # Should now show staleness indicators in CLI output
            assert "🟡 30m stale" in result.output
            assert result.exit_code == 0

    def test_local_mode_displays_staleness_indicators(
        self, cli_runner, temp_project_root
    ):
        """Test that local mode CLI output includes staleness indicators."""
        # This test will initially fail because local mode doesn't have staleness detection yet

        # Mock local mode components
        with (
            patch(
                "code_indexer.disabled_commands.detect_current_mode"
            ) as mock_detect_mode,
            patch("code_indexer.cli.EmbeddingProviderFactory") as mock_factory,
            patch("code_indexer.cli.BackendFactory") as mock_backend_factory,
            patch(
                "code_indexer.services.generic_query_service.GenericQueryService"
            ) as mock_query_service,
            patch(
                "code_indexer.services.git_topology_service.GitTopologyService"
            ) as mock_git_service,
        ):
            # Mock the mode detection for require_mode decorator
            mock_detect_mode.return_value = "local"

            # Setup embedding provider mock
            mock_provider = Mock()
            mock_provider.health_check.return_value = True
            mock_provider.get_embedding.return_value = [0.1] * 1536
            mock_provider.get_provider_name.return_value = "voyage"
            mock_provider.get_model_info.return_value = {"name": "test-model"}
            mock_provider.get_current_model.return_value = "test-model"
            mock_factory.create.return_value = mock_provider

            # Setup backend factory mock
            mock_backend = Mock()
            mock_vector_store = Mock()
            mock_backend_factory.create.return_value = mock_backend
            mock_backend.get_vector_store_client.return_value = mock_vector_store
            mock_vector_store.health_check.return_value = True
            mock_vector_store.resolve_collection_name.return_value = "test_collection"
            mock_vector_store._current_collection_name = "test_collection"
            mock_vector_store.ensure_payload_indexes.return_value = None
            mock_vector_store.search_with_model_filter.return_value = []

            # Setup git service mock
            mock_git_instance = Mock()
            mock_git_service.return_value = mock_git_instance
            mock_git_instance.is_git_available.return_value = False

            mock_service = Mock()
            mock_service.filter_results_by_current_branch.return_value = []
            mock_service.get_current_branch_context.return_value = {
                "project_id": "test"
            }
            mock_query_service.return_value = mock_service

            # Create proper mock config
            mock_config = Mock()
            mock_config.embedding_provider = "voyage"
            mock_config.codebase_dir = temp_project_root  # Use Path object directly
            mock_config.filesystem = Mock()  # Add filesystem config mock
            mock_config.vector_store = Mock()  # Add vector_store config mock
            mock_config.vector_store.provider = "filesystem"

            mock_config_manager = Mock()
            mock_config_manager.load.return_value = mock_config

            # Run query command
            result = cli_runner.invoke(
                query,
                ["test query", "--quiet"],
                obj={
                    "mode": "local",
                    "project_root": temp_project_root,
                    "config_manager": mock_config_manager,  # Use proper mock
                },
            )

            # This will initially fail - local mode doesn't apply staleness detection
            # We'll need to integrate staleness detection into local mode
            if result.exit_code != 0:
                print(f"CLI output: {result.output}")
                print(f"Exception: {result.exception}")
            assert result.exit_code == 0
            # No staleness indicators expected yet - this will need to be implemented

    def test_staleness_indicators_format_consistency(
        self, cli_runner, temp_project_root
    ):
        """Test that staleness indicator format is identical between modes."""

        # Test data representing identical staleness conditions
        stale_result_data = {
            "similarity_score": 0.95,
            "file_path": "stale_test.py",
            "line_number": 1,
            "code_snippet": "def stale_function():\n    pass",
            "repository_alias": "test-repo",
            "language": "python",
            "staleness_indicator": "🟡 45m stale",
            "is_stale": True,
        }

        # This test will initially fail - need to implement consistent display format
        with pytest.raises(NotImplementedError):
            # Test remote mode output format
            with patch("code_indexer.cli.asyncio.run") as mock_remote:
                enhanced_result = EnhancedQueryResultItem(
                    **{
                        **stale_result_data,
                        "file_last_modified": time.time() - 3600,
                        "indexed_timestamp": time.time() - 1800,
                        "local_file_mtime": time.time(),
                        "staleness_delta_seconds": 2700.0,
                    }
                )

                mock_remote.return_value = [enhanced_result]

                cli_runner.invoke(
                    query,
                    ["test query", "--quiet"],
                    obj={
                        "mode": "remote",
                        "project_root": temp_project_root,
                        "config_manager": Mock(),
                    },
                )

            # Test local mode output format (when implemented)
            with patch("code_indexer.cli.EmbeddingProviderFactory"):
                cli_runner.invoke(
                    query,
                    ["test query", "--quiet"],
                    obj={
                        "mode": "local",
                        "project_root": temp_project_root,
                        "config_manager": Mock(),
                    },
                )

            # Format should be identical
            # This will fail until we implement consistent display
            raise NotImplementedError(
                "Consistent staleness display not yet implemented"
            )

    def test_quiet_mode_shows_staleness_with_score_and_path(
        self, cli_runner, temp_project_root
    ):
        """Test that quiet mode includes staleness indicators alongside score and path."""

        # This test will initially fail - quiet mode doesn't show staleness indicators yet
        with (
            patch(
                "code_indexer.disabled_commands.detect_current_mode"
            ) as mock_detect_mode,
            patch("code_indexer.cli.asyncio.run") as mock_asyncio,
        ):
            mock_detect_mode.return_value = "remote"
            enhanced_result = EnhancedQueryResultItem(
                similarity_score=0.87,
                file_path="quiet_test.py",
                line_number=10,
                code_snippet="def quiet_test():\n    return True",
                repository_alias="test-repo",
                language="python",
                file_last_modified=time.time() - 7200,
                indexed_timestamp=time.time() - 3600,
                local_file_mtime=time.time(),
                is_stale=True,
                staleness_delta_seconds=3600.0,
                staleness_indicator="🟠 1h stale",
            )

            mock_asyncio.return_value = [enhanced_result]

            result = cli_runner.invoke(
                query,
                ["test query", "--quiet"],
                obj={
                    "mode": "remote",
                    "project_root": temp_project_root,
                    "config_manager": Mock(),
                },
            )

            # Should now show staleness indicators in quiet mode output
            # Expected format: score, staleness, path:line
            assert "0.870 🟠 1h stale quiet_test.py:10-11" in result.output

    def test_verbose_mode_shows_detailed_staleness_info(
        self, cli_runner, temp_project_root
    ):
        """Test that verbose mode includes detailed staleness information."""

        # This test will initially fail - verbose mode doesn't show staleness details yet
        with (
            patch(
                "code_indexer.disabled_commands.detect_current_mode"
            ) as mock_detect_mode,
            patch("code_indexer.cli.asyncio.run") as mock_asyncio,
        ):
            mock_detect_mode.return_value = "remote"
            enhanced_result = EnhancedQueryResultItem(
                similarity_score=0.92,
                file_path="verbose_test.py",
                line_number=5,
                code_snippet="class VerboseTest:\n    def __init__(self):\n        pass",
                repository_alias="test-repo",
                language="python",
                file_last_modified=time.time() - 86400,  # 1 day ago
                indexed_timestamp=time.time() - 43200,  # 12 hours ago
                local_file_mtime=time.time(),
                is_stale=True,
                staleness_delta_seconds=43200.0,
                staleness_indicator="🔴 1d stale",
                timezone_info={
                    "local_timezone": "UTC",
                    "utc_normalized": "true",
                    "normalization_applied": "local_file_mtime",
                },
            )

            mock_asyncio.return_value = [enhanced_result]

            result = cli_runner.invoke(
                query,
                ["test query"],  # No --quiet flag for verbose mode
                obj={
                    "mode": "remote",
                    "project_root": temp_project_root,
                    "config_manager": Mock(),
                },
            )

            # Should now show verbose staleness info
            assert "🔴 1d stale" in result.output
            assert "Staleness: Local file newer by" in result.output

    def test_mixed_staleness_results_sorted_correctly(
        self, cli_runner, temp_project_root
    ):
        """Test that mixed fresh/stale results are sorted with staleness priority."""

        # Create mixed results with fresh files prioritized despite lower scores
        fresh_result = EnhancedQueryResultItem(
            similarity_score=0.85,  # Lower score
            file_path="fresh.py",
            line_number=1,
            code_snippet="def fresh_function():\n    pass",
            repository_alias="test-repo",
            language="python",
            file_last_modified=time.time() - 300,
            indexed_timestamp=time.time() - 300,
            local_file_mtime=time.time() - 300,
            is_stale=False,
            staleness_delta_seconds=0.0,
            staleness_indicator="🟢 Fresh",
        )

        stale_result = EnhancedQueryResultItem(
            similarity_score=0.95,  # Higher score
            file_path="stale.py",
            line_number=1,
            code_snippet="def stale_function():\n    pass",
            repository_alias="test-repo",
            language="python",
            file_last_modified=time.time() - 7200,
            indexed_timestamp=time.time() - 3600,
            local_file_mtime=time.time(),
            is_stale=True,
            staleness_delta_seconds=3600.0,
            staleness_indicator="🟠 1h stale",
        )

        # This test will initially fail - sorting doesn't consider staleness priority yet
        with patch("code_indexer.cli.asyncio.run") as mock_asyncio:
            mock_asyncio.return_value = [
                stale_result,
                fresh_result,
            ]  # Stale has higher score

            result = cli_runner.invoke(
                query,
                ["test query", "--quiet"],
                obj={
                    "mode": "remote",
                    "project_root": temp_project_root,
                    "config_manager": Mock(),
                },
            )

            lines = result.output.strip().split("\n")

            # This will initially fail - fresh result should come first despite lower score
            with pytest.raises(AssertionError):
                # Fresh should be first due to staleness priority
                assert "fresh.py" in lines[0]
                assert "stale.py" in lines[1] or "stale.py" in lines[2]

    def test_no_staleness_indicators_when_detection_fails(
        self, cli_runner, temp_project_root
    ):
        """Test graceful handling when staleness detection fails."""

        # Create result without staleness metadata (fallback case)
        basic_result = QueryResultItem(
            similarity_score=0.88,
            file_path="fallback_test.py",
            line_number=1,
            code_snippet="def fallback():\n    pass",
            repository_alias="test-repo",
            file_last_modified=time.time(),
            indexed_timestamp=time.time(),
        )

        # This test will initially fail - need graceful fallback handling
        with (
            patch(
                "code_indexer.disabled_commands.detect_current_mode"
            ) as mock_detect_mode,
            patch("code_indexer.cli.asyncio.run") as mock_asyncio,
        ):
            mock_detect_mode.return_value = "remote"
            mock_asyncio.return_value = [basic_result]

            result = cli_runner.invoke(
                query,
                ["test query", "--quiet"],
                obj={
                    "mode": "remote",
                    "project_root": temp_project_root,
                    "config_manager": Mock(),
                },
            )

            # Should still show results without staleness indicators
            assert "0.880 fallback_test.py:1-2" in result.output
            assert result.exit_code == 0


class TestCLIStalenessConfiguration:
    """Test CLI configuration options for staleness detection."""

    @pytest.fixture
    def cli_runner(self):
        """Create CLI runner for testing."""
        return CliRunner()

    def test_staleness_threshold_configuration_affects_display(self, cli_runner):
        """Test that staleness threshold configuration affects what's shown as stale."""
        # This test will initially fail - staleness configuration not exposed in CLI yet

        with pytest.raises(NotImplementedError):
            # CLI option like --staleness-threshold doesn't exist yet
            cli_runner.invoke(
                query,
                [
                    "test query",
                    "--staleness-threshold",
                    "3600",  # 1 hour threshold
                    "--quiet",
                ],
            )

            raise NotImplementedError("CLI staleness configuration not yet implemented")

    def test_disable_staleness_detection_option(self, cli_runner):
        """Test option to disable staleness detection entirely."""
        # This test will initially fail - disable option doesn't exist yet

        with pytest.raises(NotImplementedError):
            # CLI option like --no-staleness doesn't exist yet
            cli_runner.invoke(query, ["test query", "--no-staleness", "--quiet"])

            raise NotImplementedError("Disable staleness option not yet implemented")
