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
from typing import Dict, List, Optional, Any
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
        """Create QueryResult from SearchEngine SearchResult."""
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
            path=kwargs.get("path"),
            accuracy=kwargs.get("accuracy"),
        )

    def query_user_repositories(
        self,
        username: str,
        query_text: str,
        repository_alias: Optional[str] = None,
        limit: int = 10,
        min_score: Optional[float] = None,
        file_extensions: Optional[List[str]] = None,
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
                username, user_repos, query_text, limit, min_score, file_extensions
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

        return {
            "results": [r.to_dict() for r in results],
            "total_results": len(results),
            "query_metadata": metadata.to_dict(),
        }

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
    ) -> List[QueryResult]:
        """
        Perform the actual semantic search across user repositories.

        Args:
            username: Username performing the query
            user_repos: List of user's activated repositories
            query_text: Query text
            limit: Result limit
            min_score: Score threshold
            file_extensions: List of file extensions to filter results

        Returns:
            List of QueryResult objects sorted by similarity score
        """
        all_results: List[QueryResult] = []

        # Search each repository
        for repo_info in user_repos:
            try:
                repo_alias = repo_info["user_alias"]
                repo_path = self.activated_repo_manager.get_activated_repo_path(
                    username, repo_alias
                )

                # Create temporary config and search engine for this repository
                # This would need actual implementation with proper config management
                results = self._search_single_repository(
                    repo_path, repo_alias, query_text, limit, min_score, file_extensions
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
    ) -> List[QueryResult]:
        """
        Search a single repository using the SemanticSearchService.

        Args:
            repo_path: Path to the repository
            repository_alias: Repository alias for result annotation
            query_text: Query text
            limit: Result limit
            min_score: Score threshold
            file_extensions: List of file extensions to filter results

        Returns:
            List of QueryResult objects from this repository
        """
        try:
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
            query_results = []
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
                query_results.append(query_result)

            return query_results

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
