"""SCIP database schema migration operations."""

try:
    from pysqlite3 import dbapi2 as sqlite3
except ImportError:
    import sqlite3

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def get_scip_db_version(config_path: Path) -> int:
    """
    Get SCIP database schema version from config.json.

    Args:
        config_path: Path to .code-indexer/config.json

    Returns:
        Schema version number (0 if not set, 2 for current version)
    """
    if not config_path.exists():
        return 0

    try:
        with open(config_path, "r") as f:
            config_data = json.load(f)
        version = config_data.get("scip_db_version", 0)
        return int(version) if version is not None else 0
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read SCIP DB version from {config_path}: {e}")
        return 0


def update_scip_db_version(config_path: Path, version: int) -> None:
    """
    Update SCIP database schema version in config.json.

    Args:
        config_path: Path to .code-indexer/config.json
        version: Schema version number to set
    """
    # Create parent directory if it doesn't exist
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing config or create new one
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                config_data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                f"Failed to read config from {config_path}: {e}. Creating new config."
            )
            config_data = {}
    else:
        config_data = {}

    # Update version
    config_data["scip_db_version"] = version

    # Write back to file
    try:
        with open(config_path, "w") as f:
            json.dump(config_data, f, indent=2)
    except OSError as e:
        logger.error(f"Failed to write SCIP DB version to {config_path}: {e}")
        raise


def ensure_indexes_created(conn: sqlite3.Connection) -> None:
    """
    Create required indexes for SCIP call graph queries (idempotent).

    Creates 5 indexes to optimize trace_call_chain_v2 performance:
    - idx_call_graph_caller: Speeds up forward BFS from caller
    - idx_call_graph_callee: Speeds up backward reachability from callee
    - idx_symbol_references_from: Speeds up dependency lookups
    - idx_symbol_references_to: Speeds up reverse dependency lookups
    - idx_occurrences_symbol_id: Speeds up symbol location lookups

    This function is idempotent (safe to run multiple times).
    Uses CREATE INDEX IF NOT EXISTS to avoid errors on repeat runs.

    Args:
        conn: SQLite database connection

    Note:
        This migration brings query performance from 20+ minutes to <2 seconds
        by eliminating full table scans in recursive CTEs.
    """
    cursor = conn.cursor()

    # Index 1: call_graph caller lookup (forward BFS)
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_call_graph_caller
        ON call_graph(caller_symbol_id)
    """
    )

    # Index 2: call_graph callee lookup (backward reachability)
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_call_graph_callee
        ON call_graph(callee_symbol_id)
    """
    )

    # Index 3: symbol_references from lookup (dependency queries)
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_symbol_references_from
        ON symbol_references(from_symbol_id)
    """
    )

    # Index 4: symbol_references to lookup (reverse dependency queries)
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_symbol_references_to
        ON symbol_references(to_symbol_id)
    """
    )

    # Index 5: occurrences symbol lookup (location queries)
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_occurrences_symbol_id
        ON occurrences(symbol_id)
    """
    )

    conn.commit()
