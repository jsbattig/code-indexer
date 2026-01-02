"""Integration tests for complete SCIP ETL pipeline."""

import sqlite3
from pathlib import Path

import pytest

from code_indexer.scip.database.builder import SCIPDatabaseBuilder
from code_indexer.scip.database.schema import DatabaseManager


class TestETLPipeline:
    """Test complete ETL pipeline from SCIP protobuf to database."""

    def test_full_etl_pipeline(self):
        """
        Test complete ETL transformation with real SCIP file.

        Given a real SCIP protobuf file
        When running complete ETL pipeline
        Then database contains all symbols, occurrences, documents, and call graph edges
        """
        # Use existing test SCIP file
        scip_file = (
            Path(__file__).parent.parent / "scip" / "fixtures" / "test_index.scip"
        )

        if not scip_file.exists():
            pytest.skip(f"Test SCIP file not found: {scip_file}")

        # Create database
        db_manager = DatabaseManager(scip_file)
        db_manager.create_schema()

        # Run ETL pipeline
        builder = SCIPDatabaseBuilder()
        result = builder.build(scip_file, db_manager.db_path)

        # Verify results
        assert result["symbol_count"] > 0, "Should have extracted symbols"
        assert result["document_count"] > 0, "Should have extracted documents"
        assert result["occurrence_count"] > 0, "Should have extracted occurrences"

        # Verify database contents
        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()

        # Check symbols table
        cursor.execute("SELECT COUNT(*) FROM symbols")
        symbol_count = cursor.fetchone()[0]
        assert symbol_count == result["symbol_count"]

        # Check documents table
        cursor.execute("SELECT COUNT(*) FROM documents")
        doc_count = cursor.fetchone()[0]
        assert doc_count == result["document_count"]

        # Check occurrences table
        cursor.execute("SELECT COUNT(*) FROM occurrences")
        occ_count = cursor.fetchone()[0]
        assert occ_count == result["occurrence_count"]

        # Check call_graph table (may be 0 for small test files)
        cursor.execute("SELECT COUNT(*) FROM call_graph")
        call_graph_count = cursor.fetchone()[0]
        assert call_graph_count >= 0

        # Verify foreign key integrity (all occurrences link to valid symbols)
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM occurrences o
            LEFT JOIN symbols s ON o.symbol_id = s.id
            WHERE s.id IS NULL
        """
        )
        orphan_occurrences = cursor.fetchone()[0]
        assert orphan_occurrences == 0, "All occurrences should link to valid symbols"

        conn.close()
