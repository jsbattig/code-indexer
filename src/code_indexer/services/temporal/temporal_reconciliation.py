"""Temporal reconciliation for crash-resilient indexing.

This module provides disk-based commit discovery and reconciliation
to enable recovery from crashed or interrupted temporal indexing jobs.

Story #669: Fix Temporal Indexing Filename Length Issue
- V1 format detection and cleanup during reconcile
- Enables migration from v1 (long filenames) to v2 (hash-based)
"""

import json
import logging
from pathlib import Path
from typing import Set, Tuple, List

from .models import CommitInfo
from ...storage.temporal_metadata_store import TemporalMetadataStore

logger = logging.getLogger(__name__)


def _cleanup_v1_format_files(collection_path: Path) -> int:
    """Delete v1 format vector files during reconcile to enable v2 migration.

    Story #669: V1 format uses long filenames that can exceed 255 characters.
    During reconcile, we detect v1 format (no temporal_metadata.db) and delete
    all v1 vector files so they can be re-indexed in v2 format (hash-based naming).

    Args:
        collection_path: Path to temporal collection directory

    Returns:
        Number of v1 files deleted

    Detection:
        V1 format: No temporal_metadata.db present
        V2 format: temporal_metadata.db exists
    """
    # Check if v1 format (no metadata db)
    format_version = TemporalMetadataStore.detect_format(collection_path)

    if format_version == "v2":
        # Already in v2 format, nothing to clean up
        logger.debug("Temporal collection already in v2 format, skipping v1 cleanup")
        return 0

    # V1 format detected - delete all vector files for migration
    logger.info("Detected v1 format temporal collection (legacy long filenames)")
    logger.info(
        "Cleaning up v1 vector files to enable v2 migration (hash-based naming)"
    )

    deleted_count = 0
    try:
        vector_files = list(collection_path.glob("vector_*.json"))
        for vector_file in vector_files:
            try:
                vector_file.unlink()
                deleted_count += 1
            except Exception as e:
                logger.warning(f"Failed to delete v1 file {vector_file.name}: {e}")
    except Exception as e:
        logger.error(f"Error during v1 cleanup: {e}")

    if deleted_count > 0:
        logger.info(f"V1 migration: Deleted {deleted_count} legacy vector files")
        logger.info("Will re-index all commits in v2 format (hash-based naming)")

    return deleted_count


def discover_indexed_commits_from_disk(collection_path: Path) -> Tuple[Set[str], int]:
    """Discover indexed commits by scanning vector files on disk.

    This function provides crash-resilient commit discovery by reading
    actual vector files instead of relying on potentially corrupted metadata.

    Args:
        collection_path: Path to the temporal collection directory

    Returns:
        Tuple of (set of indexed commit hashes, count of skipped files)

    Point ID Format:
        {project}:diff:{COMMIT_HASH}:{path}:{chunk}
        Example: "evolution:diff:abc123:src/main.py:0"
    """
    indexed_commits: Set[str] = set()
    skipped_files = 0

    # Handle non-existent collection
    if not collection_path.exists():
        logger.warning(f"Collection path does not exist: {collection_path}")
        return indexed_commits, skipped_files

    # Scan all vector files
    try:
        vector_files = list(collection_path.rglob("vector_*.json"))
    except Exception as e:
        logger.error(f"Error listing vector files: {e}")
        return indexed_commits, skipped_files

    for vector_file in vector_files:
        try:
            with open(vector_file, "r") as f:
                data = json.load(f)

            # Validate data is a dictionary
            if not isinstance(data, dict):
                skipped_files += 1
                logger.debug(f"Skipped non-dict data in {vector_file}")
                continue

            # Extract point_id
            point_id = data.get("id", "")

            # Parse point_id: {project}:diff:{COMMIT_HASH}:{path}:{chunk}
            parts = point_id.split(":")
            if len(parts) >= 3 and parts[1] == "diff":
                commit_hash = parts[2]
                indexed_commits.add(commit_hash)

        except (json.JSONDecodeError, IOError, KeyError) as e:
            # Skip corrupted files
            skipped_files += 1
            logger.debug(f"Skipped corrupted file {vector_file}: {e}")
            continue

    # Log summary
    if skipped_files > 0:
        logger.warning(
            f"Skipped {skipped_files} corrupted vector files during discovery"
        )

    logger.info(
        f"Discovered {len(indexed_commits)} indexed commits "
        f"from {len(vector_files) - skipped_files} vector files"
    )

    return indexed_commits, skipped_files


def reconcile_temporal_index(
    vector_store,
    all_commits: List[CommitInfo],
    temporal_collection: str = "code-indexer-temporal",
) -> List[CommitInfo]:
    """Reconcile git history with indexed commits to find missing commits.

    Compares full git commit history against indexed commits on disk
    to identify which commits still need to be processed.

    CRITICAL: Deletes stale metadata files (HNSW index, ID index, temporal metadata)
    to prevent reconciliation from being tricked by corrupted/stale metadata from
    interrupted runs. The whole point of --reconcile is to recover from bad states
    by scanning what's actually on disk.

    PRESERVES: collection_meta.json (required for collection_exists()) and
    projection_matrix.npy (cannot be recreated - required for vector quantization).

    Story #669: V1 to V2 Migration
    During reconcile, detects v1 format (no temporal_metadata.db) and deletes all
    v1 vector files to enable re-indexing in v2 format (hash-based naming).

    Args:
        vector_store: FilesystemVectorStore instance
        all_commits: Full list of commits from git history (chronological order)
        temporal_collection: Name of temporal collection

    Returns:
        List of missing CommitInfo objects (preserves chronological order)
    """
    # Get collection path from vector store (base_path / collection_name)
    collection_path = vector_store.base_path / temporal_collection

    # Story #669: Clean up v1 format files if detected (before metadata cleanup)
    # This enables migration from v1 (long filenames) to v2 (hash-based naming)
    if collection_path.exists():
        v1_deleted = _cleanup_v1_format_files(collection_path)
        if v1_deleted > 0:
            logger.info(
                f"V1 to V2 migration: Removed {v1_deleted} legacy files, "
                "will re-index in v2 format"
            )

    # Delete all metadata files to ensure clean reconciliation
    # These will be regenerated from scratch during end_indexing()
    metadata_files_to_delete = [
        collection_path / "hnsw_index.bin",
        collection_path / "id_index.bin",
        # NOTE: collection_meta.json is NOT deleted because:
        # - collection_exists() depends on it
        # - end_indexing() requires collection to exist
        # - _calculate_and_save_unique_file_count() reads and updates it
        # NOTE: projection_matrix.npy is NOT deleted because:
        # - It's a randomly generated matrix that cannot be recreated
        # - Vector quantization depends on using the same projection matrix
        # - Deleting it would make all queries return wrong results
        collection_path / "temporal_meta.json",
        collection_path / "temporal_progress.json",
    ]

    deleted_count = 0
    for meta_file in metadata_files_to_delete:
        if meta_file.exists():
            try:
                meta_file.unlink()
                deleted_count += 1
                logger.debug(f"Deleted stale metadata: {meta_file.name}")
            except Exception as e:
                logger.warning(f"Failed to delete {meta_file}: {e}")

    if deleted_count > 0:
        logger.info(f"Reconciliation: Deleted {deleted_count} stale metadata files")

    # Discover commits from disk (will be empty after v1 cleanup, leading to full re-index)
    indexed_commits, skipped_count = discover_indexed_commits_from_disk(collection_path)

    # Filter out already-indexed commits, preserving order
    missing_commits = [
        commit for commit in all_commits if commit.hash not in indexed_commits
    ]

    # Log reconciliation summary
    logger.info(
        f"Reconciliation: {len(indexed_commits)} indexed, "
        f"{len(missing_commits)} missing ({len(indexed_commits)*100//(len(all_commits) or 1)}% complete)"
    )

    return missing_commits
