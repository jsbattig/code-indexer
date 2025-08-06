"""Override filtering service for file inclusion/exclusion rules.

This service applies override rules with the following precedence:
1. force_exclude_patterns (highest priority - absolute exclusion)
2. force_include_patterns (overrides base exclusion)
3. Extension filtering (add_extensions, remove_extensions)
4. Directory filtering (add_exclude_dirs, add_include_dirs)
5. Base filtering result (lowest priority)
"""

import logging
from pathlib import Path
import pathspec

from code_indexer.config import OverrideConfig

logger = logging.getLogger(__name__)


class OverrideFilterService:
    """Service for applying override filtering rules to file paths."""

    def __init__(self, override_config: OverrideConfig):
        """Initialize with override configuration.

        Args:
            override_config: Override configuration with filtering rules
        """
        self.override_config = override_config

        # Pre-compile pathspec patterns for efficiency
        self._force_include_spec = None
        self._force_exclude_spec = None

        if override_config.force_include_patterns:
            self._force_include_spec = pathspec.PathSpec.from_lines(
                "gitwildmatch", override_config.force_include_patterns
            )

        if override_config.force_exclude_patterns:
            self._force_exclude_spec = pathspec.PathSpec.from_lines(
                "gitwildmatch", override_config.force_exclude_patterns
            )

    def should_include_file(self, file_path: Path, base_result: bool) -> bool:
        """Determine if file should be included after applying override rules.

        Args:
            file_path: Path to the file to check
            base_result: Base filtering decision (from config + gitignore)

        Returns:
            True if file should be included, False otherwise
        """
        # Convert to string for pattern matching
        path_str = str(file_path)

        # 1. force_exclude_patterns have absolute priority
        if self._force_exclude_spec and self._force_exclude_spec.match_file(path_str):
            return False

        # 2. force_include_patterns override base exclusion
        if self._force_include_spec and self._force_include_spec.match_file(path_str):
            return True

        # 3. Apply extension filtering
        extension_result = self._apply_extension_filtering(file_path, base_result)
        if extension_result != base_result:
            return extension_result

        # 4. Apply directory filtering
        directory_result = self._apply_directory_filtering(file_path, base_result)
        if directory_result != base_result:
            return directory_result

        # 5. Keep base result if no overrides apply
        return base_result

    def _apply_extension_filtering(self, file_path: Path, base_result: bool) -> bool:
        """Apply extension-based filtering rules.

        Args:
            file_path: Path to check
            base_result: Current filtering result

        Returns:
            Updated filtering result based on extension rules
        """
        file_suffix = file_path.suffix.lower()

        # Check if extension should be excluded (remove_extensions)
        if file_suffix in self.override_config.remove_extensions:
            return False

        # Check if extension should be included (add_extensions)
        if file_suffix in self.override_config.add_extensions:
            return True

        return base_result

    def _apply_directory_filtering(self, file_path: Path, base_result: bool) -> bool:
        """Apply directory-based filtering rules.

        Args:
            file_path: Path to check
            base_result: Current filtering result

        Returns:
            Updated filtering result based on directory rules
        """
        path_parts = file_path.parts

        # Check if file is in excluded directory (add_exclude_dirs)
        for exclude_dir in self.override_config.add_exclude_dirs:
            if exclude_dir in path_parts:
                return False

        # Check if file is in included directory (add_include_dirs)
        for include_dir in self.override_config.add_include_dirs:
            if include_dir in path_parts:
                return True

        return base_result
