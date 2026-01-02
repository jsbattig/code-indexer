"""
Test-driven development for cross-platform path handling.

Tests that path exclusion patterns work correctly across different platforms:
- Windows paths (backslashes)
- Unix paths (forward slashes)
- Mixed separators
- Path normalization
- Case sensitivity considerations
"""

import pytest
import sys


class TestPathSeparatorHandling:
    """Test handling of different path separators across platforms."""

    def test_unix_paths_with_forward_slashes(self):
        """Test that Unix-style paths work correctly."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Unix paths: src/tests/test.py
        assert matcher.matches_pattern("src/tests/test.py", "**/tests/*")
        assert matcher.matches_pattern("lib/vendor/module.js", "**/vendor/**")

    def test_windows_paths_with_backslashes(self):
        """Test that Windows-style paths are normalized and work correctly."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Windows paths: src\tests\test.py (should be normalized to forward slashes)
        assert matcher.matches_pattern("src\\tests\\test.py", "**/tests/*")
        assert matcher.matches_pattern("lib\\vendor\\module.js", "**/vendor/**")

    def test_mixed_separator_paths_normalized(self):
        """Test that mixed separator paths are normalized correctly."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Mixed separators: src/tests\unit/test.py
        assert matcher.matches_pattern("src/tests\\unit/test.py", "**/tests/*")
        assert matcher.matches_pattern("src\\lib/vendor\\module.js", "**/vendor/**")

    def test_pattern_separator_normalization(self):
        """Test that pattern separators are also normalized."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Pattern with backslashes should work
        assert matcher.matches_pattern("src/tests/test.py", "*\\tests\\*")
        assert matcher.matches_pattern("lib/vendor/module.js", "**\\vendor\\**")

    def test_absolute_vs_relative_paths(self):
        """Test that both absolute and relative paths work correctly."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Relative paths
        assert matcher.matches_pattern("src/tests/test.py", "**/tests/*")

        # Absolute paths (Unix-style)
        assert matcher.matches_pattern("/home/user/project/tests/test.py", "**/tests/*")

        # Absolute paths (Windows-style)
        assert matcher.matches_pattern("C:\\project\\tests\\test.py", "**/tests/*")


class TestPathNormalization:
    """Test path normalization and canonicalization."""

    def test_trailing_slash_handling(self):
        """Test gitignore behavior for trailing slashes."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Pattern **/tests/* requires a file after tests/
        # Bare directory "src/tests/" should NOT match (correct gitignore behavior)
        assert not matcher.matches_pattern("src/tests/", "**/tests/*")
        assert not matcher.matches_pattern("src/tests", "**/tests/*")

        # But files inside tests/ should match
        assert matcher.matches_pattern("src/tests/file.py", "**/tests/*")

    def test_leading_slash_handling(self):
        """Test that leading slashes don't affect matching."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Paths with and without leading slashes should match the same
        assert matcher.matches_pattern("/src/tests/test.py", "**/tests/*")
        assert matcher.matches_pattern("src/tests/test.py", "**/tests/*")

    def test_double_slash_normalization(self):
        """Test that double slashes are normalized to single slashes."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Double slashes should be normalized
        assert matcher.matches_pattern("src//tests//test.py", "**/tests/*")
        assert matcher.matches_pattern("lib///vendor///module.js", "**/vendor/**")

    def test_dot_directory_handling(self):
        """Test that . and .. in paths are handled correctly."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Paths with . and .. should be normalized
        assert matcher.matches_pattern("src/./tests/test.py", "**/tests/*")
        assert matcher.matches_pattern("src/lib/../tests/test.py", "**/tests/*")


class TestCaseSensitivity:
    """Test case sensitivity handling across platforms."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Case-insensitive on Windows")
    def test_case_sensitive_on_unix(self):
        """Test that paths are case-sensitive on Unix systems."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # On Unix, case matters
        assert matcher.matches_pattern("src/Tests/test.py", "*/Tests/*")
        assert not matcher.matches_pattern("src/Tests/test.py", "**/tests/*")

    @pytest.mark.skipif(
        sys.platform != "win32", reason="Case-insensitive only on Windows"
    )
    def test_case_insensitive_on_windows(self):
        """Test that paths are case-insensitive on Windows."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # On Windows, case should not matter
        assert matcher.matches_pattern("src/Tests/test.py", "**/tests/*")
        assert matcher.matches_pattern("src/TESTS/test.py", "**/tests/*")
