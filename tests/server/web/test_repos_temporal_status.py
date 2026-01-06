"""
Tests for temporal status display in web UI (Story #669 AC6).

These tests follow TDD methodology - tests are written FIRST before implementation.
All tests use real components following MESSI Rule #1: No mocks.
"""

from typing import Dict, Any

from .conftest import WebTestInfrastructure


# =============================================================================
# AC6: Temporal Status Display Tests - Backend Integration
# =============================================================================


class TestTemporalStatusIntegration:
    """Tests for temporal status integration in web UI routes."""

    def test_get_all_activated_repos_includes_temporal_status(
        self,
        web_infrastructure: WebTestInfrastructure,
        admin_user: Dict[str, Any],
    ):
        """
        AC6: _get_all_activated_repos() fetches temporal status for each repository.

        Given I have activated repositories
        When _get_all_activated_repos() is called
        Then each repo dict includes temporal_status field with required keys
        """
        from code_indexer.server.web.routes import _get_all_activated_repos

        # Execute
        all_repos = _get_all_activated_repos()

        # Verify function returns a list
        assert isinstance(all_repos, list), "Should return a list"

        # If repos exist, verify temporal_status is present with required structure
        for repo in all_repos:
            assert (
                "temporal_status" in repo
            ), f"Repository {repo.get('user_alias', 'unknown')} should have temporal_status field"

            temporal_status = repo["temporal_status"]
            assert isinstance(
                temporal_status, dict
            ), f"temporal_status should be a dict for repo {repo.get('user_alias', 'unknown')}"

            # Verify required temporal status fields
            required_fields = ["format", "file_count", "needs_reindex", "message"]
            for field in required_fields:
                assert (
                    field in temporal_status
                ), f"temporal_status should have '{field}' field for repo {repo.get('user_alias', 'unknown')}"

            # Verify format value is valid
            assert temporal_status["format"] in ["v1", "v2", "none", "error"], (
                f"format should be v1, v2, none, or error for repo {repo.get('user_alias', 'unknown')}, "
                f"got: {temporal_status['format']}"
            )

            # Verify types
            assert isinstance(
                temporal_status["file_count"], int
            ), f"file_count should be int for repo {repo.get('user_alias', 'unknown')}"
            assert isinstance(
                temporal_status["needs_reindex"], bool
            ), f"needs_reindex should be bool for repo {repo.get('user_alias', 'unknown')}"
            assert isinstance(
                temporal_status["message"], str
            ), f"message should be str for repo {repo.get('user_alias', 'unknown')}"

    def test_temporal_status_v2_format_structure(
        self,
        web_infrastructure: WebTestInfrastructure,
        admin_user: Dict[str, Any],
    ):
        """
        AC6: Temporal status correctly identifies v2 format (active/working).

        Given I have repositories
        When temporal status indicates v2 format
        Then format='v2', needs_reindex=False, message indicates active
        """
        from code_indexer.server.web.routes import _get_all_activated_repos

        all_repos = _get_all_activated_repos()

        # Find repos with v2 format (if any exist)
        v2_repos = [
            r for r in all_repos if r.get("temporal_status", {}).get("format") == "v2"
        ]

        # Validate v2 format structure (only if v2 repos exist)
        for repo in v2_repos:
            temporal_status = repo["temporal_status"]

            assert (
                temporal_status["format"] == "v2"
            ), f"Format should be v2 for repo {repo.get('user_alias', 'unknown')}"

            assert (
                temporal_status["needs_reindex"] is False
            ), f"v2 format should not need reindex for repo {repo.get('user_alias', 'unknown')}"

            assert (
                temporal_status["file_count"] >= 0
            ), f"file_count should be >= 0 for repo {repo.get('user_alias', 'unknown')}"

            message_lower = temporal_status["message"].lower()
            assert "active" in message_lower or "v2" in message_lower, (
                f"v2 message should indicate active/v2 for repo {repo.get('user_alias', 'unknown')}, "
                f"got: {temporal_status['message']}"
            )

    def test_temporal_status_v1_format_structure(
        self,
        web_infrastructure: WebTestInfrastructure,
        admin_user: Dict[str, Any],
    ):
        """
        AC6: Temporal status correctly identifies v1 format (legacy, needs reindex).

        Given I have repositories
        When temporal status indicates v1 format
        Then format='v1', needs_reindex=True, message includes reindex instructions
        """
        from code_indexer.server.web.routes import _get_all_activated_repos

        all_repos = _get_all_activated_repos()

        # Find repos with v1 format (if any exist)
        v1_repos = [
            r for r in all_repos if r.get("temporal_status", {}).get("format") == "v1"
        ]

        # Validate v1 format structure (only if v1 repos exist)
        for repo in v1_repos:
            temporal_status = repo["temporal_status"]

            assert (
                temporal_status["format"] == "v1"
            ), f"Format should be v1 for repo {repo.get('user_alias', 'unknown')}"

            assert (
                temporal_status["needs_reindex"] is True
            ), f"v1 format should need reindex for repo {repo.get('user_alias', 'unknown')}"

            message_lower = temporal_status["message"].lower()
            assert "re-index" in message_lower or "reindex" in message_lower, (
                f"v1 message should include reindex instructions for repo {repo.get('user_alias', 'unknown')}, "
                f"got: {temporal_status['message']}"
            )

            assert "cidx index" in temporal_status["message"], (
                f"v1 message should include 'cidx index' command for repo {repo.get('user_alias', 'unknown')}, "
                f"got: {temporal_status['message']}"
            )

    def test_temporal_status_none_format_structure(
        self,
        web_infrastructure: WebTestInfrastructure,
        admin_user: Dict[str, Any],
    ):
        """
        AC6: Temporal status correctly identifies missing temporal index.

        Given I have repositories
        When temporal status indicates no temporal index
        Then format='none', file_count=0, message indicates not indexed
        """
        from code_indexer.server.web.routes import _get_all_activated_repos

        all_repos = _get_all_activated_repos()

        # Find repos with none format (if any exist)
        none_repos = [
            r for r in all_repos if r.get("temporal_status", {}).get("format") == "none"
        ]

        # Validate none format structure (only if none repos exist)
        for repo in none_repos:
            temporal_status = repo["temporal_status"]

            assert (
                temporal_status["format"] == "none"
            ), f"Format should be none for repo {repo.get('user_alias', 'unknown')}"

            assert temporal_status["file_count"] == 0, (
                f"none format should have file_count=0 for repo {repo.get('user_alias', 'unknown')}, "
                f"got: {temporal_status['file_count']}"
            )

            message_lower = temporal_status["message"].lower()
            assert "not indexed" in message_lower or "no temporal" in message_lower, (
                f"none message should indicate not indexed for repo {repo.get('user_alias', 'unknown')}, "
                f"got: {temporal_status['message']}"
            )

    def test_temporal_status_error_handling_graceful(
        self,
        web_infrastructure: WebTestInfrastructure,
        admin_user: Dict[str, Any],
    ):
        """
        AC6: Temporal status fetch errors don't break repo display.

        Given I have repositories
        When temporal status fetch fails for a repository
        Then repo still appears with error/fallback temporal_status
        """
        from code_indexer.server.web.routes import _get_all_activated_repos

        # Execute - should not raise exceptions
        all_repos = _get_all_activated_repos()

        # All repos should have temporal_status field, even if fetch failed
        for repo in all_repos:
            assert "temporal_status" in repo, (
                f"Repository {repo.get('user_alias', 'unknown')} should have temporal_status "
                "even if fetch failed"
            )

            temporal_status = repo["temporal_status"]

            # Should either have valid format OR error indicator
            has_format = "format" in temporal_status
            has_error = "error" in temporal_status

            assert has_format or has_error, (
                f"temporal_status should have 'format' or 'error' field for repo "
                f"{repo.get('user_alias', 'unknown')}, got: {list(temporal_status.keys())}"
            )

            # If error occurred, verify it's handled gracefully
            if has_error:
                assert isinstance(
                    temporal_status["error"], str
                ), f"Error field should be a string for repo {repo.get('user_alias', 'unknown')}"
                # Should still have basic fields to prevent template errors
                assert (
                    "message" in temporal_status
                ), "temporal_status with error should have fallback message"
