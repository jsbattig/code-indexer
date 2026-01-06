"""
LogAggregatorService - Backend service for querying logs from SQLite database.

Implements AC6: LogAggregatorService Backend
- Query method with pagination support
- Count method for total records
- Filtering by level, source, correlation_id
- Sorting (ascending/descending)
- Consistent response format across Web UI, REST API, and MCP API
- Handles empty database gracefully
"""

import logging
import math
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from code_indexer.server.middleware.correlation import get_correlation_id

logger = logging.getLogger(__name__)


class LogAggregatorService:
    """
    Backend service for querying operational logs from SQLite database.

    Provides consistent interface for Web UI, REST API, and MCP API to query logs
    with pagination, filtering, and sorting capabilities.

    Response Format (matches API spec from issue #664):
        {
            "logs": [
                {
                    "id": 123,
                    "timestamp": "2025-01-02T10:30:00Z",
                    "level": "ERROR",
                    "source": "auth.oidc",
                    "message": "SSO authentication failed",
                    "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                    "user_id": "admin@example.com",
                    "request_path": "/auth/sso/callback"
                }
            ],
            "pagination": {
                "page": 1,
                "page_size": 50,
                "total": 1234,
                "total_pages": 25
            }
        }
    """

    DEFAULT_PAGE_SIZE = 50
    MAX_PAGE_SIZE = 1000

    def __init__(self, db_path: Path):
        """
        Initialize LogAggregatorService.

        Args:
            db_path: Path to SQLite logs database (e.g., ~/.cidx-server/logs.db)
        """
        self.db_path = Path(db_path)

    def query(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        sort_order: str = "desc",
        level: Optional[str] = None,
        levels: Optional[List[str]] = None,
        source: Optional[str] = None,
        correlation_id: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Query logs with pagination, filtering, and sorting.

        Args:
            page: Page number (1-indexed, default 1)
            page_size: Number of logs per page (default 50, max 1000)
            sort_order: Sort order - "asc" or "desc" (default "desc" = newest first)
            level: Filter by single log level (optional, for backward compatibility)
            levels: Filter by multiple log levels (optional, takes precedence over level)
            source: Filter by logger name (optional)
            correlation_id: Filter by correlation ID (optional)
            search: Text search across message and correlation_id (optional, case-insensitive)

        Returns:
            Dict with "logs" array and "pagination" metadata matching API spec
        """
        # Normalize parameters
        page = max(1, page)  # Ensure page >= 1

        # Handle page_size: 0 or negative => use default, otherwise clamp to [1, MAX]
        if page_size <= 0:
            page_size = self.DEFAULT_PAGE_SIZE
        else:
            page_size = min(page_size, self.MAX_PAGE_SIZE)

        # Check if database exists
        if not self.db_path.exists():
            return self._empty_response(page, page_size)

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row  # Enable column access by name
            cursor = conn.cursor()

            # Build WHERE clause for filtering
            where_sql, params = self._build_where_clause(
                level, levels, source, correlation_id, search
            )

            # Get total count
            total = self._get_total_count(cursor, where_sql, params)

            # Calculate pagination
            total_pages = math.ceil(total / page_size) if total > 0 else 0
            offset = (page - 1) * page_size

            # Query logs with sorting and pagination
            logs = self._query_logs(cursor, where_sql, params, sort_order, page_size, offset)

            conn.close()

            return {
                "logs": logs,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": total_pages,
                },
            }

        except sqlite3.Error as e:
            # Log error for debugging but return graceful empty response
            logger.error(f"Database error querying logs: {e}", exc_info=True, extra={"correlation_id": get_correlation_id()})
            return self._empty_response(page, page_size)

    def query_all(
        self,
        sort_order: str = "desc",
        level: Optional[str] = None,
        levels: Optional[List[str]] = None,
        source: Optional[str] = None,
        correlation_id: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query all logs without pagination (for export functionality).

        Args:
            sort_order: Sort order - "asc" or "desc" (default "desc" = newest first)
            level: Filter by single log level (optional, for backward compatibility)
            levels: Filter by multiple log levels (optional, takes precedence over level)
            source: Filter by logger name (optional)
            correlation_id: Filter by correlation ID (optional)
            search: Text search across message and correlation_id (optional, case-insensitive)

        Returns:
            List of log entry dicts (not paginated)
        """
        # Check if database exists
        if not self.db_path.exists():
            return []

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row  # Enable column access by name
            cursor = conn.cursor()

            # Build WHERE clause for filtering (reuse existing logic)
            where_sql, params = self._build_where_clause(
                level, levels, source, correlation_id, search
            )

            # Query all logs with sorting (no LIMIT/OFFSET)
            logs = self._query_logs_all(cursor, where_sql, params, sort_order)

            conn.close()

            return logs

        except sqlite3.Error as e:
            # Log error for debugging but return empty list
            logger.error(f"Database error querying all logs: {e}", exc_info=True, extra={"correlation_id": get_correlation_id()})
            return []

    def count(self) -> int:
        """
        Count total number of log records in database.

        Returns:
            Total count of log records
        """
        if not self.db_path.exists():
            return 0

        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM logs")
            total = int(cursor.fetchone()[0])
            conn.close()
            return total

        except sqlite3.Error as e:
            # Log error for debugging but return 0
            logger.error(f"Database error counting logs: {e}", exc_info=True, extra={"correlation_id": get_correlation_id()})
            return 0

    def close(self) -> None:
        """Close service and cleanup resources."""
        # No persistent connections to close
        # This method exists for interface consistency and future expansion
        pass

    def _build_where_clause(
        self,
        level: Optional[str],
        levels: Optional[List[str]],
        source: Optional[str],
        correlation_id: Optional[str],
        search: Optional[str],
    ) -> Tuple[str, List[Any]]:
        """
        Build WHERE clause and parameters for filtering.

        Args:
            level: Filter by single log level (optional, for backward compatibility)
            levels: Filter by multiple log levels (optional, takes precedence over level)
            source: Filter by logger name (optional)
            correlation_id: Filter by correlation ID (optional)
            search: Text search across message and correlation_id (optional, case-insensitive)

        Returns:
            Tuple of (WHERE SQL string, parameters list)
        """
        where_clauses: List[str] = []
        params: List[Any] = []

        # Handle level filtering (support both single level and multiple levels)
        # 'levels' takes precedence over 'level' for backward compatibility
        if levels is not None and len(levels) > 0:
            # Multiple levels - use IN clause
            placeholders = ",".join(["?"] * len(levels))
            where_clauses.append(f"level IN ({placeholders})")
            params.extend(levels)
        elif level:
            # Single level - use equality
            where_clauses.append("level = ?")
            params.append(level)

        if source:
            where_clauses.append("source = ?")
            params.append(source)

        if correlation_id:
            where_clauses.append("correlation_id = ?")
            params.append(correlation_id)

        # Handle text search (case-insensitive search across message and correlation_id)
        if search:
            # Use LIKE with wildcards for substring matching (case-insensitive in SQLite)
            # Search in both message and correlation_id fields
            where_clauses.append(
                "(message LIKE ? OR correlation_id LIKE ?)"
            )
            search_pattern = f"%{search}%"
            params.append(search_pattern)
            params.append(search_pattern)

        where_sql = ""
        if where_clauses:
            where_sql = " WHERE " + " AND ".join(where_clauses)

        return where_sql, params

    def _get_total_count(
        self, cursor: sqlite3.Cursor, where_sql: str, params: List[Any]
    ) -> int:
        """
        Get total count of logs matching filter criteria.

        Args:
            cursor: Database cursor
            where_sql: WHERE clause SQL
            params: Query parameters

        Returns:
            Total count of matching logs
        """
        count_query = f"SELECT COUNT(*) FROM logs{where_sql}"
        cursor.execute(count_query, params)
        return int(cursor.fetchone()[0])

    def _query_logs(
        self,
        cursor: sqlite3.Cursor,
        where_sql: str,
        params: List[Any],
        sort_order: str,
        limit: int,
        offset: int,
    ) -> List[Dict[str, Any]]:
        """
        Query logs with sorting and pagination.

        Args:
            cursor: Database cursor
            where_sql: WHERE clause SQL
            params: Query parameters
            sort_order: Sort order ("asc" or "desc")
            limit: Number of results to return
            offset: Number of results to skip

        Returns:
            List of log entry dicts
        """
        order_direction = "DESC" if sort_order == "desc" else "ASC"
        query = f"""
            SELECT
                id,
                timestamp,
                level,
                source,
                message,
                correlation_id,
                user_id,
                request_path
            FROM logs
            {where_sql}
            ORDER BY timestamp {order_direction}
            LIMIT ? OFFSET ?
        """

        query_params = params + [limit, offset]
        cursor.execute(query, query_params)
        rows = cursor.fetchall()

        # Convert rows to list of dicts
        logs = []
        for row in rows:
            log_entry = self._row_to_dict(row)
            logs.append(log_entry)

        return logs

    def _query_logs_all(
        self,
        cursor: sqlite3.Cursor,
        where_sql: str,
        params: List[Any],
        sort_order: str,
    ) -> List[Dict[str, Any]]:
        """
        Query all logs with sorting (no pagination).

        Args:
            cursor: Database cursor
            where_sql: WHERE clause SQL
            params: Query parameters
            sort_order: Sort order ("asc" or "desc")

        Returns:
            List of all matching log entry dicts
        """
        order_direction = "DESC" if sort_order == "desc" else "ASC"
        query = f"""
            SELECT
                id,
                timestamp,
                level,
                source,
                message,
                correlation_id,
                user_id,
                request_path
            FROM logs
            {where_sql}
            ORDER BY timestamp {order_direction}
        """

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # Convert rows to list of dicts
        logs = []
        for row in rows:
            log_entry = self._row_to_dict(row)
            logs.append(log_entry)

        return logs

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """
        Convert database row to log entry dict.

        Args:
            row: SQLite row object

        Returns:
            Log entry dict matching API format
        """
        return {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "level": row["level"],
            "source": row["source"],
            "message": row["message"],
            "correlation_id": row["correlation_id"],
            "user_id": row["user_id"],
            "request_path": row["request_path"],
        }

    def _empty_response(self, page: int, page_size: int) -> Dict[str, Any]:
        """
        Generate empty response with pagination metadata.

        Args:
            page: Current page number
            page_size: Page size

        Returns:
            Empty response matching API format
        """
        return {
            "logs": [],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": 0,
                "total_pages": 0,
            },
        }
