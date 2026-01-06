"""Unit tests for temporal collection format detection (Story #669).

Tests v1 vs v2 format detection and v1 graceful error handling.
"""

import tempfile
from pathlib import Path
import pytest

from src.code_indexer.storage.temporal_metadata_store import (
    TemporalMetadataStore,
    TemporalFormatError,
)


class TestTemporalFormatDetection:
    """Test format detection for temporal collections (v1 vs v2)."""

    def test_detect_v2_format_when_metadata_db_exists(self):
        """AC4: Detect v2 format when temporal_metadata.db exists."""
        # Given: A temporal collection with temporal_metadata.db file (v2 format)
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir) / "code-indexer-temporal"
            collection_path.mkdir()

            # Create temporal_metadata.db to indicate v2 format
            TemporalMetadataStore(collection_path)

            # When: Detecting format
            format_version = TemporalMetadataStore.detect_format(collection_path)

            # Then: Should detect v2
            assert format_version == "v2", f"Expected v2 format, got {format_version}"

    def test_detect_v1_format_when_metadata_db_missing(self):
        """AC4: Detect v1 format when temporal_metadata.db is missing."""
        # Given: A temporal collection WITHOUT temporal_metadata.db (v1 format)
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir) / "code-indexer-temporal"
            collection_path.mkdir()

            # Don't create metadata store - this simulates v1 format
            # (legacy indexes have no temporal_metadata.db)

            # When: Detecting format
            format_version = TemporalMetadataStore.detect_format(collection_path)

            # Then: Should detect v1
            assert format_version == "v1", f"Expected v1 format, got {format_version}"

    def test_handle_v1_format_raises_error_with_reindex_instructions(self):
        """AC4: V1 format detection raises clear error with re-index instructions."""
        # Given: A temporal collection in v1 format (no metadata db)
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir) / "code-indexer-temporal"
            collection_path.mkdir()

            # Don't create metadata store (v1 format)

            # When: Handling v1 format
            with pytest.raises(TemporalFormatError) as exc_info:
                TemporalMetadataStore.handle_v1_format(collection_path)

            # Then: Error message should contain clear instructions
            error_message = str(exc_info.value)

            assert "Legacy temporal index format (v1) detected" in error_message, (
                "Error should mention v1 format detection"
            )

            assert "cidx index --index-commits --reconcile" in error_message, (
                "Error should provide re-index command"
            )

            assert str(collection_path) in error_message, (
                "Error should include collection path for debugging"
            )

    def test_handle_v2_format_does_not_raise_error(self):
        """AC4: V2 format detection should not raise error."""
        # Given: A temporal collection in v2 format (with metadata db)
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir) / "code-indexer-temporal"
            collection_path.mkdir()

            # Create metadata store (v2 format)
            TemporalMetadataStore(collection_path)

            # When/Then: Handling v2 format should not raise error
            try:
                TemporalMetadataStore.handle_v1_format(collection_path)
            except TemporalFormatError:
                pytest.fail("V2 format should not raise TemporalFormatError")

    def test_is_temporal_collection_identifies_correct_name(self):
        """Helper method correctly identifies temporal collection name."""
        # Given: Various collection names
        assert TemporalMetadataStore.is_temporal_collection("code-indexer-temporal") is True
        assert TemporalMetadataStore.is_temporal_collection("default") is False
        assert TemporalMetadataStore.is_temporal_collection("my-collection") is False
        assert TemporalMetadataStore.is_temporal_collection("") is False

    def test_metadata_store_initialization_creates_database(self):
        """Initializing metadata store creates temporal_metadata.db file."""
        # Given: A new temporal collection path
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir) / "code-indexer-temporal"

            # When: Initializing metadata store
            TemporalMetadataStore(collection_path)

            # Then: Database file should exist
            db_path = collection_path / TemporalMetadataStore.METADATA_DB_NAME
            assert db_path.exists(), f"Metadata database not created at {db_path}"

            # And: Database should have correct schema (temporal_metadata table)
            import sqlite3
            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='temporal_metadata'"
                )
                table_exists = cursor.fetchone() is not None
                assert table_exists, "temporal_metadata table not created"
            finally:
                conn.close()

    def test_metadata_store_initialization_creates_indexes(self):
        """Initializing metadata store creates indexes for efficient queries."""
        # Given: A new temporal collection path
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir) / "code-indexer-temporal"

            # When: Initializing metadata store
            TemporalMetadataStore(collection_path)

            # Then: Indexes should exist
            import sqlite3
            db_path = collection_path / TemporalMetadataStore.METADATA_DB_NAME
            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
                )
                indexes = {row[0] for row in cursor.fetchall()}

                # Check for expected indexes (excluding sqlite internal indexes)
                expected_indexes = {"idx_point_id", "idx_commit_hash", "idx_file_path"}
                missing_indexes = expected_indexes - indexes

                assert not missing_indexes, (
                    f"Missing indexes: {missing_indexes}. Found: {indexes}"
                )
            finally:
                conn.close()
