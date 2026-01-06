"""Staleness Detection for CIDX Remote Repository Linking Mode.

Implements Feature 5 Story 1: Local vs Remote Timestamp Comparison that provides
file-level staleness indicators comparing local file modifications with remote
index timestamps for better query result relevance assessment.
"""

import time
import logging
import datetime
import zoneinfo
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from pydantic import BaseModel, Field

from ..api_clients.remote_query_client import QueryResultItem

logger = logging.getLogger(__name__)


class StalenessDetectionError(Exception):
    """Exception raised when staleness detection fails."""

    pass


@dataclass
class CacheEntry:
    """Cache entry for file modification times."""

    mtime: Optional[float]
    cached_at: float
    ttl_seconds: float = 300  # 5 minutes default TTL

    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        return time.time() - self.cached_at > self.ttl_seconds


class EnhancedQueryResultItem(BaseModel):
    """Enhanced query result item with staleness metadata.

    Extends QueryResultItem with additional staleness detection fields while
    maintaining full backwards compatibility.
    """

    # All original QueryResultItem fields
    similarity_score: float = Field(
        ..., description="Relevance score between 0.0 and 1.0"
    )
    file_path: str = Field(..., description="Path to the file containing the result")
    line_number: int = Field(..., description="Line number")
    code_snippet: str = Field(..., description="Source code content")
    repository_alias: str = Field(..., description="Repository alias identifier")
    language: Optional[str] = Field(
        None, description="Programming language of the file"
    )
    file_last_modified: Optional[float] = Field(
        None, description="Unix timestamp when file was last modified"
    )
    indexed_timestamp: Optional[float] = Field(
        None, description="Unix timestamp when file was indexed"
    )

    # Additional staleness detection fields
    local_file_mtime: Optional[float] = Field(
        None, description="Local file modification time (stat result)"
    )
    is_stale: bool = Field(
        False, description="Whether local file is newer than remote index"
    )
    staleness_delta_seconds: Optional[float] = Field(
        None, description="Time difference between local and remote (seconds)"
    )
    staleness_indicator: str = Field("🟢", description="Visual staleness indicator")

    # Timezone metadata for debugging (Feature 5 Story 2)
    timezone_info: Optional[Dict[str, str]] = Field(
        None, description="Timezone information for debugging cross-timezone accuracy"
    )

    @classmethod
    def from_query_result(
        cls,
        query_result: QueryResultItem,
        local_file_mtime: Optional[float] = None,
        is_stale: bool = False,
        staleness_delta_seconds: Optional[float] = None,
        staleness_indicator: str = "🟢",
        timezone_info: Optional[Dict[str, str]] = None,
    ) -> "EnhancedQueryResultItem":
        """Create EnhancedQueryResultItem from QueryResultItem."""
        return cls(
            similarity_score=query_result.similarity_score,
            file_path=query_result.file_path,
            line_number=query_result.line_number,
            code_snippet=query_result.code_snippet,
            repository_alias=query_result.repository_alias,
            language=getattr(query_result, "language", None),
            file_last_modified=query_result.file_last_modified,
            indexed_timestamp=query_result.indexed_timestamp,
            local_file_mtime=local_file_mtime,
            is_stale=is_stale,
            staleness_delta_seconds=staleness_delta_seconds,
            staleness_indicator=staleness_indicator,
            timezone_info=timezone_info,
        )


class StalenessDetector:
    """Detects staleness of query results by comparing local file modifications
    with remote index timestamps.

    Provides file-level staleness indicators with configurable thresholds and
    performance-optimized caching to minimize filesystem operations.
    """

    def __init__(
        self, staleness_threshold_seconds: float = 0.0, cache_ttl_seconds: float = 300
    ):
        """Initialize staleness detector.

        Args:
            staleness_threshold_seconds: Minimum time difference to consider stale (default: 0.0)
            cache_ttl_seconds: Cache time-to-live in seconds (default: 300 = 5 minutes)
        """
        self.staleness_threshold_seconds = staleness_threshold_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self._file_mtime_cache: Dict[str, CacheEntry] = {}

        # Performance tracking
        self._cache_hits = 0
        self._cache_misses = 0
        self._file_stat_calls = 0

    def normalize_to_utc(
        self, timestamp: float, source_timezone: Optional[str] = None
    ) -> Optional[float]:
        """Normalize timestamp to UTC for timezone-independent comparison.

        Converts local system timestamps or timezone-specific timestamps to UTC
        to ensure accurate staleness detection across different timezone configurations.

        Args:
            timestamp: Unix timestamp to normalize
            source_timezone: Optional timezone string (e.g., "US/Eastern", "UTC")
                           If None, uses system local timezone

        Returns:
            UTC-normalized timestamp, or None if conversion fails

        Raises:
            No exceptions - handles errors gracefully by returning None or original timestamp
        """
        try:
            # Handle invalid timestamps
            if (
                timestamp is None or timestamp < 0 or timestamp > 4294967295
            ):  # Beyond year 2106
                logger.debug(f"Invalid timestamp for UTC normalization: {timestamp}")
                return None

            # Create datetime object from timestamp
            if source_timezone is None:
                # Use system local timezone - fromtimestamp already handles local time
                local_dt = datetime.datetime.fromtimestamp(timestamp)
                # Make it timezone-aware using system timezone
                local_dt_aware = local_dt.astimezone()
                # Convert to UTC
                utc_dt = local_dt_aware.astimezone(datetime.timezone.utc)
            else:
                # Use specified timezone
                try:
                    tz = zoneinfo.ZoneInfo(source_timezone)
                    # Create timezone-aware datetime in specified timezone
                    local_dt = datetime.datetime.fromtimestamp(timestamp, tz=tz)
                    # Convert to UTC
                    utc_dt = local_dt.astimezone(datetime.timezone.utc)
                except zoneinfo.ZoneInfoNotFoundError:
                    logger.debug(
                        f"Invalid timezone: {source_timezone}, falling back to system timezone"
                    )
                    # Fallback to system timezone
                    local_dt = datetime.datetime.fromtimestamp(timestamp)
                    local_dt_aware = local_dt.astimezone()
                    utc_dt = local_dt_aware.astimezone(datetime.timezone.utc)

            # Return UTC timestamp
            utc_timestamp = utc_dt.timestamp()
            logger.debug(f"Normalized timestamp {timestamp} -> {utc_timestamp} UTC")
            return utc_timestamp

        except Exception as e:
            logger.debug(f"Failed to normalize timestamp {timestamp} to UTC: {e}")
            # Return original timestamp as fallback
            return timestamp

    def _get_index_timestamp_utc(
        self, result: QueryResultItem, mode: str
    ) -> Optional[float]:
        """Get index timestamp for comparison based on execution mode.

        Args:
            result: Query result item
            mode: Execution mode ("local" or "remote")

        Returns:
            UTC-normalized timestamp for staleness comparison, or None if not available
        """
        if mode == "remote":
            # Remote mode: prefer indexed_timestamp from API, fallback to file_last_modified
            timestamp = result.indexed_timestamp
            if timestamp is None:
                timestamp = result.file_last_modified
        elif mode == "local":
            # Local mode: prefer file_last_modified, fallback to indexed_timestamp
            timestamp = result.file_last_modified
            if timestamp is None:
                timestamp = result.indexed_timestamp
        else:
            raise ValueError(f"Invalid mode: {mode}")

        # Normalize timestamp to UTC for timezone-independent comparison
        if timestamp is not None:
            return self.normalize_to_utc(timestamp)
        return None

    def apply_staleness_detection(
        self, results: List[QueryResultItem], project_root: Path, mode: str = "remote"
    ) -> List[EnhancedQueryResultItem]:
        """Apply staleness detection to query results for both local and remote modes.

        Compares local file modification times with index timestamps
        to provide staleness indicators for better relevance assessment.

        Args:
            results: List of query results from local or remote repository
            project_root: Path to project root directory
            mode: Query execution mode ("local" or "remote")

        Returns:
            List of enhanced query results with staleness metadata

        Raises:
            StalenessDetectionError: If staleness detection fails
            ValueError: If mode is not "local" or "remote"
        """
        if mode not in ("local", "remote"):
            raise ValueError(f"Invalid mode: {mode}. Must be 'local' or 'remote'.")
        if not results:
            return []

        start_time = time.time()
        enhanced_results = []

        try:
            # Batch file operations for performance
            file_paths = [result.file_path for result in results]
            local_mtimes = self._batch_file_stats(file_paths, project_root)

            for result in results:
                try:
                    local_mtime = local_mtimes.get(result.file_path)

                    # Get index timestamp based on mode
                    index_timestamp = self._get_index_timestamp_utc(result, mode)

                    # Calculate staleness
                    is_stale = self._is_result_stale(local_mtime, index_timestamp)
                    staleness_delta = self._calculate_staleness_delta(
                        local_mtime, index_timestamp
                    )
                    staleness_indicator = self._format_staleness_indicator(
                        is_stale, staleness_delta
                    )

                    # Create timezone metadata for debugging
                    timezone_info = {
                        "local_timezone": str(
                            datetime.datetime.now().astimezone().tzinfo
                        ),
                        "utc_normalized": "true",
                        "normalization_applied": (
                            "local_file_mtime" if local_mtime else "none"
                        ),
                        "execution_mode": mode,
                        "timestamp_source": (
                            "indexed_timestamp"
                            if mode == "remote" and result.indexed_timestamp is not None
                            else (
                                "file_last_modified"
                                if result.file_last_modified is not None
                                else "none"
                            )
                        ),
                    }

                    # Create enhanced result with timezone metadata
                    enhanced_result = EnhancedQueryResultItem.from_query_result(
                        query_result=result,
                        local_file_mtime=local_mtime,
                        is_stale=is_stale,
                        staleness_delta_seconds=staleness_delta,
                        staleness_indicator=staleness_indicator,
                        timezone_info=timezone_info,
                    )
                    enhanced_results.append(enhanced_result)

                except Exception as e:
                    logger.warning(
                        f"Failed to process staleness for {result.file_path}: {e}"
                    )
                    # Fallback: create enhanced result without staleness data
                    enhanced_result = EnhancedQueryResultItem.from_query_result(result)
                    enhanced_results.append(enhanced_result)

            # Sort results with staleness priority
            sorted_results = self._sort_with_staleness_priority(enhanced_results)

            # Performance logging
            processing_time = (time.time() - start_time) * 1000  # milliseconds
            logger.debug(
                f"Staleness detection completed in {processing_time:.2f}ms "
                f"for {len(results)} results. Cache hits: {self._cache_hits}, "
                f"misses: {self._cache_misses}"
            )

            # Ensure performance requirement is met
            if processing_time > 100:
                logger.warning(
                    f"Staleness detection took {processing_time:.2f}ms, "
                    "exceeds 100ms performance requirement"
                )

            return sorted_results

        except Exception as e:
            raise StalenessDetectionError(f"Failed to apply staleness detection: {e}")

    def _batch_file_stats(
        self, file_paths: List[str], project_root: Path
    ) -> Dict[str, Optional[float]]:
        """Batch file stat operations for performance optimization.

        Args:
            file_paths: List of relative file paths
            project_root: Project root directory

        Returns:
            Dictionary mapping file paths to modification times
        """
        results: Dict[str, Optional[float]] = {}

        for file_path in file_paths:
            try:
                # Use cached result if available
                cached_mtime = self._get_cached_file_mtime(file_path)
                if cached_mtime is not None:
                    results[file_path] = cached_mtime
                    self._cache_hits += 1
                    continue

                # Perform file stat and cache result
                absolute_path = project_root / file_path
                mtime = self._get_local_file_mtime(absolute_path)
                results[file_path] = mtime
                self._cache_file_mtime(file_path, mtime)
                self._cache_misses += 1

            except Exception as e:
                logger.debug(f"Failed to get mtime for {file_path}: {e}")
                results[file_path] = None

        return results

    def _get_local_file_mtime(self, file_path: Path) -> Optional[float]:
        """Get local file modification time with UTC normalization.

        Converts local file system timestamps to UTC for timezone-independent
        comparison with remote index timestamps.

        Args:
            file_path: Absolute path to file

        Returns:
            UTC-normalized file modification time or None if file doesn't exist/can't be accessed
        """
        try:
            if not file_path.exists():
                return None

            stat_result = file_path.stat()
            self._file_stat_calls += 1

            # Get local file modification time
            local_mtime = stat_result.st_mtime

            # Normalize to UTC for timezone-independent comparison
            utc_mtime = self.normalize_to_utc(local_mtime)

            return utc_mtime

        except (OSError, PermissionError) as e:
            logger.debug(f"Cannot access file {file_path}: {e}")
            return None

    def _get_cached_file_mtime(self, file_path: str) -> Optional[float]:
        """Get cached file modification time if available and not expired.

        Args:
            file_path: Relative file path

        Returns:
            Cached modification time or None if not cached/expired
        """
        cache_entry = self._file_mtime_cache.get(file_path)
        if cache_entry and not cache_entry.is_expired():
            return cache_entry.mtime
        elif cache_entry and cache_entry.is_expired():
            # Remove expired entry
            del self._file_mtime_cache[file_path]

        return None

    def _cache_file_mtime(self, file_path: str, mtime: Optional[float]):
        """Cache file modification time.

        Args:
            file_path: Relative file path
            mtime: File modification time to cache
        """
        self._file_mtime_cache[file_path] = CacheEntry(
            mtime=mtime, cached_at=time.time(), ttl_seconds=self.cache_ttl_seconds
        )

        # Prevent unbounded cache growth - keep last 1000 entries
        if len(self._file_mtime_cache) > 1000:
            # Remove oldest entries
            sorted_entries = sorted(
                self._file_mtime_cache.items(), key=lambda x: x[1].cached_at
            )
            # Keep newest 800 entries
            self._file_mtime_cache = dict(sorted_entries[-800:])

    def _is_result_stale(
        self, local_mtime: Optional[float], remote_timestamp: Optional[float]
    ) -> bool:
        """Determine if result is stale based on timestamp comparison.

        Args:
            local_mtime: Local file modification time
            remote_timestamp: Remote index timestamp

        Returns:
            True if local file is newer than remote index (stale)
        """
        if local_mtime is None or remote_timestamp is None:
            return False

        # Invalid timestamps
        if local_mtime < 0 or remote_timestamp < 0:
            return False

        time_difference = local_mtime - remote_timestamp
        return time_difference > self.staleness_threshold_seconds

    def _calculate_staleness_delta(
        self, local_mtime: Optional[float], remote_timestamp: Optional[float]
    ) -> Optional[float]:
        """Calculate staleness delta in seconds.

        Args:
            local_mtime: Local file modification time
            remote_timestamp: Remote index timestamp

        Returns:
            Time difference in seconds (positive if local is newer)
        """
        if local_mtime is None or remote_timestamp is None:
            return None

        if local_mtime < 0 or remote_timestamp < 0:
            return None

        return local_mtime - remote_timestamp

    def _format_staleness_indicator(
        self, is_stale: bool, delta_seconds: Optional[float]
    ) -> str:
        """Format visual staleness indicator based on staleness level.

        Args:
            is_stale: Whether result is stale
            delta_seconds: Time difference in seconds

        Returns:
            Visual staleness indicator with emoji and description
        """
        if not is_stale or delta_seconds is None:
            return "🟢 Fresh"

        if delta_seconds <= 0:
            return "🟢 Fresh"

        # Convert seconds to hours for readability
        hours = delta_seconds / 3600

        if hours <= 1:
            # 0-1 hour: slightly stale
            minutes = int(delta_seconds / 60)
            return f"🟡 {minutes}m stale"
        elif hours <= 24:
            # 1-24 hours: moderately stale
            hours_rounded = int(hours)
            return f"🟠 {hours_rounded}h stale"
        else:
            # >24 hours: significantly stale
            days = int(hours / 24)
            if days == 1:
                return "🔴 1d stale"
            else:
                return f"🔴 {days}d stale"

    def _sort_with_staleness_priority(
        self, results: List[EnhancedQueryResultItem]
    ) -> List[EnhancedQueryResultItem]:
        """Sort results prioritizing fresh results while maintaining score order.

        Fresh results with high scores are prioritized over stale results with
        similar scores to improve result relevance.

        Args:
            results: List of enhanced query results

        Returns:
            Sorted list with staleness priority applied
        """

        def staleness_sort_key(result: EnhancedQueryResultItem) -> Tuple[bool, float]:
            # Sort by: (is_stale, -score)
            # This puts fresh results first, then sorts by descending score within each group
            return (result.is_stale, -result.similarity_score)

        return sorted(results, key=staleness_sort_key)

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics for performance monitoring.

        Returns:
            Dictionary with cache hit/miss statistics
        """
        return {
            "cache_size": len(self._file_mtime_cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "file_stat_calls": self._file_stat_calls,
        }

    def clear_cache(self):
        """Clear the file modification time cache."""
        self._file_mtime_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        self._file_stat_calls = 0
