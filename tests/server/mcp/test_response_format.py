"""Tests for response_format parameter in omni-search handlers."""

import pytest
from code_indexer.server.mcp.handlers import _format_omni_response


class TestFormatOmniResponse:
    """Test the response formatting helper function."""

    def test_flat_format_returns_array(self):
        """Test flat format returns results as array."""
        results = [
            {"file_path": "a.py", "source_repo": "repo1"},
            {"file_path": "b.py", "source_repo": "repo2"},
        ]

        response = _format_omni_response(
            all_results=results,
            response_format="flat",
            total_repos_searched=2,
            errors={},
        )

        assert response["success"] is True
        assert "results" in response
        assert isinstance(response["results"], list)
        assert len(response["results"]) == 2
        assert "results_by_repo" not in response

    def test_grouped_format_returns_dict(self):
        """Test grouped format returns results_by_repo object."""
        results = [
            {"file_path": "a.py", "source_repo": "repo1"},
            {"file_path": "b.py", "source_repo": "repo1"},
            {"file_path": "c.py", "source_repo": "repo2"},
        ]

        response = _format_omni_response(
            all_results=results,
            response_format="grouped",
            total_repos_searched=2,
            errors={},
        )

        assert response["success"] is True
        assert "results_by_repo" in response
        assert "results" not in response
        assert "repo1" in response["results_by_repo"]
        assert "repo2" in response["results_by_repo"]
        assert response["results_by_repo"]["repo1"]["count"] == 2
        assert response["results_by_repo"]["repo2"]["count"] == 1

    def test_grouped_includes_total_results(self):
        """Test grouped format includes total_results count."""
        results = [
            {"file_path": "a.py", "source_repo": "repo1"},
            {"file_path": "b.py", "source_repo": "repo2"},
        ]

        response = _format_omni_response(
            all_results=results,
            response_format="grouped",
            total_repos_searched=2,
            errors={},
        )

        assert response["total_results"] == 2

    def test_errors_included_in_both_formats(self):
        """Test errors dict is included regardless of format."""
        results = [{"file_path": "a.py", "source_repo": "repo1"}]
        errors = {"repo2": "Not found"}

        for fmt in ["flat", "grouped"]:
            response = _format_omni_response(
                all_results=results,
                response_format=fmt,
                total_repos_searched=1,
                errors=errors,
            )

            assert response["errors"] == {"repo2": "Not found"}

    def test_cursor_included_when_provided(self):
        """Test cursor is included when provided."""
        response = _format_omni_response(
            all_results=[],
            response_format="flat",
            total_repos_searched=0,
            errors={},
            cursor="abc123",
        )

        assert response["cursor"] == "abc123"

    def test_cursor_not_included_when_none(self):
        """Test cursor is not included when None."""
        response = _format_omni_response(
            all_results=[],
            response_format="flat",
            total_repos_searched=0,
            errors={},
            cursor=None,
        )

        assert "cursor" not in response

    def test_empty_results_flat(self):
        """Test empty results in flat format."""
        response = _format_omni_response(
            all_results=[],
            response_format="flat",
            total_repos_searched=2,
            errors={},
        )

        assert response["results"] == []
        assert response["total_results"] == 0

    def test_empty_results_grouped(self):
        """Test empty results in grouped format."""
        response = _format_omni_response(
            all_results=[],
            response_format="grouped",
            total_repos_searched=2,
            errors={},
        )

        assert response["results_by_repo"] == {}
        assert response["total_results"] == 0
