"""
Test for --dry-run-show-claude-prompt functionality.

This test verifies that the dry-run option shows the prompt without executing Claude.
"""

from click.testing import CliRunner
from unittest.mock import patch, MagicMock
import tempfile
from pathlib import Path

from src.code_indexer.cli import cli


@patch("src.code_indexer.cli.check_claude_sdk_availability")
def test_dry_run_show_claude_prompt_flag_exists(mock_claude_check):
    """Test that the dry-run flag is properly defined in CLI."""
    # Mock Claude SDK availability check to avoid dependency issues
    mock_claude_check.return_value = True

    runner = CliRunner()

    # Test that the flag exists by checking help text
    # Use catch_exceptions=False to see the actual error if there is one
    result = runner.invoke(cli, ["claude", "--help"], catch_exceptions=False)

    assert result.exit_code == 0, f"CLI help failed: {result.output}"
    assert "--dry-run-show-claude-prompt" in result.output
    assert "without executing analysis" in result.output


@patch("src.code_indexer.cli.check_claude_sdk_availability")
@patch("src.code_indexer.cli.GenericQueryService")
@patch("src.code_indexer.cli.ClaudeIntegrationService")
@patch("src.code_indexer.cli.QdrantClient")
@patch("src.code_indexer.cli.EmbeddingProviderFactory")
@patch("src.code_indexer.cli.ConfigManager")
def test_dry_run_shows_prompt_without_execution(
    mock_config_manager,
    mock_embedding_factory,
    mock_qdrant,
    mock_claude_service,
    mock_query_service,
    mock_claude_check,
):
    """Test that --dry-run-show-claude-prompt shows prompt without executing Claude."""

    # Mock Claude SDK availability check
    mock_claude_check.return_value = True

    # Setup config manager mock
    mock_config_manager_instance = MagicMock()
    mock_config_instance = MagicMock()
    mock_config_instance.codebase_dir = Path("/tmp/test")
    mock_config_instance.qdrant = MagicMock()
    mock_config_manager_instance.load.return_value = mock_config_instance
    mock_config_manager.return_value = mock_config_manager_instance

    mock_embedding_instance = MagicMock()
    mock_embedding_instance.health_check.return_value = True
    mock_embedding_instance.get_provider_name.return_value = "test"
    mock_embedding_factory.create.return_value = mock_embedding_instance

    mock_qdrant_instance = MagicMock()
    mock_qdrant_instance.health_check.return_value = True
    mock_qdrant_instance.resolve_collection_name.return_value = "test_collection"
    mock_qdrant.return_value = mock_qdrant_instance

    mock_claude_instance = MagicMock()
    # Mock the prompt creation method
    mock_claude_instance.create_claude_first_prompt.return_value = (
        "Test prompt for Claude"
    )
    mock_claude_service.return_value = mock_claude_instance

    # Mock GenericQueryService
    mock_query_instance = MagicMock()
    mock_query_instance.get_current_branch_context.return_value = {
        "git_available": True,
        "project_id": "test_project",
        "current_branch": "main",
        "current_commit": "abc123",
        "file_count": 5,
    }
    mock_query_service.return_value = mock_query_instance

    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        # Mock the codebase directory
        mock_config_instance.codebase_dir = Path(temp_dir)

        runner = CliRunner()

        # Test the dry-run flag
        result = runner.invoke(
            cli,
            ["claude", "Test question", "--dry-run-show-claude-prompt"],
            catch_exceptions=False,
        )

        # The command should succeed
        assert result.exit_code == 0, f"Dry-run command failed: {result.output}"

        # Should show the prompt in output
        assert "Test prompt for Claude" in result.output

        # Should NOT call run_claude_first_analysis (no actual execution)
        mock_claude_instance.run_claude_first_analysis.assert_not_called()

        # SHOULD call create_claude_first_prompt to generate the prompt
        mock_claude_instance.create_claude_first_prompt.assert_called_once()


@patch("src.code_indexer.cli.check_claude_sdk_availability")
@patch("src.code_indexer.cli.GenericQueryService")
@patch("src.code_indexer.cli.ClaudeIntegrationService")
@patch("src.code_indexer.cli.QdrantClient")
@patch("src.code_indexer.cli.EmbeddingProviderFactory")
@patch("src.code_indexer.cli.Config")
def test_dry_run_prevents_claude_execution(
    mock_config,
    mock_embedding_factory,
    mock_qdrant,
    mock_claude_service,
    mock_query_service,
    mock_claude_check,
):
    """Test that dry-run prevents any actual Claude API calls."""

    # Mock Claude CLI availability check to avoid dependency issues
    mock_claude_check.return_value = True

    # Setup mocks similar to above
    mock_config_instance = MagicMock()
    mock_config_instance.codebase_dir = Path("/tmp/test")
    mock_config_instance.qdrant = MagicMock()
    mock_config.return_value = mock_config_instance

    mock_embedding_instance = MagicMock()
    mock_embedding_instance.health_check.return_value = True
    mock_embedding_instance.get_provider_name.return_value = "test"
    mock_embedding_factory.create.return_value = mock_embedding_instance

    mock_qdrant_instance = MagicMock()
    mock_qdrant_instance.health_check.return_value = True
    mock_qdrant_instance.resolve_collection_name.return_value = "test_collection"
    mock_qdrant.return_value = mock_qdrant_instance

    mock_claude_instance = MagicMock()
    mock_claude_instance.create_claude_first_prompt.return_value = (
        "Generated prompt text"
    )
    mock_claude_service.return_value = mock_claude_instance

    # Mock GenericQueryService
    mock_query_instance = MagicMock()
    mock_query_instance.get_current_branch_context.return_value = {
        "git_available": True,
        "project_id": "test_project",
        "current_branch": "main",
        "current_commit": "abc123",
        "file_count": 5,
    }
    mock_query_service.return_value = mock_query_instance

    with tempfile.TemporaryDirectory() as temp_dir:
        mock_config_instance.codebase_dir = Path(temp_dir)

        runner = CliRunner()

        # Run with dry-run flag
        result = runner.invoke(
            cli,
            ["claude", "Test query", "--dry-run-show-claude-prompt"],
            catch_exceptions=False,
        )

        # The command should succeed
        assert result.exit_code == 0, f"Dry-run command failed: {result.output}"

        # Verify no execution methods are called
        mock_claude_instance.run_claude_first_analysis.assert_not_called()
        mock_claude_instance._run_claude_cli_analysis.assert_not_called()
        mock_claude_instance._run_claude_cli_streaming.assert_not_called()

        # But prompt generation should be called
        mock_claude_instance.create_claude_first_prompt.assert_called()


def test_dry_run_with_rag_first_approach():
    """Test that dry-run works with both claude-first and rag-first approaches."""

    # For now, focus on testing that the flag is properly recognized
    # We'll implement this after fixing the basic dry-run functionality
    pass


def test_normal_execution_without_dry_run():
    """Test that normal execution (without dry-run) still works as expected."""

    # This test ensures we don't break the normal flow when fixing dry-run
    # We'll implement this as a sanity check after the fix
    pass
