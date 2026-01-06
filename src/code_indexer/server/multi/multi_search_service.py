"""
Multi-Repository Search Service.

Orchestrates parallel search execution across multiple repositories with
timeout enforcement, partial failure handling, and ReDoS protection for regex queries.

Implements:
- AC2: Threaded Execution (ThreadPoolExecutor for semantic/FTS/temporal)
- AC3: Subprocess Execution (isolated processes for regex/ReDoS protection)
- AC4: Timeout Enforcement (30s default timeout for all queries)
- AC5: Partial Failure Handling (some repos succeed, others fail)
- AC7: Actionable Error Messages (timeout recommendations)
"""

import logging
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from pathlib import Path
from typing import Dict, List, Any

from .multi_search_config import MultiSearchConfig
from .multi_result_aggregator import MultiResultAggregator
from .models import MultiSearchRequest, MultiSearchResponse, MultiSearchMetadata

logger = logging.getLogger(__name__)

# Constants for timeout recommendations
MAX_RECOMMENDED_REPOS = 10
RECOMMENDED_MIN_SCORE = 0.7


class MultiSearchService:
    """
    Orchestrates parallel search execution across multiple repositories.

    Threading Strategy:
    - Semantic/FTS/Temporal: ThreadPoolExecutor (API-bound, threads efficient)
    - Regex: Subprocess isolation (server protection from ReDoS attacks)

    Timeout: 30s default for all queries (configurable)
    """

    def __init__(self, config: MultiSearchConfig):
        """
        Initialize multi-search service.

        Args:
            config: Multi-search configuration
        """
        self.config = config
        self.thread_executor = ThreadPoolExecutor(max_workers=config.max_workers)
        self._shutdown = False

    async def search(self, request: MultiSearchRequest) -> MultiSearchResponse:
        """
        Execute search across multiple repositories.

        Args:
            request: Multi-search request with repositories, query, and search type

        Returns:
            MultiSearchResponse with results grouped by repository and metadata
        """
        start_time = time.time()

        # Route to appropriate search strategy
        if request.search_type == "regex":
            response = await self._search_regex_subprocess(request)
        else:
            response = await self._search_threaded(request)

        # Calculate execution time
        execution_time_ms = int((time.time() - start_time) * 1000)
        response.metadata.execution_time_ms = execution_time_ms

        return response

    async def _search_threaded(
        self, request: MultiSearchRequest
    ) -> MultiSearchResponse:
        """
        Execute search using ThreadPoolExecutor (semantic, FTS, temporal).

        Args:
            request: Multi-search request

        Returns:
            MultiSearchResponse with aggregated results
        """
        return await self._execute_parallel_search(
            request, self._search_single_repo_sync
        )

    async def _search_regex_subprocess(
        self, request: MultiSearchRequest
    ) -> MultiSearchResponse:
        """
        Execute regex search in isolated subprocesses (ReDoS protection).

        Each repository search runs in a separate subprocess to protect the server
        from potentially malicious regex patterns that could cause ReDoS attacks.

        Args:
            request: Multi-search request with regex query

        Returns:
            MultiSearchResponse with aggregated results
        """
        return await self._execute_parallel_search(
            request, self._search_single_repo_subprocess
        )

    async def _execute_parallel_search(
        self, request: MultiSearchRequest, search_func
    ) -> MultiSearchResponse:
        """
        Execute parallel search across repositories using provided search function.

        Extracts common logic for threaded and subprocess searches.

        Args:
            request: Multi-search request
            search_func: Function to execute for each repository

        Returns:
            MultiSearchResponse with aggregated results
        """
        repo_results: Dict[str, List[Dict[str, Any]]] = {}
        errors: Dict[str, str] = {}

        # Submit all search tasks
        future_to_repo = {
            self.thread_executor.submit(search_func, repo_id, request): repo_id
            for repo_id in request.repositories
        }

        # Collect results as they complete
        for future in as_completed(future_to_repo):
            repo_id = future_to_repo[future]

            try:
                result = future.result(timeout=self.config.query_timeout_seconds)
                if result:
                    repo_results[repo_id] = result
                else:
                    repo_results[repo_id] = []
            except TimeoutError:
                error_msg = self._format_timeout_error(request, [repo_id])
                errors[repo_id] = error_msg
                logger.warning(
                    f"Search timeout for repo {repo_id} after {self.config.query_timeout_seconds}s"
                )
            except Exception as e:
                errors[repo_id] = f"Search failed: {str(e)}"
                logger.error(f"Search error for repo {repo_id}: {e}")

        # Aggregate results with optional score filtering
        aggregator = MultiResultAggregator(
            limit=request.limit,
            min_score=request.min_score
        )
        aggregated_results = aggregator.aggregate(repo_results)

        # Calculate metadata
        total_results = sum(len(results) for results in aggregated_results.values())
        total_repos_searched = len(repo_results)

        metadata = MultiSearchMetadata(
            total_results=total_results,
            total_repos_searched=total_repos_searched,
            execution_time_ms=0,  # Will be set by caller
        )

        return MultiSearchResponse(
            results=aggregated_results,
            metadata=metadata,
            errors=errors if errors else None,
        )

    def _search_single_repo_sync(
        self, repo_id: str, request: MultiSearchRequest
    ) -> List[Dict[str, Any]]:
        """
        Search a single repository synchronously (runs in thread pool).

        Routes to appropriate search implementation based on search_type.
        Note: Regex searches use subprocess execution (handled separately).

        Args:
            repo_id: Repository identifier
            request: Multi-search request

        Returns:
            List of search results for this repository

        Raises:
            ValueError: If search type is not supported
            Exception: If search fails
        """
        search_type = request.search_type

        if search_type == "semantic":
            return self._search_semantic_sync(repo_id, request)
        elif search_type == "fts":
            return self._search_fts_sync(repo_id, request)
        elif search_type == "temporal":
            return self._search_temporal_sync(repo_id, request)
        else:
            raise ValueError(f"Unsupported search type: {search_type}")

    def _search_semantic_sync(
        self, repo_id: str, request: MultiSearchRequest
    ) -> List[Dict[str, Any]]:
        """
        Execute semantic search for a single repository.

        Args:
            repo_id: Repository identifier
            request: Multi-search request

        Returns:
            List of semantic search results

        Raises:
            Exception: If semantic search fails
        """
        # Import here to avoid circular dependency
        from ..services.search_service import SemanticSearchService
        from ..models.api_models import SemanticSearchRequest

        # Create search service
        search_service = SemanticSearchService()

        # Create single-repo search request
        single_repo_request = SemanticSearchRequest(
            query=request.query,
            limit=min(request.limit, self.config.max_results_per_repo),
            include_source=False,
        )

        # Execute search
        try:
            response = search_service.search_repository(repo_id, single_repo_request)

            # Convert response to dict format
            results = []
            for item in response.results:
                result_dict = {
                    "file_path": item.file_path,
                    "line_start": item.line_start,
                    "line_end": item.line_end,
                    "score": item.score,
                    "content": item.content,
                    "language": item.language,
                }
                results.append(result_dict)

            return results

        except Exception as e:
            logger.error(f"Failed semantic search for repository {repo_id}: {e}")
            raise

    def _search_fts_sync(
        self, repo_id: str, request: MultiSearchRequest
    ) -> List[Dict[str, Any]]:
        """
        Execute FTS search for a single repository.

        Args:
            repo_id: Repository identifier
            request: Multi-search request

        Returns:
            List of FTS search results

        Raises:
            Exception: If FTS search fails
        """
        from pathlib import Path as PathLib
        from ...services.tantivy_index_manager import TantivyIndexManager

        try:
            # Get repository path
            repo_path = self._get_repository_path(repo_id)

            # FTS index is in .code-indexer/fts-index
            fts_index_dir = PathLib(repo_path) / ".code-indexer" / "fts-index"

            if not fts_index_dir.exists():
                raise FileNotFoundError(
                    f"FTS index not found for repository {repo_id} at {fts_index_dir}"
                )

            # Initialize FTS manager and search
            tantivy_manager = TantivyIndexManager(fts_index_dir)
            tantivy_manager.initialize_index(create_new=False)

            # Convert language filter to list if present
            languages = [request.language] if request.language else None

            # Convert path filter to list if present
            path_filters = [request.path_filter] if request.path_filter else None

            # Execute FTS search
            fts_results = tantivy_manager.search(
                query_text=request.query,
                limit=min(request.limit, self.config.max_results_per_repo),
                languages=languages,
                path_filters=path_filters,
                use_regex=False,
                snippet_lines=3,
            )

            # Convert FTS results to standardized format
            results = []
            for fts_result in fts_results:
                result_dict = {
                    "file_path": fts_result.get("path", ""),
                    "line_start": fts_result.get("line", 0),
                    "line_end": fts_result.get("line", 0),
                    "score": fts_result.get("score", 0.0),
                    "content": fts_result.get("match_text", ""),
                    "language": fts_result.get("language", ""),
                }
                results.append(result_dict)

            return results

        except Exception as e:
            logger.error(f"Failed FTS search for repository {repo_id}: {e}")
            raise

    def _search_temporal_sync(
        self, repo_id: str, request: MultiSearchRequest
    ) -> List[Dict[str, Any]]:
        """
        Execute temporal search for a single repository.

        Args:
            repo_id: Repository identifier
            request: Multi-search request

        Returns:
            List of temporal search results

        Raises:
            Exception: If temporal search fails
        """
        from pathlib import Path as PathLib
        from ...services.temporal.temporal_search_service import (
            TemporalSearchService,
            ALL_TIME_RANGE,
        )
        from ...config import ConfigManager
        from ...storage.filesystem_vector_store import FilesystemVectorStore

        try:
            # Get repository path
            repo_path = PathLib(self._get_repository_path(repo_id))

            # Load repository configuration
            config_manager = ConfigManager.create_with_backtrack(repo_path)

            # Initialize vector store for temporal search
            index_dir = repo_path / ".code-indexer" / "index"
            vector_store_client = FilesystemVectorStore(
                base_path=index_dir, project_root=repo_path
            )

            # Create temporal service
            temporal_service = TemporalSearchService(
                config_manager=config_manager,
                project_root=repo_path,
                vector_store_client=vector_store_client,
            )

            # Check if temporal index exists
            if not temporal_service.has_temporal_index():
                raise FileNotFoundError(
                    f"Temporal index not found for repository {repo_id}"
                )

            # Execute temporal query with all-time range (default)
            temporal_results = temporal_service.query_temporal(
                query=request.query,
                time_range=ALL_TIME_RANGE,
                limit=min(request.limit, self.config.max_results_per_repo),
                min_score=request.min_score,
                language=[request.language] if request.language else None,
                path_filter=[request.path_filter] if request.path_filter else None,
            )

            # Convert temporal results to standardized format
            results = []
            for temporal_result in temporal_results.results:
                result_dict = {
                    "file_path": temporal_result.file_path,
                    "line_start": 0,
                    "line_end": 0,
                    "score": temporal_result.score,
                    "content": temporal_result.content,
                    "language": "",
                    "commit_hash": temporal_result.metadata.get("commit_hash", ""),
                    "commit_date": temporal_result.temporal_context.get(
                        "commit_date", ""
                    ),
                    "author": temporal_result.temporal_context.get("author_name", ""),
                }
                results.append(result_dict)

            return results

        except Exception as e:
            logger.error(f"Failed temporal search for repository {repo_id}: {e}")
            raise

    def _search_single_repo_subprocess(
        self, repo_id: str, request: MultiSearchRequest
    ) -> List[Dict[str, Any]]:
        """
        Search a single repository in isolated subprocess (ReDoS protection).

        Args:
            repo_id: Repository identifier
            request: Multi-search request

        Returns:
            List of search results for this repository

        Raises:
            Exception: If search fails or subprocess times out
        """
        # Create temporary file for subprocess output
        with tempfile.NamedTemporaryFile(
            mode="w+", suffix=".json", delete=False
        ) as tmp_file:
            output_file = tmp_file.name

        try:
            # Build subprocess command for regex search
            # Uses cidx CLI for isolated execution
            cmd = [
                "python3",
                "-m",
                "code_indexer.cli",
                "query",
                request.query,
                "--quiet",
                "--limit",
                str(min(request.limit, self.config.max_results_per_repo)),
                "--fts",
                "--regex",
            ]

            # Add optional filters
            if request.language:
                cmd.extend(["--language", request.language])
            if request.path_filter:
                cmd.extend(["--path-filter", request.path_filter])

            # Get repository path for working directory
            repo_path = self._get_repository_path(repo_id)

            # Execute in subprocess with timeout
            process = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=self.config.query_timeout_seconds,
            )

            if process.returncode != 0:
                raise RuntimeError(
                    f"Subprocess failed with exit code {process.returncode}: {process.stderr}"
                )

            # Parse results from subprocess stdout
            # Quiet mode format: "N. path:line:column"
            results = []
            if process.stdout:
                for line in process.stdout.strip().split("\n"):
                    if not line.strip():
                        continue

                    # Parse format: "1. src/file.py:123:45"
                    try:
                        # Split on first space to separate number from path
                        parts = line.split(". ", 1)
                        if len(parts) < 2:
                            continue

                        # Parse path:line:column
                        location = parts[1]
                        location_parts = location.rsplit(":", 2)

                        if len(location_parts) >= 2:
                            file_path = location_parts[0]
                            line_num = int(location_parts[1])

                            result_dict = {
                                "file_path": file_path,
                                "line_start": line_num,
                                "line_end": line_num,
                                "score": 1.0,  # Regex matches are binary (match/no-match)
                                "content": "",  # Content not available in quiet mode
                                "language": "",
                            }
                            results.append(result_dict)

                    except (ValueError, IndexError) as e:
                        logger.warning(
                            f"Failed to parse subprocess output line: {line} - {e}"
                        )
                        continue

            return results

        except subprocess.TimeoutExpired:
            raise TimeoutError(
                f"Subprocess timeout after {self.config.query_timeout_seconds}s"
            )
        except Exception as e:
            logger.error(f"Subprocess search failed for repo {repo_id}: {e}")
            raise
        finally:
            # Cleanup temporary file
            try:
                Path(output_file).unlink(missing_ok=True)
            except Exception:
                pass

    def _get_repository_path(self, repo_id: str) -> str:
        """
        Get file system path for repository.

        Args:
            repo_id: Repository identifier

        Returns:
            File system path to repository

        Raises:
            FileNotFoundError: If repository not found
        """
        from ..repositories.golden_repo_manager import GoldenRepoManager

        home_dir = Path.home()
        data_dir = str(home_dir / ".cidx-server" / "data")
        repo_manager = GoldenRepoManager(data_dir=data_dir)

        # Search for repository by alias
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

        raise FileNotFoundError(
            f"Repository {repo_id} not found in golden repositories"
        )

    def _format_timeout_error(
        self, request: MultiSearchRequest, timed_out_repos: List[str]
    ) -> str:
        """
        Format actionable timeout error message with recommendations (AC7).

        Args:
            request: Original multi-search request
            timed_out_repos: List of repository IDs that timed out

        Returns:
            Actionable error message with recommendations
        """
        recommendations = []

        # Recommend reducing repositories if many were queried
        if len(request.repositories) > MAX_RECOMMENDED_REPOS:
            recommendations.append(
                f"Reduce repositories from {len(request.repositories)} to {MAX_RECOMMENDED_REPOS} or fewer"
            )

        # Recommend adding filters if not present
        if not request.min_score:
            recommendations.append(
                f"Add --min-score {RECOMMENDED_MIN_SCORE} to filter low-relevance results"
            )

        if not request.path_filter:
            recommendations.append('Add --path-filter "*/src/*" to narrow scope')

        # Build error message
        error_msg = (
            f"Query timeout after {self.config.query_timeout_seconds} seconds. "
            f"Recommendations: {'; '.join(recommendations)}. "
            f"Timed out repositories: {', '.join(timed_out_repos)}"
        )

        return error_msg

    def shutdown(self):
        """Shutdown the executor and clean up resources."""
        self._shutdown = True
        self.thread_executor.shutdown(wait=True)
        logger.info("MultiSearchService shutdown complete")
