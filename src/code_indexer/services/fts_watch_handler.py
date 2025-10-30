"""
FTS Watch Handler for real-time FTS index maintenance.

Monitors file system changes and updates the Tantivy FTS index incrementally
alongside the semantic index in watch mode.
"""

import logging
from pathlib import Path
from watchdog.events import FileSystemEventHandler

from .tantivy_index_manager import TantivyIndexManager

logger = logging.getLogger(__name__)


class FTSWatchHandler(FileSystemEventHandler):
    """File system event handler for FTS index maintenance in watch mode."""

    def __init__(
        self,
        tantivy_index_manager: TantivyIndexManager,
        config,
    ):
        """
        Initialize FTS watch handler.

        Args:
            tantivy_index_manager: TantivyIndexManager instance for FTS operations
            config: Application configuration
        """
        super().__init__()
        self.tantivy_manager = tantivy_index_manager
        self.config = config

        # Statistics
        self.files_updated_count = 0
        self.files_deleted_count = 0

    def on_modified(self, event):
        """Handle file modification events."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Check if file should be indexed
        if not self._should_include_file(file_path):
            return

        try:
            # Read file content
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Extract identifiers (simple implementation - can be enhanced)
            identifiers = self._extract_identifiers(content, file_path)

            # Detect language
            language = self._detect_language(file_path)

            # Create FTS document
            doc = {
                "path": str(file_path),
                "content": content,
                "content_raw": content,
                "identifiers": identifiers,
                "line_start": 1,
                "line_end": len(content.splitlines()),
                "language": language,
            }

            # Update document in FTS index (atomic operation)
            self.tantivy_manager.update_document(str(file_path), doc)
            self.files_updated_count += 1
            logger.debug(f"Updated FTS index for: {file_path}")

        except Exception as e:
            logger.warning(f"Failed to update FTS index for {file_path}: {e}")

    def on_deleted(self, event):
        """Handle file deletion events."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Check if file extension would have been indexed
        if not self._should_include_deleted_file(file_path):
            return

        try:
            # Delete document from FTS index (atomic operation)
            self.tantivy_manager.delete_document(str(file_path))
            self.files_deleted_count += 1
            logger.debug(f"Deleted from FTS index: {file_path}")

        except Exception as e:
            logger.warning(f"Failed to delete from FTS index {file_path}: {e}")

    def on_created(self, event):
        """Handle file creation events (same as modification)."""
        if event.is_directory:
            return

        # Treat creation same as modification
        self.on_modified(event)

    def on_moved(self, event):
        """Handle file move events."""
        if event.is_directory:
            return

        # Treat move as delete old + create new
        old_path = Path(event.src_path)

        # Delete old path
        if self._should_include_deleted_file(old_path):
            try:
                self.tantivy_manager.delete_document(str(old_path))
                self.files_deleted_count += 1
            except Exception as e:
                logger.warning(
                    f"Failed to delete old path from FTS index {old_path}: {e}"
                )

        # Add new path (will be handled by on_created via watchdog)
        # Note: watchdog fires both on_moved and on_created for destination

    def _should_include_file(self, file_path: Path) -> bool:
        """Check if file should be included in FTS indexing."""
        try:
            # Use the same logic as regular indexing
            from ..indexing import FileFinder

            file_finder = FileFinder(self.config)
            return file_finder._should_include_file(file_path)
        except Exception as e:
            logger.warning(f"Failed to check if file should be included: {e}")
            return False

    def _should_include_deleted_file(self, file_path: Path) -> bool:
        """Check if a deleted file would have been included in indexing."""
        try:
            # For deleted files, just check the file extension
            extension = file_path.suffix.lstrip(".")
            return extension in self.config.file_extensions
        except Exception as e:
            logger.warning(f"Failed to check if deleted file should be included: {e}")
            return False

    def _extract_identifiers(self, content: str, file_path: Path) -> list:
        """
        Extract identifiers from content for identifier-based search.

        This is a simple implementation that can be enhanced with
        proper tokenization and language-specific parsing.
        """
        import re

        # Simple regex to extract potential identifiers (alphanumeric + underscore)
        pattern = r"\b[a-zA-Z_][a-zA-Z0-9_]*\b"
        identifiers = list(set(re.findall(pattern, content)))

        # Limit to reasonable number to avoid bloat
        return identifiers[:1000]

    def _detect_language(self, file_path: Path) -> str:
        """Detect programming language from file extension."""
        extension = file_path.suffix.lstrip(".").lower()

        # Map extensions to language names
        language_map = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "java": "java",
            "cpp": "cpp",
            "c": "c",
            "h": "c",
            "hpp": "cpp",
            "go": "go",
            "rs": "rust",
            "rb": "ruby",
            "php": "php",
            "swift": "swift",
            "kt": "kotlin",
            "scala": "scala",
            "sh": "shell",
            "bash": "shell",
            "sql": "sql",
            "md": "markdown",
            "txt": "text",
            "yaml": "yaml",
            "yml": "yaml",
            "json": "json",
            "xml": "xml",
            "html": "html",
            "css": "css",
        }

        return language_map.get(extension, "unknown")

    def get_statistics(self) -> dict:
        """Get FTS watch handler statistics."""
        return {
            "fts_files_updated": self.files_updated_count,
            "fts_files_deleted": self.files_deleted_count,
        }
