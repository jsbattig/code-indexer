"""SCIP database schema management."""

try:
    # Try pysqlite3-binary first (provides newer SQLite)
    from pysqlite3 import dbapi2 as sqlite3
except ImportError:
    # Fall back to standard library sqlite3
    import sqlite3

from pathlib import Path


class DatabaseManager:
    """Manages SCIP database creation and schema."""

    def __init__(self, scip_file: Path):
        """
        Initialize DatabaseManager and create database file.

        Args:
            scip_file: Path to .scip protobuf file

        Raises:
            OSError: If database file cannot be created (permissions, disk space)
            RuntimeError: If SQLite version is below 3.35
        """
        # Validate SQLite version before proceeding
        version = sqlite3.sqlite_version
        major, minor, patch = map(int, version.split("."))
        if major < 3 or (major == 3 and minor < 35):
            raise RuntimeError(
                f"SQLite 3.35+ required for recursive CTEs and window functions. "
                f"Found: {version}. Upgrade SQLite or install pysqlite3-binary."
            )

        self.scip_file = Path(scip_file)
        self.db_path = Path(str(scip_file) + ".db")

        # Delete existing database to ensure clean slate
        # Prevents stale data accumulation from previous generations
        if self.db_path.exists():
            self.db_path.unlink()

        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create fresh database file
        try:
            conn = sqlite3.connect(self.db_path)
            conn.close()
        except OSError as e:
            raise OSError(f"Failed to create database at {self.db_path}: {e}") from e

    def create_schema(self) -> None:
        """Create database schema with all tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Enable foreign key constraints
            cursor.execute("PRAGMA foreign_keys = ON")
            # Create symbols table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS symbols (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    display_name TEXT,
                    kind TEXT,
                    signature TEXT,
                    documentation TEXT,
                    package_id TEXT,
                    enclosing_symbol_id INTEGER
                )
            """
            )

            # Create documents table (needed for FK constraint in occurrences)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY,
                    relative_path TEXT NOT NULL,
                    language TEXT,
                    occurrences TEXT
                )
            """
            )

            # Create occurrences table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS occurrences (
                    id INTEGER PRIMARY KEY,
                    symbol_id INTEGER NOT NULL,
                    document_id INTEGER NOT NULL,
                    start_line INTEGER NOT NULL,
                    start_char INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    end_char INTEGER NOT NULL,
                    role INTEGER,
                    enclosing_range_start_line INTEGER,
                    enclosing_range_start_char INTEGER,
                    enclosing_range_end_line INTEGER,
                    enclosing_range_end_char INTEGER,
                    syntax_kind TEXT,
                    FOREIGN KEY (symbol_id) REFERENCES symbols(id),
                    FOREIGN KEY (document_id) REFERENCES documents(id)
                )
            """
            )

            # Create call_graph table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS call_graph (
                    id INTEGER PRIMARY KEY,
                    caller_symbol_id INTEGER NOT NULL,
                    callee_symbol_id INTEGER NOT NULL,
                    occurrence_id INTEGER,
                    relationship TEXT,
                    caller_display_name TEXT,
                    callee_display_name TEXT,
                    FOREIGN KEY (caller_symbol_id) REFERENCES symbols(id),
                    FOREIGN KEY (callee_symbol_id) REFERENCES symbols(id),
                    FOREIGN KEY (occurrence_id) REFERENCES occurrences(id)
                )
            """
            )

            # Create symbol_relationships table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS symbol_relationships (
                    id INTEGER PRIMARY KEY,
                    from_symbol_id INTEGER NOT NULL,
                    to_symbol_id INTEGER NOT NULL,
                    relationship_type TEXT NOT NULL,
                    FOREIGN KEY (from_symbol_id) REFERENCES symbols(id),
                    FOREIGN KEY (to_symbol_id) REFERENCES symbols(id)
                )
            """
            )

            # Create symbol_references table (for fast trace_call_chain queries)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS symbol_references (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_symbol_id INTEGER NOT NULL,
                    to_symbol_id INTEGER NOT NULL,
                    relationship_type TEXT NOT NULL,
                    occurrence_id INTEGER NOT NULL,
                    FOREIGN KEY (from_symbol_id) REFERENCES symbols(id),
                    FOREIGN KEY (to_symbol_id) REFERENCES symbols(id),
                    FOREIGN KEY (occurrence_id) REFERENCES occurrences(id)
                )
            """
            )

            # Create FTS5 virtual table for symbol search
            cursor.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts USING fts5(
                    name,
                    display_name,
                    documentation,
                    content=symbols,
                    content_rowid=id
                )
            """
            )

            conn.commit()
        finally:
            conn.close()

    def create_indexes(self) -> None:
        """Create all indexes for optimal query performance (deferred after bulk inserts)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Enable foreign key constraints
            cursor.execute("PRAGMA foreign_keys = ON")
            # Symbols table indexes
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_symbols_display_name ON symbols(display_name)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_symbols_enclosing ON symbols(enclosing_symbol_id)"
            )

            # Occurrences table indexes
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_occurrences_symbol ON occurrences(symbol_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_occurrences_document ON occurrences(document_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_occurrences_role ON occurrences(role)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_occurrences_location ON occurrences(start_line, start_char)"
            )

            # Call graph indexes
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_call_graph_caller ON call_graph(caller_symbol_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_call_graph_callee ON call_graph(callee_symbol_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_call_graph_occurrence ON call_graph(occurrence_id)"
            )

            # Symbol relationships indexes
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_relationships_from ON symbol_relationships(from_symbol_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_relationships_to ON symbol_relationships(to_symbol_id)"
            )

            # Symbol references indexes (for fast trace_call_chain queries)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_symbol_refs_from ON symbol_references(from_symbol_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_symbol_refs_to ON symbol_references(to_symbol_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_symbol_refs_type ON symbol_references(relationship_type)"
            )

            # Documents table indexes
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(relative_path)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_language ON documents(language)"
            )

            conn.commit()
        finally:
            conn.close()

    def delete_source_scip_file(self) -> bool:
        """
        Delete the source .scip protobuf file after successful database generation.

        The .scip file is only needed for ETL (deserializing to build the SQLite database).
        After successful database generation and verification, the .scip file is dead weight
        consuming disk space. All queries use the database exclusively.

        Returns:
            True if file was deleted, False if file didn't exist

        Raises:
            OSError: If file deletion fails due to permissions or other OS errors
        """
        if self.scip_file.exists():
            self.scip_file.unlink()
            return True
        return False
