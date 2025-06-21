"""
Schema Migration System for Code Indexer.

This module provides automatic detection and migration from legacy architecture
to the new BranchAwareIndexer architecture.

Legacy architecture:
- Single points with git_branch field
- Content directly stored in search points

New architecture:
- Content points (immutable, type: content)
- Visibility points (mutable, type: visibility)
- Separation of content storage from branch visibility
"""

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

logger = logging.getLogger(__name__)


@dataclass
class SchemaVersion:
    """Represents a detected schema version."""

    version: str
    description: str
    is_legacy: bool
    sample_payload: Dict[str, Any]


@dataclass
class MigrationResult:
    """Result of migration operation."""

    points_migrated: int
    content_points_created: int
    visibility_points_created: int
    legacy_points_deleted: int
    processing_time: float
    errors: List[str]


class SchemaVersionManager:
    """Manages schema version detection and validation."""

    def __init__(self, qdrant_client, console: Optional[Console] = None):
        self.qdrant_client = qdrant_client
        self.console = console or Console()

    def detect_schema_version(self, collection_name: str) -> SchemaVersion:
        """
        Detect the schema version of a collection by examining point payloads.

        Args:
            collection_name: Name of the collection to examine

        Returns:
            SchemaVersion with detected version info
        """
        try:
            # Get a sample of points to analyze
            sample_points, _ = self.qdrant_client.scroll_points(
                collection_name=collection_name,
                limit=10,
                with_payload=True,
                with_vectors=False,
            )

            if not sample_points:
                return SchemaVersion(
                    version="empty",
                    description="Empty collection",
                    is_legacy=False,
                    sample_payload={},
                )

            # Analyze payload structure - check all sample points first
            has_legacy = False
            has_new = False
            legacy_sample = None
            new_sample = None

            for point in sample_points:
                payload = point.get("payload", {})

                # Check for new architecture markers
                if payload.get("type") in ["content", "visibility"]:
                    has_new = True
                    if new_sample is None:
                        new_sample = payload

                # Check for legacy architecture markers
                if "git_branch" in payload and "type" not in payload:
                    has_legacy = True
                    if legacy_sample is None:
                        legacy_sample = payload

            # Determine schema version based on what we found
            if has_legacy and has_new:
                # Mixed schema - prioritize legacy for migration purposes
                return SchemaVersion(
                    version="v1_legacy_mixed",
                    description="Mixed legacy and new architecture (migration needed)",
                    is_legacy=True,
                    sample_payload=legacy_sample or {},
                )
            elif has_new:
                return SchemaVersion(
                    version="v2_branch_aware",
                    description="New BranchAwareIndexer architecture",
                    is_legacy=False,
                    sample_payload=new_sample or {},
                )
            elif has_legacy:
                return SchemaVersion(
                    version="v1_legacy",
                    description="Legacy single-point architecture",
                    is_legacy=True,
                    sample_payload=legacy_sample or {},
                )

            # Default to unknown if we can't determine
            return SchemaVersion(
                version="unknown",
                description="Unknown schema version",
                is_legacy=True,  # Assume legacy for safety
                sample_payload=(
                    sample_points[0].get("payload", {}) if sample_points else {}
                ),
            )

        except Exception as e:
            logger.error(f"Failed to detect schema version for {collection_name}: {e}")
            return SchemaVersion(
                version="error",
                description=f"Error detecting schema: {e}",
                is_legacy=True,
                sample_payload={},
            )

    def is_migration_needed(self, collection_name: str) -> bool:
        """Check if migration is needed for a collection."""
        schema = self.detect_schema_version(collection_name)
        return schema.is_legacy and schema.version != "empty"

    def get_migration_stats(self, collection_name: str) -> Dict[str, Any]:
        """Get statistics about points that need migration."""
        try:
            # Count legacy points (those with git_branch but no type)
            # Get all points and filter manually since Qdrant doesn't have an "exists" filter
            all_points, _ = self.qdrant_client.scroll_points(
                collection_name=collection_name,
                limit=10000,
                with_payload=True,
                with_vectors=False,
            )

            # Filter to legacy points: have git_branch field but no type field
            legacy_points = []
            for point in all_points:
                payload = point.get("payload", {})
                has_git_branch = "git_branch" in payload
                has_type = "type" in payload
                if has_git_branch and not has_type:
                    legacy_points.append(point)

            # Count by branch
            branch_counts: Dict[str, int] = {}
            for point in legacy_points:
                branch = point.get("payload", {}).get("git_branch", "unknown")
                branch_counts[branch] = branch_counts.get(branch, 0) + 1

            return {
                "total_legacy_points": len(legacy_points),
                "branches": len(branch_counts),
                "branch_counts": branch_counts,
            }

        except Exception as e:
            logger.error(f"Failed to get migration stats: {e}")
            return {"total_legacy_points": 0, "branches": 0, "branch_counts": {}}


class QdrantMigrator:
    """Handles migration from legacy to new BranchAwareIndexer architecture."""

    def __init__(self, qdrant_client, console: Optional[Console] = None):
        self.qdrant_client = qdrant_client
        self.console = console or Console()
        self.schema_manager = SchemaVersionManager(qdrant_client, console)

    def migrate_collection(
        self, collection_name: str, batch_size: int = 50, quiet: bool = False
    ) -> MigrationResult:
        """
        Migrate a collection from legacy to new architecture.

        Args:
            collection_name: Name of collection to migrate
            batch_size: Number of points to process per batch
            quiet: Suppress progress output

        Returns:
            MigrationResult with migration statistics
        """
        start_time = time.time()
        result = MigrationResult(
            points_migrated=0,
            content_points_created=0,
            visibility_points_created=0,
            legacy_points_deleted=0,
            processing_time=0,
            errors=[],
        )

        try:
            # Check if migration is needed
            if not self.schema_manager.is_migration_needed(collection_name):
                if not quiet:
                    self.console.print(
                        f"✅ Collection {collection_name} is already using new architecture",
                        style="green",
                    )
                return result

            # Get migration statistics
            stats = self.schema_manager.get_migration_stats(collection_name)
            total_points = stats["total_legacy_points"]

            if total_points == 0:
                if not quiet:
                    self.console.print(
                        f"✅ No legacy points found in {collection_name}", style="green"
                    )
                return result

            if not quiet:
                self.console.print(
                    f"🔄 Migrating {total_points} legacy points in {collection_name}",
                    style="blue",
                )
                branch_list: List[str] = (
                    list(stats["branch_counts"].keys())
                    if isinstance(stats["branch_counts"], dict)
                    else []
                )
                self.console.print(
                    f"📊 Found {stats['branches']} branches: {branch_list}",
                    style="blue",
                )

            # Process migration with progress bar
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=None if quiet else self.console,
                disable=quiet,
            ) as progress:
                task = progress.add_task("Migrating points...", total=total_points)

                # Get all legacy points in batches
                offset = None
                while True:
                    all_points, next_offset = self.qdrant_client.scroll_points(
                        collection_name=collection_name,
                        limit=batch_size,
                        with_payload=True,
                        with_vectors=True,
                        offset=offset,
                    )

                    # Filter to legacy points
                    legacy_points = []
                    for point in all_points:
                        payload = point.get("payload", {})
                        if "git_branch" in payload and "type" not in payload:
                            legacy_points.append(point)

                    if not legacy_points:
                        break

                    # Process batch
                    batch_result = self._migrate_batch(
                        legacy_points, collection_name, quiet
                    )

                    # Update results
                    result.points_migrated += batch_result.points_migrated
                    result.content_points_created += batch_result.content_points_created
                    result.visibility_points_created += (
                        batch_result.visibility_points_created
                    )
                    result.legacy_points_deleted += batch_result.legacy_points_deleted
                    result.errors.extend(batch_result.errors)

                    # Update progress
                    progress.update(task, advance=len(legacy_points))

                    if not next_offset:
                        break
                    offset = next_offset

            result.processing_time = time.time() - start_time

            if not quiet:
                self.console.print(
                    f"✅ Migration completed in {result.processing_time:.2f}s",
                    style="green",
                )
                self.console.print(
                    f"📊 Created {result.content_points_created} content points",
                    style="green",
                )
                self.console.print(
                    f"📊 Created {result.visibility_points_created} visibility points",
                    style="green",
                )
                self.console.print(
                    f"🗑️  Deleted {result.legacy_points_deleted} legacy points",
                    style="green",
                )

                if result.errors:
                    self.console.print(
                        f"⚠️  {len(result.errors)} errors occurred", style="yellow"
                    )
                    for error in result.errors[:5]:  # Show first 5 errors
                        self.console.print(f"   {error}", style="yellow")
                    if len(result.errors) > 5:
                        self.console.print(
                            f"   ... and {len(result.errors) - 5} more", style="yellow"
                        )

            return result

        except Exception as e:
            logger.error(f"Migration failed for {collection_name}: {e}")
            result.errors.append(f"Migration failed: {e}")
            result.processing_time = time.time() - start_time
            if not quiet:
                self.console.print(f"❌ Migration failed: {e}", style="red")
            return result

    def _migrate_batch(
        self,
        legacy_points: List[Dict[str, Any]],
        collection_name: str,
        quiet: bool = False,
    ) -> MigrationResult:
        """Migrate a batch of legacy points to new architecture."""
        result = MigrationResult(0, 0, 0, 0, 0, [])

        new_points: List[Dict[str, Any]] = []
        legacy_point_ids = []

        # Group points by file to create content points efficiently
        file_groups: Dict[str, List[Dict[str, Any]]] = {}
        for point in legacy_points:
            payload = point.get("payload", {})
            file_path = payload.get("path", "unknown")

            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(point)

        # Process each file group
        for file_path, file_points in file_groups.items():
            try:
                # Create content points (deduplicated by content)
                content_points_created = self._create_content_points_for_file(
                    file_points, new_points
                )
                result.content_points_created += content_points_created

                # Create visibility points
                visibility_points_created = self._create_visibility_points_for_file(
                    file_points, new_points
                )
                result.visibility_points_created += visibility_points_created

                # Mark legacy points for deletion
                for point in file_points:
                    legacy_point_ids.append(point["id"])

                result.points_migrated += len(file_points)

            except Exception as e:
                error_msg = f"Failed to migrate file {file_path}: {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)

        # Batch upsert new points
        if new_points:
            try:
                success = self.qdrant_client.upsert_points(new_points, collection_name)
                if not success:
                    result.errors.append("Failed to upsert new points")
            except Exception as e:
                error_msg = f"Failed to upsert new points: {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)

        # Delete legacy points
        if legacy_point_ids:
            try:
                deleted_count = self.qdrant_client.delete_points(
                    legacy_point_ids, collection_name
                )
                result.legacy_points_deleted = deleted_count
            except Exception as e:
                error_msg = f"Failed to delete legacy points: {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)

        return result

    def _create_content_points_for_file(
        self, file_points: List[Dict[str, Any]], new_points: List[Dict[str, Any]]
    ) -> int:
        """Create deduplicated content points for a file."""
        content_points_created = 0
        seen_content_hashes = set()

        for point in file_points:
            payload = point.get("payload", {})
            vector = point.get("vector", [])

            # Generate content hash for deduplication
            content_text = payload.get("content", "")
            content_hash = hashlib.sha256(content_text.encode()).hexdigest()

            if content_hash in seen_content_hashes:
                continue  # Skip duplicate content

            seen_content_hashes.add(content_hash)

            # Create content point
            content_id = self._generate_content_id(
                payload.get("path", "unknown"),
                payload.get("git_commit_hash", "unknown"),
                payload.get("chunk_index", 0),
            )

            content_payload = {
                "type": "content",
                "path": payload.get("path", "unknown"),
                "chunk_index": payload.get("chunk_index", 0),
                "total_chunks": payload.get("total_chunks", 1),
                "git_commit": payload.get("git_commit_hash", "unknown"),
                "content_hash": content_hash,
                "file_size": len(content_text),
                "language": payload.get("language", "unknown"),
                "created_at": time.time(),
                "content": content_text,
                "embedding_model": payload.get("embedding_model", "unknown"),
            }

            new_points.append(
                {"id": content_id, "vector": vector, "payload": content_payload}
            )

            content_points_created += 1

        return content_points_created

    def _create_visibility_points_for_file(
        self, file_points: List[Dict[str, Any]], new_points: List[Dict[str, Any]]
    ) -> int:
        """Create visibility points for a file."""
        visibility_points_created = 0

        for point in file_points:
            payload = point.get("payload", {})

            # Generate content ID
            content_id = self._generate_content_id(
                payload.get("path", "unknown"),
                payload.get("git_commit_hash", "unknown"),
                payload.get("chunk_index", 0),
            )

            # Generate visibility ID
            visibility_id = self._generate_visibility_id(
                payload.get("git_branch", "unknown"),
                payload.get("path", "unknown"),
                payload.get("chunk_index", 0),
            )

            # Create zero vector for visibility point
            zero_vector = [0.0] * len(point.get("vector", []))

            visibility_payload = {
                "type": "visibility",
                "branch": payload.get("git_branch", "unknown"),
                "path": payload.get("path", "unknown"),
                "chunk_index": payload.get("chunk_index", 0),
                "content_id": content_id,
                "status": "visible",
                "priority": 1,
                "created_at": time.time(),
            }

            new_points.append(
                {
                    "id": visibility_id,
                    "vector": zero_vector,
                    "payload": visibility_payload,
                }
            )

            visibility_points_created += 1

        return visibility_points_created

    def _generate_content_id(
        self, file_path: str, commit: str, chunk_index: int = 0
    ) -> str:
        """Generate deterministic content ID."""
        content_str = f"{file_path}:{commit}:{chunk_index}"
        namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
        return str(uuid.uuid5(namespace, content_str))

    def _generate_visibility_id(
        self, branch: str, file_path: str, chunk_index: int
    ) -> str:
        """Generate deterministic visibility ID."""
        visibility_str = f"vis_{branch}_{file_path}_{chunk_index}"
        namespace = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")
        return str(uuid.uuid5(namespace, visibility_str))

    def is_migration_safe(self, collection_name: str) -> Tuple[bool, List[str]]:
        """
        Check if migration is safe to perform.

        Returns:
            Tuple of (is_safe, list_of_warnings)
        """
        warnings = []

        try:
            # Check collection size
            size_info = self.qdrant_client.get_collection_size(collection_name)
            point_count = size_info.get("points_count", 0)

            if point_count > 100000:
                warnings.append(
                    f"Large collection ({point_count} points) - migration may take significant time"
                )

            # Check available disk space (if possible)
            # Note: This is approximate since we don't have direct access to disk info
            if point_count > 50000:
                warnings.append(
                    "Large collection - ensure sufficient disk space for temporary storage during migration"
                )

            # Check schema version
            schema = self.schema_manager.detect_schema_version(collection_name)
            if schema.version == "unknown":
                warnings.append(
                    "Unknown schema version detected - migration may not work correctly"
                )

            # Check for mixed schemas
            stats = self.schema_manager.get_migration_stats(collection_name)
            if stats["total_legacy_points"] > 0:
                # Check if we also have new architecture points
                all_points, _ = self.qdrant_client.scroll_points(
                    collection_name=collection_name,
                    limit=100,
                    with_payload=True,
                    with_vectors=False,
                )

                # Check for new architecture points manually
                new_points = []
                for point in all_points:
                    payload = point.get("payload", {})
                    point_type = payload.get("type")
                    is_new_arch = point_type in ["content", "visibility"]
                    if is_new_arch:
                        new_points.append(point)

                if new_points:
                    warnings.append(
                        "Collection contains both legacy and new architecture points - migration will preserve existing new points"
                    )

            # Migration is generally safe, warnings are just informational
            return True, warnings

        except Exception as e:
            logger.error(f"Failed to check migration safety: {e}")
            return False, [f"Failed to check migration safety: {e}"]
