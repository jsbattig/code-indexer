"""
File Listing Service.

Provides real file listing operations following CLAUDE.md Foundation #1: No mocks.
All operations use real file system operations with proper pagination and filtering.
"""

import os
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any, Set
from datetime import datetime, timezone
import logging
import fnmatch
import math

import pathspec

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

    # Directories that are always excluded from file listings
    ALWAYS_EXCLUDED_DIRS: Set[str] = {".code-indexer", ".git"}

    def __init__(self):
        """Initialize the file listing service."""
        # Import here to avoid circular imports
        from ..repositories.activated_repo_manager import ActivatedRepoManager

        self.activated_repo_manager = ActivatedRepoManager()

    def list_files(
        self, repo_id: str, username: str, query_params: FileListQueryParams
    ) -> FileListResponse:
        """
        List files in repository with pagination and filtering.

        Args:
            repo_id: Repository identifier (user_alias)
            username: Username owning the activated repository
            query_params: Query parameters for filtering and pagination

        Returns:
            File list response with pagination

        Raises:
            FileNotFoundError: If repository doesn't exist
            PermissionError: If repository access denied
            ValueError: If query parameters are invalid
        """
        repo_path = self._get_repository_path(repo_id, username)

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

    def _get_repository_path(self, repo_id: str, username: str) -> str:
        """
        Get file system path for repository from activated repositories.

        CRITICAL FIX: Searches activated repositories (user workspace) instead of
        golden repositories (shared source).

        Args:
            repo_id: Repository identifier (user_alias)
            username: Username owning the activated repository

        Returns:
            Real file system path to activated repository

        Raises:
            RuntimeError: If database lookup fails
            FileNotFoundError: If repository not found
        """
        try:
            # Use ActivatedRepositoryManager to search user's workspace
            activated_path = self.activated_repo_manager.get_activated_repo_path(
                username=username, user_alias=repo_id
            )

            # Verify path exists
            if not activated_path or not Path(activated_path).exists():
                raise FileNotFoundError(
                    f"Repository '{repo_id}' not found for user '{username}'"
                )

            return activated_path

        except Exception as e:
            logger.error(f"Failed to get repository path for {repo_id}/{username}: {e}")
            if isinstance(e, FileNotFoundError):
                raise
            raise RuntimeError(f"Unable to access repository {repo_id}: {e}")

    def _collect_files(self, repo_path: str) -> List[FileInfo]:
        """
        Collect all files in repository, excluding system directories and gitignored files.

        Excludes:
        - .code-indexer/ directory (CIDX index storage)
        - .git/ directory (Git internals)
        - Files matching .gitignore patterns (if .gitignore exists)

        Args:
            repo_path: Repository file system path

        Returns:
            List of file information objects
        """
        files = []
        repo_root = Path(repo_path)

        # Load .gitignore patterns if present
        gitignore_spec = self._load_gitignore_spec(repo_root)

        try:
            for file_path in repo_root.rglob("*"):
                if file_path.is_file():
                    try:
                        relative_path = file_path.relative_to(repo_root)
                        relative_path_str = str(relative_path)

                        # Skip files in always-excluded directories
                        if self._is_in_excluded_dir(relative_path):
                            continue

                        # Skip files matching .gitignore patterns
                        if gitignore_spec and gitignore_spec.match_file(
                            relative_path_str
                        ):
                            continue

                        stat_info = file_path.stat()

                        file_info = FileInfo(
                            path=relative_path_str,
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

    def _is_in_excluded_dir(self, relative_path: Path) -> bool:
        """
        Check if a file path is within an excluded directory.

        Args:
            relative_path: Path relative to repository root

        Returns:
            True if path is in an excluded directory
        """
        # Check each part of the path against excluded directories
        for part in relative_path.parts:
            if part in self.ALWAYS_EXCLUDED_DIRS:
                return True
        return False

    def _load_gitignore_spec(self, repo_root: Path) -> Optional[pathspec.PathSpec]:
        """
        Load and parse .gitignore file if present.

        Args:
            repo_root: Repository root directory

        Returns:
            PathSpec object for matching gitignore patterns, or None if no .gitignore
        """
        gitignore_path = repo_root / ".gitignore"

        if not gitignore_path.exists():
            return None

        try:
            with open(gitignore_path, "r", encoding="utf-8") as f:
                gitignore_content = f.read()

            # Parse gitignore patterns using pathspec library
            return pathspec.PathSpec.from_lines(
                "gitwildmatch", gitignore_content.splitlines()
            )
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"Failed to read .gitignore at {gitignore_path}: {e}")
            return None

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
        # In real implementation, query vector store or index database
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

    def get_file_content(
        self, repository_alias: str, file_path: str, username: str
    ) -> Dict[str, Any]:
        """Get content of a specific file from repository."""
        repo_path = self._get_repository_path(repository_alias, username)
        full_file_path = Path(repo_path) / file_path
        full_file_path = full_file_path.resolve()
        repo_root = Path(repo_path).resolve()
        if not str(full_file_path).startswith(str(repo_root)):
            raise PermissionError("Access denied")
        if not full_file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if not full_file_path.is_file():
            raise FileNotFoundError(f"Not a file: {file_path}")
        with open(full_file_path, "r", encoding="utf-8") as f:
            content = f.read()
        stat_info = full_file_path.stat()
        metadata = {
            "size": stat_info.st_size,
            "modified_at": datetime.fromtimestamp(
                stat_info.st_mtime, tz=timezone.utc
            ).isoformat(),
            "language": self._detect_language(full_file_path),
            "path": file_path,
        }
        return {"content": content, "metadata": metadata}


# Global service instance
file_service = FileListingService()
