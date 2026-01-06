"""
TDD tests for MultiSearchConfig (AC8: Configuration Management).

Tests written FIRST before implementation.

Verifies:
- Sensible default values
- Environment variable overrides
- Configuration validation
"""

import pytest
import os
from code_indexer.server.multi.multi_search_config import MultiSearchConfig


class TestMultiSearchConfigDefaults:
    """Test default configuration values."""

    def test_max_workers_default(self):
        """max_workers defaults to 10."""
        config = MultiSearchConfig()
        assert config.max_workers == 10

    def test_query_timeout_default(self):
        """query_timeout_seconds defaults to 30."""
        config = MultiSearchConfig()
        assert config.query_timeout_seconds == 30

    def test_max_repos_per_query_default(self):
        """max_repos_per_query defaults to 50."""
        config = MultiSearchConfig()
        assert config.max_repos_per_query == 50

    def test_max_results_per_repo_default(self):
        """max_results_per_repo defaults to 100."""
        config = MultiSearchConfig()
        assert config.max_results_per_repo == 100


class TestMultiSearchConfigEnvironmentOverrides:
    """Test environment variable overrides."""

    def test_max_workers_env_override(self, monkeypatch):
        """CIDX_MULTI_MAX_WORKERS overrides max_workers default."""
        monkeypatch.setenv("CIDX_MULTI_MAX_WORKERS", "20")
        config = MultiSearchConfig.from_env()
        assert config.max_workers == 20

    def test_query_timeout_env_override(self, monkeypatch):
        """CIDX_MULTI_QUERY_TIMEOUT overrides query_timeout_seconds default."""
        monkeypatch.setenv("CIDX_MULTI_QUERY_TIMEOUT", "60")
        config = MultiSearchConfig.from_env()
        assert config.query_timeout_seconds == 60

    def test_max_repos_env_override(self, monkeypatch):
        """CIDX_MULTI_MAX_REPOS overrides max_repos_per_query default."""
        monkeypatch.setenv("CIDX_MULTI_MAX_REPOS", "100")
        config = MultiSearchConfig.from_env()
        assert config.max_repos_per_query == 100

    def test_max_results_per_repo_env_override(self, monkeypatch):
        """CIDX_MULTI_MAX_RESULTS_PER_REPO overrides max_results_per_repo default."""
        monkeypatch.setenv("CIDX_MULTI_MAX_RESULTS_PER_REPO", "200")
        config = MultiSearchConfig.from_env()
        assert config.max_results_per_repo == 200

    def test_partial_env_override(self, monkeypatch):
        """Only specified env vars are overridden, others use defaults."""
        monkeypatch.setenv("CIDX_MULTI_MAX_WORKERS", "15")
        config = MultiSearchConfig.from_env()
        assert config.max_workers == 15
        assert config.query_timeout_seconds == 30  # default
        assert config.max_repos_per_query == 50  # default
        assert config.max_results_per_repo == 100  # default


class TestMultiSearchConfigValidation:
    """Test configuration validation at startup."""

    def test_invalid_max_workers_raises_error(self):
        """max_workers <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="max_workers must be positive"):
            MultiSearchConfig(max_workers=0)

        with pytest.raises(ValueError, match="max_workers must be positive"):
            MultiSearchConfig(max_workers=-1)

    def test_invalid_query_timeout_raises_error(self):
        """query_timeout_seconds <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="query_timeout_seconds must be positive"):
            MultiSearchConfig(query_timeout_seconds=0)

        with pytest.raises(ValueError, match="query_timeout_seconds must be positive"):
            MultiSearchConfig(query_timeout_seconds=-10)

    def test_invalid_max_repos_raises_error(self):
        """max_repos_per_query <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="max_repos_per_query must be positive"):
            MultiSearchConfig(max_repos_per_query=0)

    def test_invalid_max_results_raises_error(self):
        """max_results_per_repo <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="max_results_per_repo must be positive"):
            MultiSearchConfig(max_results_per_repo=0)

    def test_valid_configuration_passes(self):
        """Valid configuration does not raise errors."""
        config = MultiSearchConfig(
            max_workers=5,
            query_timeout_seconds=20,
            max_repos_per_query=25,
            max_results_per_repo=50,
        )
        assert config.max_workers == 5
        assert config.query_timeout_seconds == 20
        assert config.max_repos_per_query == 25
        assert config.max_results_per_repo == 50
