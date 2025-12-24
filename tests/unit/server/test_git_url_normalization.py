"""
Unit tests for git URL normalization functionality.

Following TDD methodology - these tests define the expected behavior for git URL normalization
that will be used in the Repository Discovery endpoint.
"""

import pytest

from code_indexer.server.services.git_url_normalizer import (
    GitUrlNormalizer,
    GitUrlNormalizationError,
    NormalizedGitUrl,
)


class TestGitUrlNormalization:
    """Test git URL normalization for repository discovery."""

    def setup_method(self):
        """Set up test fixtures."""
        self.normalizer = GitUrlNormalizer()

    def test_normalize_https_github_url(self):
        """Test normalization of HTTPS GitHub URLs."""
        url = "https://github.com/user/repo.git"
        result = self.normalizer.normalize(url)

        assert isinstance(result, NormalizedGitUrl)
        assert result.canonical_form == "github.com/user/repo"
        assert result.domain == "github.com"
        assert result.user == "user"
        assert result.repo == "repo"
        assert result.original_url == url

    def test_normalize_ssh_github_url(self):
        """Test normalization of SSH GitHub URLs."""
        url = "git@github.com:user/repo.git"
        result = self.normalizer.normalize(url)

        assert result.canonical_form == "github.com/user/repo"
        assert result.domain == "github.com"
        assert result.user == "user"
        assert result.repo == "repo"
        assert result.original_url == url

    def test_normalize_https_without_git_suffix(self):
        """Test normalization of HTTPS URLs without .git suffix."""
        url = "https://github.com/user/repo"
        result = self.normalizer.normalize(url)

        assert result.canonical_form == "github.com/user/repo"
        assert result.domain == "github.com"
        assert result.user == "user"
        assert result.repo == "repo"

    def test_normalize_ssh_without_git_suffix(self):
        """Test normalization of SSH URLs without .git suffix."""
        url = "git@github.com:user/repo"
        result = self.normalizer.normalize(url)

        assert result.canonical_form == "github.com/user/repo"

    def test_normalize_gitlab_urls(self):
        """Test normalization of GitLab URLs."""
        test_cases = [
            "https://gitlab.com/user/project.git",
            "git@gitlab.com:user/project.git",
            "https://gitlab.example.com/user/project.git",
        ]

        for url in test_cases:
            result = self.normalizer.normalize(url)
            assert result.domain in ["gitlab.com", "gitlab.example.com"]
            assert result.user == "user"
            assert result.repo == "project"

    def test_normalize_bitbucket_urls(self):
        """Test normalization of Bitbucket URLs."""
        url = "https://bitbucket.org/user/repo.git"
        result = self.normalizer.normalize(url)

        assert result.canonical_form == "bitbucket.org/user/repo"
        assert result.domain == "bitbucket.org"

    def test_normalize_custom_git_server(self):
        """Test normalization of custom Git server URLs."""
        url = "https://git.company.com/team/project.git"
        result = self.normalizer.normalize(url)

        assert result.canonical_form == "git.company.com/team/project"
        assert result.domain == "git.company.com"
        assert result.user == "team"
        assert result.repo == "project"

    def test_normalize_equivalent_urls_same_canonical_form(self):
        """Test that equivalent URLs normalize to the same canonical form."""
        equivalent_urls = [
            "https://github.com/user/repo.git",
            "git@github.com:user/repo.git",
            "https://github.com/user/repo",
            "git@github.com:user/repo",
        ]

        canonical_forms = set()
        for url in equivalent_urls:
            result = self.normalizer.normalize(url)
            canonical_forms.add(result.canonical_form)

        assert len(canonical_forms) == 1
        assert "github.com/user/repo" in canonical_forms

    def test_normalize_invalid_url_raises_error(self):
        """Test that invalid URLs raise GitUrlNormalizationError."""
        invalid_urls = [
            "",
            "not-a-url",
            "http://example.com",  # Not a git URL
            "ftp://github.com/user/repo.git",  # Wrong protocol
            "https://github.com/",  # Missing user/repo
            "https://github.com/user",  # Missing repo
        ]

        for invalid_url in invalid_urls:
            with pytest.raises(GitUrlNormalizationError):
                self.normalizer.normalize(invalid_url)

    def test_normalize_url_with_port(self):
        """Test normalization of URLs with port numbers."""
        url = "https://git.company.com:8080/user/repo.git"
        result = self.normalizer.normalize(url)

        assert result.canonical_form == "git.company.com:8080/user/repo"
        assert result.domain == "git.company.com:8080"

    def test_normalize_ssh_with_user_prefix(self):
        """Test normalization of SSH URLs with custom user prefixes."""
        url = "ssh://git@git.company.com/user/repo.git"
        result = self.normalizer.normalize(url)

        assert result.canonical_form == "git.company.com/user/repo"
        assert result.domain == "git.company.com"

    def test_normalize_preserves_case_sensitivity(self):
        """Test that normalization preserves case in user/repo names."""
        url = "https://github.com/UserName/RepoName.git"
        result = self.normalizer.normalize(url)

        assert result.user == "UserName"
        assert result.repo == "RepoName"
        assert result.canonical_form == "github.com/UserName/RepoName"

    def test_find_matching_urls(self):
        """Test finding URLs that match a given canonical form."""
        base_url = "https://github.com/user/repo.git"
        result = self.normalizer.normalize(base_url)

        matching_urls = [
            "git@github.com:user/repo.git",
            "https://github.com/user/repo",
            "git@github.com:user/repo",
        ]

        for matching_url in matching_urls:
            match_result = self.normalizer.normalize(matching_url)
            assert match_result.canonical_form == result.canonical_form

    def test_normalize_url_with_subdirectories(self):
        """Test normalization of URLs with subdirectories/groups."""
        url = "https://gitlab.com/group/subgroup/project.git"
        result = self.normalizer.normalize(url)

        assert result.canonical_form == "gitlab.com/group/subgroup/project"
        assert result.domain == "gitlab.com"
        # For complex paths, user could be the full path minus repo
        assert result.repo == "project"


class TestNormalizedGitUrl:
    """Test the NormalizedGitUrl data model."""

    def test_normalized_git_url_creation(self):
        """Test creation of NormalizedGitUrl objects."""
        url = NormalizedGitUrl(
            original_url="https://github.com/user/repo.git",
            canonical_form="github.com/user/repo",
            domain="github.com",
            user="user",
            repo="repo",
        )

        assert url.original_url == "https://github.com/user/repo.git"
        assert url.canonical_form == "github.com/user/repo"
        assert url.domain == "github.com"
        assert url.user == "user"
        assert url.repo == "repo"

    def test_normalized_git_url_equality(self):
        """Test equality comparison of NormalizedGitUrl objects."""
        url1 = NormalizedGitUrl(
            original_url="https://github.com/user/repo.git",
            canonical_form="github.com/user/repo",
            domain="github.com",
            user="user",
            repo="repo",
        )

        url2 = NormalizedGitUrl(
            original_url="git@github.com:user/repo.git",
            canonical_form="github.com/user/repo",
            domain="github.com",
            user="user",
            repo="repo",
        )

        # Should be equal based on canonical form, not original URL
        assert url1.canonical_form == url2.canonical_form


class TestGitUrlNormalizationPerformance:
    """Test performance characteristics of git URL normalization."""

    def setup_method(self):
        """Set up test fixtures."""
        self.normalizer = GitUrlNormalizer()

    def test_normalize_large_batch_of_urls(self):
        """Test normalization performance with large batch of URLs."""
        import time

        urls = [f"https://github.com/user{i}/repo{i}.git" for i in range(1000)]

        start_time = time.time()
        results = [self.normalizer.normalize(url) for url in urls]
        end_time = time.time()

        # Should complete within reasonable time (less than 1 second)
        assert end_time - start_time < 1.0
        assert len(results) == 1000

        # Verify all results are valid
        for result in results:
            assert isinstance(result, NormalizedGitUrl)
            assert result.domain == "github.com"
