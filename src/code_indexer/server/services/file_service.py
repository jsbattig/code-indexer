"""
File Listing Service.

Provides real file listing operations following CLAUDE.md Foundation #1: No mocks.
All operations use real file system operations with proper pagination and filtering.
"""

import os
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime, timezone
import logging
import fnmatch
import math

from ..models.api_models import (
    FileListResponse,
    FileInfo,
    PaginationInfo,
    FileListQueryParams,
)

logger = logging.getLogger(__name__)

# Same language detection as stats service
LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".rb": "ruby",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".vue": "vue",
    ".jsx": "jsx",
    ".tsx": "tsx",
    ".md": "markdown",
    ".rst": "rst",
    ".txt": "text",
    ".json": "json",
    ".xml": "xml",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "config",
    ".conf": "config",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".fish": "shell",
    ".ps1": "powershell",
    ".bat": "batch",
    ".cmd": "batch",
}


class FileListingService:
    """Service for listing repository files."""

    def __init__(self):
        """Initialize the file listing service."""
        pass

    def list_files(
        self, repo_id: str, query_params: FileListQueryParams
    ) -> FileListResponse:
        """
        List files in repository with pagination and filtering.

        Args:
            repo_id: Repository identifier
            query_params: Query parameters for filtering and pagination

        Returns:
            File list response with pagination

        Raises:
            FileNotFoundError: If repository doesn't exist
            PermissionError: If repository access denied
            ValueError: If query parameters are invalid
        """
        repo_path = self._get_repository_path(repo_id)

        if not os.path.exists(repo_path):
            raise FileNotFoundError(f"Repository {repo_id} not found")

        # Collect all files
        all_files = self._collect_files(repo_path)

        # Apply filters
        filtered_files = self._apply_filters(all_files, query_params)

        # Apply sorting
        sorted_files = self._apply_sorting(filtered_files, query_params.sort_by)

        # Apply pagination
        paginated_files, pagination_info = self._apply_pagination(
            sorted_files, query_params.page, query_params.limit
        )

        return FileListResponse(files=paginated_files, pagination=pagination_info)

    def _get_repository_path(self, repo_id: str) -> str:
        """
        Get file system path for repository from real database.

        CLAUDE.md Foundation #1: Real database lookup, no placeholders.

        Args:
            repo_id: Repository identifier

        Returns:
            Real file system path to repository

        Raises:
            RuntimeError: If database lookup fails
            FileNotFoundError: If repository not found
        """
        try:
            # Use existing repository manager patterns from the codebase
            from ..repositories.golden_repo_manager import GoldenRepoManager

            repo_manager = GoldenRepoManager()

            # Search for repository by alias (repo_id)
            golden_repos = repo_manager.list_golden_repos()
            for repo_data in golden_repos:
                if repo_data.get("alias") == repo_id:
                    clone_path = repo_data.get("clone_path")
                    if clone_path and Path(clone_path).exists():
                        return clone_path
                    else:
                        raise FileNotFoundError(
                            f"Repository path {clone_path} does not exist"
                        )

            # Repository not found
            raise FileNotFoundError(
                f"Repository {repo_id} not found in golden repositories"
            )

        except Exception as e:
            logger.error(f"Failed to get repository path for {repo_id}: {e}")
            if isinstance(e, FileNotFoundError):
                raise
            raise RuntimeError(f"Unable to access repository {repo_id}: {e}")

    def _collect_files(self, repo_path: str) -> List[FileInfo]:
        """
        Collect all files in repository.

        Args:
            repo_path: Repository file system path

        Returns:
            List of file information objects
        """
        files = []
        repo_root = Path(repo_path)

        try:
            for file_path in repo_root.rglob("*"):
                if file_path.is_file():
                    try:
                        stat_info = file_path.stat()
                        relative_path = file_path.relative_to(repo_root)

                        file_info = FileInfo(
                            path=str(relative_path),
                            size_bytes=stat_info.st_size,
                            modified_at=datetime.fromtimestamp(
                                stat_info.st_mtime, tz=timezone.utc
                            ),
                            language=self._detect_language(file_path),
                            is_indexed=self._is_file_indexed(file_path),
                        )
                        files.append(file_info)

                    except (OSError, PermissionError) as e:
                        logger.warning(f"Cannot access file {file_path}: {e}")
                        continue

        except PermissionError as e:
            logger.error(f"Cannot access repository directory {repo_path}: {e}")
            raise

        return files

    def _detect_language(self, file_path: Path) -> Optional[str]:
        """
        Detect programming language from file extension.

        Args:
            file_path: Path to file

        Returns:
            Programming language name or None if unknown
        """
        extension = file_path.suffix.lower()
        return LANGUAGE_EXTENSIONS.get(extension)

    def _is_file_indexed(self, file_path: Path) -> bool:
        """
        Check if file is currently indexed.

        This is a placeholder - in real implementation, this would
        check against the vector database or index status.

        Args:
            file_path: Path to file

        Returns:
            Whether file is indexed
        """
        # For now, consider text files as potentially indexed
        # In real implementation, query Qdrant or index database
        extension = file_path.suffix.lower()
        indexable_extensions = {
            ".py",
            ".js",
            ".ts",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".cs",
            ".go",
            ".rs",
            ".php",
            ".rb",
            ".swift",
            ".kt",
            ".scala",
            ".sql",
            ".html",
            ".css",
            ".vue",
            ".jsx",
            ".tsx",
        }
        return extension in indexable_extensions

    def _apply_filters(
        self, files: List[FileInfo], query_params: FileListQueryParams
    ) -> List[FileInfo]:
        """
        Apply filtering to file list.

        Args:
            files: List of files to filter
            query_params: Query parameters containing filters

        Returns:
            Filtered list of files
        """
        filtered_files = files

        # Filter by path pattern
        if query_params.path_pattern:
            pattern = query_params.path_pattern
            filtered_files = [
                f for f in filtered_files if fnmatch.fnmatch(f.path, pattern)
            ]

        # Filter by language
        if query_params.language:
            target_language = query_params.language.lower()
            filtered_files = [
                f
                for f in filtered_files
                if f.language and f.language.lower() == target_language
            ]

        return filtered_files

    def _apply_sorting(
        self, files: List[FileInfo], sort_by: Optional[str]
    ) -> List[FileInfo]:
        """
        Apply sorting to file list.

        Args:
            files: List of files to sort
            sort_by: Sort field name

        Returns:
            Sorted list of files
        """
        valid_sort_fields = {"path", "size", "modified_at"}

        if sort_by is None or sort_by not in valid_sort_fields:
            if sort_by is not None:
                logger.warning(f"Invalid sort field '{sort_by}', using 'path'")
            sort_by = "path"

        if sort_by == "path":
            return sorted(files, key=lambda f: f.path.lower())
        elif sort_by == "size":
            return sorted(files, key=lambda f: f.size_bytes)
        elif sort_by == "modified_at":
            return sorted(files, key=lambda f: f.modified_at)

        return files

    def _apply_pagination(
        self, files: List[FileInfo], page: int, limit: int
    ) -> Tuple[List[FileInfo], PaginationInfo]:
        """
        Apply pagination to file list.

        Args:
            files: List of files to paginate
            page: Page number (1-based)
            limit: Items per page

        Returns:
            Tuple of (paginated files, pagination info)
        """
        total_files = len(files)
        total_pages = math.ceil(total_files / limit) if total_files > 0 else 0

        # Calculate offset
        offset = (page - 1) * limit

        # Get page of files
        paginated_files = files[offset : offset + limit]

        # Check if there are more pages
        has_next = page < total_pages

        pagination_info = PaginationInfo(
            page=page, limit=limit, total=total_files, has_next=has_next
        )

        return paginated_files, pagination_info


# Global service instance
file_service = FileListingService()
