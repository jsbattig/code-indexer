"""
Test for --rag-first claude_service variable bug.

This test reproduces the issue where claude_service is not defined in the --rag-first code path.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from src.code_indexer.cli import cli


def test_rag_first_approach_now_works():
    """Test that --rag-first approach now works after fixing the claude_service variable scope error."""

    runner = CliRunner()

    # Mock the config to use current project directory
    with patch("src.code_indexer.cli.Config") as mock_config:
        mock_config_instance = MagicMock()
        mock_config_instance.codebase_dir = Path(
            "/home/jsbattig/Dev/code-indexer"
        )  # Use current project
        mock_config_instance.qdrant = MagicMock()
        mock_config.return_value = mock_config_instance

        # Mock embedding provider factory
        with patch(
            "src.code_indexer.cli.EmbeddingProviderFactory"
        ) as mock_embedding_factory:
            mock_embedding_instance = MagicMock()
            mock_embedding_instance.health_check.return_value = True
            mock_embedding_instance.get_provider_name.return_value = "test_provider"
            mock_embedding_factory.create.return_value = mock_embedding_instance

            # Mock Qdrant client
            with patch("src.code_indexer.cli.QdrantClient") as mock_qdrant:
                mock_qdrant_instance = MagicMock()
                mock_qdrant_instance.health_check.return_value = True
                mock_qdrant_instance.resolve_collection_name.return_value = (
                    "test_collection"
                )
                mock_qdrant.return_value = mock_qdrant_instance

                # Mock GenericQueryService to avoid actual semantic search
                with patch(
                    "src.code_indexer.cli.GenericQueryService"
                ) as mock_query_service:
                    mock_query_instance = MagicMock()
                    mock_query_instance.search.return_value = []  # Empty search results
                    mock_query_service.return_value = mock_query_instance

                    # Run the command with --rag-first flag that causes the error
                    result = runner.invoke(
                        cli,
                        [
                            "claude",
                            "Test question",
                            "--rag-first",  # This should trigger the bug
                        ],
                    )

                    # This should fail with the claude_service error
                    print(f"Exit code: {result.exit_code}")
                    print(f"Output: {result.output}")
                    print(f"Exception: {result.exception}")

                    # After the fix, this should now work successfully
                    assert (
                        result.exit_code == 0
                    ), f"Command should now succeed after the fix, got exit code: {result.exit_code}, output: {result.output}"

                    # Check that it's using the RAG-first approach
                    assert (
                        "🔄 Using legacy RAG-first approach" in result.output
                    ), "Should show that it's using RAG-first approach"

                    # Check that it ran successfully and shows Claude results
                    assert (
                        "🤖 Claude Analysis Results" in result.output
                    ), "Should show Claude analysis results without error"

                    # Make sure there's no claude_service error
                    assert (
                        "claude_service" not in result.output
                        and "cannot access local variable" not in result.output
                    ), f"Should not contain claude_service error anymore, got: {result.output}"


def test_rag_first_vs_claude_first_comparison():
    """Test to compare the differences between --rag-first and default (claude-first) approaches."""

    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        (temp_path / "main.py").write_text("print('hello world')")

        # Test default approach (claude-first)
        with patch("src.code_indexer.cli.Config") as mock_config:
            mock_config_instance = MagicMock()
            mock_config_instance.codebase_dir = temp_path
            mock_config_instance.qdrant = MagicMock()
            mock_config.return_value = mock_config_instance

            with patch(
                "src.code_indexer.cli.EmbeddingProviderFactory"
            ) as mock_embedding_factory:
                mock_embedding_instance = MagicMock()
                mock_embedding_instance.health_check.return_value = True
                mock_embedding_instance.get_provider_name.return_value = "test_provider"
                mock_embedding_factory.create.return_value = mock_embedding_instance

                with patch("src.code_indexer.cli.QdrantClient") as mock_qdrant:
                    mock_qdrant_instance = MagicMock()
                    mock_qdrant_instance.health_check.return_value = True
                    mock_qdrant_instance.resolve_collection_name.return_value = (
                        "test_collection"
                    )
                    mock_qdrant.return_value = mock_qdrant_instance

                    # Test claude-first (default)
                    result_claude_first = runner.invoke(
                        cli, ["claude", "Test question"]
                    )

                    print(f"Claude-first exit code: {result_claude_first.exit_code}")
                    print(f"Claude-first output: {result_claude_first.output}")
                    if result_claude_first.exception:
                        print(
                            f"Claude-first exception: {result_claude_first.exception}"
                        )

                    # Now test rag-first
                    with patch(
                        "src.code_indexer.cli.GenericQueryService"
                    ) as mock_query_service:
                        mock_query_instance = MagicMock()
                        mock_query_instance.search.return_value = []
                        mock_query_service.return_value = mock_query_instance

                        result_rag_first = runner.invoke(
                            cli, ["claude", "Test question", "--rag-first"]
                        )

                        print(f"RAG-first exit code: {result_rag_first.exit_code}")
                        print(f"RAG-first output: {result_rag_first.output}")
                        if result_rag_first.exception:
                            print(f"RAG-first exception: {result_rag_first.exception}")

                        # Both approaches should now work after the fix
                        assert (
                            result_claude_first.exit_code == 0
                        ), "Claude-first should work"
                        assert (
                            result_rag_first.exit_code == 0
                        ), "RAG-first should now work after the fix"


def test_rag_first_with_dry_run():
    """Test that --rag-first works properly with --dry-run-show-claude-prompt functionality."""

    runner = CliRunner()

    # Mock the config to use current project directory
    with patch("src.code_indexer.cli.Config") as mock_config:
        mock_config_instance = MagicMock()
        mock_config_instance.codebase_dir = Path(
            "/home/jsbattig/Dev/code-indexer"
        )  # Use current project
        mock_config_instance.qdrant = MagicMock()
        mock_config.return_value = mock_config_instance

        # Mock embedding provider factory
        with patch(
            "src.code_indexer.cli.EmbeddingProviderFactory"
        ) as mock_embedding_factory:
            mock_embedding_instance = MagicMock()
            mock_embedding_instance.health_check.return_value = True
            mock_embedding_instance.get_provider_name.return_value = "test_provider"
            mock_embedding_instance.get_embedding.return_value = [
                0.1
            ] * 384  # Mock embedding vector
            mock_embedding_factory.create.return_value = mock_embedding_instance

            # Mock Qdrant client with search results
            with patch("src.code_indexer.cli.QdrantClient") as mock_qdrant:
                mock_qdrant_instance = MagicMock()
                mock_qdrant_instance.health_check.return_value = True
                mock_qdrant_instance.resolve_collection_name.return_value = (
                    "test_collection"
                )
                # Mock search results
                mock_qdrant_instance.search_with_model_filter.return_value = [
                    {
                        "id": "test_id",
                        "score": 0.9,
                        "payload": {
                            "file_path": "test.py",
                            "content": "def test(): pass",
                            "line_start": 1,
                            "line_end": 1,
                        },
                    }
                ]
                mock_qdrant.return_value = mock_qdrant_instance

                # Mock GenericQueryService for branch filtering
                with patch(
                    "src.code_indexer.cli.GenericQueryService"
                ) as mock_query_service:
                    mock_query_instance = MagicMock()
                    mock_query_instance.get_current_branch_context.return_value = {
                        "git_available": True,
                        "project_id": "test_project",
                        "current_branch": "main",
                        "current_commit": "abc123",
                        "file_count": 5,
                    }
                    # Mock filtered results to return the search results
                    mock_query_instance.filter_results_by_current_branch.return_value = [
                        {
                            "id": "test_id",
                            "score": 0.9,
                            "payload": {
                                "file_path": "test.py",
                                "content": "def test(): pass",
                                "line_start": 1,
                                "line_end": 1,
                            },
                        }
                    ]
                    mock_query_service.return_value = mock_query_instance

                    # Run the command with --rag-first and --dry-run-show-claude-prompt
                    result = runner.invoke(
                        cli,
                        [
                            "claude",
                            "Test question about code",
                            "--rag-first",  # Use legacy RAG-first approach
                            "--dry-run-show-claude-prompt",  # Show prompt without calling Claude
                        ],
                    )

                    print(f"Exit code: {result.exit_code}")
                    print(f"Output: {result.output}")
                    if result.exception:
                        print(f"Exception: {result.exception}")

                    # After the fix, this should now work successfully
                    assert (
                        result.exit_code == 0
                    ), f"RAG-first with dry-run should succeed after the fix, got exit code: {result.exit_code}, output: {result.output}"

                    # Check that it's using the RAG-first approach
                    assert (
                        "🔄 Using legacy RAG-first approach" in result.output
                    ), "Should show that it's using RAG-first approach"

                    # Check that it shows the dry-run behavior (prompt but no Claude call)
                    assert (
                        "📄 Generated Claude Prompt (RAG-first)" in result.output
                    ), "Should show RAG-first dry-run prompt output"

                    # Make sure there's no claude_service error
                    assert (
                        "claude_service" not in result.output
                        and "cannot access local variable" not in result.output
                    ), f"Should not contain claude_service error anymore, got: {result.output}"

                    # Verify that the search was performed (RAG-first should search before creating prompt)
                    mock_qdrant_instance.search_with_model_filter.assert_called_once()
                    mock_query_instance.filter_results_by_current_branch.assert_called_once()
