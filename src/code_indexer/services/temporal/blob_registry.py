"""BlobRegistry - SQLite-based blob deduplication tracking."""
import sqlite3
from pathlib import Path
from typing import List


class BlobRegistry:
    """SQLite-based registry tracking blob_hash -> point_id mappings.

    This registry enables efficient deduplication by tracking which blobs
    already have vectors computed. Each blob (identified by git SHA-1 hash)
    can map to multiple point IDs (one per chunk).

    Performance characteristics:
    - Indexed lookups: O(log n) for has_blob()
    - Batch inserts: 1000 rows per transaction
    - WAL mode: Concurrent reads during writes
    """

    def __init__(self, db_path: Path):
        """Initialize blob registry.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database and connection
        self.conn = self._initialize_database()

    def _initialize_database(self) -> sqlite3.Connection:
        """Create database with proper schema and indexes.

        Returns:
            Database connection
        """
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)

        # Create table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS blob_registry (
                blob_hash TEXT NOT NULL,
                point_id TEXT NOT NULL,
                PRIMARY KEY (blob_hash, point_id)
            )
        """)

        # Create index for fast blob_hash lookups
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_blob_hash
            ON blob_registry(blob_hash)
        """)

        # Performance tuning for concurrent access
        conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
        conn.execute("PRAGMA synchronous=NORMAL")  # Balance safety/performance
        conn.execute("PRAGMA cache_size=10000")  # 10MB cache
        conn.execute("PRAGMA busy_timeout=5000")  # 5 second timeout

        conn.commit()
        return conn

    def register(self, blob_hash: str, point_id: str) -> None:
        """Register a blob_hash -> point_id mapping.

        Args:
            blob_hash: Git blob hash (SHA-1)
            point_id: Vector store point ID

        Note:
            This operation is idempotent - registering the same
            mapping twice has no effect (INSERT OR IGNORE).
        """
        self.conn.execute(
            "INSERT OR IGNORE INTO blob_registry (blob_hash, point_id) VALUES (?, ?)",
            (blob_hash, point_id)
        )
        self.conn.commit()

    def has_blob(self, blob_hash: str) -> bool:
        """Check if blob exists in registry.

        Args:
            blob_hash: Git blob hash to check

        Returns:
            True if blob has at least one point ID registered
        """
        cursor = self.conn.execute(
            "SELECT 1 FROM blob_registry WHERE blob_hash = ? LIMIT 1",
            (blob_hash,)
        )
        return cursor.fetchone() is not None

    def get_point_ids(self, blob_hash: str) -> List[str]:
        """Get all point IDs for a blob.

        Args:
            blob_hash: Git blob hash

        Returns:
            List of point IDs (one per chunk), empty if blob not found
        """
        cursor = self.conn.execute(
            "SELECT point_id FROM blob_registry WHERE blob_hash = ?",
            (blob_hash,)
        )
        return [row[0] for row in cursor.fetchall()]

    def clear(self) -> None:
        """Remove all entries from registry."""
        self.conn.execute("DELETE FROM blob_registry")
        self.conn.commit()

    def count(self) -> int:
        """Count total number of unique blobs in registry.

        Returns:
            Number of unique blob hashes
        """
        cursor = self.conn.execute(
            "SELECT COUNT(DISTINCT blob_hash) FROM blob_registry"
        )
        return cursor.fetchone()[0]

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close connection."""
        self.close()
