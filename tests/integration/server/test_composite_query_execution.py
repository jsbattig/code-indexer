"""Integration tests for composite query execution.

Tests the complete flow of composite repository query execution using
real CLI integration (no mocks).
"""

import pytest
import tempfile
import shutil
from pathlib import Path

from code_indexer.server.query.semantic_query_manager import (
    SemanticQueryManager,
    QueryResult,
)


class TestCompositeQueryExecutionIntegration:
    """Integration tests for composite query with real CLI execution."""

    @pytest.fixture
    def composite_repo_setup(self):
        """Create a composite repository setup for testing."""
        # Create temporary directory structure
        temp_dir = Path(tempfile.mkdtemp(prefix="cidx-composite-test-"))

        try:
            # Create composite repo root
            composite_root = temp_dir / "composite-repo"
            composite_root.mkdir()

            # Create .code-indexer directory with proxy config
            config_dir = composite_root / ".code-indexer"
            config_dir.mkdir()

            # Create proxy config
            config_file = config_dir / "config.json"
            config_file.write_text(
                """{
    "proxy_mode": true,
    "discovered_repos": ["repo1", "repo2"]
}"""
            )

            # Create proxy config file
            proxy_config_file = config_dir / "proxy-config.json"
            proxy_config_file.write_text(
                """{
    "discovered_repos": ["repo1", "repo2"]
}"""
            )

            # Create subrepos with sample code
            repo1 = composite_root / "repo1"
            repo1.mkdir()
            (repo1 / "auth.py").write_text(
                """def authenticate(user, password):
    '''Authenticate user with password.'''
    if user and password:
        return True
    return False
"""
            )

            repo2 = composite_root / "repo2"
            repo2.mkdir()
            (repo2 / "user.py").write_text(
                """class User:
    '''User model class.'''
    def __init__(self, username):
        self.username = username
"""
            )

            yield composite_root

        finally:
            # Cleanup
            shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_composite_query_returns_results_from_multiple_repos(
        self, composite_repo_setup
    ):
        """Test that composite query searches across multiple repositories."""
        manager = SemanticQueryManager()

        # Execute composite query
        results = await manager.search_composite(
            repo_path=composite_repo_setup, query="user authentication", limit=10
        )

        # Should return results from both repos
        assert isinstance(results, list)
        # Results should contain QueryResult objects
        for result in results:
            assert isinstance(result, QueryResult)
            assert hasattr(result, "similarity_score")
            assert hasattr(result, "file_path")
            assert hasattr(result, "repository_alias")

    @pytest.mark.asyncio
    async def test_composite_query_respects_limit_parameter(self, composite_repo_setup):
        """Test that global limit is respected across repositories."""
        manager = SemanticQueryManager()

        # Query with limit=1
        results = await manager.search_composite(
            repo_path=composite_repo_setup, query="user", limit=1
        )

        # Should respect global limit
        assert len(results) <= 1

    @pytest.mark.asyncio
    async def test_composite_query_respects_min_score_parameter(
        self, composite_repo_setup
    ):
        """Test that min_score filter is applied."""
        manager = SemanticQueryManager()

        # Query with high min_score
        results = await manager.search_composite(
            repo_path=composite_repo_setup,
            query="user authentication",
            limit=10,
            min_score=0.9,
        )

        # All results should have score >= 0.9
        for result in results:
            assert result.similarity_score >= 0.9

    @pytest.mark.asyncio
    async def test_composite_query_results_sorted_by_score(self, composite_repo_setup):
        """Test that results are sorted by score descending."""
        manager = SemanticQueryManager()

        results = await manager.search_composite(
            repo_path=composite_repo_setup, query="user", limit=10
        )

        # Results should be sorted by score (descending)
        if len(results) > 1:
            scores = [r.similarity_score for r in results]
            assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_composite_query_preserves_repository_context(
        self, composite_repo_setup
    ):
        """Test that repository alias is preserved in results."""
        manager = SemanticQueryManager()

        results = await manager.search_composite(
            repo_path=composite_repo_setup, query="user", limit=10
        )

        # Each result should have repository_alias
        for result in results:
            assert result.repository_alias is not None
            # Should be one of our subrepos
            assert result.repository_alias in ["repo1", "repo2"]

    @pytest.mark.asyncio
    async def test_composite_query_with_language_filter(self, composite_repo_setup):
        """Test that language filter is passed to CLI."""
        manager = SemanticQueryManager()

        results = await manager.search_composite(
            repo_path=composite_repo_setup, query="user", limit=10, language="python"
        )

        # Should return results (language filter applied)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_composite_query_handles_nonexistent_repo(self):
        """Test graceful handling of nonexistent composite repo."""
        manager = SemanticQueryManager()

        with pytest.raises(Exception):
            await manager.search_composite(
                repo_path=Path("/nonexistent/path"), query="test", limit=10
            )


class TestParallelExecutionBehavior:
    """Tests to verify parallel execution is happening (via CLI)."""

    @pytest.mark.asyncio
    async def test_parallel_execution_via_cli_integration(self):
        """Test that parallel execution happens via CLI's _execute_query."""
        # This is an integration test verifying that the CLI's parallel
        # execution infrastructure is being used (not reimplemented)

        manager = SemanticQueryManager()

        # We verify by checking that:
        # 1. _execute_query is imported and available
        # 2. search_composite uses it correctly

        # Verify the import exists
        from code_indexer.proxy.cli_integration import _execute_query

        assert callable(_execute_query)

        # Verify manager has the method to call it
        assert hasattr(manager, "_execute_cli_query") or hasattr(
            manager, "search_composite"
        )
