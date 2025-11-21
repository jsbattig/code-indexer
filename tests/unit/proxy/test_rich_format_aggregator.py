"""Unit tests for RichFormatAggregator.

This module tests the RichFormatAggregator which handles aggregation, merging,
sorting, and formatting of query results from multiple repositories in rich
format (non-quiet mode) with full metadata preservation.
"""

from code_indexer.proxy.rich_format_aggregator import RichFormatAggregator


class TestRichFormatAggregatorSorting:
    """Test suite for result sorting by score descending."""

    def test_aggregate_sorts_by_score_descending(self):
        """Verify results from multiple repos are sorted by score descending.

        Bug #5 fix requirement: Results must be sorted by score across ALL
        repositories, not per-repository.
        """
        aggregator = RichFormatAggregator()

        # Create mock outputs with different scores
        repo1_output = """📄 File: /repo1/auth.py:1-10 | 🏷️  Language: python | 📊 Score: 0.850
📏 Size: 1024 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: main | 📦 Commit: abc123 | 🏗️  Project: repo1

📖 Content (Lines 1-10):
──────────────────────────────────────────────────
  1: def authenticate_user():
──────────────────────────────────────────────────"""

        repo2_output = """📄 File: /repo2/user.py:5-15 | 🏷️  Language: python | 📊 Score: 0.950
📏 Size: 2048 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: main | 📦 Commit: def456 | 🏗️  Project: repo2

📖 Content (Lines 5-15):
──────────────────────────────────────────────────
  5: class User:
──────────────────────────────────────────────────"""

        repo3_output = """📄 File: /repo3/login.py:10-20 | 🏷️  Language: python | 📊 Score: 0.750
📏 Size: 512 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: main | 📦 Commit: ghi789 | 🏗️  Project: repo3

📖 Content (Lines 10-20):
──────────────────────────────────────────────────
  10: def login_user():
──────────────────────────────────────────────────"""

        repository_outputs = {
            "/repo1": repo1_output,
            "/repo2": repo2_output,
            "/repo3": repo3_output,
        }

        # Aggregate results
        result = aggregator.aggregate_results(repository_outputs, limit=None)

        # Verify results are sorted by score descending (0.950, 0.850, 0.750)
        assert "0.950" in result
        assert "0.850" in result
        assert "0.750" in result

        # Find positions of scores in output
        pos_950 = result.find("0.950")
        pos_850 = result.find("0.850")
        pos_750 = result.find("0.750")

        # Verify ordering: 0.950 < 0.850 < 0.750 (positions in string)
        assert pos_950 < pos_850, "Score 0.950 should appear before 0.850"
        assert pos_850 < pos_750, "Score 0.850 should appear before 0.750"

    def test_aggregate_sorts_equal_scores_consistently(self):
        """Verify results with equal scores maintain consistent ordering."""
        aggregator = RichFormatAggregator()

        repo1_output = """📄 File: /repo1/auth.py:1-10 | 🏷️  Language: python | 📊 Score: 0.800
📏 Size: 1024 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: main | 📦 Commit: abc123 | 🏗️  Project: repo1

📖 Content (Lines 1-10):
──────────────────────────────────────────────────
  1: def authenticate_user():
──────────────────────────────────────────────────"""

        repo2_output = """📄 File: /repo2/user.py:5-15 | 🏷️  Language: python | 📊 Score: 0.800
📏 Size: 2048 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: main | 📦 Commit: def456 | 🏗️  Project: repo2

📖 Content (Lines 5-15):
──────────────────────────────────────────────────
  5: class User:
──────────────────────────────────────────────────"""

        repository_outputs = {"/repo1": repo1_output, "/repo2": repo2_output}

        # Should not raise exception and return both results
        result = aggregator.aggregate_results(repository_outputs, limit=None)

        assert "0.800" in result
        assert "/repo1/auth.py" in result
        assert "/repo2/user.py" in result


class TestRichFormatAggregatorLimits:
    """Test suite for global limit application."""

    def test_aggregate_applies_global_limit(self):
        """Verify limit applies to merged results from all repos, not per-repo.

        Bug #5 fix requirement: The limit must apply globally across all
        repositories, not per-repository.
        """
        aggregator = RichFormatAggregator()

        # Create 3 results from 2 repos, limit to 2 total
        repo1_output = """📄 File: /repo1/auth.py:1-10 | 🏷️  Language: python | 📊 Score: 0.900
📏 Size: 1024 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: main | 📦 Commit: abc123 | 🏗️  Project: repo1

📖 Content (Lines 1-10):
──────────────────────────────────────────────────
  1: def authenticate_user():
──────────────────────────────────────────────────

================================================================================

📄 File: /repo1/login.py:5-15 | 🏷️  Language: python | 📊 Score: 0.700
📏 Size: 512 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: main | 📦 Commit: abc123 | 🏗️  Project: repo1

📖 Content (Lines 5-15):
──────────────────────────────────────────────────
  5: def login():
──────────────────────────────────────────────────"""

        repo2_output = """📄 File: /repo2/user.py:10-20 | 🏷️  Language: python | 📊 Score: 0.800
📏 Size: 2048 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: main | 📦 Commit: def456 | 🏗️  Project: repo2

📖 Content (Lines 10-20):
──────────────────────────────────────────────────
  10: class User:
──────────────────────────────────────────────────"""

        repository_outputs = {"/repo1": repo1_output, "/repo2": repo2_output}

        # Apply global limit of 2
        result = aggregator.aggregate_results(repository_outputs, limit=2)

        # Should only contain top 2 results by score: 0.900 and 0.800
        assert "0.900" in result, "Top score 0.900 should be included"
        assert "0.800" in result, "Second score 0.800 should be included"
        assert "0.700" not in result, "Third score 0.700 should be excluded by limit"

        # Verify result count in header
        assert "Found 2 results:" in result

    def test_aggregate_with_limit_zero_returns_all(self):
        """Verify limit=0 returns all results (unlimited)."""
        aggregator = RichFormatAggregator()

        repo_output = """📄 File: /repo1/auth.py:1-10 | 🏷️  Language: python | 📊 Score: 0.900
📏 Size: 1024 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: main | 📦 Commit: abc123 | 🏗️  Project: repo1

📖 Content (Lines 1-10):
──────────────────────────────────────────────────
  1: def authenticate_user():
──────────────────────────────────────────────────

================================================================================

📄 File: /repo1/login.py:5-15 | 🏷️  Language: python | 📊 Score: 0.800
📏 Size: 512 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: main | 📦 Commit: abc123 | 🏗️  Project: repo1

📖 Content (Lines 5-15):
──────────────────────────────────────────────────
  5: def login():
──────────────────────────────────────────────────"""

        repository_outputs = {"/repo1": repo_output}

        # limit=0 should return all results
        result = aggregator.aggregate_results(repository_outputs, limit=0)

        assert "0.900" in result
        assert "0.800" in result
        assert "Found 2 results:" in result

    def test_aggregate_with_limit_none_returns_all(self):
        """Verify limit=None returns all results (unlimited)."""
        aggregator = RichFormatAggregator()

        repo_output = """📄 File: /repo1/auth.py:1-10 | 🏷️  Language: python | 📊 Score: 0.900
📏 Size: 1024 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: main | 📦 Commit: abc123 | 🏗️  Project: repo1

📖 Content (Lines 1-10):
──────────────────────────────────────────────────
  1: def authenticate_user():
──────────────────────────────────────────────────

================================================================================

📄 File: /repo1/login.py:5-15 | 🏷️  Language: python | 📊 Score: 0.800
📏 Size: 512 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: main | 📦 Commit: abc123 | 🏗️  Project: repo1

📖 Content (Lines 5-15):
──────────────────────────────────────────────────
  5: def login():
──────────────────────────────────────────────────"""

        repository_outputs = {"/repo1": repo_output}

        # limit=None should return all results
        result = aggregator.aggregate_results(repository_outputs, limit=None)

        assert "0.900" in result
        assert "0.800" in result
        assert "Found 2 results:" in result


class TestRichFormatAggregatorErrorHandling:
    """Test suite for error output filtering."""

    def test_aggregate_filters_error_outputs(self):
        """Verify error messages don't break aggregation."""
        aggregator = RichFormatAggregator()

        repo1_output = """📄 File: /repo1/auth.py:1-10 | 🏷️  Language: python | 📊 Score: 0.900
📏 Size: 1024 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: main | 📦 Commit: abc123 | 🏗️  Project: repo1

📖 Content (Lines 1-10):
──────────────────────────────────────────────────
  1: def authenticate_user():
──────────────────────────────────────────────────"""

        # repo2 has error output
        repo2_output = "Error: Cannot connect to Filesystem service"

        # repo3 has error output
        repo3_output = "Failed to execute query: Connection refused"

        repository_outputs = {
            "/repo1": repo1_output,
            "/repo2": repo2_output,
            "/repo3": repo3_output,
        }

        # Should only return results from repo1
        result = aggregator.aggregate_results(repository_outputs, limit=10)

        assert "0.900" in result
        assert "/repo1/auth.py" in result
        assert "Error:" not in result
        assert "Failed to" not in result
        assert "Found 1 results:" in result

    def test_aggregate_handles_empty_outputs(self):
        """Verify empty outputs are skipped gracefully."""
        aggregator = RichFormatAggregator()

        repo1_output = """📄 File: /repo1/auth.py:1-10 | 🏷️  Language: python | 📊 Score: 0.900
📏 Size: 1024 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: main | 📦 Commit: abc123 | 🏗️  Project: repo1

📖 Content (Lines 1-10):
──────────────────────────────────────────────────
  1: def authenticate_user():
──────────────────────────────────────────────────"""

        repository_outputs = {
            "/repo1": repo1_output,
            "/repo2": "",
            "/repo3": "   ",
            "/repo4": None,
        }

        # Should only return results from repo1
        result = aggregator.aggregate_results(repository_outputs, limit=10)

        assert "0.900" in result
        assert "/repo1/auth.py" in result
        assert "Found 1 results:" in result

    def test_aggregate_handles_malformed_outputs(self):
        """Verify malformed outputs are skipped with warning."""
        aggregator = RichFormatAggregator()

        repo1_output = """📄 File: /repo1/auth.py:1-10 | 🏷️  Language: python | 📊 Score: 0.900
📏 Size: 1024 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: main | 📦 Commit: abc123 | 🏗️  Project: repo1

📖 Content (Lines 1-10):
──────────────────────────────────────────────────
  1: def authenticate_user():
──────────────────────────────────────────────────"""

        # repo2 has malformed output (missing score)
        repo2_output = """📄 File: /repo2/user.py:5-15 | 🏷️  Language: python
Some random text without proper format"""

        repository_outputs = {"/repo1": repo1_output, "/repo2": repo2_output}

        # Should handle gracefully and return results from repo1
        result = aggregator.aggregate_results(repository_outputs, limit=10)

        assert "0.900" in result
        assert "/repo1/auth.py" in result


class TestRichFormatAggregatorFormatting:
    """Test suite for format reconstruction with metadata."""

    def test_format_preserves_all_metadata(self):
        """Verify all metadata fields are included in formatted output."""
        aggregator = RichFormatAggregator()

        repo_output = """📄 File: /repo1/auth.py:1-10 | 🏷️  Language: python | 📊 Score: 0.900
📏 Size: 1024 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: main | 📦 Commit: abc123 | 🏗️  Project: repo1

📖 Content (Lines 1-10):
──────────────────────────────────────────────────
  1: def authenticate_user():
──────────────────────────────────────────────────"""

        repository_outputs = {"/repo1": repo_output}

        result = aggregator.aggregate_results(repository_outputs, limit=10)

        # Verify all metadata is preserved
        assert "📄 File: /repo1/auth.py:1-10" in result
        assert "🏷️  Language: python" in result
        assert "📊 Score: 0.900" in result
        assert "📏 Size: 1024 bytes" in result
        assert "🕒 Indexed: 2025-10-09T10:00:00" in result
        assert "🌿 Branch: main" in result
        assert "📦 Commit: abc123" in result
        assert "🏗️  Project: repo1" in result
        assert "📖 Content (Lines 1-10):" in result
        assert "def authenticate_user():" in result

    def test_repository_context_preserved(self):
        """Verify repository identification is clear in output."""
        aggregator = RichFormatAggregator()

        repo1_output = """📄 File: /repo1/auth.py:1-10 | 🏷️  Language: python | 📊 Score: 0.900
📏 Size: 1024 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: main | 📦 Commit: abc123 | 🏗️  Project: repo1

📖 Content (Lines 1-10):
──────────────────────────────────────────────────
  1: def authenticate_user():
──────────────────────────────────────────────────"""

        repo2_output = """📄 File: /repo2/user.py:5-15 | 🏷️  Language: python | 📊 Score: 0.800
📏 Size: 2048 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: develop | 📦 Commit: def456 | 🏗️  Project: repo2

📖 Content (Lines 5-15):
──────────────────────────────────────────────────
  5: class User:
──────────────────────────────────────────────────"""

        repository_outputs = {"/repo1": repo1_output, "/repo2": repo2_output}

        result = aggregator.aggregate_results(repository_outputs, limit=10)

        # Verify repository context is preserved
        assert "🏗️  Project: repo1" in result
        assert "🏗️  Project: repo2" in result
        assert "/repo1/auth.py" in result
        assert "/repo2/user.py" in result

    def test_format_handles_missing_optional_fields(self):
        """Verify formatting handles missing optional metadata gracefully."""
        aggregator = RichFormatAggregator()

        # Output with minimal metadata (no size, timestamp, branch, etc.)
        repo_output = """📄 File: /repo1/auth.py:1-10 | 🏷️  Language: unknown | 📊 Score: 0.900
📏 Size: 0 bytes | 🕒 Indexed: unknown | 🌿 Branch: unknown | 📦 Commit: unknown | 🏗️  Project: unknown

📖 Content (Lines 1-10):
──────────────────────────────────────────────────
  1: def authenticate_user():
──────────────────────────────────────────────────"""

        repository_outputs = {"/repo1": repo_output}

        result = aggregator.aggregate_results(repository_outputs, limit=10)

        # Should handle gracefully with "unknown" placeholders
        assert "📊 Score: 0.900" in result
        assert "/repo1/auth.py" in result
        assert "unknown" in result.lower()

    def test_format_returns_empty_string_for_no_results(self):
        """Verify empty string returned when no valid results."""
        aggregator = RichFormatAggregator()

        # All repos have errors
        repository_outputs = {
            "/repo1": "Error: Cannot connect",
            "/repo2": "Failed to execute",
        }

        result = aggregator.aggregate_results(repository_outputs, limit=10)

        assert result == ""


class TestRichFormatAggregatorIntegration:
    """Integration tests for complete aggregation workflow."""

    def test_complete_aggregation_workflow(self):
        """Verify complete workflow: parse, merge, sort, limit, format."""
        aggregator = RichFormatAggregator()

        # Create 5 results from 3 repos with different scores
        repo1_output = """📄 File: /repo1/auth.py:1-10 | 🏷️  Language: python | 📊 Score: 0.950
📏 Size: 1024 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: main | 📦 Commit: abc123 | 🏗️  Project: repo1

📖 Content (Lines 1-10):
──────────────────────────────────────────────────
  1: def authenticate_user():
──────────────────────────────────────────────────

================================================================================

📄 File: /repo1/login.py:5-15 | 🏷️  Language: python | 📊 Score: 0.750
📏 Size: 512 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: main | 📦 Commit: abc123 | 🏗️  Project: repo1

📖 Content (Lines 5-15):
──────────────────────────────────────────────────
  5: def login():
──────────────────────────────────────────────────"""

        repo2_output = """📄 File: /repo2/user.py:10-20 | 🏷️  Language: python | 📊 Score: 0.900
📏 Size: 2048 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: develop | 📦 Commit: def456 | 🏗️  Project: repo2

📖 Content (Lines 10-20):
──────────────────────────────────────────────────
  10: class User:
──────────────────────────────────────────────────

================================================================================

📄 File: /repo2/session.py:15-25 | 🏷️  Language: python | 📊 Score: 0.650
📏 Size: 768 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: develop | 📦 Commit: def456 | 🏗️  Project: repo2

📖 Content (Lines 15-25):
──────────────────────────────────────────────────
  15: class Session:
──────────────────────────────────────────────────"""

        repo3_output = """📄 File: /repo3/token.py:20-30 | 🏷️  Language: python | 📊 Score: 0.800
📏 Size: 1536 bytes | 🕒 Indexed: 2025-10-09T10:00:00 | 🌿 Branch: feature | 📦 Commit: ghi789 | 🏗️  Project: repo3

📖 Content (Lines 20-30):
──────────────────────────────────────────────────
  20: def generate_token():
──────────────────────────────────────────────────"""

        repository_outputs = {
            "/repo1": repo1_output,
            "/repo2": repo2_output,
            "/repo3": repo3_output,
        }

        # Aggregate with limit of 3
        result = aggregator.aggregate_results(repository_outputs, limit=3)

        # Verify workflow steps:
        # 1. Parse: All 5 results extracted
        # 2. Merge: Combined into single list
        # 3. Sort: Ordered by score descending (0.950, 0.900, 0.800, 0.750, 0.650)
        # 4. Limit: Top 3 kept (0.950, 0.900, 0.800)
        # 5. Format: Rich format output with metadata

        # Verify limit applied
        assert "Found 3 results:" in result

        # Verify top 3 scores present
        assert "0.950" in result
        assert "0.900" in result
        assert "0.800" in result

        # Verify bottom 2 scores excluded
        assert "0.750" not in result
        assert "0.650" not in result

        # Verify sorting order
        pos_950 = result.find("0.950")
        pos_900 = result.find("0.900")
        pos_800 = result.find("0.800")
        assert pos_950 < pos_900 < pos_800

        # Verify metadata preserved
        assert "🏗️  Project: repo1" in result
        assert "🏗️  Project: repo2" in result
        assert "🏗️  Project: repo3" in result
