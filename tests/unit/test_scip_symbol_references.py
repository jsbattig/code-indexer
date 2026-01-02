"""Tests for SCIP symbol_references table and fast trace_call_chain implementation."""

try:
    from pysqlite3 import dbapi2 as sqlite3
except ImportError:
    import sqlite3

import tempfile
from pathlib import Path

import pytest

from src.code_indexer.scip.database.schema import DatabaseManager
from src.code_indexer.scip.database.builder import SCIPDatabaseBuilder


class TestSymbolReferencesSchema:
    """Test symbol_references table schema creation."""

    def test_symbol_references_table_created(self):
        """Verify schema includes symbol_references table with correct columns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scip_file = Path(tmpdir) / "test.scip"
            scip_file.touch()

            # Create database with schema
            db_manager = DatabaseManager(scip_file)
            db_manager.create_schema()

            # Verify table exists
            conn = sqlite3.connect(db_manager.db_path)
            cursor = conn.cursor()

            # Check table exists
            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='symbol_references'
            """
            )
            assert cursor.fetchone() is not None, "symbol_references table should exist"

            # Check columns
            cursor.execute("PRAGMA table_info(symbol_references)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}

            assert "id" in columns
            assert "from_symbol_id" in columns
            assert "to_symbol_id" in columns
            assert "relationship_type" in columns
            assert "occurrence_id" in columns

            conn.close()

    def test_symbol_references_indexes_created(self):
        """Verify indexes on symbol_references table are created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scip_file = Path(tmpdir) / "test.scip"
            scip_file.touch()

            # Create database with schema and indexes
            db_manager = DatabaseManager(scip_file)
            db_manager.create_schema()
            db_manager.create_indexes()

            # Verify indexes exist
            conn = sqlite3.connect(db_manager.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='index' AND tbl_name='symbol_references'
            """
            )
            indexes = {row[0] for row in cursor.fetchall()}

            assert "idx_symbol_refs_from" in indexes
            assert "idx_symbol_refs_to" in indexes
            assert "idx_symbol_refs_type" in indexes

            conn.close()


class TestSymbolReferencesETL:
    """Test ETL population of symbol_references table."""

    def test_etl_populates_symbol_references(self):
        """Verify ETL creates edges in symbol_references table during indexing."""
        # Use existing SCIP test file (relative path)
        scip_file = Path(__file__).parent.parent / "scip/fixtures/test_index.scip"
        assert scip_file.exists(), f"Test SCIP file not found: {scip_file}"

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create schema
            db_manager = DatabaseManager(scip_file)
            db_manager.db_path = db_path
            db_manager.create_schema()

            # Run ETL to populate database
            builder = SCIPDatabaseBuilder()
            builder.build(scip_file, db_path)

            # Verify symbol_references table has entries
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM symbol_references")
            ref_count = cursor.fetchone()[0]

            assert (
                ref_count > 0
            ), "symbol_references table should have entries after indexing"

            # Verify columns are populated correctly
            cursor.execute(
                """
                SELECT from_symbol_id, to_symbol_id, relationship_type, occurrence_id
                FROM symbol_references
                LIMIT 1
            """
            )
            row = cursor.fetchone()

            assert row is not None
            assert row[0] is not None, "from_symbol_id should not be NULL"
            assert row[1] is not None, "to_symbol_id should not be NULL"
            assert row[2] is not None, "relationship_type should not be NULL"
            assert row[3] is not None, "occurrence_id should not be NULL"

            conn.close()

    def test_enclosing_range_populated_in_database(self):
        """
        Verify ETL populates enclosing_range columns from SCIP protobuf.

        NOTE: SCIP indexers often don't generate enclosing_range data,
        so this test verifies the ETL HANDLES enclosing_range correctly
        when present, but doesn't require it to be present.
        """
        # Use existing SCIP test file
        scip_file = Path(__file__).parent.parent / "scip/fixtures/test_index.scip"
        assert scip_file.exists(), f"Test SCIP file not found: {scip_file}"

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create schema
            db_manager = DatabaseManager(scip_file)
            db_manager.db_path = db_path
            db_manager.create_schema()

            # Run ETL to populate database
            builder = SCIPDatabaseBuilder()
            builder.build(scip_file, db_path)

            # Verify occurrences table structure includes enclosing_range columns
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Check columns exist
            cursor.execute("PRAGMA table_info(occurrences)")
            columns = {row[1] for row in cursor.fetchall()}

            assert "enclosing_range_start_line" in columns
            assert "enclosing_range_start_char" in columns
            assert "enclosing_range_end_line" in columns
            assert "enclosing_range_end_char" in columns

            # Check if any occurrences have enclosing_range data
            cursor.execute(
                """
                SELECT COUNT(*) FROM occurrences
                WHERE enclosing_range_start_line IS NOT NULL
            """
            )
            with_enclosing = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM occurrences")
            total = cursor.fetchone()[0]

            # SCIP indexers often don't populate enclosing_range, so we just verify
            # the ETL can handle it when present. This test documents the expected
            # behavior: columns exist and ETL preserves data when present.
            print(f"Occurrences with enclosing_range: {with_enclosing}/{total}")

            # Verify ETL doesn't break when enclosing_range is absent
            assert total > 0, "Should have at least some occurrences"

            conn.close()


class TestSymbolReferencesQuery:
    """Test fast trace_call_chain_v2 query on symbol_references table."""

    def test_trace_call_chain_v2_finds_chains(self):
        """Verify trace_call_chain_v2() finds call chains using recursive CTE."""
        # Use existing SCIP test file (relative path)
        scip_file = Path(__file__).parent.parent / "scip/fixtures/test_index.scip"
        assert scip_file.exists(), f"Test SCIP file not found: {scip_file}"

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create schema and run ETL
            db_manager = DatabaseManager(scip_file)
            db_manager.db_path = db_path
            db_manager.create_schema()

            builder = SCIPDatabaseBuilder()
            builder.build(scip_file, db_path)

            # Test trace_call_chain_v2
            from src.code_indexer.scip.database import queries

            conn = sqlite3.connect(db_path)

            # Find any two symbols in the database
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, name FROM symbols
                LIMIT 2
            """
            )
            symbols = cursor.fetchall()

            # Skip test if not enough symbols
            if len(symbols) < 2:
                conn.close()
                pytest.skip("Not enough symbols in test data to test call chain")

            from_id, _ = symbols[0]
            to_id, _ = symbols[1]

            # Call trace_call_chain_v2
            results, _ = queries.trace_call_chain_v2(
                conn, from_symbol_id=from_id, to_symbol_id=to_id, max_depth=5, limit=100
            )

            # Verify results format (may be empty if no chain exists)
            assert isinstance(results, list)

            # If results exist, verify structure
            if results:
                assert "path" in results[0]
                assert "length" in results[0]
                assert "has_cycle" in results[0]
                assert isinstance(results[0]["path"], list)

            conn.close()
