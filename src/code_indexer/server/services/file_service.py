"""
File Listing Service.

Provides real file listing operations following CLAUDE.md Foundation #1: No mocks.
All operations use real file system operations with proper pagination and filtering.
"""

from code_indexer.server.middleware.correlation import get_correlation_id

import os
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any, Set, cast
from datetime import datetime, timezone
import logging
import math

import pathspec

from ..models.api_models import (
    FileListResponse,
    FileInfo,
    PaginationInfo,
    FileListQueryParams,
)
from ..services.file_content_limits_config_manager import FileContentLimitsConfigManager

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

    # Story #686: Line-based default chunking limits
    # Applied IN ADDITION to token limits - the stricter limit wins
    DEFAULT_MAX_LINES: int = 500  # Default limit when no explicit limit provided
    MAX_ALLOWED_LIMIT: int = 5000  # Maximum limit client can request

    def __init__(self):
        """Initialize the file listing service."""
        # Import here to avoid circular imports
        from ..repositories.activated_repo_manager import ActivatedRepoManager

        self.activated_repo_manager = ActivatedRepoManager()
        self._config_manager = None

    def _get_config_manager(self):
        """Get config manager instance (lazy initialization)."""
        if not hasattr(self, "_config_manager") or self._config_manager is None:
            self._config_manager = FileContentLimitsConfigManager.get_instance()
        return self._config_manager

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

    def list_files_by_path(
        self, repo_path: str, query_params: FileListQueryParams
    ) -> FileListResponse:
        """
        List files from a direct filesystem path (for global repos).

        Unlike list_files() which looks up activated repos by alias,
        this method accepts a direct path for global repository browsing.

        Args:
            repo_path: Direct filesystem path to repository
            query_params: Query parameters for filtering and pagination

        Returns:
            File list response with pagination

        Raises:
            FileNotFoundError: If path doesn't exist
        """
        if not os.path.exists(repo_path):
            raise FileNotFoundError(f"Path {repo_path} not found")

        all_files = self._collect_files(repo_path)
        filtered_files = self._apply_filters(all_files, query_params)
        sorted_files = self._apply_sorting(filtered_files, query_params.sort_by)
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

            return cast(str, activated_path)

        except Exception as e:
            logger.error(
                f"Failed to get repository path for {repo_id}/{username}: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
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
                        logger.warning(
                            f"Cannot access file {file_path}: {e}",
                            extra={"correlation_id": get_correlation_id()},
                        )
                        continue

        except PermissionError as e:
            logger.error(
                f"Cannot access repository directory {repo_path}: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
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
            logger.warning(
                f"Failed to read .gitignore at {gitignore_path}: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
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
            # Use pathspec for proper ** glob support (gitignore-style)
            # pathspec treats ** as "this directory and all subdirectories"
            # while fnmatch treats ** as requiring 1+ subdirectories
            spec = pathspec.PathSpec.from_lines("gitwildmatch", [pattern])
            filtered_files = [f for f in filtered_files if spec.match_file(f.path)]

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
                logger.warning(
                    f"Invalid sort field '{sort_by}', using 'path'",
                    extra={"correlation_id": get_correlation_id()},
                )
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

    def _enforce_token_limits(
        self, content: str, total_lines: int, effective_offset: int
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Enforce token limits on content and generate metadata.

        Args:
            content: Content to potentially truncate
            total_lines: Total lines in the file
            effective_offset: Starting line number (1-indexed)

        Returns:
            Tuple of (possibly truncated content, metadata dict with token info)
        """
        config = self._get_config_manager().get_config()
        max_chars = config.max_chars_per_request

        # Calculate estimated tokens from content length
        estimated_tokens = len(content) // config.chars_per_token

        # Check if truncation needed
        truncated = False
        truncated_at_line = None
        actual_content = content

        if len(content) > max_chars:
            # Truncate content to fit token budget
            actual_content = content[:max_chars]
            truncated = True

            # Calculate which line we truncated at
            lines_before_truncation = actual_content.count("\n")
            truncated_at_line = effective_offset + lines_before_truncation

            # Recalculate estimated tokens for truncated content
            estimated_tokens = len(actual_content) // config.chars_per_token

        # Determine if pagination required
        # Formula: last_returned_line = effective_offset + returned_lines - 1
        # Has more if last_returned_line < total_lines, which simplifies to:
        # effective_offset + returned_lines - 1 < total_lines
        # OR: effective_offset + returned_lines <= total_lines
        returned_lines = actual_content.count("\n") + (
            1 if actual_content and not actual_content.endswith("\n") else 0
        )
        last_returned_line = effective_offset + returned_lines - 1
        requires_pagination = truncated or (last_returned_line < total_lines)

        # Generate pagination hint
        pagination_hint = ""
        if requires_pagination:
            if truncated:
                assert (
                    truncated_at_line is not None
                ), "truncated_at_line must be set when truncated=True"
                pagination_hint = f"Content truncated at line {truncated_at_line} due to token limit. Use offset={truncated_at_line + 1} to continue reading."
            else:
                next_offset = effective_offset + returned_lines
                pagination_hint = f"More content available. Use offset={next_offset} to continue reading."

        # Build token enforcement metadata
        token_metadata = {
            "estimated_tokens": estimated_tokens,
            "max_tokens_per_request": config.max_tokens_per_request,
            "truncated": truncated,
            "truncated_at_line": truncated_at_line,
            "requires_pagination": requires_pagination,
            "pagination_hint": pagination_hint if requires_pagination else None,
        }

        return actual_content, token_metadata

    def get_file_content(
        self,
        repository_alias: str,
        file_path: str,
        username: str,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get content of a specific file from repository with optional pagination.

        CRITICAL BEHAVIOR CHANGE: When offset and limit are both None, returns FIRST CHUNK ONLY
        (not entire file) to prevent LLM context window exhaustion. Token limits are enforced
        in all cases.

        Args:
            repository_alias: Repository user alias
            file_path: Relative path to file within repository
            username: Username owning the repository
            offset: 1-indexed line number to start reading from (default: 1)
            limit: Maximum number of lines to return (default: None = token-limited chunk)

        Returns:
            Dict with 'content' and 'metadata' keys. Metadata includes pagination info:
            - total_lines: Total lines in file
            - returned_lines: Lines returned in this response
            - offset: Starting line number (1-indexed)
            - limit: Limit used (None if unlimited)
            - has_more: True if more lines exist beyond returned range
            - estimated_tokens: Estimated token count of returned content
            - max_tokens_per_request: Current token limit from config
            - truncated: True if content was truncated due to token limit
            - truncated_at_line: Line number where truncation occurred (if truncated)
            - requires_pagination: True if file has more content to read
            - pagination_hint: Helpful message for navigating large files
        """
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

        # Read all lines for pagination
        with open(full_file_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)

        # CRITICAL: Default behavior changed - return first chunk only (not entire file)
        # Apply offset (convert 1-indexed to 0-indexed for slicing)
        effective_offset = offset if offset is not None else 1
        start_index = max(0, effective_offset - 1)

        # Story #686: Apply line-based limits IN ADDITION to token limits
        # The stricter of (line limit, token limit) wins
        if limit is None:
            # No user-specified limit: apply default max lines
            effective_limit = self.DEFAULT_MAX_LINES
        else:
            # User specified limit: cap at max allowed
            effective_limit = min(limit, self.MAX_ALLOWED_LIMIT)

        # Apply the effective limit
        end_index = start_index + effective_limit
        selected_lines = all_lines[start_index:end_index]

        # Build content string
        content = "".join(selected_lines)

        # Apply token enforcement (may truncate content further)
        enforced_content, token_metadata = self._enforce_token_limits(
            content, total_lines, effective_offset
        )

        # Calculate returned_lines from enforced content
        returned_lines = enforced_content.count("\n") + (
            1 if enforced_content and not enforced_content.endswith("\n") else 0
        )

        # Calculate has_more: true if more content exists after returned lines
        last_returned_line = effective_offset + returned_lines - 1
        has_more = last_returned_line < total_lines

        # Story #686: Calculate next_offset for pagination
        next_offset = effective_offset + returned_lines if has_more else None

        # Build metadata with pagination info
        stat_info = full_file_path.stat()
        metadata = {
            "size": stat_info.st_size,
            "modified_at": datetime.fromtimestamp(
                stat_info.st_mtime, tz=timezone.utc
            ).isoformat(),
            "language": self._detect_language(full_file_path),
            "path": file_path,
            # Original pagination metadata
            "total_lines": total_lines,
            "returned_lines": returned_lines,
            "offset": effective_offset,
            "limit": limit,  # Keep original limit for client visibility
            "has_more": has_more,
            # Story #686: Add next_offset for easy pagination
            "next_offset": next_offset,
        }

        # Merge token enforcement metadata
        metadata.update(token_metadata)

        return {"content": enforced_content, "metadata": metadata}

    def get_file_content_by_path(
        self,
        repo_path: str,
        file_path: str,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get content of a specific file from a direct filesystem path (for global repos).

        Unlike get_file_content() which looks up activated repos by alias,
        this method accepts a direct path for global repository file access.

        CRITICAL BEHAVIOR CHANGE: When offset and limit are both None, returns FIRST CHUNK ONLY
        (not entire file) to prevent LLM context window exhaustion. Token limits are enforced
        in all cases.

        Args:
            repo_path: Direct filesystem path to repository root
            file_path: Relative path to file within repository
            offset: 1-indexed line number to start reading from (default: 1)
            limit: Maximum number of lines to return (default: None = token-limited chunk)

        Returns:
            Dict with 'content' and 'metadata' keys. Metadata includes pagination info:
            - total_lines: Total lines in file
            - returned_lines: Lines returned in this response
            - offset: Starting line number (1-indexed)
            - limit: Limit used (None if unlimited)
            - has_more: True if more lines exist beyond returned range
            - estimated_tokens: Estimated token count of returned content
            - max_tokens_per_request: Current token limit from config
            - truncated: True if content was truncated due to token limit
            - truncated_at_line: Line number where truncation occurred (if truncated)
            - requires_pagination: True if file has more content to read
            - pagination_hint: Helpful message for navigating large files

        Raises:
            PermissionError: If path traversal attempted
            FileNotFoundError: If file doesn't exist
        """
        full_file_path = Path(repo_path) / file_path
        full_file_path = full_file_path.resolve()
        repo_root = Path(repo_path).resolve()
        if not str(full_file_path).startswith(str(repo_root)):
            raise PermissionError("Access denied")
        if not full_file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if not full_file_path.is_file():
            raise FileNotFoundError(f"Not a file: {file_path}")

        # Read all lines for pagination
        with open(full_file_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)

        # CRITICAL: Default behavior changed - return first chunk only (not entire file)
        # Apply offset (convert 1-indexed to 0-indexed for slicing)
        effective_offset = offset if offset is not None else 1
        start_index = max(0, effective_offset - 1)

        # Story #686: Apply line-based limits IN ADDITION to token limits
        # The stricter of (line limit, token limit) wins
        if limit is None:
            # No user-specified limit: apply default max lines
            effective_limit = self.DEFAULT_MAX_LINES
        else:
            # User specified limit: cap at max allowed
            effective_limit = min(limit, self.MAX_ALLOWED_LIMIT)

        # Apply the effective limit
        end_index = start_index + effective_limit
        selected_lines = all_lines[start_index:end_index]

        # Build content string
        content = "".join(selected_lines)

        # Apply token enforcement (may truncate content further)
        enforced_content, token_metadata = self._enforce_token_limits(
            content, total_lines, effective_offset
        )

        # Calculate returned_lines from enforced content
        returned_lines = enforced_content.count("\n") + (
            1 if enforced_content and not enforced_content.endswith("\n") else 0
        )

        # Calculate has_more: true if more content exists after returned lines
        last_returned_line = effective_offset + returned_lines - 1
        has_more = last_returned_line < total_lines

        # Story #686: Calculate next_offset for pagination
        next_offset = effective_offset + returned_lines if has_more else None

        # Build metadata with pagination info
        stat_info = full_file_path.stat()
        metadata = {
            "size": stat_info.st_size,
            "modified_at": datetime.fromtimestamp(
                stat_info.st_mtime, tz=timezone.utc
            ).isoformat(),
            "language": self._detect_language(full_file_path),
            "path": file_path,
            # Original pagination metadata
            "total_lines": total_lines,
            "returned_lines": returned_lines,
            "offset": effective_offset,
            "limit": limit,  # Keep original limit for client visibility
            "has_more": has_more,
            # Story #686: Add next_offset for easy pagination
            "next_offset": next_offset,
        }

        # Merge token enforcement metadata
        metadata.update(token_metadata)

        return {"content": enforced_content, "metadata": metadata}


# Global service instance
file_service = FileListingService()
