"""
Test-driven development for fixing CLI option name conflict.

BUG: The --exclude-path option fails due to Click option name conflict.
Both top-level cli group and query subcommand define --path, causing
Click to fail parsing --exclude-path with "Got unexpected extra argument".

FIX: Rename query subcommand's --path to --path-filter.
"""

import pytest
from click.testing import CliRunner
from unittest.mock import patch, Mock


class TestCLIOptionConflictFix:
    """Test that --exclude-path works without Click parsing errors."""

    def test_exclude_path_option_parses_correctly(self):
        """
        GIVEN a query command with --exclude-path option
        WHEN the command is invoked via CLI
        THEN Click should parse it without "Got unexpected extra argument" error

        This test demonstrates the bug: currently fails due to --path conflict.
        After renaming query's --path to --path-filter, this test should pass.
        """
        from code_indexer.cli import cli

        runner = CliRunner()

        # Mock all the backend dependencies to isolate CLI parsing
        with patch("code_indexer.cli.ConfigManager") as mock_config:
            with patch("code_indexer.cli.BackendFactory.create") as mock_backend:
                with patch(
                    "code_indexer.cli.EmbeddingProviderFactory.create"
                ) as mock_embed:
                    with patch(
                        "code_indexer.services.git_topology_service.GitTopologyService"
                    ) as mock_git:
                        with patch(
                            "code_indexer.services.generic_query_service.GenericQueryService"
                        ) as mock_query_svc:
                            # Setup mocks to avoid execution failures
                            mock_config_instance = Mock()
                            mock_config_instance.get_config.return_value = Mock(
                                mode="local", filesystem=Mock(), embedding=Mock()
                            )
                            mock_config.create_with_backtrack.return_value = (
                                mock_config_instance
                            )

                            mock_backend_instance = Mock()
                            mock_vector_store = Mock()
                            mock_vector_store.health_check.return_value = True
                            mock_vector_store.resolve_collection_name.return_value = (
                                "test_collection"
                            )
                            mock_vector_store.ensure_payload_indexes.return_value = None
                            mock_vector_store.search.return_value = []
                            mock_backend_instance.get_vector_store_client.return_value = (
                                mock_vector_store
                            )
                            mock_backend.return_value = mock_backend_instance

                            mock_embed_instance = Mock()
                            mock_embed_instance.health_check.return_value = True
                            mock_embed_instance.get_provider_name.return_value = (
                                "voyageai"
                            )
                            mock_embed_instance.get_model_info.return_value = {
                                "name": "test-model"
                            }
                            mock_embed_instance.get_embedding.return_value = [
                                0.1
                            ] * 1536
                            mock_embed.return_value = mock_embed_instance

                            mock_git_instance = Mock()
                            mock_git_instance.is_git_available.return_value = False
                            mock_git.return_value = mock_git_instance

                            mock_query_instance = Mock()
                            mock_query_instance.get_current_branch_context.return_value = (
                                None
                            )
                            mock_query_svc.return_value = mock_query_instance

                            # THIS IS THE CRITICAL TEST
                            # Test that --exclude-path parses without error
                            result = runner.invoke(
                                cli,
                                ["query", "test query", "--exclude-path", "*/tests/*"],
                            )

                            # CRITICAL ASSERTION: Should NOT have "unexpected extra argument" error
                            assert (
                                "Got unexpected extra argument" not in result.output
                            ), (
                                f"CLI parsing failed with option conflict error. "
                                f"Output: {result.output}"
                            )

                            # Should not have Click parsing errors (exit code 2 = usage error)
                            if result.exit_code == 2:
                                pytest.fail(
                                    f"CLI parsing failed (exit code 2). "
                                    f"This indicates a Click option conflict. "
                                    f"Output: {result.output}"
                                )

    def test_exclude_path_with_path_filter_both_work(self):
        """
        GIVEN a query command with both --exclude-path and --path-filter
        WHEN the command is invoked via CLI
        THEN both options should parse correctly without conflicts

        This test verifies that after renaming --path to --path-filter,
        both filtering options work together.
        """
        from code_indexer.cli import cli

        runner = CliRunner()

        # Mock dependencies
        with patch("code_indexer.cli.ConfigManager") as mock_config:
            with patch("code_indexer.cli.BackendFactory.create") as mock_backend:
                with patch(
                    "code_indexer.cli.EmbeddingProviderFactory.create"
                ) as mock_embed:
                    with patch(
                        "code_indexer.services.git_topology_service.GitTopologyService"
                    ) as mock_git:
                        with patch(
                            "code_indexer.services.generic_query_service.GenericQueryService"
                        ) as mock_query_svc:
                            # Setup mocks
                            mock_config_instance = Mock()
                            mock_config_instance.get_config.return_value = Mock(
                                mode="local", filesystem=Mock(), embedding=Mock()
                            )
                            mock_config.create_with_backtrack.return_value = (
                                mock_config_instance
                            )

                            mock_backend_instance = Mock()
                            mock_vector_store = Mock()
                            mock_vector_store.health_check.return_value = True
                            mock_vector_store.resolve_collection_name.return_value = (
                                "test_collection"
                            )
                            mock_vector_store.ensure_payload_indexes.return_value = None
                            mock_vector_store.search.return_value = []
                            mock_backend_instance.get_vector_store_client.return_value = (
                                mock_vector_store
                            )
                            mock_backend.return_value = mock_backend_instance

                            mock_embed_instance = Mock()
                            mock_embed_instance.health_check.return_value = True
                            mock_embed_instance.get_provider_name.return_value = (
                                "voyageai"
                            )
                            mock_embed_instance.get_model_info.return_value = {
                                "name": "test-model"
                            }
                            mock_embed_instance.get_embedding.return_value = [
                                0.1
                            ] * 1536
                            mock_embed.return_value = mock_embed_instance

                            mock_git_instance = Mock()
                            mock_git_instance.is_git_available.return_value = False
                            mock_git.return_value = mock_git_instance

                            mock_query_instance = Mock()
                            mock_query_instance.get_current_branch_context.return_value = (
                                None
                            )
                            mock_query_svc.return_value = mock_query_instance

                            # Test with both --path-filter and --exclude-path
                            result = runner.invoke(
                                cli,
                                [
                                    "query",
                                    "test query",
                                    "--path-filter",
                                    "src/**",
                                    "--exclude-path",
                                    "*/tests/*",
                                ],
                            )

                            # Should NOT have parsing errors
                            assert "Got unexpected extra argument" not in result.output
                            assert "Error: no such option" not in result.output.lower()

                            # Should not have Click usage errors
                            if result.exit_code == 2:
                                pytest.fail(
                                    f"CLI parsing failed with both options. "
                                    f"Output: {result.output}"
                                )

    def test_path_filter_option_exists_after_rename(self):
        """
        GIVEN the query command after fixing the option conflict
        WHEN we inspect the command's parameters
        THEN --path-filter option should exist (renamed from --path)

        This test verifies the actual parameter name change in the command definition.
        """
        from code_indexer.cli import query

        # Check that query command has path_filter parameter (not path)
        param_names = [p.name for p in query.params]

        # After fix, should have 'path_filter' parameter
        assert "path_filter" in param_names, (
            f"query command should have 'path_filter' parameter after rename. "
            f"Current parameters: {param_names}"
        )

        # Should also have exclude_paths parameter
        assert "exclude_paths" in param_names, (
            f"query command should have 'exclude_paths' parameter. "
            f"Current parameters: {param_names}"
        )
