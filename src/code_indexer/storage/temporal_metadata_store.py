"""Temporal metadata storage for v2 format filename resolution.

Story #669: Fix Temporal Indexing Filename Length Issue

This module provides SQLite-based metadata storage for temporal collections using
v2 format (hash-based filenames). It maintains point_id-to-hash mappings with full
metadata to enable efficient queries and format detection.

V2 Format:
- Filenames: vector_{sha256(point_id)[:16]}.json (28 chars total)
- Metadata: SQLite database with point_id, commit_hash, file_path, chunk_index
- Detection: Presence of temporal_metadata.db file indicates v2 format

V1 Format (Legacy):
- Filenames: vector_{point_id_with_slashes_replaced}.json (can exceed 255 chars)
- No metadata database
- Detection: Absence of temporal_metadata.db indicates v1 format
"""

import hashlib
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)


class TemporalFormatError(Exception):
    """Raised when legacy v1 format is detected and requires re-indexing."""

    pass


class TemporalMetadataStore:
    """SQLite-based metadata storage for temporal collections v2 format.

    Stores point_id-to-hash mappings with metadata:
    - hash_prefix: 16-char SHA256 prefix (used as filename)
    - point_id: Full point_id (original)
    - commit_hash: Git commit hash
    - file_path: File path from payload
    - chunk_index: Chunk index
    - created_at: Timestamp

    Schema:
        CREATE TABLE temporal_metadata (
            hash_prefix TEXT PRIMARY KEY,
            point_id TEXT NOT NULL UNIQUE,
            commit_hash TEXT,
            file_path TEXT,
            chunk_index INTEGER,
            created_at TEXT,
            format_version INTEGER DEFAULT 2
        );
    """

    TEMPORAL_COLLECTION_NAME = "code-indexer-temporal"
    METADATA_DB_NAME = "temporal_metadata.db"
    HASH_PREFIX_LENGTH = 16  # 16-char SHA256 prefix for v2 format filenames

    def __init__(self, collection_path: Path):
        """Initialize temporal metadata store.

        Args:
            collection_path: Path to the temporal collection directory
        """
        self.collection_path = collection_path
        self.db_path = collection_path / self.METADATA_DB_NAME
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database with schema."""
        self.collection_path.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            # Create table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS temporal_metadata (
                    hash_prefix TEXT PRIMARY KEY,
                    point_id TEXT NOT NULL UNIQUE,
                    commit_hash TEXT,
                    file_path TEXT,
                    chunk_index INTEGER,
                    created_at TEXT,
                    format_version INTEGER DEFAULT 2
                )
            """
            )

            # Create indexes for efficient queries
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_point_id
                ON temporal_metadata(point_id)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_commit_hash
                ON temporal_metadata(commit_hash)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_file_path
                ON temporal_metadata(file_path)
            """
            )

            conn.commit()
        finally:
            conn.close()

    def generate_hash_prefix(self, point_id: str) -> str:
        """Generate 16-char SHA256 hash prefix for point_id.

        Args:
            point_id: Full point_id (e.g., "project:diff:hash:path:index")

        Returns:
            16-character SHA256 hash prefix
        """
        return hashlib.sha256(point_id.encode()).hexdigest()[:self.HASH_PREFIX_LENGTH]

    def save_metadata(self, point_id: str, payload: Dict) -> str:
        """Save metadata for a point and return hash prefix.

        Args:
            point_id: Full point_id
            payload: Payload dict containing commit_hash, path, chunk_index

        Returns:
            16-char hash prefix (to be used as filename)
        """
        hash_prefix = self.generate_hash_prefix(point_id)

        # Extract metadata from payload with validation logging
        commit_hash = payload.get("commit_hash", "")
        if not commit_hash:
            logger.warning(f"Missing commit_hash in payload for point_id: {point_id}")

        file_path = payload.get("path", "")
        if not file_path:
            logger.warning(f"Missing path in payload for point_id: {point_id}")

        chunk_index = payload.get("chunk_index", 0)
        if "chunk_index" not in payload:
            logger.debug(f"chunk_index not in payload for {point_id}, defaulting to 0")

        created_at = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO temporal_metadata
                (hash_prefix, point_id, commit_hash, file_path, chunk_index, created_at, format_version)
                VALUES (?, ?, ?, ?, ?, ?, 2)
            """,
                (hash_prefix, point_id, commit_hash, file_path, chunk_index, created_at),
            )
            conn.commit()
        finally:
            conn.close()

        return hash_prefix

    def get_point_id(self, hash_prefix: str) -> Optional[str]:
        """Retrieve point_id from hash prefix.

        Args:
            hash_prefix: 16-char hash prefix

        Returns:
            Full point_id if found, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT point_id FROM temporal_metadata
                WHERE hash_prefix = ?
            """,
                (hash_prefix,),
            )
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def get_metadata(self, hash_prefix: str) -> Optional[Dict]:
        """Retrieve full metadata from hash prefix.

        Args:
            hash_prefix: 16-char hash prefix

        Returns:
            Dict with point_id, commit_hash, file_path, chunk_index, or None
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT point_id, commit_hash, file_path, chunk_index, created_at
                FROM temporal_metadata
                WHERE hash_prefix = ?
            """,
                (hash_prefix,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "point_id": row[0],
                    "commit_hash": row[1],
                    "file_path": row[2],
                    "chunk_index": row[3],
                    "created_at": row[4],
                }
            return None
        finally:
            conn.close()

    def delete_metadata(self, hash_prefix: str) -> None:
        """Delete metadata entry.

        Args:
            hash_prefix: 16-char hash prefix to delete
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM temporal_metadata
                WHERE hash_prefix = ?
            """,
                (hash_prefix,),
            )
            conn.commit()
        finally:
            conn.close()

    def cleanup_stale_metadata(self, valid_hash_prefixes: Set[str]) -> int:
        """Remove metadata entries without corresponding vector files.

        Args:
            valid_hash_prefixes: Set of hash prefixes that have vector files

        Returns:
            Number of stale entries removed
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            # Get all hash prefixes in database
            cursor.execute("SELECT hash_prefix FROM temporal_metadata")
            all_prefixes = {row[0] for row in cursor.fetchall()}

            # Find stale entries (in DB but no vector file)
            stale_prefixes = all_prefixes - valid_hash_prefixes

            if stale_prefixes:
                placeholders = ",".join(["?"] * len(stale_prefixes))
                cursor.execute(
                    f"""
                    DELETE FROM temporal_metadata
                    WHERE hash_prefix IN ({placeholders})
                """,
                    list(stale_prefixes),
                )
                conn.commit()
                logger.info(f"Cleaned up {len(stale_prefixes)} stale metadata entries")

            return len(stale_prefixes)
        finally:
            conn.close()

    def count_entries(self) -> int:
        """Count total metadata entries.

        Returns:
            Number of entries in metadata database
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM temporal_metadata")
            row = cursor.fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    @classmethod
    def detect_format(cls, collection_path: Path) -> str:
        """Detect temporal collection format (v1 or v2).

        Args:
            collection_path: Path to temporal collection directory

        Returns:
            "v2" if temporal_metadata.db exists, "v1" otherwise
        """
        metadata_db_path = collection_path / cls.METADATA_DB_NAME

        if metadata_db_path.exists():
            return "v2"
        return "v1"

    @classmethod
    def handle_v1_format(cls, collection_path: Path) -> None:
        """Handle v1 format detection with graceful error.

        Args:
            collection_path: Path to temporal collection directory

        Raises:
            TemporalFormatError: Always raised with clear re-index instructions
        """
        format_version = cls.detect_format(collection_path)

        if format_version == "v1":
            error_message = (
                f"Legacy temporal index format (v1) detected at {collection_path}\n"
                f"Re-index required. Run: cidx index --index-commits --reconcile"
            )
            logger.error(error_message)
            raise TemporalFormatError(error_message)

    @classmethod
    def is_temporal_collection(cls, collection_name: str) -> bool:
        """Check if collection name is the temporal collection.

        Args:
            collection_name: Collection name to check

        Returns:
            True if this is the temporal collection
        """
        return collection_name == cls.TEMPORAL_COLLECTION_NAME
