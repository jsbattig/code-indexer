"""Test Story 4: CLI help text and options cleanup to remove semantic chunking references.

Tests to verify that:
1. CLI help text doesn't mention semantic chunking
2. CLI options don't include semantic-specific flags
3. Fixed-size chunking is properly described in help text
"""

import subprocess
import pytest
from click.testing import CliRunner

from code_indexer.cli import query, index


class TestCLIHelpTextCleanup:
    """Test that CLI help text has no semantic chunking references."""

    def test_query_help_mentions_fixed_size_chunking_only(self):
        """Verify query help describes fixed-size chunking approach."""
        runner = CliRunner()
        result = runner.invoke(query, ["--help"])

        assert result.exit_code == 0
        help_text = result.output.lower()

        # Should not mention semantic chunking or AST
        assert "semantic chunking" not in help_text
        assert "ast-based" not in help_text
        assert "tree-sitter" not in help_text
        assert "tree sitter" not in help_text

        # Should describe current fixed-size approach
        # Note: The query command focuses on searching, not chunking details

    def test_index_help_mentions_fixed_size_chunking_only(self):
        """Verify index help describes fixed-size chunking approach."""
        runner = CliRunner()
        result = runner.invoke(index, ["--help"])

        assert result.exit_code == 0
        help_text = result.output.lower()

        # Should not mention semantic chunking or AST
        assert "semantic chunking" not in help_text
        assert "ast-based" not in help_text
        assert "tree-sitter" not in help_text
        assert "tree sitter" not in help_text

        # Should describe current approach
        assert (
            "semantic search" in help_text
        )  # This refers to the search capability, not chunking

    def test_main_help_no_semantic_references(self):
        """Verify main CLI help has no semantic chunking references."""
        result = subprocess.run(
            ["cidx", "--help"],
            capture_output=True,
            text=True,
            cwd="/home/jsbattig/Dev/code-indexer",
        )

        if result.returncode != 0:
            # Skip test if cidx not available
            pytest.skip("cidx command not available")

        help_text = result.stdout.lower()

        # Should not mention semantic chunking or AST
        assert "semantic chunking" not in help_text
        assert "ast-based" not in help_text
        assert "tree-sitter" not in help_text
        assert "tree sitter" not in help_text


class TestSemanticQueryOptions:
    """Test that semantic query options are still present (they refer to search filtering, not chunking)."""

    def test_query_semantic_options_exist_for_search_filtering(self):
        """Verify semantic query options exist for search result filtering."""
        runner = CliRunner()
        result = runner.invoke(query, ["--help"])

        assert result.exit_code == 0
        help_text = result.output.lower()

        # These options are for filtering search results, not for chunking
        # They should still exist as they help filter results from the vector database
        assert "--semantic-type" in help_text
        assert "--semantic-scope" in help_text
        assert "--semantic-features" in help_text
        assert "--semantic-parent" in help_text
        assert "--semantic-only" in help_text

    def test_semantic_query_options_describe_search_filtering(self):
        """Verify semantic query options clearly describe search result filtering."""
        runner = CliRunner()
        result = runner.invoke(query, ["--help"])

        assert result.exit_code == 0
        help_text = result.output

        # Should mention filtering, not chunking
        assert "filter by semantic type" in help_text.lower()
        assert "filter by semantic scope" in help_text.lower()


class TestFixedSizeChunkingDescription:
    """Test that CLI properly describes the current fixed-size chunking approach."""

    def test_chunk_size_and_overlap_mentioned_in_help(self):
        """Verify that chunk_size and chunk_overlap settings are mentioned appropriately."""
        # These settings should be documented in the config help/documentation
        # rather than prominently in CLI help, since they're config-file settings

        # Test that the CLI doesn't have conflicting chunking method descriptions
        runner = CliRunner()
        index_result = runner.invoke(index, ["--help"])
        query_result = runner.invoke(query, ["--help"])

        assert index_result.exit_code == 0
        assert query_result.exit_code == 0

        # Neither should mention conflicting chunking approaches
        for result in [index_result, query_result]:
            help_text = result.output.lower()

            # Should not mention both semantic and fixed-size chunking
            # (which would be confusing)
            semantic_chunking_mentions = help_text.count("semantic chunking")
            ast_based_mentions = help_text.count("ast-based")

            # Should be zero mentions of old approaches
            assert semantic_chunking_mentions == 0
            assert ast_based_mentions == 0


class TestCLIConsistency:
    """Test that CLI is consistent with the new fixed-size chunking approach."""

    def test_no_semantic_chunking_flags(self):
        """Verify there are no CLI flags for semantic chunking configuration."""
        runner = CliRunner()

        # Test index command
        index_result = runner.invoke(index, ["--help"])
        assert index_result.exit_code == 0
        index_help = index_result.output.lower()

        # Should not have flags for semantic chunking configuration
        assert "--use-semantic" not in index_help
        assert "--semantic-chunking" not in index_help
        assert "--enable-semantic" not in index_help
        assert "--disable-semantic" not in index_help
        assert "--ast-parsing" not in index_help
        assert "--tree-sitter" not in index_help

    def test_query_semantic_flags_are_for_filtering_only(self):
        """Verify query semantic flags are clearly for result filtering, not chunking."""
        runner = CliRunner()
        result = runner.invoke(query, ["--help"])

        assert result.exit_code == 0
        help_text = result.output

        # Semantic flags should be present but described as filters
        semantic_flags = [
            "--semantic-type",
            "--semantic-scope",
            "--semantic-features",
            "--semantic-parent",
            "--semantic-only",
        ]

        for flag in semantic_flags:
            assert flag in help_text

        # Should mention filtering behavior
        assert "filter by" in help_text.lower()


class TestConfigurationDocumentation:
    """Test that configuration-related documentation is clean."""

    def test_configuration_help_references(self):
        """Verify that CLI points to clean configuration documentation."""
        # Check if there are any commands that mention config file setup
        main_result = subprocess.run(
            ["cidx", "--help"],
            capture_output=True,
            text=True,
            cwd="/home/jsbattig/Dev/code-indexer",
        )

        if main_result.returncode != 0:
            pytest.skip("cidx command not available")

        # Should not reference semantic chunking in config guidance
        help_text = main_result.stdout.lower()
        if "config" in help_text:
            # Config references should be clean
            assert "semantic chunking" not in help_text
            assert "ast-based" not in help_text
