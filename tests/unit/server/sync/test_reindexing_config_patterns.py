"""
Unit tests for ReindexingConfig.is_config_file() wildcard matching.

Tests focus on validating that ** glob patterns work correctly with pathspec
(gitignore-style matching) instead of fnmatch.

The critical bug being fixed:
- fnmatch: '**/*.json' does NOT match 'config.json' (requires at least one directory)
- pathspec: '**/*.json' DOES match 'config.json' (zero or more directories)
"""

import pytest
from code_indexer.server.sync.reindexing_config import ReindexingConfig


class TestReindexingConfigPatterns:
    """Test suite for ReindexingConfig pattern matching with pathspec."""

    def test_double_star_matches_zero_directories(self):
        """Test ** matches zero directories (pathspec behavior)."""
        config = ReindexingConfig(
            config_file_patterns={"**/*.json", "exact.txt"}
        )

        # Should match files at root
        assert config.is_config_file("config.json"), "** should match zero directories"
        assert config.is_config_file("package.json"), "** should match zero directories"

        # Should also match nested files
        assert config.is_config_file("src/config.json"), "** should match one directory"
        assert config.is_config_file("deep/nested/config.json"), "** should match multiple directories"

    def test_double_star_prefix_pattern(self):
        """Test patterns like **/.gitignore match at any depth."""
        config = ReindexingConfig(
            config_file_patterns={"**/.gitignore"}
        )

        assert config.is_config_file(".gitignore"), "** should match zero directories"
        assert config.is_config_file("src/.gitignore"), "** should match one directory"
        assert config.is_config_file("a/b/c/.gitignore"), "** should match multiple directories"

    def test_star_matches_within_filename(self):
        """Test * matches within filename."""
        config = ReindexingConfig(
            config_file_patterns={"test_*.py"}
        )

        assert config.is_config_file("test_auth.py")
        assert config.is_config_file("test_database.py")
        assert not config.is_config_file("run_tests.py")

    def test_question_mark_matches_single_char(self):
        """Test ? matches exactly one character."""
        config = ReindexingConfig(
            config_file_patterns={"config?.json"}
        )

        assert config.is_config_file("config1.json")
        assert config.is_config_file("config2.json")
        assert not config.is_config_file("config10.json")

    def test_exact_match_no_wildcards(self):
        """Test exact matching when no wildcards present."""
        config = ReindexingConfig(
            config_file_patterns={"package.json", "tsconfig.json"}
        )

        assert config.is_config_file("package.json")
        assert config.is_config_file("tsconfig.json")
        assert not config.is_config_file("other.json")

    def test_multiple_patterns(self):
        """Test multiple patterns combined."""
        config = ReindexingConfig(
            config_file_patterns={"*.json", "*.yaml", "Dockerfile"}
        )

        assert config.is_config_file("config.json")
        assert config.is_config_file("settings.yaml")
        assert config.is_config_file("Dockerfile")
        assert not config.is_config_file("script.py")

    def test_bracket_expressions(self):
        """Test [abc] bracket expressions in patterns."""
        config = ReindexingConfig(
            config_file_patterns={"config[123].txt"}
        )

        assert config.is_config_file("config1.txt")
        assert config.is_config_file("config2.txt")
        assert config.is_config_file("config3.txt")
        assert not config.is_config_file("config4.txt")

    def test_default_config_file_patterns(self):
        """Test default config file patterns include common files."""
        config = ReindexingConfig()

        # Check default patterns work
        assert "package.json" in config.config_file_patterns
        assert ".gitignore" in config.config_file_patterns
        assert "pyproject.toml" in config.config_file_patterns

    def test_empty_patterns_set(self):
        """Test empty patterns set returns False for all files."""
        config = ReindexingConfig(config_file_patterns=set())

        assert not config.is_config_file("any_file.txt")
        assert not config.is_config_file("config.json")

    def test_pattern_only_matches_filename_not_path(self):
        """Test patterns match against filename only, not full path."""
        config = ReindexingConfig(
            config_file_patterns={"*.json"}
        )

        # Should match - filename is config.json
        assert config.is_config_file("/path/to/config.json")

        # Should match - filename is package.json
        assert config.is_config_file("deep/nested/dir/package.json")

        # Should NOT match - filename is config.txt
        assert not config.is_config_file("/path/to/config.txt")

    def test_complex_double_star_pattern(self):
        """Test complex ** patterns in config files."""
        config = ReindexingConfig(
            config_file_patterns={"**/*config*.json"}
        )

        # All should match
        assert config.is_config_file("app-config-prod.json")
        assert config.is_config_file("nested/my-config-dev.json")
        assert config.is_config_file("deep/path/database-config.json")

        # Should not match
        assert not config.is_config_file("settings.json")

    def test_special_config_files(self):
        """Test special config file names with dots."""
        config = ReindexingConfig(
            config_file_patterns={
                ".env",
                ".gitignore",
                ".dockerignore",
                "**/.env*"
            }
        )

        assert config.is_config_file(".env")
        assert config.is_config_file(".gitignore")
        assert config.is_config_file(".dockerignore")
        assert config.is_config_file(".env.production")
        assert config.is_config_file(".env.local")

    def test_pattern_case_sensitivity(self):
        """Test that patterns are case-sensitive."""
        config = ReindexingConfig(
            config_file_patterns={"Config.json"}
        )

        assert config.is_config_file("Config.json")
        # fnmatch/pathspec is case-sensitive on Linux
        assert not config.is_config_file("config.json")

    def test_is_config_file_extracts_filename(self):
        """Test is_config_file correctly extracts filename from full path."""
        config = ReindexingConfig(
            config_file_patterns={"package.json"}
        )

        # All should match because filename is package.json
        assert config.is_config_file("package.json")
        assert config.is_config_file("/root/package.json")
        assert config.is_config_file("src/package.json")
        assert config.is_config_file("/home/user/project/package.json")
