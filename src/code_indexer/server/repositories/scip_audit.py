"""
SCIP Audit Repository for Dependency Installation Tracking.

Provides audit trail for SCIP dependency installations with project context.
Part of AC3: Audit Table for Dependency Installations with Project Context (Story #646).
"""

import sqlite3
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple


class SCIPAuditRepository:
    """
    Repository for managing SCIP dependency installation audit records.

    Provides atomic record creation and comprehensive querying capabilities
    for tracking dependency installations across projects and languages.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize SCIP Audit Repository.

        Args:
            db_path: Path to SQLite database (defaults to ~/.cidx-server/scip_audit.db)
        """
        self._lock = threading.Lock()

        # Set database path with fallback to user home directory
        if db_path:
            self.db_path = Path(db_path)
        else:
            server_dir = Path.home() / ".cidx-server"
            server_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = server_dir / "scip_audit.db"

        # Ensure database directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database schema
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database schema for audit records."""
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            # Create scip_dependency_installations table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scip_dependency_installations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    job_id VARCHAR(36) NOT NULL,
                    repo_alias VARCHAR(255) NOT NULL,
                    project_path VARCHAR(255),
                    project_language VARCHAR(50),
                    project_build_system VARCHAR(50),
                    package VARCHAR(255) NOT NULL,
                    command TEXT NOT NULL,
                    reasoning TEXT,
                    username VARCHAR(255)
                )
            """
            )

            # Create indexes for efficient querying
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON scip_dependency_installations (timestamp)
            """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_repo_alias
                ON scip_dependency_installations (repo_alias)
            """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_job_id
                ON scip_dependency_installations (job_id)
            """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_project_language
                ON scip_dependency_installations (project_language)
            """
            )

            conn.commit()

    def create_audit_record(
        self,
        job_id: str,
        repo_alias: str,
        package: str,
        command: str,
        project_path: Optional[str] = None,
        project_language: Optional[str] = None,
        project_build_system: Optional[str] = None,
        reasoning: Optional[str] = None,
        username: Optional[str] = None,
    ) -> int:
        """
        Create an audit record for a dependency installation.

        Atomic write operation - record is immediately queryable after insertion.

        Args:
            job_id: Background job ID that triggered installation
            repo_alias: Repository alias being processed
            package: Package name that was installed
            command: Full installation command executed
            project_path: Project path within repository (optional)
            project_language: Programming language (optional)
            project_build_system: Build system used (optional)
            reasoning: Claude's reasoning for installation (optional)
            username: User who triggered the job (optional)

        Returns:
            Record ID of created audit record

        Raises:
            sqlite3.Error: If database operation fails
        """
        with self._lock:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO scip_dependency_installations
                    (job_id, repo_alias, project_path, project_language,
                     project_build_system, package, command, reasoning, username)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        job_id,
                        repo_alias,
                        project_path,
                        project_language,
                        project_build_system,
                        package,
                        command,
                        reasoning,
                        username,
                    ),
                )
                record_id = cursor.lastrowid
                conn.commit()
                assert record_id is not None, "Failed to get record ID after INSERT"
                return record_id

    def query_audit_records(
        self,
        job_id: Optional[str] = None,
        repo_alias: Optional[str] = None,
        project_language: Optional[str] = None,
        project_build_system: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Query audit records with filtering and pagination.

        Args:
            job_id: Filter by job ID (optional)
            repo_alias: Filter by repository alias (optional)
            project_language: Filter by project language (optional)
            project_build_system: Filter by build system (optional)
            since: Filter records after this ISO timestamp (optional)
            until: Filter records before this ISO timestamp (optional)
            limit: Maximum records to return (default: 100)
            offset: Number of records to skip (default: 0)

        Returns:
            Tuple of (records list, total count)
            Each record is a dictionary with all audit fields
        """
        with self._lock:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.row_factory = sqlite3.Row

                # Build WHERE clause and parameters
                where_sql, params = self._build_where_clause(
                    job_id=job_id,
                    repo_alias=repo_alias,
                    project_language=project_language,
                    project_build_system=project_build_system,
                    since=since,
                    until=until,
                )

                # Get total count
                count_sql = f"""
                    SELECT COUNT(*) as total
                    FROM scip_dependency_installations
                    {where_sql}
                """
                cursor = conn.execute(count_sql, params)
                total = cursor.fetchone()["total"]

                # Get records with pagination
                query_sql = f"""
                    SELECT
                        id,
                        timestamp,
                        job_id,
                        repo_alias,
                        project_path,
                        project_language,
                        project_build_system,
                        package,
                        command,
                        reasoning,
                        username
                    FROM scip_dependency_installations
                    {where_sql}
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                """
                cursor = conn.execute(query_sql, params + [limit, offset])

                # Convert rows to dictionaries
                records = [self._row_to_dict(row) for row in cursor.fetchall()]

                return records, total

    def _build_where_clause(
        self,
        job_id: Optional[str],
        repo_alias: Optional[str],
        project_language: Optional[str],
        project_build_system: Optional[str],
        since: Optional[str],
        until: Optional[str],
    ) -> Tuple[str, List[Any]]:
        """
        Build WHERE clause and parameters for query filtering.

        Args:
            job_id: Filter by job ID (optional)
            repo_alias: Filter by repository alias (optional)
            project_language: Filter by project language (optional)
            project_build_system: Filter by build system (optional)
            since: Filter records after this ISO timestamp (optional)
            until: Filter records before this ISO timestamp (optional)

        Returns:
            Tuple of (WHERE SQL clause, parameters list)
        """
        where_clauses = []
        params = []

        if job_id:
            where_clauses.append("job_id = ?")
            params.append(job_id)

        if repo_alias:
            where_clauses.append("repo_alias = ?")
            params.append(repo_alias)

        if project_language:
            where_clauses.append("project_language = ?")
            params.append(project_language)

        if project_build_system:
            where_clauses.append("project_build_system = ?")
            params.append(project_build_system)

        if since:
            where_clauses.append("timestamp >= ?")
            params.append(since)

        if until:
            where_clauses.append("timestamp <= ?")
            params.append(until)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        return where_sql, params

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """
        Convert SQLite row to dictionary.

        Args:
            row: SQLite row object

        Returns:
            Dictionary with all audit record fields
        """
        return {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "job_id": row["job_id"],
            "repo_alias": row["repo_alias"],
            "project_path": row["project_path"],
            "project_language": row["project_language"],
            "project_build_system": row["project_build_system"],
            "package": row["package"],
            "command": row["command"],
            "reasoning": row["reasoning"],
            "username": row["username"],
        }
