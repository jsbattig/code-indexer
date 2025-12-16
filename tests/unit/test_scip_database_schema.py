"""Unit tests for SCIP database schema creation."""

from pathlib import Path

import pytest

try:
    # Try pysqlite3-binary first (provides newer SQLite)
    from pysqlite3 import dbapi2 as sqlite3
except ImportError:
    # Fall back to standard library sqlite3
    import sqlite3

from code_indexer.scip.database.schema import DatabaseManager


class TestDatabaseFileCreation:
    """Tests for database file creation logic."""

    def test_database_file_creation(self, tmp_path: Path):
        """Test that DatabaseManager creates .scip.db file from .scip file path."""
        # Given a SCIP protobuf file path
        scip_file = tmp_path / "index.scip"
        scip_file.touch()  # Create empty file
        expected_db_file = tmp_path / "index.scip.db"

        # When creating database
        db_manager = DatabaseManager(scip_file)

        # Then database file should be created
        assert expected_db_file.exists()
        assert db_manager.db_path == expected_db_file

    def test_database_uses_sqlite3(self, tmp_path: Path):
        """Test that created database is valid SQLite3 format."""
        scip_file = tmp_path / "index.scip"
        scip_file.touch()

        db_manager = DatabaseManager(scip_file)

        # Should be able to connect to database
        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()
        # Verify it's a valid SQLite database
        cursor.execute("SELECT sqlite_version()")
        version = cursor.fetchone()[0]
        assert version is not None
        conn.close()


class TestTableSchema:
    """Tests for database table schema creation."""

    def test_symbols_table_schema(self, tmp_path: Path):
        """Test that symbols table exists with correct schema."""
        scip_file = tmp_path / "index.scip"
        scip_file.touch()

        db_manager = DatabaseManager(scip_file)
        db_manager.create_schema()

        # Verify symbols table exists with correct columns
        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(symbols)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        expected_columns = {
            "id": "INTEGER",
            "name": "TEXT",
            "display_name": "TEXT",
            "kind": "TEXT",
            "signature": "TEXT",
            "documentation": "TEXT",
            "package_id": "TEXT",
            "enclosing_symbol_id": "INTEGER",
        }

        assert columns == expected_columns
        conn.close()

    def test_occurrences_table_schema(self, tmp_path: Path):
        """Test that occurrences table exists with correct schema."""
        scip_file = tmp_path / "index.scip"
        scip_file.touch()

        db_manager = DatabaseManager(scip_file)
        db_manager.create_schema()

        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(occurrences)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        expected_columns = {
            "id": "INTEGER",
            "symbol_id": "INTEGER",
            "document_id": "INTEGER",
            "start_line": "INTEGER",
            "start_char": "INTEGER",
            "end_line": "INTEGER",
            "end_char": "INTEGER",
            "role": "INTEGER",
            "enclosing_range_start_line": "INTEGER",
            "enclosing_range_start_char": "INTEGER",
            "enclosing_range_end_line": "INTEGER",
            "enclosing_range_end_char": "INTEGER",
            "syntax_kind": "TEXT",
        }

        assert columns == expected_columns
        conn.close()

    def test_call_graph_table_schema(self, tmp_path: Path):
        """Test that call_graph table exists with correct schema."""

        scip_file = tmp_path / "index.scip"
        scip_file.touch()

        db_manager = DatabaseManager(scip_file)
        db_manager.create_schema()

        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(call_graph)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        expected_columns = {
            "id": "INTEGER",
            "caller_symbol_id": "INTEGER",
            "callee_symbol_id": "INTEGER",
            "occurrence_id": "INTEGER",
            "relationship": "TEXT",
            "caller_display_name": "TEXT",
            "callee_display_name": "TEXT",
        }

        assert columns == expected_columns
        conn.close()

    def test_symbol_relationships_table_schema(self, tmp_path: Path):
        """Test that symbol_relationships table exists with correct schema."""

        scip_file = tmp_path / "index.scip"
        scip_file.touch()

        db_manager = DatabaseManager(scip_file)
        db_manager.create_schema()

        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(symbol_relationships)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        expected_columns = {
            "id": "INTEGER",
            "from_symbol_id": "INTEGER",
            "to_symbol_id": "INTEGER",
            "relationship_type": "TEXT",
        }

        assert columns == expected_columns
        conn.close()

    def test_documents_table_schema(self, tmp_path: Path):
        """Test that documents table exists with correct schema."""

        scip_file = tmp_path / "index.scip"
        scip_file.touch()

        db_manager = DatabaseManager(scip_file)
        db_manager.create_schema()

        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(documents)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        expected_columns = {
            "id": "INTEGER",
            "relative_path": "TEXT",
            "language": "TEXT",
            "occurrences": "TEXT",
        }

        assert columns == expected_columns
        conn.close()

    def test_symbols_fts_table_exists(self, tmp_path: Path):
        """Test that symbols_fts FTS5 virtual table exists."""

        scip_file = tmp_path / "index.scip"
        scip_file.touch()

        db_manager = DatabaseManager(scip_file)
        db_manager.create_schema()

        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()

        # Check if FTS table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='symbols_fts'
        """)
        result = cursor.fetchone()

        assert result is not None
        assert result[0] == "symbols_fts"
        conn.close()


class TestSQLiteVersionValidation:
    """Tests for SQLite version requirements."""

    def test_sqlite_version_validation(self, tmp_path: Path):
        """Test that SQLite 3.35+ requirement is validated and document current version."""

        scip_file = tmp_path / "index.scip"
        scip_file.touch()

        # Document current SQLite version
        version = sqlite3.sqlite_version
        major, minor, patch = map(int, version.split('.'))
        print(f"\nCurrent SQLite version: {version}")

        # Check if version meets requirement
        version_ok = major > 3 or (major == 3 and minor >= 35)

        if version_ok:
            # Should succeed without error
            db_manager = DatabaseManager(scip_file)
            assert db_manager is not None
        else:
            # Should raise RuntimeError due to insufficient version
            with pytest.raises(
                RuntimeError,
                match="SQLite 3.35\\+ required for recursive CTEs and window functions"
            ):
                DatabaseManager(scip_file)


class TestForeignKeyEnforcement:
    """Tests for foreign key constraint enforcement."""

    def test_foreign_key_constraints_enforced(self, tmp_path: Path):
        """Test that foreign key constraints are enforced by attempting invalid insert."""

        scip_file = tmp_path / "index.scip"
        scip_file.touch()

        db_manager = DatabaseManager(scip_file)
        db_manager.create_schema()

        # Open new connection and enable foreign keys
        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")

        # First create a document (needed for FK constraint)
        cursor.execute("""
            INSERT INTO documents (relative_path, language)
            VALUES ('test.py', 'python')
        """)
        conn.commit()

        # Attempt to insert occurrence with invalid symbol_id (should fail due to FK)
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
            cursor.execute("""
                INSERT INTO occurrences (
                    symbol_id, document_id, start_line, start_char,
                    end_line, end_char, role
                ) VALUES (999, 1, 1, 0, 1, 10, 'reference')
            """)
            conn.commit()

        conn.close()


class TestIndexCreation:
    """Tests for database index creation."""

    def test_create_indexes_creates_all_indexes(self, tmp_path: Path):
        """Test that create_indexes() creates all required indexes."""

        scip_file = tmp_path / "index.scip"
        scip_file.touch()

        db_manager = DatabaseManager(scip_file)
        db_manager.create_schema()
        db_manager.create_indexes()

        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()

        # Get all indexes
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        indexes = {row[0] for row in cursor.fetchall()}

        # Verify all required indexes exist
        expected_indexes = {
            "idx_symbols_name",
            "idx_symbols_display_name",
            "idx_symbols_kind",
            "idx_symbols_enclosing",
            "idx_occurrences_symbol",
            "idx_occurrences_document",
            "idx_occurrences_role",
            "idx_occurrences_location",
            "idx_call_graph_caller",
            "idx_call_graph_callee",
            "idx_call_graph_occurrence",
            "idx_relationships_from",
            "idx_relationships_to",
            "idx_documents_path",
            "idx_documents_language",
        }

        assert indexes >= expected_indexes  # All expected indexes must exist
        conn.close()
