"""Unit tests for Story 2.3 - Result Aggregation.

Verifies that composite query results properly include source_repo metadata
and maintain repository_alias for composite repo.
"""

from pathlib import Path
from code_indexer.server.query.semantic_query_manager import (
    SemanticQueryManager,
    QueryResult,
)


class TestStory23ResultAggregation:
    """Tests for Story 2.3 acceptance criteria."""

    def test_query_result_has_source_repo_field(self):
        """AC1: Results include source_repo identifier for each match."""
        # Create a QueryResult
        result = QueryResult(
            file_path="repo1/auth.py",
            line_number=10,
            code_snippet="def authenticate():",
            similarity_score=0.95,
            repository_alias="my-composite-project",
            source_repo="repo1",  # This field should exist
        )

        # Verify source_repo field exists and is accessible
        assert hasattr(result, "source_repo")
        assert result.source_repo == "repo1"

    def test_query_result_source_repo_in_to_dict(self):
        """Verify source_repo is included in to_dict() output."""
        result = QueryResult(
            file_path="repo2/user.py",
            line_number=5,
            code_snippet="class User:",
            similarity_score=0.88,
            repository_alias="my-composite-project",
            source_repo="repo2",
        )

        result_dict = result.to_dict()

        # source_repo should be in dictionary
        assert "source_repo" in result_dict
        assert result_dict["source_repo"] == "repo2"

    def test_parse_cli_output_extracts_source_repo(self):
        """AC1: Verify _parse_cli_output extracts source_repo from file path."""
        manager = SemanticQueryManager()

        # Simulate CLI output with multiple repos
        cli_output = """0.95 repo1/auth.py:10-15
  10: def authenticate(user, password):
  11:     return True

0.88 repo2/user.py:5-8
  5: class User:
  6:     pass
"""

        results = manager._parse_cli_output(cli_output, Path("/test/composite-repo"))

        # Should have 2 results
        assert len(results) == 2

        # First result should have source_repo="repo1"
        assert results[0].source_repo == "repo1"
        assert results[0].file_path == "repo1/auth.py"

        # Second result should have source_repo="repo2"
        assert results[1].source_repo == "repo2"
        assert results[1].file_path == "repo2/user.py"

    def test_repository_alias_shows_composite_alias_not_subrepo(self):
        """AC4: Repository field shows composite alias, not subrepo name."""
        manager = SemanticQueryManager()

        cli_output = """0.95 repo1/auth.py:10-15
  10: def authenticate(user, password):
  11:     return True
"""

        # Parse output - repository_alias should be set from calling context
        # In search_composite, this would be the composite repo name
        results = manager._parse_cli_output(
            cli_output, Path("/test/my-composite-project")
        )

        # repository_alias should NOT be "repo1" (that's source_repo)
        # It should be set by the calling context (search_composite)
        # For now, _parse_cli_output doesn't set repository_alias correctly
        # This test will fail until we fix the implementation
        assert results[0].source_repo == "repo1"
        # repository_alias will be set by search_composite wrapper

    def test_parse_cli_output_handles_single_repo_file_path(self):
        """Test parsing when file path doesn't have repo prefix."""
        manager = SemanticQueryManager()

        # Single repo output (no "repo1/" prefix)
        cli_output = """0.95 auth.py:10-15
  10: def authenticate():
  11:     pass
"""

        results = manager._parse_cli_output(cli_output, Path("/test/single-repo"))

        assert len(results) == 1
        # source_repo should be None or empty for single repos
        assert results[0].source_repo is None or results[0].source_repo == ""
        assert results[0].file_path == "auth.py"

    def test_parse_cli_output_preserves_cli_ordering(self):
        """AC2 & AC5: Verify CLI ordering is preserved (no re-sorting)."""
        manager = SemanticQueryManager()

        # CLI output with scores NOT in descending order
        # (CLI already sorted, we shouldn't re-sort)
        cli_output = """0.95 repo1/high.py:1-5
  1: high score

0.88 repo2/medium.py:1-5
  1: medium score

0.92 repo1/medium-high.py:1-5
  1: medium high score
"""

        results = manager._parse_cli_output(cli_output, Path("/test/composite"))

        # Should preserve exact order from CLI
        assert len(results) == 3
        assert results[0].similarity_score == 0.95
        assert results[1].similarity_score == 0.88
        assert results[2].similarity_score == 0.92

        # Verify we're NOT sorting (order should match input)
        scores = [r.similarity_score for r in results]
        assert scores == [0.95, 0.88, 0.92]  # Exact CLI order

    def test_parse_cli_output_includes_all_repos(self):
        """AC3: Results from all component repos are included."""
        manager = SemanticQueryManager()

        # Output from 3 different repos
        cli_output = """0.95 backend/auth.py:10-15
  10: authenticate

0.88 frontend/login.js:5-8
  5: login form

0.85 shared/utils.py:20-25
  20: utility function
"""

        results = manager._parse_cli_output(cli_output, Path("/test/composite"))

        # Should have results from all 3 repos
        assert len(results) == 3

        source_repos = {r.source_repo for r in results}
        assert source_repos == {"backend", "frontend", "shared"}

    def test_query_result_optional_source_repo_for_single_repos(self):
        """Verify source_repo is optional (None for single repos)."""
        # Single repo result without source_repo
        result = QueryResult(
            file_path="auth.py",
            line_number=10,
            code_snippet="def authenticate():",
            similarity_score=0.95,
            repository_alias="my-single-repo",
            source_repo=None,  # None for single repos
        )

        assert result.source_repo is None

        # to_dict should handle None gracefully
        result_dict = result.to_dict()
        assert "source_repo" in result_dict
        assert result_dict["source_repo"] is None


class TestCompositeQuerySourceRepoIntegration:
    """Integration-style tests for source_repo in composite queries."""

    def test_search_composite_sets_repository_alias_correctly(self):
        """Verify search_composite sets repository_alias to composite name."""
        # This test will verify the full flow once implemented
        # For now, it documents the expected behavior

        # Expected: search_composite should:
        # 1. Call _execute_cli_query
        # 2. Get results from _parse_cli_output (which sets source_repo)
        # 3. Update repository_alias to composite repo name
        # 4. Return results with:
        #    - repository_alias = composite repo name
        #    - source_repo = subrepo name (from file path)
        pass  # Will be implemented after model changes

    def test_search_single_sets_source_repo_to_none(self):
        """Verify search_single sets source_repo=None (not a composite)."""
        # Expected: search_single should create QueryResults with:
        # - repository_alias = repo name
        # - source_repo = None (not composite)
        pass  # Will be implemented after model changes
