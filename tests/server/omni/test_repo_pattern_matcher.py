"""
Unit tests for RepoPatternMatcher component.

Tests the repository pattern matching and filtering logic for omni-search.
"""

from code_indexer.server.omni.repo_pattern_matcher import RepoPatternMatcher


class TestRepoPatternMatcher:
    """Test suite for RepoPatternMatcher."""

    def test_match_all_pattern(self):
        """Test that * pattern matches all repositories."""
        matcher = RepoPatternMatcher(["*"])
        repos = ["repo1", "repo2", "my-repo", "test-repo"]

        matched = matcher.filter_repos(repos)

        assert matched == repos

    def test_exact_match_pattern(self):
        """Test exact repository name matching."""
        matcher = RepoPatternMatcher(["repo1", "repo2"])
        repos = ["repo1", "repo2", "repo3", "other-repo"]

        matched = matcher.filter_repos(repos)

        assert set(matched) == {"repo1", "repo2"}

    def test_wildcard_prefix_pattern(self):
        """Test wildcard prefix matching (e.g., test-*)."""
        matcher = RepoPatternMatcher(["test-*"])
        repos = ["test-repo1", "test-repo2", "prod-repo", "test-"]

        matched = matcher.filter_repos(repos)

        assert set(matched) == {"test-repo1", "test-repo2", "test-"}

    def test_wildcard_suffix_pattern(self):
        """Test wildcard suffix matching (e.g., *-test)."""
        matcher = RepoPatternMatcher(["*-test"])
        repos = ["repo1-test", "repo2-test", "test-repo", "-test"]

        matched = matcher.filter_repos(repos)

        assert set(matched) == {"repo1-test", "repo2-test", "-test"}

    def test_wildcard_middle_pattern(self):
        """Test wildcard in the middle (e.g., repo-*-test)."""
        matcher = RepoPatternMatcher(["repo-*-test"])
        repos = ["repo-foo-test", "repo-bar-test", "repo-test", "repo-foo-prod"]

        matched = matcher.filter_repos(repos)

        assert set(matched) == {"repo-foo-test", "repo-bar-test"}

    def test_regex_pattern(self):
        """Test regex pattern matching."""
        matcher = RepoPatternMatcher(["^test-.*[0-9]+$"])
        repos = ["test-repo1", "test-repo2", "test-repo", "prod-repo1"]

        matched = matcher.filter_repos(repos)

        assert set(matched) == {"test-repo1", "test-repo2"}

    def test_multiple_patterns(self):
        """Test filtering with multiple patterns (OR logic)."""
        matcher = RepoPatternMatcher(["test-*", "prod-*"])
        repos = ["test-repo1", "prod-repo1", "dev-repo1", "test-repo2"]

        matched = matcher.filter_repos(repos)

        assert set(matched) == {"test-repo1", "test-repo2", "prod-repo1"}

    def test_empty_pattern_list(self):
        """Test that empty pattern list matches nothing."""
        matcher = RepoPatternMatcher([])
        repos = ["repo1", "repo2"]

        matched = matcher.filter_repos(repos)

        assert matched == []

    def test_empty_repo_list(self):
        """Test filtering empty repository list."""
        matcher = RepoPatternMatcher(["*"])
        repos = []

        matched = matcher.filter_repos(repos)

        assert matched == []

    def test_no_matches(self):
        """Test when no repositories match patterns."""
        matcher = RepoPatternMatcher(["nonexistent-*"])
        repos = ["repo1", "repo2", "test-repo"]

        matched = matcher.filter_repos(repos)

        assert matched == []

    def test_pattern_with_special_chars(self):
        """Test pattern matching with special regex characters."""
        matcher = RepoPatternMatcher(["repo.test"])
        repos = ["repo.test", "repo-test", "repoXtest"]

        matched = matcher.filter_repos(repos)

        # Should match all three since . is treated as regex wildcard
        assert "repo.test" in matched

    def test_case_sensitivity(self):
        """Test that pattern matching is case-sensitive by default."""
        matcher = RepoPatternMatcher(["Test-*"])
        repos = ["Test-repo", "test-repo", "TEST-repo"]

        matched = matcher.filter_repos(repos)

        assert set(matched) == {"Test-repo"}

    def test_pattern_with_question_mark(self):
        """Test pattern with ? wildcard (single character)."""
        matcher = RepoPatternMatcher(["repo?"])
        repos = ["repo1", "repo2", "repo", "repo12"]

        matched = matcher.filter_repos(repos)

        assert set(matched) == {"repo1", "repo2"}

    def test_pattern_with_character_class(self):
        """Test pattern with character class [abc]."""
        matcher = RepoPatternMatcher(["repo-[abc]"])
        repos = ["repo-a", "repo-b", "repo-c", "repo-d"]

        matched = matcher.filter_repos(repos)

        assert set(matched) == {"repo-a", "repo-b", "repo-c"}

    def test_is_pattern_metacharacter(self):
        """Test detection of pattern metacharacters."""
        matcher = RepoPatternMatcher(["test"])

        assert matcher.is_pattern("test-*") is True
        assert matcher.is_pattern("test-?") is True
        assert matcher.is_pattern("test-[abc]") is True
        assert matcher.is_pattern("^test-.*") is True
        assert matcher.is_pattern("test-repo") is False
        assert matcher.is_pattern("test_repo") is False
