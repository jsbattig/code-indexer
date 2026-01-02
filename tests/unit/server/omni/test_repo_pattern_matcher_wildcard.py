"""
Unit tests for RepoPatternMatcher.filter_repos() wildcard matching.

Tests focus on validating that ** glob patterns work correctly with pathspec
(gitignore-style matching) instead of fnmatch.

The critical bug being fixed:
- fnmatch: 'org/**/prod' does NOT match 'org/prod' (requires at least one directory)
- pathspec: 'org/**/prod' DOES match 'org/prod' (zero or more directories)
"""

from code_indexer.server.omni.repo_pattern_matcher import RepoPatternMatcher


class TestRepoPatternMatcherWildcard:
    """Test suite for RepoPatternMatcher wildcard matching with pathspec."""

    def test_double_star_matches_zero_directories(self):
        """Test ** matches zero directories (pathspec behavior)."""
        repos = ["org/prod", "org/team/prod", "company/prod"]
        matcher = RepoPatternMatcher(["org/**/prod"])

        result = matcher.filter_repos(repos)

        assert "org/prod" in result, "** should match zero directories"
        assert "org/team/prod" in result, "** should match one directory"
        assert "company/prod" not in result, "Should not match different org"

    def test_double_star_at_start(self):
        """Test ** at the start of pattern matches any depth."""
        repos = ["prod", "team/prod", "org/team/prod"]
        matcher = RepoPatternMatcher(["**/prod"])

        result = matcher.filter_repos(repos)

        assert "prod" in result, "** should match zero directories"
        assert "team/prod" in result, "** should match one directory"
        assert "org/team/prod" in result, "** should match multiple directories"

    def test_double_star_at_end(self):
        """Test ** at the end of pattern matches any depth."""
        repos = ["org", "org/team", "org/dept/team"]
        matcher = RepoPatternMatcher(["org/**"])

        result = matcher.filter_repos(repos)

        # Note: gitignore-style matching - org/** matches subdirectories, not org itself
        assert "org/team" in result
        assert "org/dept/team" in result

    def test_star_matches_single_segment(self):
        """Test * matches within single path segment."""
        repos = ["test-repo1", "test-repo2", "prod-repo"]
        matcher = RepoPatternMatcher(["test-*"])

        result = matcher.filter_repos(repos)

        assert "test-repo1" in result
        assert "test-repo2" in result
        assert "prod-repo" not in result

    def test_question_mark_matches_single_char(self):
        """Test ? matches exactly one character."""
        repos = ["repo1", "repo2", "repo10"]
        matcher = RepoPatternMatcher(["repo?"])

        result = matcher.filter_repos(repos)

        assert "repo1" in result
        assert "repo2" in result
        assert "repo10" not in result

    def test_regex_pattern_with_anchors(self):
        """Test regex patterns (with ^ or $) use regex matching."""
        repos = ["test-repo", "my-test-repo", "test-repo-v2"]
        matcher = RepoPatternMatcher(["^test-.*"])

        result = matcher.filter_repos(repos)

        assert "test-repo" in result
        assert "test-repo-v2" in result
        assert "my-test-repo" not in result, "Regex ^ should anchor to start"

    def test_exact_match_no_metacharacters(self):
        """Test exact matching when no metacharacters present."""
        repos = ["exact-repo", "other-repo"]
        matcher = RepoPatternMatcher(["exact-repo"])

        result = matcher.filter_repos(repos)

        assert result == ["exact-repo"]

    def test_multiple_patterns(self):
        """Test multiple patterns combined."""
        repos = ["test-1", "test-2", "prod-1", "dev-1"]
        matcher = RepoPatternMatcher(["test-*", "prod-*"])

        result = matcher.filter_repos(repos)

        assert "test-1" in result
        assert "test-2" in result
        assert "prod-1" in result
        assert "dev-1" not in result

    def test_empty_patterns_returns_empty(self):
        """Test empty pattern list returns empty."""
        repos = ["repo1", "repo2"]
        matcher = RepoPatternMatcher([])

        result = matcher.filter_repos(repos)

        assert result == []

    def test_preserves_input_order(self):
        """Test result preserves input repo order."""
        repos = ["repo1", "repo2", "repo3", "repo4"]
        matcher = RepoPatternMatcher(["repo*"])

        result = matcher.filter_repos(repos)

        assert result == ["repo1", "repo2", "repo3", "repo4"]

    def test_deduplication(self):
        """Test overlapping patterns deduplicate results."""
        repos = ["test-repo", "test-other"]
        # Both patterns will match test-repo
        matcher = RepoPatternMatcher(["test-*", "test-repo"])

        result = matcher.filter_repos(repos)

        # test-repo should appear only once
        assert result.count("test-repo") == 1
        assert "test-other" in result

    def test_bracket_expressions(self):
        """Test [abc] bracket expressions."""
        repos = ["repo-a", "repo-b", "repo-c", "repo-d"]
        matcher = RepoPatternMatcher(["repo-[abc]"])

        result = matcher.filter_repos(repos)

        assert "repo-a" in result
        assert "repo-b" in result
        assert "repo-c" in result
        assert "repo-d" not in result

    def test_complex_nested_path_pattern(self):
        """Test complex nested path patterns."""
        repos = [
            "company/team1/service",
            "company/team2/service",
            "company/dept/team1/service",
        ]
        matcher = RepoPatternMatcher(["company/**/service"])

        result = matcher.filter_repos(repos)

        # All should match with ** matching zero or more directories
        assert "company/team1/service" in result
        assert "company/team2/service" in result
        assert "company/dept/team1/service" in result

    def test_invalid_regex_falls_back_gracefully(self):
        """Test invalid regex patterns fail gracefully."""
        repos = ["test-repo"]
        # Invalid regex with unmatched (
        matcher = RepoPatternMatcher(["^test-("])

        result = matcher.filter_repos(repos)

        # Should return empty instead of crashing
        assert result == []

    def test_custom_metacharacters(self):
        """Test custom metacharacters parameter."""
        repos = ["test*repo", "test-repo"]
        # Only treat - as pattern metacharacter (not *)
        matcher = RepoPatternMatcher(["test*repo"], metacharacters="-")

        result = matcher.filter_repos(repos)

        # * should be treated as literal, not wildcard
        assert "test*repo" in result
        assert "test-repo" not in result
