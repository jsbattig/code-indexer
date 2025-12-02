"""
Semantic Query Manager for CIDX Server.

Provides semantic search functionality for activated repositories with user isolation,
background job integration, and proper resource management.
"""

import json
import logging
import re
import io
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass

from ..repositories.activated_repo_manager import ActivatedRepoManager
from ..repositories.background_jobs import BackgroundJobManager
from ...search.query import SearchResult
from ...proxy.config_manager import ProxyConfigManager
from ...proxy.cli_integration import _execute_query


class SemanticQueryError(Exception):
    """Base exception for semantic query operations."""

    pass


@dataclass
class QueryResult:
    """Individual query result with standardized format.

    For composite repositories:
        - repository_alias: The composite repository name (parent)
        - source_repo: Which component repo this result came from
        - file_path: Relative path within source_repo

    For single repositories:
        - repository_alias: The repository name
        - source_repo: None (not a composite)
        - file_path: Relative path within repository
    """

    file_path: str
    line_number: int
    code_snippet: str
    similarity_score: float
    repository_alias: str
    source_repo: Optional[str] = None  # Which component repo (for composite repos)

    @classmethod
    def from_search_result(
        cls, search_result: SearchResult, repository_alias: str
    ) -> "QueryResult":
        """Create QueryResult from SearchResult dataclass."""
        return cls(
            file_path=search_result.file_path,
            line_number=1,  # SearchResult doesn't have line numbers, default to 1
            code_snippet=search_result.content,
            similarity_score=search_result.score,
            repository_alias=repository_alias,
            source_repo=None,  # Single repository, no source_repo
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "code_snippet": self.code_snippet,
            "similarity_score": self.similarity_score,
            "repository_alias": self.repository_alias,
            "source_repo": self.source_repo,
        }


@dataclass
class QueryMetadata:
    """Metadata about query execution."""

    query_text: str
    execution_time_ms: int
    repositories_searched: int
    timeout_occurred: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "query_text": self.query_text,
            "execution_time_ms": self.execution_time_ms,
            "repositories_searched": self.repositories_searched,
            "timeout_occurred": self.timeout_occurred,
        }


class SemanticQueryManager:
    """
    Manages semantic queries for CIDX server users.

    Provides semantic search capabilities with user isolation, background job integration,
    and proper resource management. Integrates with existing cidx query functionality.
    """

    def __init__(
        self,
        data_dir: Optional[str] = None,
        activated_repo_manager: Optional[ActivatedRepoManager] = None,
        background_job_manager: Optional[BackgroundJobManager] = None,
        query_timeout_seconds: int = 30,
        max_concurrent_queries_per_user: int = 5,
        max_results_per_query: int = 100,
    ):
        """
        Initialize semantic query manager.

        Args:
            data_dir: Data directory path (defaults to ~/.cidx-server/data)
            activated_repo_manager: Activated repo manager instance
            background_job_manager: Background job manager instance
            query_timeout_seconds: Query timeout in seconds
            max_concurrent_queries_per_user: Maximum concurrent queries per user
            max_results_per_query: Maximum results per query
        """
        if data_dir:
            self.data_dir = data_dir
        else:
            home_dir = Path.home()
            self.data_dir = str(home_dir / ".cidx-server" / "data")

        self.activated_repo_manager = activated_repo_manager or ActivatedRepoManager(
            data_dir
        )
        self.background_job_manager = background_job_manager or BackgroundJobManager()

        self.query_timeout_seconds = query_timeout_seconds
        self.max_concurrent_queries_per_user = max_concurrent_queries_per_user
        self.max_results_per_query = max_results_per_query

        # Set up logging
        self.logger = logging.getLogger(__name__)

        # Track concurrent queries per user (in production this would need persistence)
        self._active_queries_per_user: Dict[str, int] = {}

    def _is_composite_repository(self, repo_path: Path) -> bool:
        """
        Check if repository is in proxy mode (composite).

        Args:
            repo_path: Path to the repository

        Returns:
            True if repository is composite (proxy_mode=true), False otherwise

        Raises:
            json.JSONDecodeError: If config file contains invalid JSON
        """
        config_file = repo_path / ".code-indexer" / "config.json"
        if not config_file.exists():
            self.logger.debug(
                f"Config file not found at {config_file}, defaulting to single repository mode"
            )
            return False

        try:
            config = json.loads(config_file.read_text())
            is_composite = bool(config.get("proxy_mode", False))
            self.logger.debug(
                f"Repository at {repo_path} detected as {'composite' if is_composite else 'single'}"
            )
            return is_composite
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in config file {config_file}: {str(e)}")
            raise

    async def search(
        self,
        repo_path: Path,
        query: str,
        limit: int = 10,
        min_score: Optional[float] = None,
        file_extensions: Optional[List[str]] = None,
        **kwargs,
    ) -> List[QueryResult]:
        """
        Main entry point for semantic search - routes to appropriate handler.

        Args:
            repo_path: Path to the repository
            query: Query text
            limit: Maximum results to return
            min_score: Minimum similarity score threshold
            file_extensions: List of file extensions to filter results
            **kwargs: Additional keyword arguments

        Returns:
            List of QueryResult objects

        Raises:
            SemanticQueryError: If routing or search fails
        """
        try:
            if self._is_composite_repository(repo_path):
                self.logger.info(
                    f"Routing query to composite handler for repository: {repo_path}"
                )
                return await self.search_composite(
                    repo_path,
                    query,
                    limit=limit,
                    min_score=min_score,
                    file_extensions=file_extensions,
                    **kwargs,
                )

            self.logger.info(
                f"Routing query to single repository handler for: {repo_path}"
            )
            return await self.search_single(
                repo_path,
                query,
                limit=limit,
                min_score=min_score,
                file_extensions=file_extensions,
                **kwargs,
            )
        except Exception as e:
            self.logger.error(
                f"Search routing failed for repository {repo_path}: {str(e)}"
            )
            raise

    async def search_single(
        self,
        repo_path: Path,
        query: str,
        limit: int = 10,
        min_score: Optional[float] = None,
        file_extensions: Optional[List[str]] = None,
        repository_alias: Optional[str] = None,
        **kwargs,
    ) -> List[QueryResult]:
        """
        Search a single repository (existing logic).

        Args:
            repo_path: Path to the repository
            query: Query text
            limit: Result limit
            min_score: Score threshold
            file_extensions: List of file extensions to filter results
            repository_alias: Repository alias for result annotation (defaults to repo name)
            **kwargs: Additional keyword arguments

        Returns:
            List of QueryResult objects from this repository
        """
        # If no alias provided, use the repository directory name
        if repository_alias is None:
            repository_alias = repo_path.name

        # This is the existing _search_single_repository logic
        return self._search_single_repository(
            str(repo_path), repository_alias, query, limit, min_score, file_extensions
        )

    async def search_composite(
        self,
        repo_path: Path,
        query: str,
        limit: int = 10,
        min_score: Optional[float] = None,
        file_extensions: Optional[List[str]] = None,
        **kwargs,
    ) -> List[QueryResult]:
        """
        Search a composite repository using CLI's _execute_query.

        This is a thin wrapper around the CLI's existing parallel query
        execution infrastructure. It converts server parameters to CLI args,
        calls _execute_query, and parses the output.

        Args:
            repo_path: Path to the composite repository
            query: Query text
            limit: Maximum results to return
            min_score: Minimum similarity score threshold
            file_extensions: List of file extensions to filter results
            **kwargs: Additional keyword arguments (language, path, accuracy)

        Returns:
            List of QueryResult objects from all subrepos

        Raises:
            Exception: If CLI execution or parsing fails
        """
        self.logger.info(
            f"Composite repository search for {repo_path} using CLI integration"
        )

        # Execute query using CLI integration
        return self._execute_cli_query(
            repo_path=repo_path,
            query=query,
            limit=limit,
            min_score=min_score,
            language=kwargs.get("language"),
            path=kwargs.get("path_filter"),
            accuracy=kwargs.get("accuracy"),
            exclude_language=kwargs.get("exclude_language"),
            exclude_path=kwargs.get("exclude_path"),
        )

    def query_user_repositories(
        self,
        username: str,
        query_text: str,
        repository_alias: Optional[str] = None,
        limit: int = 10,
        min_score: Optional[float] = None,
        file_extensions: Optional[List[str]] = None,
        language: Optional[str] = None,
        exclude_language: Optional[str] = None,
        path_filter: Optional[str] = None,
        exclude_path: Optional[str] = None,
        accuracy: Optional[str] = None,
        # Search mode parameter (Story #503 - FTS Bug Fix)
        search_mode: str = "semantic",
        # Temporal query parameters (Story #446)
        time_range: Optional[str] = None,
        time_range_all: bool = False,
        at_commit: Optional[str] = None,
        include_removed: bool = False,
        show_evolution: bool = False,
        evolution_limit: Optional[int] = None,
        # FTS-specific parameters (Story #503 Phase 2)
        case_sensitive: bool = False,
        fuzzy: bool = False,
        edit_distance: int = 0,
        snippet_lines: int = 5,
        regex: bool = False,
        # Temporal filtering parameters (Story #503 Phase 3)
        diff_type: Optional[Union[str, List[str]]] = None,
        author: Optional[str] = None,
        chunk_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Perform semantic query on user's activated repositories.

        Args:
            username: Username performing the query
            query_text: Natural language query text
            repository_alias: Specific repository to query (optional)
            limit: Maximum results to return
            min_score: Minimum similarity score threshold
            file_extensions: List of file extensions to filter results (e.g., ['.py', '.js'])
            language: Filter by programming language (e.g., 'python', 'js', 'typescript')
            exclude_language: Exclude files of specified language
            path_filter: Filter by file path pattern using glob syntax (e.g., '*/tests/*')
            exclude_path: Exclude files matching path pattern (e.g., '*/node_modules/*')
            accuracy: Search accuracy profile ('fast', 'balanced', 'high')
            search_mode: Search mode - 'semantic' (default), 'fts', or 'hybrid'
            time_range: Time range filter for temporal queries (format: YYYY-MM-DD..YYYY-MM-DD)
            time_range_all: Query across all git history without time range limit
            at_commit: Query code at specific commit hash or ref
            include_removed: Include files removed from current HEAD
            show_evolution: Include code evolution timeline with diffs
            evolution_limit: Limit evolution entries (user-controlled)
            case_sensitive: Enable case-sensitive FTS matching (FTS-only)
            fuzzy: Enable fuzzy matching with edit distance 1 (FTS-only, incompatible with regex)
            edit_distance: Fuzzy match tolerance level 0-3 (FTS-only)
            snippet_lines: Context lines around FTS matches 0-50 (FTS-only)
            regex: Interpret query as regex pattern (FTS-only, incompatible with fuzzy)

        Returns:
            Dictionary with results, total_results, and query_metadata

        Raises:
            SemanticQueryError: If query validation fails or repositories not found
        """
        # Validate query parameters
        self._validate_query_parameters(query_text, limit, min_score)

        # Get user's activated repositories
        user_repos = self.activated_repo_manager.list_activated_repositories(username)

        if not user_repos:
            raise SemanticQueryError(
                f"No activated repositories found for user '{username}'"
            )

        # Filter to specific repository if requested
        if repository_alias:
            user_repos = [
                repo for repo in user_repos if repo["user_alias"] == repository_alias
            ]
            if not user_repos:
                raise SemanticQueryError(
                    f"Repository '{repository_alias}' not found for user '{username}'"
                )

        # Perform the search
        start_time = time.time()
        try:
            results = self._perform_search(
                username,
                user_repos,
                query_text,
                limit,
                min_score,
                file_extensions,
                language,
                exclude_language,
                path_filter,
                exclude_path,
                accuracy,
                # Search mode (Story #503 - FTS Bug Fix)
                search_mode=search_mode,
                # Temporal parameters (Story #446)
                time_range=time_range,
                time_range_all=time_range_all,
                at_commit=at_commit,
                include_removed=include_removed,
                show_evolution=show_evolution,
                evolution_limit=evolution_limit,
                # FTS-specific parameters (Story #503 Phase 2)
                case_sensitive=case_sensitive,
                fuzzy=fuzzy,
                edit_distance=edit_distance,
                snippet_lines=snippet_lines,
                regex=regex,
                # Temporal filtering parameters (Story #503 Phase 3)
                diff_type=diff_type,
                author=author,
                chunk_type=chunk_type,
            )
            execution_time_ms = int((time.time() - start_time) * 1000)
            timeout_occurred = False
        except TimeoutError as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            timeout_occurred = True
            raise SemanticQueryError(f"Query timed out: {str(e)}")
        except Exception as e:
            # Handle other exceptions that might indicate timeout or search failures
            execution_time_ms = int((time.time() - start_time) * 1000)
            if "timeout" in str(e).lower():
                raise SemanticQueryError(f"Query timed out: {str(e)}")
            raise SemanticQueryError(f"Search failed: {str(e)}")

        # Create metadata
        metadata = QueryMetadata(
            query_text=query_text,
            execution_time_ms=execution_time_ms,
            repositories_searched=len(user_repos),
            timeout_occurred=timeout_occurred,
        )

        # Handle case where mocked _perform_search returns dict instead of QueryResult list
        if isinstance(results, dict) and "results" in results:
            return results

        # Ensure results are QueryResult objects for normal list responses
        if results and len(results) > 0 and not isinstance(results[0], QueryResult):
            # This shouldn't happen in normal operation, but handle gracefully
            self.logger.warning("Unexpected result format in query response")

        # Check if temporal parameters were used but no results (graceful fallback)
        has_temporal_params = any(
            [time_range, time_range_all, at_commit, show_evolution]
        )
        warning_message = None
        if has_temporal_params and len(results) == 0:
            warning_message = (
                "Temporal index not available. Showing results from current code only. "
                "Build temporal index with 'cidx index --index-commits' to enable temporal queries."
            )

        # Build response with temporal context in results
        response_results = []
        for r in results:
            result_dict = r.to_dict()
            # Add temporal_context if present
            if hasattr(r, "_temporal_context"):
                result_dict["temporal_context"] = getattr(r, "_temporal_context")
            response_results.append(result_dict)

        response = {
            "results": response_results,
            "total_results": len(results),
            "query_metadata": metadata.to_dict(),
        }

        # Add warning if temporal fallback occurred
        if warning_message:
            response["warning"] = warning_message

        return response

    def submit_query_job(
        self,
        username: str,
        query_text: str,
        repository_alias: Optional[str] = None,
        limit: int = 10,
        min_score: Optional[float] = None,
        file_extensions: Optional[List[str]] = None,
    ) -> str:
        """
        Submit a semantic query as a background job.

        Args:
            username: Username performing the query
            query_text: Natural language query text
            repository_alias: Specific repository to query (optional)
            limit: Maximum results to return
            min_score: Minimum similarity score threshold
            file_extensions: List of file extensions to filter results (e.g., ['.py', '.js'])

        Returns:
            Job ID for tracking query progress
        """
        # Submit background job
        job_id = self.background_job_manager.submit_job(
            "semantic_query",
            self.query_user_repositories,  # type: ignore[arg-type]
            username=username,
            query_text=query_text,
            repository_alias=repository_alias,
            limit=limit,
            min_score=min_score,
            file_extensions=file_extensions,
            submitter_username=username,
        )

        self.logger.info(f"Semantic query job {job_id} submitted for user {username}")
        return job_id

    def get_query_job_status(
        self, job_id: str, username: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get status of a background query job with user isolation.

        Args:
            job_id: Job ID to check status for
            username: Username for job authorization

        Returns:
            Job status dictionary or None if job not found or not authorized
        """
        return self.background_job_manager.get_job_status(job_id, username)

    def _validate_query_parameters(
        self, query_text: str, limit: int, min_score: Optional[float]
    ) -> None:
        """
        Validate query parameters.

        Args:
            query_text: Query text to validate
            limit: Result limit to validate
            min_score: Score threshold to validate

        Raises:
            SemanticQueryError: If parameters are invalid
        """
        if not query_text or not query_text.strip():
            raise SemanticQueryError("Query text cannot be empty")

        if limit <= 0:
            raise SemanticQueryError("Limit must be greater than 0")

        if min_score is not None and (min_score < 0.0 or min_score > 1.0):
            raise SemanticQueryError("Min score must be between 0.0 and 1.0")

    def _perform_search(
        self,
        username: str,
        user_repos: List[Dict[str, Any]],
        query_text: str,
        limit: int,
        min_score: Optional[float],
        file_extensions: Optional[List[str]],
        language: Optional[str] = None,
        exclude_language: Optional[str] = None,
        path_filter: Optional[str] = None,
        exclude_path: Optional[str] = None,
        accuracy: Optional[str] = None,
        # Search mode parameter (Story #503 - FTS Bug Fix)
        search_mode: str = "semantic",
        # Temporal parameters (Story #446)
        time_range: Optional[str] = None,
        time_range_all: bool = False,
        at_commit: Optional[str] = None,
        include_removed: bool = False,
        show_evolution: bool = False,
        evolution_limit: Optional[int] = None,
        # FTS-specific parameters (Story #503 Phase 2)
        case_sensitive: bool = False,
        fuzzy: bool = False,
        edit_distance: int = 0,
        snippet_lines: int = 5,
        regex: bool = False,
        # Temporal filtering parameters (Story #503 Phase 3)
        diff_type: Optional[Union[str, List[str]]] = None,
        author: Optional[str] = None,
        chunk_type: Optional[str] = None,
    ) -> List[QueryResult]:
        """
        Perform the actual search across user repositories.

        Supports three search modes:
        - 'semantic': Vector-based semantic similarity search (default)
        - 'fts': Full-text search using Tantivy index
        - 'hybrid': Combined FTS + semantic search with result fusion

        Args:
            username: Username performing the query
            user_repos: List of user's activated repositories
            query_text: Query text
            limit: Result limit
            min_score: Score threshold
            file_extensions: List of file extensions to filter results
            language: Filter by programming language
            exclude_language: Exclude files of specified language
            path_filter: Filter by file path pattern
            exclude_path: Exclude files matching path pattern
            accuracy: Search accuracy profile
            search_mode: Search mode - 'semantic' (default), 'fts', or 'hybrid'
            time_range: Time range filter for temporal queries
            time_range_all: Query across all git history without time range limit
            at_commit: Query at specific commit
            include_removed: Include removed files
            show_evolution: Include evolution timeline
            evolution_limit: Limit evolution entries
            case_sensitive: Enable case-sensitive FTS matching
            fuzzy: Enable fuzzy matching
            edit_distance: Fuzzy match tolerance 0-3
            snippet_lines: Context lines around FTS matches 0-50
            regex: Interpret query as regex pattern

        Returns:
            List of QueryResult objects sorted by similarity score
        """
        all_results: List[QueryResult] = []

        # Search each repository
        for repo_info in user_repos:
            try:
                repo_alias = repo_info["user_alias"]

                # Check if repo_path is already provided (e.g., for global repos)
                if "repo_path" in repo_info and repo_info["repo_path"]:
                    repo_path = repo_info["repo_path"]
                else:
                    # Fall back to activated repo manager for regular activated repos
                    repo_path = self.activated_repo_manager.get_activated_repo_path(
                        username, repo_alias
                    )

                # Create temporary config and search engine for this repository
                # This would need actual implementation with proper config management
                results = self._search_single_repository(
                    repo_path,
                    repo_alias,
                    query_text,
                    limit,
                    min_score,
                    file_extensions,
                    language,
                    exclude_language,
                    path_filter,
                    exclude_path,
                    accuracy,
                    # Search mode (Story #503 - FTS Bug Fix)
                    search_mode=search_mode,
                    # Temporal parameters (Story #446)
                    time_range=time_range,
                    time_range_all=time_range_all,
                    at_commit=at_commit,
                    include_removed=include_removed,
                    show_evolution=show_evolution,
                    evolution_limit=evolution_limit,
                    # FTS-specific parameters (Story #503 Phase 2)
                    case_sensitive=case_sensitive,
                    fuzzy=fuzzy,
                    edit_distance=edit_distance,
                    snippet_lines=snippet_lines,
                    regex=regex,
                    # Temporal filtering parameters (Story #503 Phase 3)
                    diff_type=diff_type,
                    author=author,
                    chunk_type=chunk_type,
                )
                all_results.extend(results)

            except (TimeoutError, Exception) as e:
                # If it's a timeout or other critical error from one repo, propagate it
                if isinstance(e, TimeoutError) or "timeout" in str(e).lower():
                    raise TimeoutError(
                        f"Query timed out while searching repository {repo_info['user_alias']}: {str(e)}"
                    )
                # For other errors, log warning and continue with other repos
                self.logger.warning(
                    f"Failed to search repository {repo_info['user_alias']}: {str(e)}"
                )
                continue

        # Sort by similarity score (descending) and limit results
        all_results.sort(key=lambda r: r.similarity_score, reverse=True)

        # Apply global result limit
        effective_limit = min(limit, self.max_results_per_query)
        return all_results[:effective_limit]

    def _search_single_repository(
        self,
        repo_path: str,
        repository_alias: str,
        query_text: str,
        limit: int,
        min_score: Optional[float],
        file_extensions: Optional[List[str]],
        language: Optional[str] = None,
        exclude_language: Optional[str] = None,
        path_filter: Optional[str] = None,
        exclude_path: Optional[str] = None,
        accuracy: Optional[str] = None,
        # Search mode parameter (Story #503 - FTS Bug Fix)
        search_mode: str = "semantic",
        # Temporal parameters (Story #446)
        time_range: Optional[str] = None,
        time_range_all: bool = False,
        at_commit: Optional[str] = None,
        include_removed: bool = False,
        show_evolution: bool = False,
        evolution_limit: Optional[int] = None,
        # FTS-specific parameters (Story #503 Phase 2)
        case_sensitive: bool = False,
        fuzzy: bool = False,
        edit_distance: int = 0,
        snippet_lines: int = 5,
        regex: bool = False,
        # Temporal filtering parameters (Story #503 Phase 3)
        diff_type: Optional[Union[str, List[str]]] = None,
        author: Optional[str] = None,
        chunk_type: Optional[str] = None,
    ) -> List[QueryResult]:
        """
        Search a single repository using the appropriate search service.

        Supports three search modes:
        - 'semantic': Vector-based semantic similarity search (default)
        - 'fts': Full-text search using Tantivy index
        - 'hybrid': Combined FTS + semantic search with result fusion

        For temporal queries (when time_range, at_commit, or show_evolution provided),
        uses TemporalSearchService with graceful fallback to regular search if temporal
        index not available.

        For composite repositories (proxy_mode=true), delegates to CLI integration
        which supports all filter parameters (language, exclude_language, path_filter,
        exclude_path, accuracy).

        For regular repositories, uses SemanticSearchService with post-search filtering
        for file_extensions and min_score.

        Args:
            repo_path: Path to the repository
            repository_alias: Repository alias for result annotation
            query_text: Query text
            limit: Result limit
            min_score: Score threshold
            file_extensions: List of file extensions to filter results
            language: Filter by programming language
            exclude_language: Exclude files of specified language
            path_filter: Filter by file path pattern
            exclude_path: Exclude files matching path pattern
            accuracy: Search accuracy profile
            search_mode: Search mode - 'semantic' (default), 'fts', or 'hybrid'
            time_range: Time range filter for temporal queries
            time_range_all: Query across all git history without time range limit
            at_commit: Query at specific commit
            include_removed: Include removed files
            show_evolution: Include evolution timeline
            evolution_limit: Limit evolution entries
            case_sensitive: Enable case-sensitive FTS matching
            fuzzy: Enable fuzzy matching
            edit_distance: Fuzzy match tolerance 0-3
            snippet_lines: Context lines around FTS matches 0-50
            regex: Interpret query as regex pattern

        Returns:
            List of QueryResult objects from this repository
        """
        try:
            # Check if this is a composite repository
            repo_path_obj = Path(repo_path)
            if self._is_composite_repository(repo_path_obj):
                # Use CLI integration for composite repos (supports all filters)
                self.logger.debug(
                    f"Composite repository detected: {repo_path}. Using CLI integration for search."
                )
                return self._execute_cli_query(
                    repo_path=repo_path_obj,
                    query=query_text,
                    limit=limit,
                    min_score=min_score,
                    language=language,
                    path=path_filter,
                    accuracy=accuracy,
                    exclude_language=exclude_language,
                    exclude_path=exclude_path,
                    # FTS-specific parameters (Story #503 Phase 2)
                    case_sensitive=case_sensitive,
                    fuzzy=fuzzy,
                    edit_distance=edit_distance,
                    snippet_lines=snippet_lines,
                    regex=regex,
                    # Temporal filtering parameters (Story #503 Phase 3)
                    diff_type=diff_type,
                    author=author,
                    chunk_type=chunk_type,
                )

            # TEMPORAL QUERY HANDLING (Story #446)
            # Check if temporal parameters are present
            has_temporal_params = any(
                [time_range, time_range_all, at_commit, show_evolution]
            )

            if has_temporal_params:
                return self._execute_temporal_query(
                    repo_path=repo_path_obj,
                    repository_alias=repository_alias,
                    query_text=query_text,
                    limit=limit,
                    min_score=min_score,
                    time_range=time_range,
                    at_commit=at_commit,
                    include_removed=include_removed,
                    show_evolution=show_evolution,
                    evolution_limit=evolution_limit,
                    language=language,
                    exclude_language=exclude_language,
                    path_filter=path_filter,
                    exclude_path=exclude_path,
                )

            # FTS SEARCH HANDLING (Story #503 - FTS Bug Fix)
            # Execute FTS search when search_mode is 'fts' or 'hybrid'
            if search_mode in ["fts", "hybrid"]:
                fts_results = self._execute_fts_search(
                    repo_path=repo_path_obj,
                    repository_alias=repository_alias,
                    query_text=query_text,
                    limit=limit,
                    min_score=min_score,
                    language=language,
                    exclude_language=exclude_language,
                    path_filter=path_filter,
                    exclude_path=exclude_path,
                    case_sensitive=case_sensitive,
                    fuzzy=fuzzy,
                    edit_distance=edit_distance,
                    snippet_lines=snippet_lines,
                    regex=regex,
                )

                # For pure FTS mode, return FTS results directly
                if search_mode == "fts":
                    return fts_results

                # For hybrid mode, continue to semantic search and merge results
                # Fall through to semantic search below

            # For non-composite repos with semantic search, warn if advanced filters are used
            # (they are not supported by SemanticSearchService)
            if search_mode in ["semantic", "hybrid"] and any(
                [language, exclude_language, path_filter, exclude_path, accuracy]
            ):
                self.logger.warning(
                    f"Advanced filter parameters (language={language}, exclude_language={exclude_language}, "
                    f"path_filter={path_filter}, exclude_path={exclude_path}, accuracy={accuracy}) "
                    f"are not supported for non-composite repository '{repository_alias}'. "
                    "These filters will be ignored. Consider using file_extensions filter instead."
                )

            # SEMANTIC SEARCH
            # Import SemanticSearchService and related models
            from ..services.search_service import SemanticSearchService
            from ..models.api_models import SemanticSearchRequest

            # Create search service instance
            search_service = SemanticSearchService()

            # Create search request
            search_request = SemanticSearchRequest(
                query=query_text, limit=limit, include_source=True
            )

            # Perform search on the repository using direct path
            search_response = search_service.search_repository_path(
                repo_path=repo_path, search_request=search_request
            )

            # Convert search results to QueryResult objects
            semantic_results = []
            for search_item in search_response.results:
                # Apply min_score filter if specified
                if min_score is not None and search_item.score < min_score:
                    continue

                # Apply file extension filter if specified
                if file_extensions is not None:
                    file_path = Path(search_item.file_path)
                    if file_path.suffix.lower() not in [
                        ext.lower() for ext in file_extensions
                    ]:
                        continue

                # Convert SearchResultItem to QueryResult
                query_result = QueryResult(
                    file_path=search_item.file_path,
                    line_number=search_item.line_start,  # Use start line as line number
                    code_snippet=search_item.content,
                    similarity_score=search_item.score,
                    repository_alias=repository_alias,
                    source_repo=None,  # Single repository, no source_repo
                )
                semantic_results.append(query_result)

            # For hybrid mode, merge FTS and semantic results
            if search_mode == "hybrid":
                return self._merge_hybrid_results(
                    fts_results, semantic_results, limit
                )

            return semantic_results

        except Exception as e:
            self.logger.error(
                f"Failed to search repository '{repository_alias}' at '{repo_path}': {str(e)}"
            )
            # Re-raise exception to be handled by calling method
            raise

    def _build_cli_args(
        self,
        query: str,
        limit: int,
        min_score: Optional[float] = None,
        language: Optional[str] = None,
        path: Optional[str] = None,
        accuracy: Optional[str] = None,
        exclude_language: Optional[str] = None,
        exclude_path: Optional[str] = None,
        # FTS-specific parameters (Story #503 Phase 2)
        case_sensitive: bool = False,
        fuzzy: bool = False,
        edit_distance: int = 0,
        snippet_lines: int = 5,
        regex: bool = False,
        # Temporal filtering parameters (Story #503 Phase 3)
        diff_type: Optional[Union[str, List[str]]] = None,
        author: Optional[str] = None,
        chunk_type: Optional[str] = None,
    ) -> List[str]:
        """
        Convert server parameters to CLI args format.

        Args:
            query: Query text
            limit: Result limit
            min_score: Minimum score threshold
            language: Programming language filter
            path: Path pattern filter
            accuracy: Accuracy level (fast, balanced, high)
            exclude_language: Exclude specified language
            exclude_path: Exclude path pattern
            case_sensitive: Enable case-sensitive FTS matching
            fuzzy: Enable fuzzy matching
            edit_distance: Fuzzy match tolerance 0-3
            snippet_lines: Context lines around FTS matches 0-50
            regex: Interpret query as regex pattern

        Returns:
            List of CLI arguments
        """
        args = ["query", query]

        # Always set quiet mode for parsing
        args.append("--quiet")

        # Add limit
        args.extend(["--limit", str(limit)])

        # Add optional parameters
        if min_score is not None:
            args.extend(["--min-score", str(min_score)])

        if language is not None:
            args.extend(["--language", language])

        if path is not None:
            args.extend(["--path", path])

        if accuracy is not None:
            args.extend(["--accuracy", accuracy])

        if exclude_language is not None:
            args.extend(["--exclude-language", exclude_language])

        if exclude_path is not None:
            args.extend(["--exclude-path", exclude_path])

        # FTS-specific parameters (Story #503 Phase 2)
        if case_sensitive:
            args.append("--case-sensitive")

        if fuzzy:
            args.append("--fuzzy")

        if edit_distance > 0:
            args.extend(["--edit-distance", str(edit_distance)])

        if snippet_lines != 5:  # Only add if different from default
            args.extend(["--snippet-lines", str(snippet_lines)])

        if regex:
            args.append("--regex")

        # Temporal filtering parameters (Story #503 Phase 3)
        if diff_type is not None:
            # Handle diff_type: can be string, array, or comma-separated string
            if isinstance(diff_type, list):
                # Array: add --diff-type flag for each value
                for dt in diff_type:
                    args.extend(["--diff-type", dt])
            elif isinstance(diff_type, str):
                # String: check if comma-separated, split and add multiple flags
                if "," in diff_type:
                    for dt in diff_type.split(","):
                        args.extend(["--diff-type", dt.strip()])
                else:
                    # Single value
                    args.extend(["--diff-type", diff_type])

        if author is not None:
            args.extend(["--author", author])

        if chunk_type is not None:
            args.extend(["--chunk-type", chunk_type])

        return args

    def _execute_cli_query(
        self,
        repo_path: Path,
        query: str,
        limit: int,
        min_score: Optional[float] = None,
        language: Optional[str] = None,
        path: Optional[str] = None,
        accuracy: Optional[str] = None,
        exclude_language: Optional[str] = None,
        exclude_path: Optional[str] = None,
        # FTS-specific parameters (Story #503 Phase 2)
        case_sensitive: bool = False,
        fuzzy: bool = False,
        edit_distance: int = 0,
        snippet_lines: int = 5,
        regex: bool = False,
        # Temporal filtering parameters (Story #503 Phase 3)
        diff_type: Optional[Union[str, List[str]]] = None,
        author: Optional[str] = None,
        chunk_type: Optional[str] = None,
    ) -> List[QueryResult]:
        """
        Execute CLI query and parse results.

        This is a thin wrapper that:
        1. Loads ProxyConfigManager to get repository paths
        2. Converts parameters to CLI args
        3. Calls _execute_query from CLI
        4. Captures stdout and parses results
        5. Updates repository_alias to composite repo name

        Args:
            repo_path: Path to composite repository
            query: Query text
            limit: Result limit
            min_score: Score threshold
            language: Language filter
            path: Path filter
            accuracy: Accuracy level
            exclude_language: Exclude specified language
            exclude_path: Exclude path pattern

        Returns:
            List of QueryResult objects with:
                - repository_alias: Composite repo name (from repo_path)
                - source_repo: Component repo name (from file path)

        Raises:
            Exception: If ProxyConfigManager fails or CLI execution fails
        """
        # Load proxy configuration to get repository paths
        proxy_config_manager = ProxyConfigManager(repo_path)
        config = proxy_config_manager.load_config()
        discovered_repos = config.discovered_repos

        # Convert relative paths to absolute paths
        repo_paths = [str(repo_path / repo) for repo in discovered_repos]

        # Build CLI args
        args = self._build_cli_args(
            query=query,
            limit=limit,
            min_score=min_score,
            language=language,
            path=path,
            accuracy=accuracy,
            exclude_language=exclude_language,
            exclude_path=exclude_path,
            # FTS-specific parameters (Story #503 Phase 2)
            case_sensitive=case_sensitive,
            fuzzy=fuzzy,
            edit_distance=edit_distance,
            snippet_lines=snippet_lines,
            regex=regex,
            # Temporal filtering parameters (Story #503 Phase 3)
            diff_type=diff_type,
            author=author,
            chunk_type=chunk_type,
        )

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = io.StringIO()

        try:
            # Execute CLI query (this handles parallel execution, aggregation, etc.)
            _execute_query(args, repo_paths)

            # Get captured output
            cli_output = captured_output.getvalue()

        finally:
            # Restore stdout
            sys.stdout = old_stdout

        # Parse CLI output to QueryResult objects
        results = self._parse_cli_output(cli_output, repo_path)

        # Override repository_alias with composite repo name
        # (parser sets it to source_repo by default)
        composite_repo_name = repo_path.name
        for result in results:
            result.repository_alias = composite_repo_name

        return results

    def _parse_cli_output(self, cli_output: str, repo_path: Path) -> List[QueryResult]:
        """
        Parse CLI quiet mode output to QueryResult objects.

        CLI quiet mode format (from QueryResultAggregator):
            score path:line_range
              line_num: code
              line_num: code

            score path:line_range
              line_num: code

        For composite repositories, file_path includes subrepo prefix: "repo1/auth.py"
        For single repositories, file_path is just the path: "auth.py"

        Args:
            cli_output: CLI stdout output in quiet mode
            repo_path: Repository root path (used to determine composite repo name)

        Returns:
            List of QueryResult objects with source_repo populated for composite repos
        """
        if not cli_output or not cli_output.strip():
            return []

        results = []
        lines = cli_output.strip().split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]

            # Skip empty lines
            if not line.strip():
                i += 1
                continue

            # Parse result header: "score path:line_range"
            # Example: "0.95 repo1/auth.py:10-20" (composite)
            # Example: "0.95 auth.py:10-20" (single)
            header_match = re.match(r"^([\d.]+)\s+(.+):(\d+)-(\d+)\s*$", line)

            if header_match:
                score = float(header_match.group(1))
                file_path = header_match.group(2)
                line_start = int(header_match.group(3))
                # line_end is part of the match but not used in QueryResult
                # (stored in code_snippet instead)

                # Extract source_repo from file path for composite repos
                # Format: "repo1/auth.py" -> source_repo is "repo1"
                # Format: "auth.py" -> source_repo is None (single repo)
                if "/" in file_path:
                    source_repo = file_path.split("/")[0]
                else:
                    source_repo = None

                # repository_alias will be set by calling context (search_composite)
                # For now, use source_repo as placeholder (will be updated by caller)
                repo_alias = source_repo if source_repo else repo_path.name

                # Collect code snippet lines
                code_lines = []
                i += 1

                # Read indented code lines
                while i < len(lines) and lines[i].startswith("  "):
                    code_lines.append(lines[i])
                    i += 1

                # Combine code snippet
                code_snippet = "\n".join(code_lines) if code_lines else ""

                # Create QueryResult with source_repo populated
                result = QueryResult(
                    file_path=file_path,
                    line_number=line_start,
                    code_snippet=code_snippet,
                    similarity_score=score,
                    repository_alias=repo_alias,
                    source_repo=source_repo,  # NEW: Extract from file path
                )
                results.append(result)

            else:
                # Non-matching line, skip it
                i += 1

        return results

    def _execute_temporal_query(
        self,
        repo_path: Path,
        repository_alias: str,
        query_text: str,
        limit: int,
        min_score: Optional[float],
        time_range: Optional[str],
        at_commit: Optional[str],
        include_removed: bool,
        show_evolution: bool,
        evolution_limit: Optional[int],
        language: Optional[str] = None,
        exclude_language: Optional[str] = None,
        path_filter: Optional[str] = None,
        exclude_path: Optional[str] = None,
    ) -> List[QueryResult]:
        """Execute temporal query using TemporalSearchService with graceful fallback.

        Story #446: Temporal Query Parameters via API

        Integrates TemporalSearchService for time-based code searches. If temporal
        index not available, gracefully falls back to regular search with warning.

        Args:
            repo_path: Repository path
            repository_alias: Repository alias for results
            query_text: Search query
            limit: Result limit
            min_score: Minimum similarity score
            time_range: Time range filter (YYYY-MM-DD..YYYY-MM-DD)
            at_commit: Query at specific commit
            include_removed: Include removed files
            show_evolution: Show evolution timeline
            evolution_limit: Limit evolution entries
            language: Filter by language
            exclude_language: Exclude language
            path_filter: Path filter pattern
            exclude_path: Exclude path pattern

        Returns:
            List of QueryResult objects with temporal context
        """
        from ...services.temporal.temporal_search_service import TemporalSearchService
        from ...proxy.config_manager import ConfigManager
        from ...backends.backend_factory import BackendFactory
        from ...services.embedding_factory import EmbeddingProviderFactory

        try:
            # Load repository configuration
            config_manager = ConfigManager.create_with_backtrack(repo_path)
            config = config_manager.get_config()

            # Create vector store and embedding provider (Story #526: pass server cache)
            # Import here to avoid circular dependency
            from ..app import _server_hnsw_cache

            backend = BackendFactory.create(
                config=config, project_root=repo_path, hnsw_cache=_server_hnsw_cache
            )
            vector_store = backend.get_vector_store_client()
            embedding_provider = EmbeddingProviderFactory.create(config, console=None)

            # Create temporal service with correct collection name
            temporal_service = TemporalSearchService(
                config_manager=config_manager,
                project_root=repo_path,
                vector_store_client=vector_store,
                embedding_provider=embedding_provider,
                collection_name=TemporalSearchService.TEMPORAL_COLLECTION_NAME,
            )

            # Check if temporal index exists
            if not temporal_service.has_temporal_index():
                # GRACEFUL FALLBACK (Acceptance Criterion 9)
                self.logger.warning(
                    f"Temporal index not available for repository '{repository_alias}'. "
                    "Falling back to regular search."
                )
                # Fall back to regular search - return empty list with warning
                # The warning will be added to query response by caller
                return []

            # Validate and parse temporal parameters
            if time_range:
                time_range_tuple = temporal_service._validate_date_range(time_range)
            elif at_commit:
                # For at_commit, use a wide range and filter by commit later
                # This is a simplified implementation - full at_commit support
                # would require additional TemporalSearchService methods
                time_range_tuple = ("1970-01-01", "2100-12-31")
            else:
                time_range_tuple = ("1970-01-01", "2100-12-31")

            # Determine diff_types based on include_removed
            diff_types = None
            if not include_removed:
                # Exclude deleted files
                diff_types = ["added", "modified"]

            # Build language filters
            language_list = [language] if language else None
            exclude_language_list = [exclude_language] if exclude_language else None

            # Build path filters
            path_filter_list = [path_filter] if path_filter else None
            exclude_path_list = [exclude_path] if exclude_path else None

            # Execute temporal query (Acceptance Criterion 8: Internal service calls)
            temporal_results = temporal_service.query_temporal(
                query=query_text,
                time_range=time_range_tuple,
                diff_types=diff_types,
                limit=limit,
                min_score=min_score,
                language=language_list,
                exclude_language=exclude_language_list,
                path_filter=path_filter_list,
                exclude_path=exclude_path_list,
            )

            # Convert temporal results to QueryResult objects
            query_results = []
            for temporal_result in temporal_results.results:
                # Build temporal context (Acceptance Criterion 7)
                temporal_context = {
                    "first_seen": temporal_result.temporal_context.get("first_seen"),
                    "last_seen": temporal_result.temporal_context.get("last_seen"),
                    "commit_count": temporal_result.temporal_context.get(
                        "appearance_count", 0
                    ),
                    "commits": temporal_result.temporal_context.get("commits", []),
                }

                # Add is_removed flag if applicable
                if (
                    include_removed
                    and temporal_result.metadata.get("diff_type") == "deleted"
                ):
                    temporal_context["is_removed"] = True

                # Add evolution data if requested (Acceptance Criterion 5 & 6)
                if show_evolution and "evolution" in temporal_result.temporal_context:
                    evolution_data = temporal_result.temporal_context["evolution"]
                    # Apply user-controlled evolution_limit (NO arbitrary max)
                    if evolution_limit and len(evolution_data) > evolution_limit:
                        evolution_data = evolution_data[:evolution_limit]
                    temporal_context["evolution"] = evolution_data

                # Create QueryResult with temporal context
                query_result = QueryResult(
                    file_path=temporal_result.file_path,
                    line_number=1,  # Temporal results don't have line numbers
                    code_snippet=temporal_result.content,
                    similarity_score=temporal_result.score,
                    repository_alias=repository_alias,
                    source_repo=None,
                )

                # Add temporal_context to result dict
                result_dict = query_result.to_dict()
                result_dict["temporal_context"] = temporal_context

                # Convert back to QueryResult (preserve structure)
                # Note: QueryResult dataclass doesn't have temporal_context field,
                # so we'll add it as custom attribute
                query_result_with_temporal = query_result
                # Store temporal context as custom attribute for later serialization
                setattr(
                    query_result_with_temporal, "_temporal_context", temporal_context
                )

                query_results.append(query_result)

            return query_results

        except ValueError as e:
            # Clear error messages for invalid parameters (Acceptance Criterion 10)
            self.logger.error(f"Temporal query validation error: {str(e)}")
            raise ValueError(str(e))
        except Exception as e:
            # Log error and fall back to regular search
            self.logger.error(
                f"Temporal query failed for repository '{repository_alias}': {str(e)}"
            )
            # Re-raise to let caller handle
            raise SemanticQueryError(f"Temporal query failed: {str(e)}")

    def _execute_fts_search(
        self,
        repo_path: Path,
        repository_alias: str,
        query_text: str,
        limit: int,
        min_score: Optional[float] = None,
        language: Optional[str] = None,
        exclude_language: Optional[str] = None,
        path_filter: Optional[str] = None,
        exclude_path: Optional[str] = None,
        case_sensitive: bool = False,
        fuzzy: bool = False,
        edit_distance: int = 0,
        snippet_lines: int = 5,
        regex: bool = False,
    ) -> List[QueryResult]:
        """
        Execute FTS search using TantivyIndexManager.

        Story #503 - FTS Bug Fix: Implements FTS search for MCP handler.

        Args:
            repo_path: Path to the repository
            repository_alias: Repository alias for result annotation
            query_text: Search query
            limit: Maximum results to return
            min_score: Minimum similarity score threshold
            language: Filter by programming language
            exclude_language: Exclude files of specified language
            path_filter: Filter by file path pattern
            exclude_path: Exclude files matching path pattern
            case_sensitive: Enable case-sensitive matching
            fuzzy: Enable fuzzy matching
            edit_distance: Fuzzy match tolerance 0-3
            snippet_lines: Context lines around matches
            regex: Interpret query as regex pattern

        Returns:
            List of QueryResult objects from FTS search

        Raises:
            SemanticQueryError: If FTS index not available or search fails
        """
        # Check if FTS index exists
        fts_index_dir = repo_path / ".code-indexer" / "tantivy_index"
        if not fts_index_dir.exists():
            raise SemanticQueryError(
                f"FTS index not available for repository '{repository_alias}'. "
                "Build FTS index with 'cidx index --fts' in the repository."
            )

        try:
            # Import TantivyIndexManager (lazy import to avoid startup overhead)
            from ...services.tantivy_index_manager import TantivyIndexManager

            # Initialize Tantivy manager
            tantivy_manager = TantivyIndexManager(fts_index_dir)
            tantivy_manager.initialize_index(create_new=False)

            # Handle fuzzy flag
            effective_edit_distance = edit_distance
            if fuzzy and edit_distance == 0:
                effective_edit_distance = 1

            # Execute FTS query
            fts_raw_results = tantivy_manager.search(
                query_text=query_text,
                case_sensitive=case_sensitive,
                edit_distance=effective_edit_distance,
                snippet_lines=snippet_lines,
                limit=limit,
                language_filter=language,
                path_filter=path_filter,
                exclude_languages=[exclude_language] if exclude_language else None,
                exclude_paths=[exclude_path] if exclude_path else None,
                use_regex=regex,
            )

            # Convert FTS results to QueryResult objects
            query_results = []
            for result in fts_raw_results:
                # FTS doesn't have similarity scores in the same sense as semantic search
                # Use a normalized score based on result ordering (1.0 for first result)
                score = 1.0 - (len(query_results) * 0.01)  # Decreasing score

                # Apply min_score filter if specified
                if min_score is not None and score < min_score:
                    continue

                query_result = QueryResult(
                    file_path=result.get("path", ""),
                    line_number=result.get("line_start", 0),
                    code_snippet=result.get("snippet", ""),
                    similarity_score=score,
                    repository_alias=repository_alias,
                    source_repo=None,
                )
                query_results.append(query_result)

            self.logger.debug(
                f"FTS search completed for '{repository_alias}': "
                f"{len(query_results)} results"
            )
            return query_results

        except ImportError as e:
            raise SemanticQueryError(
                f"Tantivy library not available: {str(e)}. "
                "Install with: pip install tantivy==0.25.0"
            )
        except Exception as e:
            self.logger.error(
                f"FTS search failed for repository '{repository_alias}': {str(e)}"
            )
            raise SemanticQueryError(f"FTS search failed: {str(e)}")

    def _merge_hybrid_results(
        self,
        fts_results: List[QueryResult],
        semantic_results: List[QueryResult],
        limit: int,
    ) -> List[QueryResult]:
        """
        Merge FTS and semantic search results for hybrid mode.

        Uses reciprocal rank fusion (RRF) to combine results from both search types.

        Args:
            fts_results: Results from FTS search
            semantic_results: Results from semantic search
            limit: Maximum results to return

        Returns:
            Merged and deduplicated list of QueryResult objects
        """
        # Use file_path + line_number as key for deduplication
        seen_keys = set()
        merged_results = []
        rrf_scores = {}

        # Constant for RRF scoring (typically 60)
        k = 60

        # Calculate RRF scores for FTS results
        for rank, result in enumerate(fts_results, start=1):
            key = (result.file_path, result.line_number)
            rrf_score = 1.0 / (k + rank)
            rrf_scores[key] = rrf_scores.get(key, 0) + rrf_score

        # Calculate RRF scores for semantic results
        for rank, result in enumerate(semantic_results, start=1):
            key = (result.file_path, result.line_number)
            rrf_score = 1.0 / (k + rank)
            rrf_scores[key] = rrf_scores.get(key, 0) + rrf_score

        # Create a mapping of keys to results (prefer FTS for content)
        result_map = {}
        for result in semantic_results:
            key = (result.file_path, result.line_number)
            result_map[key] = result

        for result in fts_results:
            key = (result.file_path, result.line_number)
            result_map[key] = result  # FTS overwrites semantic for same key

        # Sort by RRF score and build merged results
        sorted_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)

        for key in sorted_keys[:limit]:
            if key in result_map:
                result = result_map[key]
                # Update similarity score to RRF score
                merged_result = QueryResult(
                    file_path=result.file_path,
                    line_number=result.line_number,
                    code_snippet=result.code_snippet,
                    similarity_score=rrf_scores[key],
                    repository_alias=result.repository_alias,
                    source_repo=result.source_repo,
                )
                merged_results.append(merged_result)

        return merged_results
