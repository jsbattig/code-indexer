"""Unit tests for QueryResultAggregator.

Tests the aggregation, merging, sorting, and limiting of query results
from multiple repositories (Stories 3.2, 3.3, 3.4).
"""

from code_indexer.proxy.query_aggregator import QueryResultAggregator


class TestQueryResultAggregator:
    """Test QueryResultAggregator for multi-repo result processing."""

    def test_aggregate_single_repository(self):
        """Test aggregating results from a single repository."""
        repo_outputs = {
            "/home/user/repo1": """0.95 /home/user/repo1/src/auth.py:10-50
  10: def authenticate():
  11:     pass

0.85 /home/user/repo1/src/user.py:5-20
  5: class User:
  6:     pass"""
        }

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=10)

        # Should contain both results
        assert "0.95" in output
        assert "0.85" in output
        assert "auth.py" in output
        assert "user.py" in output

    def test_aggregate_multiple_repositories(self):
        """Test aggregating results from multiple repositories."""
        repo_outputs = {
            "/home/user/repo1": """0.95 /home/user/repo1/src/auth.py:10-50
  10: def authenticate():
  11:     pass""",
            "/home/user/repo2": """0.92 /home/user/repo2/api/login.py:20-60
  20: async def login():
  21:     return True""",
            "/home/user/repo3": """0.88 /home/user/repo3/tests/test_auth.py:5-15
  5: def test_auth():
  6:     assert True""",
        }

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=10)

        # All results should be present
        assert "0.95" in output
        assert "0.92" in output
        assert "0.88" in output

    def test_sort_by_score_descending(self):
        """Test that results are sorted by score (highest first)."""
        repo_outputs = {
            "/home/user/repo1": """0.75 /home/user/repo1/file1.py:1-10
  1: code1""",
            "/home/user/repo2": """0.95 /home/user/repo2/file2.py:1-10
  1: code2""",
            "/home/user/repo3": """0.85 /home/user/repo3/file3.py:1-10
  1: code3""",
        }

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=10)

        # Extract scores in order of appearance
        lines = output.strip().split("\n")
        score_lines = [l for l in lines if l.strip() and l[0].isdigit()]

        # Verify descending order: 0.95, 0.85, 0.75
        assert score_lines[0].startswith("0.95")
        assert score_lines[1].startswith("0.85")
        assert score_lines[2].startswith("0.75")

    def test_interleave_by_score_not_repository(self):
        """Test that results are interleaved by score, not grouped by repo."""
        repo_outputs = {
            "/repo1": """0.95 /repo1/a.py:1-5
  1: a

0.75 /repo1/b.py:1-5
  1: b""",
            "/repo2": """0.85 /repo2/c.py:1-5
  1: c""",
        }

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=10)

        lines = output.strip().split("\n")
        score_lines = [l for l in lines if l.strip() and l[0].isdigit()]

        # Verify interleaved order: 0.95(repo1), 0.85(repo2), 0.75(repo1)
        assert score_lines[0].startswith("0.95")
        assert "repo1" in score_lines[0]
        assert score_lines[1].startswith("0.85")
        assert "repo2" in score_lines[1]
        assert score_lines[2].startswith("0.75")
        assert "repo1" in score_lines[2]

    def test_apply_global_limit(self):
        """Test that --limit applies to total results, not per repository."""
        repo_outputs = {
            "/repo1": """0.95 /repo1/a.py:1-5
  1: a

0.90 /repo1/b.py:1-5
  1: b

0.85 /repo1/c.py:1-5
  1: c""",
            "/repo2": """0.92 /repo2/d.py:1-5
  1: d

0.88 /repo2/e.py:1-5
  1: e

0.82 /repo2/f.py:1-5
  1: f""",
        }

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=3)

        lines = output.strip().split("\n")
        score_lines = [l for l in lines if l.strip() and l[0].isdigit()]

        # Should have exactly 3 results total (not 3 per repo)
        assert len(score_lines) == 3

        # Should be top 3 by score: 0.95, 0.92, 0.9 (note: Python drops trailing zeros)
        assert score_lines[0].startswith("0.95")
        assert score_lines[1].startswith("0.92")
        assert score_lines[2].startswith("0.9")

    def test_limit_exceeds_available_results(self):
        """Test behavior when limit exceeds available results."""
        repo_outputs = {
            "/repo1": """0.9 /repo1/a.py:1-5
  1: a""",
            "/repo2": """0.8 /repo2/b.py:1-5
  1: b""",
        }

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=10)

        lines = output.strip().split("\n")
        score_lines = [l for l in lines if l.strip() and l[0].isdigit()]

        # Should return all available results (2)
        assert len(score_lines) == 2

    def test_no_limit_returns_all_results(self):
        """Test that limit=None or limit=0 returns all results."""
        repo_outputs = {
            "/repo1": """0.9 /repo1/a.py:1-5
  1: a

0.8 /repo1/b.py:1-5
  1: b""",
            "/repo2": """0.85 /repo2/c.py:1-5
  1: c""",
        }

        aggregator = QueryResultAggregator()

        # Test with None
        output_none = aggregator.aggregate_results(repo_outputs, limit=None)
        lines_none = [
            l for l in output_none.strip().split("\n") if l.strip() and l[0].isdigit()
        ]
        assert len(lines_none) == 3

        # Test with 0
        output_zero = aggregator.aggregate_results(repo_outputs, limit=0)
        lines_zero = [
            l for l in output_zero.strip().split("\n") if l.strip() and l[0].isdigit()
        ]
        assert len(lines_zero) == 3

    def test_preserve_repository_context(self):
        """Test that repository information is preserved in output."""
        repo_outputs = {
            "/home/dev/backend": """0.9 /home/dev/backend/src/auth.py:10-20
  10: code""",
            "/home/dev/frontend": """0.8 /home/dev/frontend/api/auth.js:5-15
  5: code""",
        }

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=10)

        # Repository paths should be visible in output
        assert "/home/dev/backend" in output
        assert "/home/dev/frontend" in output

    def test_handle_empty_repository_output(self):
        """Test handling repositories with no results."""
        repo_outputs = {
            "/repo1": """0.9 /repo1/a.py:1-5
  1: a""",
            "/repo2": "",  # Empty output
            "/repo3": """0.8 /repo3/c.py:1-5
  1: c""",
        }

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=10)

        # Should only include results from repo1 and repo3
        assert "0.9" in output
        assert "0.8" in output

        lines = output.strip().split("\n")
        score_lines = [l for l in lines if l.strip() and l[0].isdigit()]
        assert len(score_lines) == 2

    def test_handle_all_empty_outputs(self):
        """Test behavior when all repositories return empty results."""
        repo_outputs = {"/repo1": "", "/repo2": "", "/repo3": ""}

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=10)

        # Should return empty output (or minimal message)
        assert output.strip() == "" or "No results" in output

    def test_handle_error_output(self):
        """Test handling repositories with error messages."""
        repo_outputs = {
            "/repo1": """0.9 /repo1/a.py:1-5
  1: a""",
            "/repo2": "Error: Failed to connect to service",
            "/repo3": """0.8 /repo3/c.py:1-5
  1: c""",
        }

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=10)

        # Should skip error output, include valid results
        assert "0.9" in output
        assert "0.8" in output
        assert "Error" not in output

    def test_stable_sort_for_equal_scores(self):
        """Test that equal scores maintain stable ordering."""
        repo_outputs = {
            "/repo1": """0.9 /repo1/a.py:1-5
  1: a

0.9 /repo1/b.py:1-5
  1: b""",
            "/repo2": """0.9 /repo2/c.py:1-5
  1: c""",
        }

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=10)

        lines = output.strip().split("\n")
        score_lines = [l for l in lines if l.strip() and l[0].isdigit()]

        # All should have same score
        assert all(l.startswith("0.9") for l in score_lines)

        # Should maintain original parse order
        assert "repo1/a.py" in score_lines[0]
        assert "repo1/b.py" in score_lines[1]
        assert "repo2/c.py" in score_lines[2]

    def test_format_output_matches_single_repo_format(self):
        """Test that aggregated output format matches single-repo query format."""
        repo_outputs = {
            "/repo": """0.9 /repo/file.py:10-20
  10: def function():
  11:     return True"""
        }

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=10)

        # Should match real format: <score> <path>:<line_range>
        assert "0.9 /repo/file.py:10-20" in output
        assert "  10: def function():" in output
        assert "  11:     return True" in output

    def test_preserve_code_content(self):
        """Test that code content is preserved in aggregated output."""
        repo_outputs = {
            "/repo": """0.9 /repo/auth.py:1-5
  1: class Authentication:
  2:     def __init__(self):
  3:         self.users = {}
  4:     def login(self, user):
  5:         return user in self.users"""
        }

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=10)

        # All content lines should be present
        assert "class Authentication:" in output
        assert "def __init__(self):" in output
        assert "self.users = {}" in output
        assert "def login(self, user):" in output
        assert "return user in self.users" in output

    def test_aggregate_large_result_set(self):
        """Test aggregating large number of results efficiently."""
        # Generate 100 results across 5 repos
        repo_outputs = {}
        for repo_num in range(5):
            results = []
            for i in range(20):
                score = 0.95 - (repo_num * 0.01) - (i * 0.001)
                results.append(
                    f"{score:.3f} /repo{repo_num}/file{i}.py:1-10\n  1: code{i}"
                )

            repo_outputs[f"/repo{repo_num}"] = "\n\n".join(results)

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=50)

        lines = output.strip().split("\n")
        score_lines = [l for l in lines if l.strip() and l[0].isdigit()]

        # Should have exactly 50 results (global limit)
        assert len(score_lines) == 50

    def test_aggregate_with_unicode_content(self):
        """Test aggregating results with Unicode characters."""
        repo_outputs = {
            "/repo1": """0.9 /repo1/file.py:1-2
  1: # Comment with émojis 🎉
  2: def función():"""
        }

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=10)

        # Unicode should be preserved
        assert "🎉" in output
        assert "función" in output

    def test_aggregate_with_special_characters(self):
        """Test aggregating results with special characters in code."""
        repo_outputs = {
            "/repo": """0.9 /repo/test.py:1-3
  1: x = "string with 'quotes'"
  2: y = r"raw\\path"
  3: z = None"""
        }

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=10)

        # Special characters should be preserved
        assert "string with 'quotes'" in output
        assert "raw\\path" in output

    def test_aggregate_preserves_blank_lines_in_code(self):
        """Test that blank lines in code content are preserved."""
        repo_outputs = {
            "/repo": """0.9 /repo/file.py:1-5
  1: def function():
  2:     x = 1
  3:
  4:     return x"""
        }

        aggregator = QueryResultAggregator()
        output = aggregator.aggregate_results(repo_outputs, limit=10)

        # Blank line should be preserved in output
        lines = output.split("\n")
        assert "  3:" in output  # Line 3 exists (even if empty after colon)
