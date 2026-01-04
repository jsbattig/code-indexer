"""
Tests for golden repos temporal status display functionality.

These tests follow TDD methodology and MESSI Rule #1: No mocks.
All tests use real components via WebTestInfrastructure fixture.
"""

from typing import Dict, Any

from .conftest import WebTestInfrastructure


class TestGoldenReposTemporalStatusIntegration:
    """Tests for temporal status integration in golden repos listing."""

    def test_golden_repos_list_includes_temporal_status_for_global_repos(
        self,
        web_infrastructure: WebTestInfrastructure,
        admin_user: Dict[str, Any],
    ):
        """
        Golden repos with global aliases include temporal_status field.

        Given I have golden repositories
        When _get_golden_repos_list() is called
        Then globally activated repos include temporal_status field
        """
        from code_indexer.server.web.routes import _get_golden_repos_list

        # Execute - uses real golden repo manager and dashboard service
        repos = _get_golden_repos_list()

        # Verify function returns a list
        assert isinstance(repos, list), "Should return a list"

        # Check temporal status for globally activated repos
        for repo in repos:
            if repo.get("global_alias"):
                # Global repos MUST have temporal_status
                assert "temporal_status" in repo, (
                    f"Globally activated repo {repo.get('alias', 'unknown')} "
                    "should have temporal_status field"
                )

                temporal_status = repo["temporal_status"]
                assert isinstance(
                    temporal_status, dict
                ), f"temporal_status should be a dict for repo {repo.get('alias', 'unknown')}"

                # Verify required temporal status fields
                assert (
                    "format" in temporal_status
                ), f"temporal_status should have 'format' field for repo {repo.get('alias', 'unknown')}"

                # Verify format value is valid
                assert temporal_status["format"] in ["v2", "v1", "none", "error"], (
                    f"format should be v2, v1, none, or error for repo {repo.get('alias', 'unknown')}, "
                    f"got: {temporal_status['format']}"
                )

    def test_golden_repos_list_handles_temporal_errors_gracefully(
        self,
        web_infrastructure: WebTestInfrastructure,
        admin_user: Dict[str, Any],
    ):
        """
        Golden repos display even if temporal status fetch fails.

        Given I have golden repositories
        When temporal status fetch fails for a repository
        Then repo still appears with error/fallback temporal_status
        """
        from code_indexer.server.web.routes import _get_golden_repos_list

        # Execute - should not raise exceptions even if temporal fetch fails
        repos = _get_golden_repos_list()

        # All repos should exist regardless of temporal status errors
        assert isinstance(repos, list), "Should return a list"

        # Global repos should have temporal_status even on errors
        for repo in repos:
            if repo.get("global_alias"):
                assert "temporal_status" in repo, (
                    f"Globally activated repo {repo.get('alias', 'unknown')} "
                    "should have temporal_status even if fetch failed"
                )

                temporal_status = repo["temporal_status"]

                # Should have format field (including "error" for failures)
                assert (
                    "format" in temporal_status
                ), f"temporal_status should have 'format' field for repo {repo.get('alias', 'unknown')}"

                # If format is "error", should have message
                if temporal_status["format"] == "error":
                    assert (
                        "message" in temporal_status
                    ), f"Error format should include message for repo {repo.get('alias', 'unknown')}"
                    assert isinstance(
                        temporal_status["message"], str
                    ), f"Error message should be string for repo {repo.get('alias', 'unknown')}"

    def test_golden_repos_without_global_alias_have_none_format(
        self,
        web_infrastructure: WebTestInfrastructure,
        admin_user: Dict[str, Any],
    ):
        """
        Golden repos without global alias have temporal_status with format='none'.

        Given I have golden repositories without global activation
        When _get_golden_repos_list() is called
        Then non-global repos have temporal_status with format='none'
        """
        from code_indexer.server.web.routes import _get_golden_repos_list

        repos = _get_golden_repos_list()

        # Find repos without global alias
        non_global_repos = [r for r in repos if not r.get("global_alias")]

        # Validate temporal status for non-global repos
        for repo in non_global_repos:
            assert (
                "temporal_status" in repo
            ), f"Non-global repo {repo.get('alias', 'unknown')} should have temporal_status"

            temporal_status = repo["temporal_status"]
            assert temporal_status["format"] == "none", (
                f"Non-global repo {repo.get('alias', 'unknown')} should have format='none', "
                f"got: {temporal_status['format']}"
            )

    def test_golden_repos_v2_format_structure(
        self,
        web_infrastructure: WebTestInfrastructure,
        admin_user: Dict[str, Any],
    ):
        """
        Golden repos with v2 temporal index have correct status structure.

        Given I have golden repositories with v2 temporal index
        When _get_golden_repos_list() is called
        Then v2 format repos include file_count and indexed_files
        """
        from code_indexer.server.web.routes import _get_golden_repos_list

        repos = _get_golden_repos_list()

        # Find repos with v2 format (if any exist)
        v2_repos = [
            r for r in repos if r.get("temporal_status", {}).get("format") == "v2"
        ]

        # Validate v2 format structure (only if v2 repos exist)
        for repo in v2_repos:
            temporal_status = repo["temporal_status"]

            assert (
                temporal_status["format"] == "v2"
            ), f"Format should be v2 for repo {repo.get('alias', 'unknown')}"

            # v2 format should include file counts
            assert (
                "file_count" in temporal_status
            ), f"v2 format should include file_count for repo {repo.get('alias', 'unknown')}"

            assert isinstance(
                temporal_status["file_count"], int
            ), f"file_count should be int for repo {repo.get('alias', 'unknown')}"

            assert (
                temporal_status["file_count"] >= 0
            ), f"file_count should be >= 0 for repo {repo.get('alias', 'unknown')}"
