"""
Test-driven development for PathPatternMatcher ** pattern bug fix.

This test suite proves that PathPatternMatcher has the same fnmatch bug we fixed
in file_service.py - using fnmatch.fnmatch() treats ** as requiring at least one
subdirectory instead of gitignore-style "this directory and all subdirectories".

Bug Impact:
- FTS searches with path filters like "code/src/**/*.java" fail to match files
  directly in the target directory (e.g., code/src/Main.java)
- Only matches files in subdirectories (e.g., code/src/util/Helper.java)
- Real-world example: Claude.ai FTS searches returned incomplete results

Fix Strategy:
- Replace fnmatch with pathspec library (same as file_service.py)
- Use gitignore-style glob patterns via pathspec.PathSpec.from_lines("gitwildmatch", [pattern])
- Ensure backward compatibility for simple patterns like *.py
"""

import pytest
from code_indexer.services.path_pattern_matcher import PathPatternMatcher


class TestDoubleStarPatternBug:
    """Test cases that should pass after fixing ** pattern bug."""

    def test_doublestar_matches_target_directory_directly(self):
        """
        CRITICAL: ** should match "this directory and all subdirectories",
        not "at least one subdirectory".

        Pattern "code/src/**/*.java" should match:
        - code/src/Main.java (direct file in target directory)
        - code/src/util/Helper.java (file in subdirectory)

        This is the PRIMARY bug causing FTS search failures.
        """
        matcher = PathPatternMatcher()

        # These MUST match - files directly in target directory
        assert matcher.matches_pattern("code/src/Main.java", "code/src/**/*.java")
        assert matcher.matches_pattern("code/src/App.java", "code/src/**/*.java")

        # These should also match - files in subdirectories
        assert matcher.matches_pattern("code/src/util/Helper.java", "code/src/**/*.java")
        assert matcher.matches_pattern("code/src/model/User.java", "code/src/**/*.java")

        # These should NOT match - wrong extension or path
        assert not matcher.matches_pattern("code/src/Main.py", "code/src/**/*.java")
        assert not matcher.matches_pattern("code/test/Main.java", "code/src/**/*.java")

    def test_doublestar_with_wildcard_name_matches_any_subdirectory(self):
        """
        Pattern "**/*Synchronizer*" should match files with "Synchronizer" in name
        at any depth, including root level.

        Real-world example from Claude.ai FTS search.
        """
        matcher = PathPatternMatcher()

        # These MUST match - files at various depths
        assert matcher.matches_pattern("RedisSynchronizer.java", "**/*Synchronizer*")
        assert matcher.matches_pattern("src/RedisSynchronizer.java", "**/*Synchronizer*")
        assert matcher.matches_pattern("src/sync/RedisSynchronizer.java", "**/*Synchronizer*")
        assert matcher.matches_pattern("code/src/sync/RedisSynchronizer.java", "**/*Synchronizer*")

        # These should NOT match - name doesn't contain "Synchronizer"
        assert not matcher.matches_pattern("src/sync/Helper.java", "**/*Synchronizer*")
        assert not matcher.matches_pattern("Redis.java", "**/*Synchronizer*")

    def test_doublestar_prefix_matches_from_root(self):
        """
        Pattern "**/src/**/*.py" should match Python files under any src directory,
        including src/ at root level.
        """
        matcher = PathPatternMatcher()

        # These MUST match - src at root and nested
        assert matcher.matches_pattern("src/main.py", "**/src/**/*.py")
        assert matcher.matches_pattern("src/util/helper.py", "**/src/**/*.py")
        assert matcher.matches_pattern("project/src/main.py", "**/src/**/*.py")
        assert matcher.matches_pattern("project/code/src/util/helper.py", "**/src/**/*.py")

        # These should NOT match - not under src/ or wrong extension
        assert not matcher.matches_pattern("main.py", "**/src/**/*.py")
        assert not matcher.matches_pattern("tests/main.py", "**/src/**/*.py")
        assert not matcher.matches_pattern("src/main.java", "**/src/**/*.py")

    def test_doublestar_suffix_matches_all_descendants(self):
        """
        Pattern "src/**" should match src/ and all its descendants.
        """
        matcher = PathPatternMatcher()

        # These MUST match - src and all descendants
        assert matcher.matches_pattern("src/main.py", "src/**")
        assert matcher.matches_pattern("src/util/helper.py", "src/**")
        assert matcher.matches_pattern("src/a/b/c/deep.py", "src/**")

        # These should NOT match - not under src/
        assert not matcher.matches_pattern("main.py", "src/**")
        assert not matcher.matches_pattern("tests/main.py", "src/**")
        assert not matcher.matches_pattern("project/src/main.py", "src/**")


class TestBackwardCompatibility:
    """Ensure simple patterns still work after pathspec migration."""

    def test_simple_wildcard_still_works(self):
        """
        Pattern "*.py" with pathspec should match Python files at any depth
        (gitignore-style behavior).

        NOTE: This differs from strict glob where *.py only matches current directory.
        We're using gitignore-style matching which is more intuitive for code search.
        """
        matcher = PathPatternMatcher()

        # Simple wildcard patterns should match at any depth (gitignore-style)
        assert matcher.matches_pattern("main.py", "*.py")
        assert matcher.matches_pattern("test.py", "*.py")
        assert matcher.matches_pattern("src/main.py", "*.py")  # gitignore-style matches subdirs too

    def test_simple_path_pattern_still_works(self):
        """
        Pattern "src/tests/*.py" matches Python files directly in src/tests/ only.

        This is correct gitignore behavior - single * does NOT match across
        directory separators. Use ** for recursive matching.
        """
        matcher = PathPatternMatcher()

        # Pattern matches files directly in src/tests/
        assert matcher.matches_pattern("src/tests/test_auth.py", "src/tests/*.py")
        assert matcher.matches_pattern("src/tests/test_user.py", "src/tests/*.py")

        # Should NOT match files in subdirectories (correct gitignore behavior)
        # Use src/tests/**/*.py for recursive matching
        assert not matcher.matches_pattern("src/tests/unit/test_auth.py", "src/tests/*.py")

        # Should NOT match different paths
        assert not matcher.matches_pattern("src/main.py", "src/tests/*.py")

    def test_character_sets_still_work(self):
        """Pattern "test[123].py" should match test1.py, test2.py, test3.py."""
        matcher = PathPatternMatcher()

        # Character set patterns should still work
        assert matcher.matches_pattern("test1.py", "test[123].py")
        assert matcher.matches_pattern("test2.py", "test[123].py")
        assert matcher.matches_pattern("test3.py", "test[123].py")

        # Should NOT match other characters
        assert not matcher.matches_pattern("test4.py", "test[123].py")
        assert not matcher.matches_pattern("testa.py", "test[123].py")


class TestEdgeCases:
    """Test edge cases and corner cases for pathspec migration."""

    def test_empty_pattern_matches_nothing(self):
        """Empty pattern should match nothing."""
        matcher = PathPatternMatcher()

        assert not matcher.matches_pattern("src/main.py", "")
        assert not matcher.matches_pattern("main.py", "   ")

    def test_none_pattern_raises_error(self):
        """None pattern should raise TypeError."""
        matcher = PathPatternMatcher()

        with pytest.raises(TypeError):
            matcher.matches_pattern("src/main.py", None)

    def test_path_normalization_preserves_behavior(self):
        """Path normalization should work consistently with pathspec."""
        matcher = PathPatternMatcher()

        # Backslash normalization
        assert matcher.matches_pattern("src\\util\\helper.py", "src/**/*.py")

        # Forward slash normalization
        assert matcher.matches_pattern("src/util/helper.py", "src/**/*.py")

        # Both should match the same pattern
        assert matcher.matches_pattern("src\\util\\helper.py", "src/util/*.py")
        assert matcher.matches_pattern("src/util/helper.py", "src/util/*.py")

    def test_multiple_patterns_with_matches_any_pattern(self):
        """matches_any_pattern should work with pathspec-based matching."""
        matcher = PathPatternMatcher()

        patterns = ["**/*.py", "**/*.java", "**/*.js"]

        # Should match at least one pattern
        assert matcher.matches_any_pattern("src/main.py", patterns)
        assert matcher.matches_any_pattern("code/App.java", patterns)
        assert matcher.matches_any_pattern("dist/bundle.js", patterns)

        # Should NOT match any pattern
        assert not matcher.matches_any_pattern("README.md", patterns)
        assert not matcher.matches_any_pattern("data.json", patterns)
