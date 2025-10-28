"""
Test-driven development for path exclusion edge cases.

Tests edge cases and error conditions:
- Empty patterns
- Invalid patterns
- Special characters
- Unicode paths
- Very long paths
- Symbolic links
- Path traversal attempts
"""

import pytest


class TestEmptyAndInvalidPatterns:
    """Test handling of empty and invalid patterns."""

    def test_empty_pattern_string_matches_nothing(self):
        """Test that empty pattern string matches nothing."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        assert not matcher.matches_pattern("src/module.py", "")
        assert not matcher.matches_pattern("any/path/file.py", "")

    def test_whitespace_only_pattern_matches_nothing(self):
        """Test that whitespace-only pattern matches nothing."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        assert not matcher.matches_pattern("src/module.py", "   ")
        assert not matcher.matches_pattern("src/module.py", "\t\n")

    def test_none_pattern_raises_appropriate_error(self):
        """Test that None pattern raises appropriate error."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        with pytest.raises((TypeError, ValueError)):
            matcher.matches_pattern("src/module.py", None)

    def test_invalid_glob_pattern_handled_gracefully(self):
        """Test that invalid glob patterns are handled gracefully."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Malformed patterns should either raise ValueError or return False
        try:
            result = matcher.matches_pattern("src/module.py", "[invalid")
            # If no exception, should return False
            assert result is False
        except ValueError:
            # Exception is also acceptable
            pass


class TestSpecialCharactersInPaths:
    """Test handling of special characters in paths."""

    def test_unicode_characters_in_paths(self):
        """Test that Unicode characters in paths work correctly."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Unicode paths
        assert matcher.matches_pattern("src/测试/test.py", "*/测试/*")
        assert matcher.matches_pattern("src/файл.py", "*/файл.py")
        assert matcher.matches_pattern("src/emoji_😀.py", "*/emoji_*.py")

    def test_spaces_in_paths(self):
        """Test that spaces in paths work correctly."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Paths with spaces
        assert matcher.matches_pattern("src/my tests/test.py", "*/my tests/*")
        assert matcher.matches_pattern("src/test file.py", "*/test file.py")

    def test_special_regex_characters_escaped(self):
        """Test that special regex characters are properly escaped."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Characters that have special meaning in regex but not in glob
        assert matcher.matches_pattern("src/file.py", "*/file.py")  # dot
        assert matcher.matches_pattern("src/file(1).py", "*/file(1).py")  # parens
        assert matcher.matches_pattern("src/file+.py", "*/file+.py")  # plus
        assert matcher.matches_pattern("src/file$.py", "*/file$.py")  # dollar

    def test_backslash_in_filename(self):
        """Test that backslashes in filenames (Unix) work correctly."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # On Unix, backslash can be part of filename
        # Pattern should still normalize path separators but preserve filename backslashes
        assert matcher.matches_pattern("src/file\\name.py", "*/file\\name.py")


class TestPathLengthEdgeCases:
    """Test handling of very long and very short paths."""

    def test_very_long_path_handled_correctly(self):
        """Test that very long paths work correctly."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Very long path (>260 chars, Windows MAX_PATH limit)
        long_path = "src/" + "/".join([f"dir{i}" for i in range(50)]) + "/file.py"
        assert len(long_path) > 260

        # Should still match pattern
        assert matcher.matches_pattern(long_path, "**/file.py")
        assert matcher.matches_pattern(long_path, "src/**/file.py")

    def test_single_component_path(self):
        """Test that single component paths work correctly."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Single component path (just filename)
        assert matcher.matches_pattern("file.py", "file.py")
        assert matcher.matches_pattern("file.py", "*.py")
        assert not matcher.matches_pattern("file.py", "*/file.py")

    def test_root_path_handled_correctly(self):
        """Test that root paths are handled correctly."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Root paths
        assert matcher.matches_pattern("/", "*")
        assert matcher.matches_pattern("/file.py", "/*.py")


class TestSymbolicLinksAndAliases:
    """Test handling of symbolic links and path aliases."""

    def test_symlink_path_treated_as_regular_path(self):
        """Test that symlink paths are treated as regular paths for pattern matching."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Symlink paths should match patterns based on their path string
        # (not their target - that's the responsibility of the file system layer)
        assert matcher.matches_pattern("src/link_to_tests/test.py", "*/link_to_tests/*")
        assert not matcher.matches_pattern("src/link_to_tests/test.py", "*/tests/*")

    def test_dot_paths_normalized(self):
        """Test that paths with . and .. are normalized."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Paths with . and .. should be normalized before matching
        assert matcher.matches_pattern("src/./tests/test.py", "*/tests/*")
        assert matcher.matches_pattern("src/lib/../tests/test.py", "*/tests/*")


class TestPathTraversalSecurity:
    """Test that path patterns don't enable path traversal attacks."""

    def test_parent_directory_pattern_contained(self):
        """Test that .. in patterns is handled safely."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Patterns with .. should work but not enable traversal
        # The pattern itself is just matched literally
        assert matcher.matches_pattern("src/../tests/test.py", "*/../tests/*")

    def test_absolute_path_pattern_works(self):
        """Test that absolute path patterns work correctly."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Absolute patterns should match absolute paths
        assert matcher.matches_pattern(
            "/home/user/project/src/file.py", "/home/*/project/**"
        )
        assert not matcher.matches_pattern("relative/path/file.py", "/absolute/**")


class TestCombinedEdgeCases:
    """Test complex combinations of edge cases."""

    def test_empty_path_components(self):
        """Test paths with empty components (double slashes)."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Paths with double slashes should be normalized
        assert matcher.matches_pattern("src//tests//test.py", "*/tests/*")
        assert matcher.matches_pattern("src///tests/test.py", "*/tests/*")

    def test_pattern_with_trailing_slash(self):
        """Test patterns with trailing slashes."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Trailing slashes in patterns should be handled
        assert matcher.matches_pattern("src/tests/", "*/tests/")
        assert matcher.matches_pattern("src/tests/test.py", "*/tests/*")

    def test_case_sensitivity_edge_cases(self):
        """Test case sensitivity with special characters."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Mixed case with special patterns
        assert matcher.matches_pattern("src/Tests/TEST.py", "*/Tests/*")
        # Platform-dependent: may or may not match */tests/*
        # This is tested separately in cross-platform tests
