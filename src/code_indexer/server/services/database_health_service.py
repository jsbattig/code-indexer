"""
Database Health Service for monitoring all 8 central databases.

Story #712: Dashboard Refinements - Database Health Honeycomb

Implements 5-point health checks per database:
1. Connect - Open SQLite connection
2. Read - SELECT from any table
3. Write - INSERT/UPDATE to _health_check table
4. Quick Integrity - PRAGMA quick_check
5. Not Locked - Check for exclusive locks
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class DatabaseHealthStatus(str, Enum):
    """Health status levels for database health checks."""

    HEALTHY = "healthy"  # Green - All 5 checks pass
    WARNING = "warning"  # Yellow - Some checks pass, some fail
    ERROR = "error"  # Red - Critical checks fail


@dataclass
class CheckResult:
    """Result of a single health check."""

    passed: bool
    error_message: Optional[str] = None


@dataclass
class DatabaseHealthResult:
    """Complete health check result for a single database."""

    file_name: str
    display_name: str
    status: DatabaseHealthStatus
    checks: Dict[str, CheckResult]

    def get_tooltip(self) -> str:
        """
        Get tooltip text for honeycomb hover.

        AC2: Healthy databases show only display name.
        AC3: Unhealthy databases show display name AND failed condition.
        """
        if self.status == DatabaseHealthStatus.HEALTHY:
            return self.display_name

        # Find first failed check to include in tooltip
        for check_name, result in self.checks.items():
            if not result.passed:
                check_display = check_name.replace("_", " ").title()
                error_info = result.error_message or "failed"
                return f"{self.display_name} - {check_display}: {error_info}"

        return self.display_name


# Database file to display name mapping
DATABASE_DISPLAY_NAMES: Dict[str, str] = {
    "cidx_server.db": "Main Server",
    "oauth.db": "OAuth",
    "refresh_tokens.db": "Refresh Tokens",
    "logs.db": "Logs",
    "search_config.db": "Search Config",
    "file_content_limits.db": "File Limits",
    "scip_audit.db": "SCIP Audit",
    "payload_cache.db": "Payload Cache",
}


class DatabaseHealthService:
    """
    Service for checking health of all 8 central CIDX databases.

    Performs 5-point health checks on each database and determines
    overall status (healthy/warning/error).
    """

    def __init__(self, server_dir: Optional[str] = None):
        """
        Initialize the database health service.

        Args:
            server_dir: Path to server data directory. If None, uses
                       CIDX_SERVER_DATA_DIR env var or ~/.cidx-server
        """
        import os

        if server_dir:
            self.server_dir = Path(server_dir)
        else:
            self.server_dir = Path(
                os.environ.get(
                    "CIDX_SERVER_DATA_DIR", str(Path.home() / ".cidx-server")
                )
            )

    def get_all_database_health(self) -> List[DatabaseHealthResult]:
        """
        Check health of all 8 central databases.

        Returns:
            List of DatabaseHealthResult for each database
        """
        results = []

        for file_name, display_name in DATABASE_DISPLAY_NAMES.items():
            # Main server DB is in data/ subdirectory
            if file_name == "cidx_server.db":
                db_path = self.server_dir / "data" / file_name
            else:
                db_path = self.server_dir / file_name

            result = self.check_database_health(str(db_path), display_name)
            results.append(result)

        return results

    @staticmethod
    def check_database_health(
        db_path: str, display_name: str = "Unknown"
    ) -> DatabaseHealthResult:
        """
        Perform 5-point health check on a single database.

        Args:
            db_path: Path to SQLite database file
            display_name: Human-readable name for display

        Returns:
            DatabaseHealthResult with all check results
        """
        file_name = Path(db_path).name
        checks: Dict[str, CheckResult] = {}

        # Check 1: Connect
        checks["connect"] = DatabaseHealthService._check_connect(db_path)

        if checks["connect"].passed:
            # Check 2: Read (only if connect succeeded)
            checks["read"] = DatabaseHealthService._check_read(db_path)

            # Check 3: Write (only if connect succeeded)
            checks["write"] = DatabaseHealthService._check_write(db_path)

            # Check 4: Integrity (only if connect succeeded)
            checks["integrity"] = DatabaseHealthService._check_integrity(db_path)

            # Check 5: Not Locked (only if connect succeeded)
            checks["not_locked"] = DatabaseHealthService._check_not_locked(db_path)
        else:
            # If connect failed, all other checks fail too
            checks["read"] = CheckResult(
                passed=False, error_message="Connection required"
            )
            checks["write"] = CheckResult(
                passed=False, error_message="Connection required"
            )
            checks["integrity"] = CheckResult(
                passed=False, error_message="Connection required"
            )
            checks["not_locked"] = CheckResult(
                passed=False, error_message="Connection required"
            )

        # Determine overall status
        status = DatabaseHealthService._determine_status(checks)

        return DatabaseHealthResult(
            file_name=file_name,
            display_name=display_name,
            status=status,
            checks=checks,
        )

    @staticmethod
    def _check_connect(db_path: str) -> CheckResult:
        """Check 1: Can we connect to the database?"""
        try:
            # Check if file exists first
            if not Path(db_path).exists():
                return CheckResult(
                    passed=False, error_message="Connection failed: file not found"
                )

            with sqlite3.connect(db_path, timeout=5) as conn:
                # Simple test to verify connection works
                conn.execute("SELECT 1")
            return CheckResult(passed=True)
        except Exception as e:
            return CheckResult(passed=False, error_message=f"Connection failed: {e}")

    @staticmethod
    def _check_read(db_path: str) -> CheckResult:
        """Check 2: Can we read from the database?"""
        try:
            with sqlite3.connect(db_path, timeout=5) as conn:
                # Read sqlite_master to verify read capability
                conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' LIMIT 1"
                )
            return CheckResult(passed=True)
        except Exception as e:
            return CheckResult(passed=False, error_message=f"Read failed: {e}")

    @staticmethod
    def _check_write(db_path: str) -> CheckResult:
        """
        Check 3: Can we write to the database?

        Uses _health_check table with INSERT OR REPLACE pattern.

        Migration Strategy Note:
            This method uses CREATE TABLE IF NOT EXISTS instead of a versioned
            migration for the _health_check table. This is intentional because:

            1. Runtime health check tables are operational metadata, not application
               data. They don't require migration versioning or schema evolution.

            2. The _health_check table is trivial (single row, single timestamp)
               and will never need schema changes.

            3. CREATE TABLE IF NOT EXISTS provides idempotency - the health check
               can run safely on any database without prior setup.

            4. This pattern keeps the health service self-contained and avoids
               coupling to the migration system for purely operational concerns.
        """
        try:
            with sqlite3.connect(db_path, timeout=5) as conn:
                # Create _health_check table if not exists (see docstring for rationale)
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS _health_check (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )"""
                )

                # Update or insert health check record
                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    "INSERT OR REPLACE INTO _health_check (id, last_check) VALUES (1, ?)",
                    (now,),
                )
                conn.commit()
            return CheckResult(passed=True)
        except Exception as e:
            return CheckResult(passed=False, error_message=f"Write failed: {e}")

    @staticmethod
    def _check_integrity(db_path: str) -> CheckResult:
        """Check 4: Does PRAGMA quick_check pass?"""
        try:
            with sqlite3.connect(db_path, timeout=5) as conn:
                cursor = conn.execute("PRAGMA quick_check")
                result = cursor.fetchone()
                if result and result[0] == "ok":
                    return CheckResult(passed=True)
                else:
                    return CheckResult(
                        passed=False,
                        error_message=f"Integrity check failed: {result[0] if result else 'unknown'}",
                    )
        except Exception as e:
            return CheckResult(
                passed=False, error_message=f"Integrity check failed: {e}"
            )

    @staticmethod
    def _check_not_locked(db_path: str) -> CheckResult:
        """Check 5: Is the database not exclusively locked?"""
        try:
            with sqlite3.connect(db_path, timeout=1) as conn:
                # Try to acquire a shared lock
                conn.execute("BEGIN IMMEDIATE")
                conn.rollback()
            return CheckResult(passed=True)
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                return CheckResult(passed=False, error_message="Database locked")
            return CheckResult(passed=False, error_message=f"Lock check failed: {e}")
        except Exception as e:
            return CheckResult(passed=False, error_message=f"Lock check failed: {e}")

    @staticmethod
    def _determine_status(checks: Dict[str, CheckResult]) -> DatabaseHealthStatus:
        """
        Determine overall health status from individual check results.

        - GREEN (HEALTHY): All 5 checks pass
        - YELLOW (WARNING): Some checks pass, some fail (degraded but operational)
        - RED (ERROR): Critical checks fail (connect/read)
        """
        # Critical checks - if these fail, status is ERROR
        critical_checks = ["connect", "read"]
        for check_name in critical_checks:
            if check_name in checks and not checks[check_name].passed:
                return DatabaseHealthStatus.ERROR

        # Check if all passed
        all_passed = all(result.passed for result in checks.values())
        if all_passed:
            return DatabaseHealthStatus.HEALTHY

        # Some non-critical checks failed
        return DatabaseHealthStatus.WARNING
