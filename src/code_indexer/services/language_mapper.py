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
- YAML-based configuration with reactive creation
"""

from typing import Set, Dict, Optional, Any
from pathlib import Path
import logging

from ..utils.yaml_utils import (
    create_language_mappings_yaml,
    load_language_mappings_yaml,
    DEFAULT_LANGUAGE_MAPPINGS,
)

logger = logging.getLogger(__name__)


class LanguageMapper:
    """
    Maps friendly language names to file extensions for query filtering.

    This class provides a centralized mapping between user-friendly language names
    (like "python", "javascript") and the file extensions stored in Filesystem (like "py", "js").

    Features:
    - Case-insensitive language matching
    - Multiple extensions per language (e.g., python -> py, pyw, pyi)
    - Direct extension usage support
    - Fast O(1) lookup performance
    - Unknown languages pass through unchanged for compatibility
    - YAML-based configuration with reactive creation
    """

    # Class-level cache for singleton pattern
    _instance: Optional["LanguageMapper"] = None
    _mappings_cache: Optional[Dict[str, Set[str]]] = None
    _yaml_path_cache: Optional[Path] = None

    def __new__(cls):
        """Implement singleton pattern for efficiency."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the language mapper with YAML-based mappings."""
        # Skip re-initialization if already loaded
        if self._mappings_cache is not None:
            self._language_to_extensions = self._mappings_cache
            return

        # Find config directory
        config_dir = self._find_config_dir()

        if config_dir:
            yaml_path = config_dir / "language-mappings.yaml"
            self._yaml_path_cache = yaml_path

            # Try to load from YAML
            try:
                if yaml_path.exists():
                    # Load existing mappings
                    self._language_to_extensions = load_language_mappings_yaml(
                        yaml_path
                    )
                    logger.debug(f"Loaded language mappings from {yaml_path}")
                else:
                    # Reactive creation: create YAML on first use
                    logger.info(
                        "Language mappings file not found, creating with defaults"
                    )
                    create_language_mappings_yaml(config_dir, force=False)
                    self._language_to_extensions = self._convert_default_mappings()

            except Exception as e:
                # Fallback to defaults on any error
                logger.warning(
                    f"Failed to load/create YAML mappings: {e}, using defaults"
                )
                self._language_to_extensions = self._convert_default_mappings()
        else:
            # No config directory found, use defaults
            logger.debug("No .code-indexer directory found, using default mappings")
            self._language_to_extensions = self._convert_default_mappings()

        # Cache the mappings
        LanguageMapper._mappings_cache = self._language_to_extensions

    def _find_config_dir(self) -> Optional[Path]:
        """
        Find .code-indexer directory by walking up from current directory.

        Returns:
            Path to .code-indexer directory if found, None otherwise
        """
        current = Path.cwd()

        # Walk up directory tree looking for .code-indexer
        while current != current.parent:
            config_dir = current / ".code-indexer"
            if config_dir.exists() and config_dir.is_dir():
                return config_dir
            current = current.parent

        # Check root directory
        config_dir = current / ".code-indexer"
        if config_dir.exists() and config_dir.is_dir():
            return config_dir

        return None

    def _convert_default_mappings(self) -> Dict[str, Set[str]]:
        """Convert default list-based mappings to set-based."""
        return {lang: set(exts) for lang, exts in DEFAULT_LANGUAGE_MAPPINGS.items()}

    def reload_mappings(self) -> None:
        """
        Force reload of mappings from YAML file.
        Useful after manual edits to the YAML file.
        """
        # Clear caches
        LanguageMapper._mappings_cache = None

        # Re-initialize by calling initialization logic directly
        config_dir = self._find_config_dir()

        if config_dir:
            yaml_path = config_dir / "language-mappings.yaml"
            self._yaml_path_cache = yaml_path

            # Try to load from YAML
            try:
                if yaml_path.exists():
                    # Load existing mappings
                    self._language_to_extensions = load_language_mappings_yaml(
                        yaml_path
                    )
                    logger.debug(f"Reloaded language mappings from {yaml_path}")
                else:
                    # Reactive creation: create YAML on first use
                    logger.info(
                        "Language mappings file not found, creating with defaults"
                    )
                    create_language_mappings_yaml(config_dir, force=False)
                    self._language_to_extensions = self._convert_default_mappings()

            except Exception as e:
                # Fallback to defaults on any error
                logger.warning(f"Failed to reload YAML mappings: {e}, using defaults")
                self._language_to_extensions = self._convert_default_mappings()
        else:
            # No config directory found, use defaults
            logger.debug("No .code-indexer directory found, using default mappings")
            self._language_to_extensions = self._convert_default_mappings()

        # Cache the mappings
        LanguageMapper._mappings_cache = self._language_to_extensions

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

    def build_language_filter(self, language: str) -> Dict[str, Any]:
        """
        Build Filesystem filter for language filtering with OR semantics.

        Args:
            language: Language name or extension

        Returns:
            Filesystem filter dict with proper OR logic for multiple extensions

        Examples:
            >>> mapper = LanguageMapper()
            >>> mapper.build_language_filter("python")
            {'should': [{'key': 'language', 'match': {'value': 'py'}},
                       {'key': 'language', 'match': {'value': 'pyw'}},
                       {'key': 'language', 'match': {'value': 'pyi'}}]}
            >>> mapper.build_language_filter("java")
            {'key': 'language', 'match': {'value': 'java'}}
            >>> mapper.build_language_filter("py")
            {'key': 'language', 'match': {'value': 'py'}}
        """
        if self.is_supported_language(language):
            extensions = self.get_extensions(language)
            if len(extensions) == 1:
                # Single extension - simple filter
                return {"key": "language", "match": {"value": list(extensions)[0]}}
            else:
                # Multiple extensions - OR filter
                return {
                    "should": [
                        {"key": "language", "match": {"value": ext}}
                        for ext in extensions
                    ]
                }
        else:
            # Direct extension or unknown language
            return {"key": "language", "match": {"value": language}}
