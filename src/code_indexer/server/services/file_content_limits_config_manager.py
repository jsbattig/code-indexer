from code_indexer.server.middleware.correlation import get_correlation_id
"""
File Content Limits Configuration Manager for database persistence.

Manages persistent storage of file content token limits configuration.
"""

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Optional

from ..models.file_content_limits_config import FileContentLimitsConfig

logger = logging.getLogger(__name__)


class FileContentLimitsConfigManager:
    """
    Manages persistent storage of file content limits configuration.

    Features:
    - SQLite-based persistence
    - Thread-safe access
    - Singleton pattern for global config
    - Default configuration on first access
    """

    _instance = None
    _lock = threading.Lock()

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize file content limits config manager.

        Args:
            db_path: Database path (defaults to ~/.cidx-server/file_content_limits.db)
        """
        if db_path:
            self.db_path = Path(db_path)
        else:
            server_dir = Path.home() / ".cidx-server"
            server_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = server_dir / "file_content_limits.db"

        # Ensure database directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database for config storage."""
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS file_content_limits_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    max_tokens_per_request INTEGER NOT NULL DEFAULT 5000,
                    chars_per_token INTEGER NOT NULL DEFAULT 4,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Insert default config if not exists
            conn.execute(
                """
                INSERT OR IGNORE INTO file_content_limits_config (id, max_tokens_per_request, chars_per_token)
                VALUES (1, 5000, 4)
            """
            )
            conn.commit()

        logger.info(
            f"File content limits config database initialized at {self.db_path}"
        , extra={"correlation_id": get_correlation_id()})

    def get_config(self) -> FileContentLimitsConfig:
        """
        Get current file content limits configuration.

        Returns:
            FileContentLimitsConfig instance
        """
        with self._lock:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                cursor = conn.execute(
                    """
                    SELECT max_tokens_per_request, chars_per_token
                    FROM file_content_limits_config
                    WHERE id = 1
                """
                )
                row = cursor.fetchone()

                if row:
                    return FileContentLimitsConfig(
                        max_tokens_per_request=row[0], chars_per_token=row[1]
                    )
                else:
                    # Return default if somehow not found
                    logger.warning("Config not found in database, using defaults", extra={"correlation_id": get_correlation_id()})
                    return FileContentLimitsConfig()

    def update_config(self, config: FileContentLimitsConfig):
        """
        Update file content limits configuration.

        Args:
            config: New configuration to persist
        """
        with self._lock:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute(
                    """
                    UPDATE file_content_limits_config
                    SET max_tokens_per_request = ?,
                        chars_per_token = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                """,
                    (config.max_tokens_per_request, config.chars_per_token),
                )
                conn.commit()

        logger.info(
            f"Updated file content limits config: {config.max_tokens_per_request} tokens, {config.chars_per_token} chars/token"
        , extra={"correlation_id": get_correlation_id()})

    @classmethod
    def get_instance(
        cls, db_path: Optional[str] = None
    ) -> "FileContentLimitsConfigManager":
        """
        Get singleton instance of config manager.

        Args:
            db_path: Database path (only used on first call)

        Returns:
            FileContentLimitsConfigManager instance
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(db_path)
        return cls._instance
