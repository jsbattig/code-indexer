"""
TDD tests for MultiResultAggregator (AC6: Result Aggregation with Per-Repo Mode).

Tests written FIRST before implementation.

Verifies:
- Always uses per_repo aggregation mode (no configuration)
- Adds repository field to each result
- Enforces per-repo limit independently
- No cross-repository deduplication
"""

import pytest
from code_indexer.server.multi.multi_result_aggregator import MultiResultAggregator


class TestMultiResultAggregatorPerRepoMode:
    """Test per-repo aggregation mode (always enforced)."""

    def test_aggregates_per_repo(self):
        """Results are grouped by repository."""
        repo_results = {
            "repo1": [
                {"file": "auth.py", "score": 0.9},
                {"file": "user.py", "score": 0.85},
            ],
            "repo2": [
                {"file": "login.py", "score": 0.88},
            ],
        }

        aggregator = MultiResultAggregator(limit=10)
        results = aggregator.aggregate(repo_results)

        assert "repo1" in results
        assert "repo2" in results
        assert len(results["repo1"]) == 2
        assert len(results["repo2"]) == 1

    def test_adds_repository_field(self):
        """Each result includes repository field."""
        repo_results = {
            "repo1": [
                {"file": "auth.py", "score": 0.9},
            ],
        }

        aggregator = MultiResultAggregator(limit=10)
        results = aggregator.aggregate(repo_results)

        assert results["repo1"][0]["repository"] == "repo1"
        assert results["repo1"][0]["file"] == "auth.py"
        assert results["repo1"][0]["score"] == 0.9

    def test_enforces_per_repo_limit(self):
        """Per-repo limit is enforced independently."""
        repo_results = {
            "repo1": [
                {"file": f"file{i}.py", "score": 0.9 - i * 0.01} for i in range(20)
            ],
            "repo2": [
                {"file": f"file{i}.py", "score": 0.85 - i * 0.01} for i in range(15)
            ],
        }

        aggregator = MultiResultAggregator(limit=10)
        results = aggregator.aggregate(repo_results)

        # Each repo limited to 10 results independently
        assert len(results["repo1"]) == 10
        assert len(results["repo2"]) == 10

    def test_no_cross_repo_deduplication(self):
        """Duplicate files across repos are NOT deduplicated."""
        repo_results = {
            "repo1": [
                {"file": "auth.py", "score": 0.9},
            ],
            "repo2": [
                {"file": "auth.py", "score": 0.85},  # Same filename, different repo
            ],
        }

        aggregator = MultiResultAggregator(limit=10)
        results = aggregator.aggregate(repo_results)

        # Both results should be present
        assert len(results["repo1"]) == 1
        assert len(results["repo2"]) == 1
        assert results["repo1"][0]["file"] == "auth.py"
        assert results["repo2"][0]["file"] == "auth.py"


class TestMultiResultAggregatorEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_repo_results(self):
        """Empty results dictionary returns empty results."""
        aggregator = MultiResultAggregator(limit=10)
        results = aggregator.aggregate({})
        assert results == {}

    def test_repo_with_no_results(self):
        """Repository with empty results array."""
        repo_results = {
            "repo1": [],
            "repo2": [{"file": "test.py", "score": 0.9}],
        }

        aggregator = MultiResultAggregator(limit=10)
        results = aggregator.aggregate(repo_results)

        assert len(results["repo1"]) == 0
        assert len(results["repo2"]) == 1

    def test_limit_smaller_than_results(self):
        """Limit smaller than number of results per repo."""
        repo_results = {
            "repo1": [
                {"file": f"file{i}.py", "score": 0.9 - i * 0.1} for i in range(10)
            ],
        }

        aggregator = MultiResultAggregator(limit=3)
        results = aggregator.aggregate(repo_results)

        assert len(results["repo1"]) == 3
        # Should take top 3 results
        assert results["repo1"][0]["file"] == "file0.py"
        assert results["repo1"][2]["file"] == "file2.py"

    def test_preserves_result_order(self):
        """Results maintain their original order within repo."""
        repo_results = {
            "repo1": [
                {"file": "a.py", "score": 0.9},
                {"file": "b.py", "score": 0.8},
                {"file": "c.py", "score": 0.7},
            ],
        }

        aggregator = MultiResultAggregator(limit=10)
        results = aggregator.aggregate(repo_results)

        assert results["repo1"][0]["file"] == "a.py"
        assert results["repo1"][1]["file"] == "b.py"
        assert results["repo1"][2]["file"] == "c.py"


class TestMultiResultAggregatorRepositoryField:
    """Test repository field is correctly added to all results."""

    def test_repository_field_added_to_all_results(self):
        """Repository field is added to every result in every repo."""
        repo_results = {
            "repo1": [
                {"file": "a.py", "score": 0.9},
                {"file": "b.py", "score": 0.8},
            ],
            "repo2": [
                {"file": "c.py", "score": 0.85},
            ],
            "repo3": [
                {"file": "d.py", "score": 0.75},
            ],
        }

        aggregator = MultiResultAggregator(limit=10)
        results = aggregator.aggregate(repo_results)

        # Verify every result has repository field
        for repo_name, repo_results_list in results.items():
            for result in repo_results_list:
                assert "repository" in result
                assert result["repository"] == repo_name

    def test_repository_field_not_overwritten(self):
        """If result already has repository field, it should be overwritten with correct value."""
        repo_results = {
            "repo1": [
                {"file": "a.py", "score": 0.9, "repository": "wrong_repo"},
            ],
        }

        aggregator = MultiResultAggregator(limit=10)
        results = aggregator.aggregate(repo_results)

        # Should overwrite with correct repository
        assert results["repo1"][0]["repository"] == "repo1"


class TestMultiResultAggregatorScoreFiltering:
    """Test min_score filtering in result aggregation (AC2: Score Filtering Consistency)."""

    def test_min_score_filters_low_scores(self):
        """Results below min_score threshold are filtered out."""
        repo_results = {
            "repo1": [
                {"file": "high.py", "score": 0.9},
                {"file": "medium.py", "score": 0.75},
                {"file": "low.py", "score": 0.5},
            ],
        }

        aggregator = MultiResultAggregator(limit=10, min_score=0.7)
        results = aggregator.aggregate(repo_results)

        # Only high and medium results should remain
        assert len(results["repo1"]) == 2
        assert results["repo1"][0]["file"] == "high.py"
        assert results["repo1"][1]["file"] == "medium.py"

    def test_min_score_applied_before_limit(self):
        """Score filtering is applied before per-repo limit enforcement."""
        repo_results = {
            "repo1": [
                {"file": f"high{i}.py", "score": 0.9 - i * 0.01} for i in range(5)
            ]
            + [{"file": f"low{i}.py", "score": 0.5 - i * 0.01} for i in range(10)],
        }

        # Limit is 3, min_score is 0.7
        # Should filter to 5 high-score results, then apply limit of 3
        aggregator = MultiResultAggregator(limit=3, min_score=0.7)
        results = aggregator.aggregate(repo_results)

        assert len(results["repo1"]) == 3
        # All results should be above 0.7
        for result in results["repo1"]:
            assert result["score"] >= 0.7

    def test_min_score_none_returns_all(self):
        """When min_score is None, all results are returned."""
        repo_results = {
            "repo1": [
                {"file": "high.py", "score": 0.9},
                {"file": "low.py", "score": 0.1},
            ],
        }

        aggregator = MultiResultAggregator(limit=10, min_score=None)
        results = aggregator.aggregate(repo_results)

        # Both results should be present
        assert len(results["repo1"]) == 2
        assert results["repo1"][0]["score"] == 0.9
        assert results["repo1"][1]["score"] == 0.1

    def test_min_score_consistent_across_repos(self):
        """Score filtering is applied consistently to all repositories."""
        repo_results = {
            "repo1": [
                {"file": "high1.py", "score": 0.9},
                {"file": "low1.py", "score": 0.5},
            ],
            "repo2": [
                {"file": "high2.py", "score": 0.85},
                {"file": "low2.py", "score": 0.4},
            ],
            "repo3": [
                {"file": "high3.py", "score": 0.95},
                {"file": "low3.py", "score": 0.3},
            ],
        }

        aggregator = MultiResultAggregator(limit=10, min_score=0.7)
        results = aggregator.aggregate(repo_results)

        # Each repo should have only high-score result
        assert len(results["repo1"]) == 1
        assert results["repo1"][0]["score"] == 0.9

        assert len(results["repo2"]) == 1
        assert results["repo2"][0]["score"] == 0.85

        assert len(results["repo3"]) == 1
        assert results["repo3"][0]["score"] == 0.95

    def test_min_score_with_limit(self):
        """Score filtering combined with per-repo limit works correctly."""
        repo_results = {
            "repo1": [
                {"file": f"file{i}.py", "score": 0.95 - i * 0.05} for i in range(10)
            ],
        }

        # min_score=0.7 should filter to 6 results (0.95, 0.9, 0.85, 0.8, 0.75, 0.7)
        # limit=3 should then take top 3
        aggregator = MultiResultAggregator(limit=3, min_score=0.7)
        results = aggregator.aggregate(repo_results)

        assert len(results["repo1"]) == 3
        assert results["repo1"][0]["score"] == pytest.approx(0.95)
        assert results["repo1"][1]["score"] == pytest.approx(0.90)
        assert results["repo1"][2]["score"] == pytest.approx(0.85)

    def test_min_score_exact_threshold(self):
        """Results at exact min_score threshold are included (>= not >)."""
        repo_results = {
            "repo1": [
                {"file": "above.py", "score": 0.71},
                {"file": "exact.py", "score": 0.7},
                {"file": "below.py", "score": 0.69},
            ],
        }

        aggregator = MultiResultAggregator(limit=10, min_score=0.7)
        results = aggregator.aggregate(repo_results)

        # Both above and exact should be included
        assert len(results["repo1"]) == 2
        assert results["repo1"][0]["file"] == "above.py"
        assert results["repo1"][1]["file"] == "exact.py"
