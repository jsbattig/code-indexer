"""
Tests for LanguageMapper - TDD implementation for language mapping system.

This module tests the core functionality of mapping friendly language names
to file extensions for the CIDX code indexer query system.
"""

import pytest
from code_indexer.services.language_mapper import LanguageMapper


class TestLanguageMapperCore:
    """Test core language mapping functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mapper = LanguageMapper()

    def test_python_friendly_name_maps_to_extensions(self):
        """Test that 'python' maps to Python file extensions."""
        extensions = self.mapper.get_extensions("python")
        expected_extensions = {"py", "pyw", "pyi"}
        assert extensions == expected_extensions

    def test_javascript_friendly_name_maps_to_extensions(self):
        """Test that 'javascript' maps to JavaScript file extensions."""
        extensions = self.mapper.get_extensions("javascript")
        expected_extensions = {"js", "jsx"}
        assert extensions == expected_extensions

    def test_typescript_friendly_name_maps_to_extensions(self):
        """Test that 'typescript' maps to TypeScript file extensions."""
        extensions = self.mapper.get_extensions("typescript")
        expected_extensions = {"ts", "tsx"}
        assert extensions == expected_extensions

    def test_case_insensitive_mapping(self):
        """Test that language names are case insensitive."""
        assert self.mapper.get_extensions("PYTHON") == {"py", "pyw", "pyi"}
        assert self.mapper.get_extensions("Python") == {"py", "pyw", "pyi"}
        assert self.mapper.get_extensions("PyThOn") == {"py", "pyw", "pyi"}

    def test_backward_compatibility_with_extensions(self):
        """Test that existing extension inputs still work."""
        # Direct extensions should return themselves as a set
        assert self.mapper.get_extensions("py") == {"py"}
        assert self.mapper.get_extensions("js") == {"js"}
        assert self.mapper.get_extensions("ts") == {"ts"}

    def test_unknown_language_returns_itself(self):
        """Test that unknown languages pass through unchanged for backward compatibility."""
        assert self.mapper.get_extensions("unknownlang") == {"unknownlang"}
        assert self.mapper.get_extensions("xyz") == {"xyz"}

    def test_comprehensive_language_support(self):
        """Test that all major programming languages are supported."""
        test_cases = [
            ("java", {"java"}),
            ("csharp", {"cs"}),
            ("cpp", {"cpp", "cc", "cxx", "c++"}),
            ("c", {"c", "h"}),
            ("go", {"go"}),
            ("rust", {"rs"}),
            ("php", {"php"}),
            ("ruby", {"rb"}),
            ("swift", {"swift"}),
            ("kotlin", {"kt", "kts"}),
            ("scala", {"scala"}),
            ("dart", {"dart"}),
        ]

        for language, expected_extensions in test_cases:
            extensions = self.mapper.get_extensions(language)
            assert extensions == expected_extensions, f"Failed for {language}"

    def test_web_languages_support(self):
        """Test support for web-specific languages."""
        test_cases = [
            ("html", {"html", "htm"}),
            ("css", {"css"}),
            ("vue", {"vue"}),
        ]

        for language, expected_extensions in test_cases:
            extensions = self.mapper.get_extensions(language)
            assert extensions == expected_extensions, f"Failed for {language}"

    def test_markup_and_config_languages(self):
        """Test support for markup and configuration languages."""
        test_cases = [
            ("markdown", {"md", "markdown"}),
            ("json", {"json"}),
            ("yaml", {"yaml", "yml"}),
            ("xml", {"xml"}),
            ("sql", {"sql"}),
            ("shell", {"sh", "bash"}),
            ("dockerfile", {"dockerfile"}),
            ("toml", {"toml"}),
        ]

        for language, expected_extensions in test_cases:
            extensions = self.mapper.get_extensions(language)
            assert extensions == expected_extensions, f"Failed for {language}"


class TestLanguageMapperAliases:
    """Test language alias functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mapper = LanguageMapper()

    def test_common_aliases(self):
        """Test that common language aliases work."""
        # JavaScript aliases
        assert self.mapper.get_extensions("js") == {"js"}
        assert self.mapper.get_extensions("javascript") == {"js", "jsx"}

        # TypeScript aliases
        assert self.mapper.get_extensions("ts") == {"ts"}
        assert self.mapper.get_extensions("typescript") == {"ts", "tsx"}

        # C++ aliases
        assert self.mapper.get_extensions("c++") == {"cpp", "cc", "cxx", "c++"}
        assert self.mapper.get_extensions("cpp") == {"cpp", "cc", "cxx", "c++"}

    def test_file_extension_direct_mapping(self):
        """Test that file extensions map directly to themselves."""
        extensions = ["py", "js", "ts", "java", "cs", "go", "rs", "php", "rb"]

        for ext in extensions:
            result = self.mapper.get_extensions(ext)
            assert ext in result, f"Extension {ext} should be in its own mapping"


class TestLanguageMapperEdgeCases:
    """Test edge cases and error conditions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mapper = LanguageMapper()

    def test_empty_string_input(self):
        """Test behavior with empty string input."""
        result = self.mapper.get_extensions("")
        assert result == {""}  # Should return empty string as set for consistency

    def test_whitespace_handling(self):
        """Test that whitespace is handled properly."""
        assert self.mapper.get_extensions("  python  ") == {"py", "pyw", "pyi"}
        assert self.mapper.get_extensions("python ") == {"py", "pyw", "pyi"}
        assert self.mapper.get_extensions(" python") == {"py", "pyw", "pyi"}

    def test_none_input_raises_error(self):
        """Test that None input raises appropriate error."""
        with pytest.raises((TypeError, AttributeError)):
            self.mapper.get_extensions(None)


class TestLanguageMapperPerformance:
    """Test performance characteristics."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mapper = LanguageMapper()

    def test_lookup_is_fast(self):
        """Test that language lookup is O(1) and fast."""
        import time

        # Warm up
        self.mapper.get_extensions("python")

        # Test many lookups
        start_time = time.time()
        for _ in range(1000):
            self.mapper.get_extensions("python")
        end_time = time.time()

        # Should complete very quickly (< 0.1 seconds for 1000 lookups)
        duration = end_time - start_time
        assert duration < 0.1, f"1000 lookups took {duration}s, should be < 0.1s"

    def test_unknown_language_is_fast(self):
        """Test that unknown language handling is also fast."""
        import time

        start_time = time.time()
        for i in range(100):
            self.mapper.get_extensions(f"unknown_lang_{i}")
        end_time = time.time()

        duration = end_time - start_time
        assert (
            duration < 0.05
        ), f"100 unknown lookups took {duration}s, should be < 0.05s"
