"""
Language validation service for CIDX code indexer.

This module provides validation for language names and helpful suggestions
when users enter invalid or unknown languages, improving the user experience
of the query command's language filtering.

The validator integrates with LanguageMapper to provide comprehensive
validation and suggestion functionality.
"""

from dataclasses import dataclass
from typing import List, Optional
import difflib
import logging

from .language_mapper import LanguageMapper

logger = logging.getLogger(__name__)


@dataclass
class LanguageValidationResult:
    """
    Result of language validation containing validation status and suggestions.

    Attributes:
        is_valid: True if the language is valid/supported
        language: The original language input (trimmed)
        suggestions: List of suggested alternatives if invalid
        error_message: Human-readable error message if invalid
    """

    is_valid: bool
    language: str
    suggestions: List[str]
    error_message: Optional[str]


class LanguageValidator:
    """
    Validates language names and provides helpful suggestions for invalid inputs.

    This class works in conjunction with LanguageMapper to provide comprehensive
    language validation, including:
    - Validation of friendly language names and file extensions
    - Fuzzy matching for typos and common mistakes
    - Suggestions for alternative names and common misspellings
    - Helpful error messages with context

    The validator is designed to be user-friendly, providing clear feedback
    and helpful suggestions when users make common mistakes.
    """

    def __init__(self, language_mapper: Optional[LanguageMapper] = None):
        """
        Initialize the language validator.

        Args:
            language_mapper: Optional LanguageMapper instance. If not provided,
                           a new instance will be created.
        """
        self.mapper = language_mapper or LanguageMapper()
        self._common_alternatives = self._build_common_alternatives()

    def _build_common_alternatives(self) -> dict[str, List[str]]:
        """
        Build mapping of common alternative names to suggested languages.

        Returns:
            Dictionary mapping alternative names to suggestion lists
        """
        return {
            # JavaScript ecosystem
            "node": ["javascript"],
            "nodejs": ["javascript"],
            "node.js": ["javascript"],
            "react": ["javascript"],
            "reactjs": ["javascript"],
            "react.js": ["javascript"],
            "vue.js": ["vue"],
            "vuejs": ["vue"],
            "angular": ["typescript", "javascript"],
            "angularjs": ["javascript"],
            # Programming language alternatives
            "c#": ["csharp"],
            "c++": ["cpp"],
            "objective-c": ["c"],
            "objc": ["c"],
            "golang": ["go"],
            # File extensions with dots (common user mistake)
            ".py": ["python"],
            ".js": ["javascript"],
            ".ts": ["typescript"],
            ".java": ["java"],
            ".cs": ["csharp"],
            ".go": ["go"],
            ".rs": ["rust"],
            ".php": ["php"],
            ".rb": ["ruby"],
            ".swift": ["swift"],
            ".kt": ["kotlin"],
            ".scala": ["scala"],
            ".dart": ["dart"],
            ".html": ["html"],
            ".css": ["css"],
            ".vue": ["vue"],
            ".md": ["markdown"],
            ".json": ["json"],
            ".yaml": ["yaml"],
            ".yml": ["yaml"],
            ".toml": ["toml"],
            ".sql": ["sql"],
            ".sh": ["shell"],
            ".bash": ["bash"],
            # Common misspellings and typos (will be supplemented by fuzzy matching)
            "pythom": ["python"],
            "pytohn": ["python"],
            "javascrip": ["javascript"],
            "javascirpt": ["javascript"],
            "typescrip": ["typescript"],
            "javasript": ["javascript"],
            "typescirpt": ["typescript"],
        }

    def validate_language(self, language: Optional[str]) -> LanguageValidationResult:
        """
        Validate a language name and provide suggestions if invalid.

        Args:
            language: Language name to validate (can be None)

        Returns:
            LanguageValidationResult with validation status and suggestions

        Examples:
            >>> validator = LanguageValidator()
            >>> result = validator.validate_language("python")
            >>> result.is_valid
            True
            >>> result = validator.validate_language("pythom")
            >>> result.is_valid
            False
            >>> "python" in result.suggestions
            True
        """
        # Handle None input
        if language is None:
            return LanguageValidationResult(
                is_valid=False,
                language="",
                suggestions=[],
                error_message="Language cannot be None or null",
            )

        # Handle empty or whitespace-only input
        if not language or not language.strip():
            return LanguageValidationResult(
                is_valid=False,
                language=language,
                suggestions=[],
                error_message="Language name cannot be empty or whitespace-only",
            )

        # Normalize input
        normalized_language = language.strip()

        try:
            # Check if this is a known friendly language name
            if self.mapper.is_supported_language(normalized_language):
                # It's a known friendly language name
                logger.debug(
                    f"Language '{normalized_language}' is a supported friendly name"
                )
                return LanguageValidationResult(
                    is_valid=True,
                    language=normalized_language,
                    suggestions=[],
                    error_message=None,
                )

            # Check if it's a known file extension
            all_extensions = self.mapper.get_all_extensions()
            if normalized_language.lower() in {ext.lower() for ext in all_extensions}:
                # It's a known file extension (case insensitive check)
                logger.debug(
                    f"Language '{normalized_language}' is a known file extension"
                )
                return LanguageValidationResult(
                    is_valid=True,
                    language=normalized_language,
                    suggestions=[],
                    error_message=None,
                )

            # If we reach here, it's an unknown language - provide suggestions
            logger.debug(
                f"Language '{normalized_language}' is unknown, generating suggestions"
            )
            suggestions = self._generate_suggestions(normalized_language)
            return LanguageValidationResult(
                is_valid=False,
                language=normalized_language,
                suggestions=suggestions,
                error_message=f"Unknown language: '{normalized_language}'. {self._format_suggestions_message(suggestions)}",
            )

        except (AttributeError, KeyError, TypeError) as e:
            # Handle expected exceptions specifically
            logger.error(f"Error validating language '{normalized_language}': {e}")
            return LanguageValidationResult(
                is_valid=False,
                language=normalized_language,
                suggestions=[],
                error_message=f"Error validating language '{normalized_language}': {str(e)}",
            )

    def _generate_suggestions(self, invalid_language: str) -> List[str]:
        """
        Generate helpful suggestions for an invalid language name.

        Args:
            invalid_language: The invalid language name

        Returns:
            List of suggested language names, sorted by relevance
        """
        suggestions = set()
        normalized_input = invalid_language.lower().strip()

        # Check common alternatives first
        if normalized_input in self._common_alternatives:
            suggestions.update(self._common_alternatives[normalized_input])
            logger.debug(
                f"Found common alternatives for '{invalid_language}': {self._common_alternatives[normalized_input]}"
            )

        # Get all supported languages for fuzzy matching
        supported_languages = self.mapper.get_supported_languages()
        all_extensions = self.mapper.get_all_extensions()

        # Combine all possible valid inputs
        all_valid_inputs = supported_languages | all_extensions

        # Use difflib for fuzzy matching
        close_matches = difflib.get_close_matches(
            normalized_input,
            [lang.lower() for lang in all_valid_inputs],
            n=5,  # Maximum 5 suggestions
            cutoff=0.4,  # Lower cutoff to catch more typos
        )

        # Map back to original case and add to suggestions
        for match in close_matches:
            # Find the original case version
            for original in all_valid_inputs:
                if original.lower() == match:
                    suggestions.add(original)
                    break

        logger.debug(
            f"Generated fuzzy suggestions for '{invalid_language}': {close_matches}"
        )

        # Convert to sorted list, prioritizing supported languages over extensions
        suggestions_list = list(suggestions)

        # Sort suggestions: friendly language names first, then extensions
        def sort_key(suggestion):
            if self.mapper.is_supported_language(suggestion):
                return (0, suggestion)  # Friendly names first
            else:
                return (1, suggestion)  # Extensions second

        suggestions_list.sort(key=sort_key)

        # Limit to reasonable number
        return suggestions_list[:5]

    def _format_suggestions_message(self, suggestions: List[str]) -> str:
        """
        Format suggestions into a helpful message.

        Args:
            suggestions: List of suggested language names

        Returns:
            Formatted message string
        """
        if not suggestions:
            return "No similar languages found."
        elif len(suggestions) == 1:
            return f"Did you mean '{suggestions[0]}'?"
        elif len(suggestions) <= 3:
            return f"Did you mean: {', '.join(suggestions)}?"
        else:
            first_three = suggestions[:3]
            return f"Did you mean: {', '.join(first_three)}, or others?"

    def get_validation_help(self) -> str:
        """
        Get help text about supported languages and common usage.

        Returns:
            Help text string explaining language validation
        """
        supported_langs = sorted(self.mapper.get_supported_languages())

        help_text = "Language Filtering Help:\n\n"
        help_text += "Supported friendly language names:\n"

        # Group languages for better readability
        programming = [
            lang
            for lang in supported_langs
            if lang
            in [
                "python",
                "javascript",
                "typescript",
                "java",
                "csharp",
                "cpp",
                "c",
                "go",
                "rust",
                "php",
                "ruby",
                "swift",
                "kotlin",
                "scala",
                "dart",
            ]
        ]
        web = [lang for lang in supported_langs if lang in ["html", "css", "vue"]]
        markup = [
            lang
            for lang in supported_langs
            if lang in ["markdown", "xml", "latex", "rst"]
        ]
        data = [
            lang
            for lang in supported_langs
            if lang in ["json", "yaml", "toml", "ini", "sql", "csv"]
        ]
        shell = [
            lang
            for lang in supported_langs
            if lang in ["shell", "bash", "powershell", "batch"]
        ]

        if programming:
            help_text += f"  Programming: {', '.join(programming)}\n"
        if web:
            help_text += f"  Web: {', '.join(web)}\n"
        if markup:
            help_text += f"  Markup: {', '.join(markup)}\n"
        if data:
            help_text += f"  Data: {', '.join(data)}\n"
        if shell:
            help_text += f"  Shell: {', '.join(shell)}\n"

        help_text += "\nYou can also use file extensions directly (py, js, ts, etc.)\n"
        help_text += "\nExamples:\n"
        help_text += "  --language python       # Find Python files\n"
        help_text += "  --language javascript   # Find JavaScript files\n"
        help_text += "  --language py          # Direct extension usage\n"
        help_text += "  --language js          # Direct extension usage\n"

        return help_text
