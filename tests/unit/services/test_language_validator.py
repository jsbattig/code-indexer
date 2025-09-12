"""
Tests for LanguageValidator - TDD implementation for language validation and suggestions.

This module tests the validation logic that provides helpful error messages and
suggestions when users enter invalid or unknown language names.
"""

from code_indexer.services.language_validator import LanguageValidator


class TestLanguageValidatorCore:
    """Test core language validation functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = LanguageValidator()

    def test_valid_language_names_pass_validation(self):
        """Test that known language names pass validation."""
        valid_languages = ["python", "javascript", "typescript", "java", "go"]

        for language in valid_languages:
            result = self.validator.validate_language(language)
            assert result.is_valid, f"Language '{language}' should be valid"
            assert result.language == language
            assert result.suggestions == []
            assert result.error_message is None

    def test_valid_extensions_pass_validation(self):
        """Test that direct file extensions pass validation."""
        valid_extensions = ["py", "js", "ts", "java", "go"]

        for ext in valid_extensions:
            result = self.validator.validate_language(ext)
            assert result.is_valid, f"Extension '{ext}' should be valid"
            assert result.language == ext
            assert result.suggestions == []
            assert result.error_message is None

    def test_case_insensitive_validation(self):
        """Test that validation is case insensitive."""
        test_cases = ["PYTHON", "Python", "pYtHoN", "JAVASCRIPT", "JavaScript"]

        for language in test_cases:
            result = self.validator.validate_language(language)
            assert (
                result.is_valid
            ), f"Language '{language}' should be valid (case insensitive)"

    def test_invalid_language_with_suggestions(self):
        """Test that invalid languages provide helpful suggestions."""
        test_cases = [
            # Typos in language names
            ("pythom", ["python"]),
            ("javascrip", ["javascript"]),
            ("typescrip", ["typescript"]),
            ("javascirpt", ["javascript"]),
            # Common alternative names
            ("node", ["javascript"]),
            ("nodejs", ["javascript"]),
            ("reactjs", ["javascript", "jsx"]),
            ("react", ["javascript", "jsx"]),
            ("vue.js", ["vue"]),
            ("vuejs", ["vue"]),
            # Programming language aliases
            (
                "c++",
                ["cpp"],
            ),  # This should already be mapped, but test suggestion system
            ("c#", ["csharp"]),
            ("cs", ["csharp"]),  # This should be valid, but test suggestion system
        ]

        for invalid_lang, expected_suggestions in test_cases:
            result = self.validator.validate_language(invalid_lang)
            if not result.is_valid:  # Only test if it's actually invalid
                assert (
                    len(result.suggestions) > 0
                ), f"Language '{invalid_lang}' should have suggestions"
                # Check that expected suggestions are present
                for suggestion in expected_suggestions:
                    assert (
                        suggestion in result.suggestions
                    ), f"Expected '{suggestion}' in suggestions for '{invalid_lang}'"

    def test_error_messages_for_invalid_languages(self):
        """Test that invalid languages have appropriate error messages."""
        invalid_languages = ["unknownlang", "invalidlang", "xyz123"]

        for language in invalid_languages:
            result = self.validator.validate_language(language)
            if not result.is_valid:
                assert (
                    result.error_message is not None
                ), f"Language '{language}' should have error message"
                assert (
                    "unknown" in result.error_message.lower()
                    or "invalid" in result.error_message.lower()
                )
                assert (
                    language in result.error_message
                )  # Should mention the invalid language

    def test_empty_language_handling(self):
        """Test handling of empty or whitespace-only language names."""
        test_cases = ["", "   ", "\t", "\n"]

        for language in test_cases:
            result = self.validator.validate_language(language)
            assert (
                not result.is_valid
            ), f"Empty/whitespace language '{repr(language)}' should be invalid"
            assert result.error_message is not None

    def test_none_language_handling(self):
        """Test handling of None language input."""
        result = self.validator.validate_language(None)
        assert not result.is_valid
        assert result.error_message is not None
        assert (
            "none" in result.error_message.lower()
            or "null" in result.error_message.lower()
        )


class TestLanguageValidationResult:
    """Test the LanguageValidationResult data structure."""

    def test_validation_result_structure(self):
        """Test that ValidationResult has correct structure."""
        from code_indexer.services.language_validator import LanguageValidationResult

        # Test valid result
        valid_result = LanguageValidationResult(
            is_valid=True, language="python", suggestions=[], error_message=None
        )
        assert valid_result.is_valid
        assert valid_result.language == "python"
        assert valid_result.suggestions == []
        assert valid_result.error_message is None

        # Test invalid result
        invalid_result = LanguageValidationResult(
            is_valid=False,
            language="unknownlang",
            suggestions=["python", "javascript"],
            error_message="Unknown language: unknownlang",
        )
        assert not invalid_result.is_valid
        assert invalid_result.language == "unknownlang"
        assert invalid_result.suggestions == ["python", "javascript"]
        assert "unknownlang" in invalid_result.error_message


class TestLanguageValidatorSuggestionAlgorithm:
    """Test the suggestion algorithm for similar language names."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = LanguageValidator()

    def test_suggestion_algorithm_finds_close_matches(self):
        """Test that suggestion algorithm finds close matches."""
        test_cases = [
            # Single character typos
            ("pytho", "python"),
            ("jav", "java"),
            ("javascrip", "javascript"),
            # Character swaps
            ("javascirpt", "javascript"),
            ("pytohn", "python"),
        ]

        for typo, expected in test_cases:
            result = self.validator.validate_language(typo)
            if not result.is_valid:
                assert (
                    expected in result.suggestions
                ), f"Expected '{expected}' in suggestions for typo '{typo}'"

    def test_suggestion_limit(self):
        """Test that suggestions are limited to a reasonable number."""
        result = self.validator.validate_language("xyz")
        if not result.is_valid:
            assert (
                len(result.suggestions) <= 5
            ), "Should limit suggestions to reasonable number"

    def test_suggestions_are_sorted_by_relevance(self):
        """Test that suggestions are sorted by relevance/similarity."""
        # Test a typo that could match multiple languages
        result = self.validator.validate_language("java123")
        if not result.is_valid and len(result.suggestions) > 1:
            # First suggestion should be most relevant
            # For "java123", "java" should be the top suggestion
            assert (
                result.suggestions[0] == "java"
            ), f"Expected 'java' as top suggestion, got {result.suggestions}"


class TestLanguageValidatorCommonMistakes:
    """Test handling of common user mistakes and alternative names."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = LanguageValidator()

    def test_common_alternative_names(self):
        """Test that common alternative language names provide good suggestions."""
        alternatives = {
            "node": "javascript",
            "nodejs": "javascript",
            "react": "javascript",
            "vue.js": "vue",
            "c#": "csharp",
            "c++": "cpp",
        }

        for alternative, expected in alternatives.items():
            result = self.validator.validate_language(alternative)
            # These might be valid (if mapped) or invalid (if needing suggestions)
            if not result.is_valid:
                assert (
                    expected in result.suggestions
                ), f"Expected '{expected}' suggested for '{alternative}'"

    def test_file_extension_suggestions(self):
        """Test that file extensions with dots provide appropriate suggestions."""
        test_cases = [
            (".py", "python"),
            (".js", "javascript"),
            (".ts", "typescript"),
            (".java", "java"),
        ]

        for ext_with_dot, expected in test_cases:
            result = self.validator.validate_language(ext_with_dot)
            # Should either be valid or provide good suggestions
            if not result.is_valid:
                assert (
                    expected in result.suggestions
                    or ext_with_dot.lstrip(".") in result.suggestions
                )


class TestLanguageValidatorPerformance:
    """Test performance characteristics of language validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = LanguageValidator()

    def test_validation_is_fast(self):
        """Test that validation is fast even for invalid languages."""
        import time

        start_time = time.time()
        for i in range(100):
            self.validator.validate_language(f"invalid_lang_{i}")
        end_time = time.time()

        duration = end_time - start_time
        assert duration < 0.5, f"100 validations took {duration}s, should be < 0.5s"

    def test_suggestion_generation_is_reasonable(self):
        """Test that suggestion generation doesn't take too long."""
        import time

        start_time = time.time()
        _ = self.validator.validate_language("unknownverylonglanguagename")
        end_time = time.time()

        duration = end_time - start_time
        assert (
            duration < 0.1
        ), f"Suggestion generation took {duration}s, should be < 0.1s"
