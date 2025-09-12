"""
Language mapping service for CIDX code indexer.

This module provides mapping between friendly language names (like "python", "javascript")
and file extensions (like "py", "js") to enable intuitive language filtering in queries.

The mapper supports:
- Friendly language names: python, javascript, typescript, etc.
- File extension pass-through: py, js, ts, etc.
- Case-insensitive matching
- Multiple extensions per language
- Fast O(1) lookup performance
"""

from typing import Set, Dict
import logging

logger = logging.getLogger(__name__)


class LanguageMapper:
    """
    Maps friendly language names to file extensions for query filtering.

    This class provides a centralized mapping between user-friendly language names
    (like "python", "javascript") and the file extensions stored in Qdrant (like "py", "js").

    Features:
    - Case-insensitive language matching
    - Multiple extensions per language (e.g., python -> py, pyw, pyi)
    - Direct extension usage support
    - Fast O(1) lookup performance
    - Unknown languages pass through unchanged for compatibility
    """

    def __init__(self):
        """Initialize the language mapper with comprehensive language mappings."""
        self._language_to_extensions = self._build_language_mappings()

    def _build_language_mappings(self) -> Dict[str, Set[str]]:
        """
        Build comprehensive mappings from friendly names to file extensions.

        Returns:
            Dictionary mapping language names to sets of file extensions
        """
        return {
            # Programming languages
            "python": {"py", "pyw", "pyi"},
            "javascript": {"js", "jsx"},
            "typescript": {"ts", "tsx"},
            "java": {"java"},
            "csharp": {"cs"},
            "c": {"c", "h"},
            "cpp": {"cpp", "cc", "cxx", "c++"},
            "c++": {"cpp", "cc", "cxx", "c++"},  # Alias for cpp
            "go": {"go"},
            "rust": {"rs"},
            "php": {"php"},
            "ruby": {"rb"},
            "swift": {"swift"},
            "kotlin": {"kt", "kts"},
            "scala": {"scala"},
            "dart": {"dart"},
            # Web technologies
            "html": {"html", "htm"},
            "css": {"css"},
            "vue": {"vue"},
            # Markup and documentation
            "markdown": {"md", "markdown"},
            "xml": {"xml"},
            "latex": {"tex", "latex"},
            "rst": {"rst"},
            # Data and configuration
            "json": {"json"},
            "yaml": {"yaml", "yml"},
            "toml": {"toml"},
            "ini": {"ini"},
            "sql": {"sql"},
            # Shell and scripting
            "shell": {"sh", "bash"},
            "bash": {"sh", "bash"},
            "powershell": {"ps1", "psm1", "psd1"},
            "batch": {"bat", "cmd"},
            # Build and config files
            "dockerfile": {"dockerfile"},
            "makefile": {"makefile", "mk"},
            "cmake": {"cmake"},
            # Other formats
            "text": {"txt"},
            "log": {"log"},
            "csv": {"csv"},
        }

    def get_extensions(self, language: str) -> Set[str]:
        """
        Get file extensions for a given language name or extension.

        This method supports:
        - Friendly names: "python" -> {"py", "pyw", "pyi"}
        - Direct extensions: "py" -> {"py"}
        - Case-insensitive matching: "PYTHON" -> {"py", "pyw", "pyi"}
        - Unknown inputs: "unknownlang" -> {"unknownlang"} (pass-through)

        Args:
            language: Language name (e.g., "python", "javascript") or extension (e.g., "py", "js")

        Returns:
            Set of file extensions for the language

        Examples:
            >>> mapper = LanguageMapper()
            >>> mapper.get_extensions("python")
            {'py', 'pyw', 'pyi'}
            >>> mapper.get_extensions("py")
            {'py'}
            >>> mapper.get_extensions("JAVASCRIPT")
            {'js', 'jsx'}
        """
        if language is None:
            raise TypeError("Language cannot be None")

        # Strip whitespace and normalize to lowercase
        normalized_language = language.strip().lower()

        # Check if it's a known friendly language name
        if normalized_language in self._language_to_extensions:
            extensions: Set[str] = self._language_to_extensions[normalized_language]
            logger.debug(f"Mapped language '{language}' to extensions: {extensions}")
            return extensions.copy()  # Return copy to prevent modification

        # For unknown languages and direct extensions, return as-is
        # This allows direct extension usage (e.g., "py") and graceful handling
        # of unknown inputs
        result = {language.strip()}  # Preserve original case for extensions
        logger.debug(
            f"Unknown language '{language}', using pass-through behavior: {result}"
        )
        return result

    def get_supported_languages(self) -> Set[str]:
        """
        Get all supported friendly language names.

        Returns:
            Set of supported language names (friendly names, not extensions)

        Examples:
            >>> mapper = LanguageMapper()
            >>> languages = mapper.get_supported_languages()
            >>> "python" in languages
            True
            >>> "javascript" in languages
            True
        """
        return set(self._language_to_extensions.keys())

    def is_supported_language(self, language: str) -> bool:
        """
        Check if a language is supported as a friendly name.

        Args:
            language: Language name to check

        Returns:
            True if the language is supported as a friendly name, False otherwise

        Note:
            This only checks for friendly names, not direct extensions.
            Direct extensions are always "supported" via pass-through behavior.

        Examples:
            >>> mapper = LanguageMapper()
            >>> mapper.is_supported_language("python")
            True
            >>> mapper.is_supported_language("py")
            False  # Direct extension, not a friendly name
            >>> mapper.is_supported_language("unknownlang")
            False
        """
        if language is None:
            return False
        return language.strip().lower() in self._language_to_extensions

    def get_all_extensions(self) -> Set[str]:
        """
        Get all file extensions from all supported languages.

        Returns:
            Set of all file extensions across all languages

        Examples:
            >>> mapper = LanguageMapper()
            >>> extensions = mapper.get_all_extensions()
            >>> "py" in extensions
            True
            >>> "js" in extensions
            True
        """
        all_extensions = set()
        for extensions in self._language_to_extensions.values():
            all_extensions.update(extensions)
        return all_extensions
