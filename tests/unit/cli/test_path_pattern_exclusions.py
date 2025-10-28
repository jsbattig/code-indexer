"""
Test-driven development for path pattern exclusion filtering.

Tests pattern matching logic for --exclude-path option, including:
- Wildcard patterns (*, **, ?)
- Character sequences ([seq], [!seq])
- Complex glob patterns
- Multiple exclusion patterns
"""


class TestBasicPathPatternMatching:
    """Test basic glob pattern matching for path exclusions."""

    def test_single_wildcard_matches_directory_component(self):
        """Test that */tests/* pattern matches any path containing tests directory."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Should match: any/path/tests/file.py
        assert matcher.matches_pattern("src/project/tests/test_auth.py", "*/tests/*")
        assert matcher.matches_pattern("lib/tests/unit.py", "*/tests/*")
        assert matcher.matches_pattern("tests/integration.py", "*/tests/*")

        # Should NOT match: no tests directory
        assert not matcher.matches_pattern("src/project/auth.py", "*/tests/*")
        assert not matcher.matches_pattern("src/testing.py", "*/tests/*")

    def test_double_wildcard_matches_nested_paths(self):
        """Test that ** pattern matches any depth of nested directories."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Should match: any depth
        assert matcher.matches_pattern("vendor/lib/module.py", "**/vendor/**")
        assert matcher.matches_pattern("src/vendor/deep/nested/file.py", "**/vendor/**")
        assert matcher.matches_pattern("vendor/file.py", "**/vendor/**")

        # Should NOT match: vendor not in path
        assert not matcher.matches_pattern("src/module.py", "**/vendor/**")

    def test_extension_wildcard_matches_file_extensions(self):
        """Test that *.ext pattern matches all files with that extension."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Should match: any .min.js file
        assert matcher.matches_pattern("dist/app.min.js", "*.min.js")
        assert matcher.matches_pattern("build/vendor.min.js", "*.min.js")
        assert matcher.matches_pattern("lib/bundle.min.js", "*.min.js")

        # Should NOT match: different extension
        assert not matcher.matches_pattern("dist/app.js", "*.min.js")
        assert not matcher.matches_pattern("src/module.py", "*.min.js")

    def test_question_mark_matches_single_character(self):
        """Test that ? pattern matches exactly one character."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Should match: single character replacement
        assert matcher.matches_pattern("src/temp_1.py", "src/temp_?.py")
        assert matcher.matches_pattern("src/temp_a.py", "src/temp_?.py")

        # Should NOT match: multiple characters or no match
        assert not matcher.matches_pattern("src/temp_12.py", "src/temp_?.py")
        assert not matcher.matches_pattern("src/temp.py", "src/temp_?.py")

    def test_character_sequence_matches_set(self):
        """Test that [seq] pattern matches characters in sequence."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Should match: characters in set
        assert matcher.matches_pattern("test1.py", "test[123].py")
        assert matcher.matches_pattern("test2.py", "test[123].py")

        # Should NOT match: characters not in set
        assert not matcher.matches_pattern("test4.py", "test[123].py")
        assert not matcher.matches_pattern("testa.py", "test[123].py")

    def test_negated_character_sequence_excludes_set(self):
        """Test that [!seq] pattern excludes characters in sequence."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Should match: characters NOT in set
        assert matcher.matches_pattern("test4.py", "test[!123].py")
        assert matcher.matches_pattern("testa.py", "test[!123].py")

        # Should NOT match: characters in excluded set
        assert not matcher.matches_pattern("test1.py", "test[!123].py")
        assert not matcher.matches_pattern("test2.py", "test[!123].py")


class TestComplexPathPatterns:
    """Test complex and combined glob patterns."""

    def test_combined_wildcard_patterns(self):
        """Test patterns combining multiple wildcard types."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Pattern: src/*/temp_*
        assert matcher.matches_pattern("src/module/temp_data.py", "src/*/temp_*")
        assert matcher.matches_pattern("src/lib/temp_cache.json", "src/*/temp_*")

        # Should NOT match: wrong directory structure
        assert not matcher.matches_pattern("src/temp_data.py", "src/*/temp_*")
        assert not matcher.matches_pattern("lib/module/temp_data.py", "src/*/temp_*")

    def test_multiple_directory_patterns(self):
        """Test patterns matching multiple directory levels."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        # Pattern: **/build/**/dist/**
        assert matcher.matches_pattern(
            "project/build/output/dist/file.js", "**/build/**/dist/**"
        )
        assert matcher.matches_pattern(
            "build/temp/dist/bundle.js", "**/build/**/dist/**"
        )

        # Should NOT match: missing required directories
        assert not matcher.matches_pattern(
            "project/build/file.js", "**/build/**/dist/**"
        )
        assert not matcher.matches_pattern(
            "project/dist/file.js", "**/build/**/dist/**"
        )


class TestMultipleExclusionPatterns:
    """Test handling of multiple exclusion patterns."""

    def test_multiple_patterns_work_independently(self):
        """Test that multiple exclusion patterns are evaluated independently."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        patterns = ["*/tests/*", "*.min.js", "**/vendor/**"]

        # Should match at least one pattern
        assert matcher.matches_any_pattern("src/tests/test.py", patterns)
        assert matcher.matches_any_pattern("dist/app.min.js", patterns)
        assert matcher.matches_any_pattern("lib/vendor/module.js", patterns)

        # Should NOT match any pattern
        assert not matcher.matches_any_pattern("src/module.py", patterns)
        assert not matcher.matches_any_pattern("dist/app.js", patterns)

    def test_empty_pattern_list_matches_nothing(self):
        """Test that empty pattern list matches no paths."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        patterns = []

        # Empty pattern list should match nothing
        assert not matcher.matches_any_pattern("src/tests/test.py", patterns)
        assert not matcher.matches_any_pattern("any/path/file.py", patterns)
