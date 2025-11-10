"""TemporalSearchService - Temporal queries with time-range filtering.

Provides semantic search with temporal filtering capabilities:
- Time-range queries using JSON payloads (no SQLite)
- Diff-based temporal indexing support
- Performance-optimized batch queries
- Query-time git reconstruction for added/deleted files
"""

import time
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any, cast
from dataclasses import dataclass

# GitBlobReader removed - diff-based indexing doesn't use blob reading

logger = logging.getLogger(__name__)


@dataclass
class TemporalSearchResult:
    """Single temporal search result with temporal context."""

    file_path: str
    chunk_index: int
    content: str
    score: float
    metadata: Dict[str, Any]
    temporal_context: Dict[str, Any]


@dataclass
class TemporalSearchResults:
    """Complete temporal search results with metadata."""

    results: List[TemporalSearchResult]
    query: str
    filter_type: str
    filter_value: Any
    total_found: int = 0
    performance: Optional[Dict[str, float]] = None
    warning: Optional[str] = None


class TemporalSearchService:
    """Service for temporal semantic search with date filtering."""

    # Temporal collection name - must match TemporalIndexer
    TEMPORAL_COLLECTION_NAME = "code-indexer-temporal"

    def __init__(
        self,
        config_manager,
        project_root: Path,
        vector_store_client=None,
        embedding_provider=None,
        collection_name: Optional[str] = None,
    ):
        """Initialize temporal search service.

        Args:
            config_manager: ConfigManager instance
            project_root: Project root directory
            vector_store_client: Vector store client (FilesystemVectorStore or QdrantClient), optional for checking index
            embedding_provider: Embedding provider for generating query embeddings, optional for checking index
            collection_name: Collection name for vector search, optional for checking index
        """
        self.config_manager = config_manager
        self.project_root = Path(project_root)
        self.temporal_dir = self.project_root / ".code-indexer" / "index" / "temporal"
        # commits_db_path removed - Story 2: No SQLite, all data from JSON payloads
        self.vector_store_client = vector_store_client
        self.embedding_provider = embedding_provider
        # Ensure collection_name is always a string (empty string if None)
        self.collection_name = collection_name or ""

    def _get_file_path_from_payload(
        self, payload: Dict[str, Any], default: str = "unknown"
    ) -> str:
        """Get file path from payload, checking both 'path' and 'file_path' fields.

        Args:
            payload: Payload dictionary from vector search result
            default: Default value if neither field exists

        Returns:
            File path string, preferring 'path' over 'file_path'
        """
        return str(payload.get("path") or payload.get("file_path", default))

    def has_temporal_index(self) -> bool:
        """Check if temporal index exists.

        Story 2: With diff-based indexing, check for temporal collection
        instead of commits.db (which no longer exists).

        Returns:
            True if temporal collection exists
        """
        # Story 2: Check for temporal collection instead of commits.db
        if self.vector_store_client:
            return bool(
                self.vector_store_client.collection_exists(
                    self.TEMPORAL_COLLECTION_NAME
                )
            )
        return False

    def _validate_date_range(self, date_range: str) -> Tuple[str, str]:
        """Validate and parse date range format.

        Args:
            date_range: Date range string in format YYYY-MM-DD..YYYY-MM-DD

        Returns:
            Tuple of (start_date, end_date)

        Raises:
            ValueError: If date range format is invalid
        """
        if ".." not in date_range:
            raise ValueError(
                "Time range must use '..' separator (format: YYYY-MM-DD..YYYY-MM-DD)"
            )

        parts = date_range.split("..")
        if len(parts) != 2:
            raise ValueError(
                "Time range must use '..' separator (format: YYYY-MM-DD..YYYY-MM-DD)"
            )

        start_date, end_date = parts

        # Validate date formats
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD (e.g., 2023-01-01)")

        # Ensure dates match strict format (YYYY-MM-DD with zero padding)
        if start_date != start_dt.strftime("%Y-%m-%d") or end_date != end_dt.strftime(
            "%Y-%m-%d"
        ):
            raise ValueError(
                "Invalid date format. Use YYYY-MM-DD with zero-padded month/day (e.g., 2023-01-01)"
            )

        # Validate end date is after start date
        if end_dt < start_dt:
            raise ValueError("End date must be after start date")

        return start_date, end_date

    def _calculate_over_fetch_multiplier(self, limit: int) -> int:
        """Calculate smart over-fetch multiplier based on limit size.

        Strategy:
        - Small limits (1-5): Need high headroom → 20x multiplier
        - Medium limits (6-10): Moderate headroom → 15x multiplier
        - Large limits (11-20): Less headroom → 10x multiplier
        - Very large limits (21+): Minimal headroom → 5x multiplier

        Rationale:
        - Temporal filtering removes results that fall outside date range
        - Removed code filtering further reduces results
        - Smaller limits need proportionally more over-fetch to ensure enough results
        - Larger limits already fetch many results, less multiplicative headroom needed

        Args:
            limit: User-requested result limit

        Returns:
            Over-fetch multiplier (5x to 20x)
        """
        if limit <= 5:
            return 20  # Small limits: high headroom
        elif limit <= 10:
            return 15  # Medium limits: moderate headroom
        elif limit <= 20:
            return 10  # Large limits: lower headroom
        else:
            return 5  # Very large limits: minimal headroom

    def _reconstruct_temporal_content(self, metadata: Dict[str, Any]) -> str:
        """Reconstruct content from git for added/deleted files.

        This method completes the storage optimization by reconstructing file content
        from git at query time for added/deleted files that use pointer-based storage
        (88% storage reduction).

        Args:
            metadata: Payload metadata with reconstruct_from_git marker

        Returns:
            Reconstructed file content or error message
        """
        # Check if reconstruction needed
        if not metadata.get("reconstruct_from_git"):
            return ""

        diff_type = metadata.get("diff_type")
        # Handle both 'path' and 'file_path' keys (different parts of the system use different names)
        path = metadata.get("path") or metadata.get("file_path", "")

        if diff_type == "added":
            # Fetch from commit where file was added
            commit_hash = metadata["commit_hash"]
            cmd = ["git", "show", f"{commit_hash}:{path}"]

        elif diff_type == "deleted":
            # Fetch from parent commit (before deletion)
            parent = metadata.get("parent_commit_hash")
            if not parent:
                return "[Content unavailable - parent commit not tracked]"
            cmd = ["git", "show", f"{parent}:{path}"]

        else:
            # Shouldn't happen but graceful fallback
            return ""

        # Execute git show
        result_proc = subprocess.run(
            cmd,
            cwd=self.project_root,
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )

        if result_proc.returncode == 0:
            return result_proc.stdout
        else:
            # Graceful error handling - truncate stderr to avoid log spam
            error_msg = (
                result_proc.stderr[:100] if result_proc.stderr else "unknown error"
            )
            return f"[Content unavailable - git error: {error_msg}]"

    def query_temporal(
        self,
        query: str,
        time_range: Tuple[str, str],
        diff_types: Optional[List[str]] = None,
        author: Optional[str] = None,
        limit: int = 10,
        min_score: Optional[float] = None,
        language: Optional[List[str]] = None,
        exclude_language: Optional[List[str]] = None,
        path_filter: Optional[List[str]] = None,
        exclude_path: Optional[List[str]] = None,
    ) -> TemporalSearchResults:
        """Execute temporal semantic search with time-range filtering.

        Args:
            query: Search query text
            time_range: Tuple of (start_date, end_date) in YYYY-MM-DD format
            diff_types: Filter by diff type(s) (e.g., ["added", "modified", "deleted"])
            limit: Maximum results to return
            min_score: Minimum similarity score
            language: Filter by language(s) (e.g., ["python", "javascript"])
            exclude_language: Exclude language(s) (e.g., ["markdown"])
            path_filter: Filter by path pattern(s) (e.g., ["src/*"])
            exclude_path: Exclude path pattern(s) (e.g., ["*/tests/*"])

        Returns:
            TemporalSearchResults with filtered results
        """
        # Ensure dependencies are available
        if not self.vector_store_client or not self.embedding_provider:
            raise RuntimeError(
                "TemporalSearchService not fully initialized. "
                "Vector store client and embedding provider required for queries."
            )

        # Build filter conditions using same logic as regular semantic search
        from ...services.language_mapper import LanguageMapper
        from ...services.path_filter_builder import PathFilterBuilder

        filter_conditions: Dict[str, Any] = {}

        # Language inclusion filters
        if language:
            language_mapper = LanguageMapper()
            must_conditions = []
            for lang in language:
                language_filter = language_mapper.build_language_filter(lang)
                must_conditions.append(language_filter)
            if must_conditions:
                filter_conditions["must"] = must_conditions

        # Path inclusion filters
        if path_filter:
            for path_pattern in path_filter:
                filter_conditions.setdefault("must", []).append(
                    {"key": "path", "match": {"text": path_pattern}}
                )

        # Language exclusion filters
        if exclude_language:
            language_mapper = LanguageMapper()
            must_not_conditions = []
            for exclude_lang in exclude_language:
                extensions = language_mapper.get_extensions(exclude_lang)
                for ext in extensions:
                    must_not_conditions.append(
                        {"key": "language", "match": {"value": ext}}
                    )
            if must_not_conditions:
                filter_conditions["must_not"] = must_not_conditions

        # Path exclusion filters
        if exclude_path:
            path_filter_builder = PathFilterBuilder()
            path_exclusion_filters = path_filter_builder.build_exclusion_filter(
                list(exclude_path)
            )
            if path_exclusion_filters.get("must_not"):
                if "must_not" in filter_conditions:
                    filter_conditions["must_not"].extend(
                        path_exclusion_filters["must_not"]
                    )
                else:
                    filter_conditions["must_not"] = path_exclusion_filters["must_not"]

        # Phase 1: Semantic search (over-fetch for filtering headroom)
        start_time = time.time()

        # Calculate smart over-fetch multiplier based on limit size
        multiplier = self._calculate_over_fetch_multiplier(limit)

        # Execute vector search using the same pattern as regular query command
        from ...storage.filesystem_vector_store import FilesystemVectorStore

        if isinstance(self.vector_store_client, FilesystemVectorStore):
            # Parallel execution: embedding generation + index loading happen concurrently
            # Always request timing for consistent return type handling
            search_result = self.vector_store_client.search(
                query=query,  # Pass query text for parallel embedding
                embedding_provider=self.embedding_provider,  # Provider for parallel execution
                filter_conditions=filter_conditions,  # Apply user-specified filters (language, path, etc.)
                limit=limit
                * multiplier,  # Smart over-fetch based on limit size (5x to 20x)
                collection_name=self.collection_name,
                return_timing=True,
            )
            # Type: Tuple[List[Dict[str, Any]], Dict[str, Any]] when return_timing=True
            raw_results, _timing_info = search_result  # type: ignore
        else:
            # QdrantClient: pre-compute embedding (no parallel support yet)
            query_embedding = self.embedding_provider.get_embedding(query)
            raw_results = self.vector_store_client.search(
                query_vector=query_embedding,
                filter_conditions=filter_conditions,  # Apply user-specified filters (language, path, etc.)
                limit=limit
                * multiplier,  # Smart over-fetch based on limit size (5x to 20x)
                collection_name=self.collection_name,
            )

        semantic_time = time.time() - start_time

        if not raw_results:
            return TemporalSearchResults(
                results=[],
                query=query,
                filter_type="time_range",
                filter_value=time_range,
                performance={
                    "semantic_search_ms": semantic_time * 1000,
                    "temporal_filter_ms": 0,
                    "blob_fetch_ms": 0,
                    "total_ms": semantic_time * 1000,
                },
            )

        # Phase 2: Temporal filtering using JSON payloads
        filter_start = time.time()
        # Type assertion: raw_results is guaranteed to be List[Dict[str, Any]] at this point
        temporal_results, blob_fetch_time_ms = self._filter_by_time_range(
            semantic_results=cast(List[Dict[str, Any]], raw_results),
            start_date=time_range[0],
            end_date=time_range[1],
            min_score=min_score,
        )
        filter_time = time.time() - filter_start

        # Phase 3: Filter by diff_types if specified
        if diff_types:
            temporal_results = [
                r for r in temporal_results if r.metadata.get("diff_type") in diff_types
            ]

        # Phase 3b: Filter by author if specified
        if author:
            author_lower = author.lower()
            temporal_results = [
                r
                for r in temporal_results
                if author_lower in r.metadata.get("author_name", "").lower()
                or author_lower in r.metadata.get("author_email", "").lower()
            ]

        # Phase 4: Sort reverse chronologically (newest to oldest, like git log)
        # With diff-based indexing, all results are changes - no filtering needed
        temporal_results = sorted(
            temporal_results,
            key=lambda r: r.temporal_context.get("commit_timestamp", 0),
            reverse=True,  # Newest first
        )

        # Results reverse chronologically sorted (newest first) like git log
        # No need to sort by score - temporal queries show evolution, not relevance

        return TemporalSearchResults(
            results=temporal_results[:limit],
            query=query,
            filter_type="time_range",
            filter_value=time_range,
            total_found=len(temporal_results),
            performance={
                "semantic_search_ms": semantic_time * 1000,
                "temporal_filter_ms": filter_time * 1000,
                "blob_fetch_ms": blob_fetch_time_ms,
                "total_ms": (semantic_time + filter_time) * 1000,
            },
        )

    def _fetch_match_content(self, payload: Dict[str, Any]) -> str:
        """Fetch content based on match type.

        Story 2: No blob fetching - content comes from payload directly.

        Args:
            payload: Match payload with content

        Returns:
            Content string for display
        """
        match_type = payload.get("type", "file_chunk")

        if match_type == "file_chunk":
            # Story 2: Content is in payload, not fetched from blobs
            content = payload.get("content", "")
            if content:
                return str(content)

            # Check if binary file
            file_path = self._get_file_path_from_payload(payload, "")
            file_ext = Path(file_path).suffix.lower()
            binary_extensions = {
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".pdf",
                ".zip",
                ".tar",
                ".gz",
                ".so",
                ".dylib",
                ".dll",
                ".exe",
            }
            if file_ext in binary_extensions:
                return f"[Binary file - {file_ext}]"

            # Fallback if no content in payload
            return "[Content not available]"

        elif match_type == "commit_message":
            # Fetch commit message from SQLite
            commit_hash = payload.get("commit_hash", "")
            char_start = payload.get("char_start", 0)
            char_end = payload.get("char_end", 0)

            try:
                commit_details = self._fetch_commit_details(commit_hash)
                if not commit_details:
                    return "[Commit message not found]"

                # Extract chunk of commit message
                message = str(commit_details["message"])
                if char_end > 0:
                    return message[char_start:char_end]
                else:
                    return message

            except Exception as e:
                logger.warning(f"Failed to fetch commit message {commit_hash[:7]}: {e}")
                return f"[⚠️ Commit message not found - {commit_hash[:7]}]"

        elif match_type == "commit_diff":
            # Story 2: Handle diff-based payloads
            # For now, return a placeholder indicating the diff type
            diff_type = payload.get("diff_type", "unknown")
            file_path = self._get_file_path_from_payload(payload, "unknown")
            return f"[{diff_type.upper()} file: {file_path}]"

        else:
            return "[Unknown match type]"

    def _filter_by_time_range(
        self,
        semantic_results: List[Dict[str, Any]],
        start_date: str,
        end_date: str,
        min_score: Optional[float] = None,
    ) -> Tuple[List[TemporalSearchResult], float]:
        """Filter semantic results by date range using JSON payloads.

        Story 2: Complete SQLite removal - all filtering done using
        commit metadata stored in JSON payloads during indexing.

        In diff-based indexing, all results are changes (added/modified/deleted/renamed/binary).
        Deleted files are automatically included with diff_type="deleted".

        Args:
            semantic_results: Results from semantic search (raw vector store format)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            min_score: Minimum similarity score filter

        Returns:
            Tuple of (filtered results, blob_fetch_time_ms)
        """
        # Convert dates to Unix timestamps
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59
        )
        end_ts = int(end_dt.timestamp())

        filtered_results = []

        # Process each semantic result
        for result in semantic_results:
            # Get payload - handles both dict and object formats
            payload = (
                result.get("payload", {})
                if isinstance(result, dict)
                else getattr(result, "payload", {})
            )
            score = (
                result.get("score", 0.0)
                if isinstance(result, dict)
                else getattr(result, "score", 0.0)
            )

            # Storage optimization: Reconstruct content from git for added/deleted files
            if payload.get("reconstruct_from_git"):
                content = self._reconstruct_temporal_content(payload)
            else:
                # Content is in chunk_text at root level (Bug 1 fix in filesystem_vector_store)
                # Handle both dict and object formats
                chunk_text = None
                if isinstance(result, dict):
                    chunk_text = result.get("chunk_text", None)
                elif hasattr(result, "chunk_text") and not callable(getattr(result, "chunk_text")):
                    # Only use chunk_text if it's actually set (not a Mock auto-attribute)
                    try:
                        chunk_text = result.chunk_text
                    except AttributeError:
                        chunk_text = None

                if chunk_text is not None:
                    content = chunk_text
                else:
                    # FAIL FAST - optimization contract broken or index corrupted
                    # No backward compatibility fallbacks (Messi Rule #2)
                    commit_hash = payload.get("commit_hash", "unknown")
                    path = payload.get("path", "unknown")
                    raise RuntimeError(
                        f"Missing chunk_text for {commit_hash}:{path} - "
                        f"optimization contract violated or index corrupted"
                    )

            # Apply min_score filter if specified
            if min_score and score < min_score:
                continue

            # Check if payload has temporal data
            commit_timestamp = payload.get("commit_timestamp")

            # Filter by timestamp range
            if commit_timestamp and start_ts <= commit_timestamp <= end_ts:
                # Create temporal result from payload data
                # Check both "path" and "file_path" - temporal indexer uses "path"
                temporal_result = TemporalSearchResult(
                    file_path=self._get_file_path_from_payload(payload, "unknown"),
                    chunk_index=payload.get("chunk_index", 0),
                    content=content,  # Now uses actual content from payload
                    score=score,
                    metadata=payload,  # Store full payload as metadata
                    temporal_context={
                        "commit_hash": payload.get("commit_hash"),
                        "commit_date": payload.get("commit_date"),
                        "commit_message": payload.get("commit_message"),
                        "author_name": payload.get("author_name"),
                        "commit_timestamp": commit_timestamp,
                        "diff_type": payload.get("diff_type"),
                    },
                )
                filtered_results.append(temporal_result)

        # Return results and 0 blob fetch time (no blob fetching in JSON approach)
        return filtered_results, 0.0

    # _get_head_file_blobs method removed - Story 2: SQLite elimination
    # No longer needed with diff-based indexing (blob-based helper)

    def _fetch_commit_details(self, commit_hash: str) -> Optional[Dict[str, Any]]:
        """Fetch commit details - deprecated, returns dummy data.

        Story 2: SQLite removed. This method is only called from CLI display
        functions and should be refactored to use payload data instead.

        Returns:
            Dict with basic commit info for backward compatibility
        """
        # Return minimal data for backward compatibility
        # The CLI should be updated to use payload data directly
        return {
            "hash": commit_hash,
            "date": "Unknown",
            "author_name": "Unknown",
            "author_email": "unknown@example.com",
            "message": "[Commit details not available - use payload data]",
        }

    # _is_new_file method removed - Story 2: SQLite elimination
    # No longer needed with diff-based indexing

    # filter_timeline_changes method removed - Story 2: diff-based indexing
    # Every result is a change by definition, no filtering needed

    # _generate_chunk_diff method removed - Story 2: SQLite elimination
    # No longer needed with diff-based indexing where diffs are pre-computed
