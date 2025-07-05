"""
Migration middleware for automatic detection and migration of storage configurations.

This module provides transparent migration from global storage to local storage
architecture, ensuring backward compatibility for all Qdrant operations.
"""

import asyncio
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass

from .docker_manager import DockerManager

logger = logging.getLogger(__name__)


@dataclass
class MigrationInfo:
    """Information about migration requirements"""

    needed: bool
    reason: str
    project_id: Optional[str] = None
    collections: Optional[List[str]] = None
    migration_type: Optional[str] = None


@dataclass
class CollectionInfo:
    """Information about a collection to be migrated"""

    name: str
    path: Path
    size: int
    project_id: str


class MigrationStateTracker:
    """Track migration state to avoid repeated checks and operations"""

    def __init__(self):
        self.state_file = Path.home() / ".code-indexer" / "migration_state.json"
        self._state: Optional[Dict] = None
        self._lock = asyncio.Lock()

    async def load_state(self) -> Dict:
        """Load migration state from disk"""
        async with self._lock:
            if self._state is None:
                if self.state_file.exists():
                    try:
                        with open(self.state_file) as f:
                            self._state = json.load(f)
                        logger.debug(f"Loaded migration state: {self._state}")
                    except (json.JSONDecodeError, IOError) as e:
                        logger.warning(f"Failed to load migration state: {e}")
                        self._state = self._get_default_state()
                else:
                    self._state = self._get_default_state()
                    logger.debug("Created default migration state")
            return self._state.copy()

    def _get_default_state(self) -> Dict:
        """Get default migration state"""
        return {
            "container_migrated": False,
            "migrated_projects": [],
            "migration_version": "1.0",
            "last_check": None,
            "failed_migrations": [],
        }

    async def save_state(self):
        """Save migration state to disk"""
        async with self._lock:
            await self._save_state_unsafe()

    async def _save_state_unsafe(self):
        """Save migration state to disk without acquiring lock"""
        if self._state is not None:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(self.state_file, "w") as f:
                    json.dump(self._state, f, indent=2)
                logger.debug(f"Saved migration state: {self._state}")
            except IOError as e:
                logger.error(f"Failed to save migration state: {e}")

    async def mark_container_migrated(self):
        """Mark container as migrated to new architecture"""
        state = await self.load_state()
        state["container_migrated"] = True
        state["last_check"] = datetime.now().isoformat()
        self._state = state
        await self.save_state()
        logger.info("Container marked as migrated in state")

    async def mark_project_migrated(self, project_path: Path):
        """Mark specific project as migrated"""
        state = await self.load_state()
        project_key = str(project_path.resolve())

        if project_key not in state["migrated_projects"]:
            state["migrated_projects"].append(project_key)
            state["last_check"] = datetime.now().isoformat()
            self._state = state
            await self.save_state()
            logger.info(f"Project {project_path} marked as migrated")

    async def mark_migration_failed(self, project_path: Path, error: str):
        """Mark migration as failed for debugging"""
        state = await self.load_state()
        failure_info = {
            "project": str(project_path.resolve()),
            "error": error,
            "timestamp": datetime.now().isoformat(),
        }
        state["failed_migrations"].append(failure_info)
        # Keep only last 10 failures
        state["failed_migrations"] = state["failed_migrations"][-10:]
        self._state = state
        await self.save_state()
        logger.error(f"Migration failure recorded for {project_path}: {error}")

    async def needs_container_migration(self) -> bool:
        """Check if container migration is needed"""
        state = await self.load_state()
        return not state.get("container_migrated", False)

    async def needs_project_migration(self, project_path: Path) -> bool:
        """Check if project migration is needed"""
        state = await self.load_state()
        project_key = str(project_path.resolve())
        return project_key not in state.get("migrated_projects", [])

    async def reset_migration_state(self):
        """Reset migration state for testing or troubleshooting"""
        async with self._lock:
            self._state = self._get_default_state()
            await self._save_state_unsafe()
            logger.info("Migration state reset to defaults")


class MigrationMiddleware:
    """Global middleware for automatic migration checking and execution"""

    def __init__(self):
        self._session_checked: Set[str] = set()
        self.state_tracker = MigrationStateTracker()
        self._migration_lock = asyncio.Lock()

    async def ensure_migration_compatibility(
        self, operation_name: str, project_path: Optional[Path] = None
    ):
        """
        Ensure system is migrated before any Qdrant operation.

        Args:
            operation_name: Name of the operation being performed
            project_path: Optional project path, defaults to current directory
        """
        if project_path is None:
            project_path = Path.cwd()

        session_key = f"{operation_name}:{project_path}"

        # Skip if already checked in this session
        if session_key in self._session_checked:
            return

        async with self._migration_lock:
            logger.debug(
                f"Checking migration compatibility for {operation_name} in {project_path}"
            )

            try:
                # Step 1: Check container configuration
                container_migration_needed = (
                    await self._check_container_migration_needed()
                )

                # Step 2: Check project-level migration
                project_migration_needed = await self._check_project_migration_needed(
                    project_path
                )

                # Step 3: Perform migrations if needed
                if container_migration_needed or project_migration_needed:
                    await self._perform_migration(
                        operation_name,
                        project_path,
                        container_migration_needed,
                        project_migration_needed,
                    )

                # Mark as checked for this session
                self._session_checked.add(session_key)

            except Exception as e:
                logger.error(
                    f"Migration compatibility check failed for {operation_name}: {e}"
                )
                await self.state_tracker.mark_migration_failed(project_path, str(e))
                raise

    async def _check_container_migration_needed(self) -> bool:
        """Check if container needs migration to home folder mounting"""
        # First check state tracker
        if not await self.state_tracker.needs_container_migration():
            return False

        # Verify actual container state
        try:
            docker_manager = DockerManager()

            # Check if container exists
            if not docker_manager._container_exists("qdrant"):
                logger.debug("No Qdrant container exists - migration needed")
                return True

            # For now, we'll assume container needs migration if it exists
            # but state tracker says it needs migration
            # TODO: Implement proper mount inspection
            logger.debug("Container exists but state indicates migration needed")
            has_home_mount = False

            if has_home_mount:
                # Container already migrated, update state
                await self.state_tracker.mark_container_migrated()
                return False

            logger.info("Container migration needed: missing home folder mount")
            return True

        except Exception as e:
            logger.warning(f"Failed to check container state: {e}")
            return True  # Assume migration needed if we can't check

    async def _check_project_migration_needed(self, project_path: Path) -> bool:
        """Check if project needs collection migration from global storage"""
        # First check state tracker
        if not await self.state_tracker.needs_project_migration(project_path):
            return False

        # Check if project has local storage already
        local_storage = project_path / ".code-indexer" / "qdrant-data"
        if local_storage.exists() and local_storage.is_dir():
            # Project already has local storage, mark as migrated
            await self.state_tracker.mark_project_migrated(project_path)
            return False

        # Check if project is initialized
        config_file = project_path / ".code-indexer" / "config.json"
        if not config_file.exists():
            logger.debug(
                f"Project {project_path} not initialized - no migration needed"
            )
            return False

        # Check for collections in global storage
        try:
            global_collections = await self._find_project_collections_in_global_storage(
                project_path
            )
            if global_collections:
                logger.info(
                    f"Project migration needed: found {len(global_collections)} collections in global storage"
                )
                return True
            else:
                # No collections found, mark as migrated (new project)
                await self.state_tracker.mark_project_migrated(project_path)
                return False

        except Exception as e:
            logger.warning(f"Failed to check project collections: {e}")
            return False  # Don't migrate if we can't reliably detect

    async def _find_project_collections_in_global_storage(
        self, project_path: Path
    ) -> List[CollectionInfo]:
        """Find collections belonging to this project in global storage"""
        collections: List[CollectionInfo] = []

        try:
            # Load project config to get project ID

            # Generate project ID
            from .embedding_factory import EmbeddingProviderFactory

            project_id = EmbeddingProviderFactory.generate_project_id(str(project_path))

            # Get global storage path
            global_storage_path = await self._get_global_storage_path()
            if not global_storage_path or not global_storage_path.exists():
                return collections

            # Look for collections with project ID in name
            collections_dir = global_storage_path / "collections"
            if collections_dir.exists():
                for collection_dir in collections_dir.iterdir():
                    if collection_dir.is_dir() and project_id in collection_dir.name:
                        size = self._get_directory_size(collection_dir)
                        collections.append(
                            CollectionInfo(
                                name=collection_dir.name,
                                path=collection_dir,
                                size=size,
                                project_id=project_id,
                            )
                        )

            logger.debug(
                f"Found {len(collections)} collections for project {project_id}"
            )

        except Exception as e:
            logger.error(f"Error finding project collections: {e}")

        return collections

    async def _get_global_storage_path(self) -> Optional[Path]:
        """Get the path to global Qdrant storage"""
        try:
            # Check if global storage volume exists

            # For now, we'll use a heuristic to find the volume
            # In production, this should be more robust
            # For now, return a reasonable default path
            # TODO: Implement proper volume inspection
            potential_paths = [
                Path("/var/lib/docker/volumes/qdrant_data/_data"),
                Path(Path.home() / ".docker" / "volumes" / "qdrant_data" / "_data"),
            ]

            for path in potential_paths:
                if path.exists():
                    return path

            return None

        except Exception as e:
            logger.debug(f"Could not find global storage path: {e}")
            return None

    def _get_directory_size(self, path: Path) -> int:
        """Get the total size of a directory in bytes"""
        total_size = 0
        try:
            for file_path in path.rglob("*"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
        except (OSError, PermissionError):
            pass
        return total_size

    async def _perform_migration(
        self,
        operation_name: str,
        project_path: Path,
        container_migration_needed: bool,
        project_migration_needed: bool,
    ):
        """Perform the actual migration operations"""
        logger.info(f"🔄 Automatic migration required for {operation_name}")

        try:
            # Step 1: Container migration
            if container_migration_needed:
                logger.info("📦 Migrating container configuration...")
                await self._migrate_container_configuration()
                await self.state_tracker.mark_container_migrated()

            # Step 2: Project migration
            if project_migration_needed:
                logger.info("📁 Migrating project collections...")
                await self._migrate_project_collections(project_path)
                await self.state_tracker.mark_project_migrated(project_path)

            logger.info("✅ Migration completed successfully")

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            await self.state_tracker.mark_migration_failed(project_path, str(e))
            raise

    async def _migrate_container_configuration(self):
        """Migrate container to use home folder mounting"""
        docker_manager = DockerManager()

        # Stop existing container if running
        if docker_manager._container_exists("qdrant"):
            logger.info("Stopping existing container for migration...")
            docker_manager.stop_services()

        # The actual container recreation will happen when services are started
        # with the new configuration
        logger.debug("Container configuration migration prepared")

    async def _migrate_project_collections(self, project_path: Path):
        """Migrate project collections from global to local storage"""
        collections = await self._find_project_collections_in_global_storage(
            project_path
        )

        if not collections:
            logger.debug("No collections to migrate")
            return

        # Create local storage directory
        local_storage = project_path / ".code-indexer" / "qdrant-data"
        local_collections = local_storage / "collections"
        local_collections.mkdir(parents=True, exist_ok=True)

        # Create backup before migration
        backup_dir = await self._create_migration_backup(collections)

        try:
            # Stop services to ensure safe migration
            docker_manager = DockerManager()
            if docker_manager._container_exists("qdrant"):
                docker_manager.stop_services()

            # Move each collection
            for collection in collections:
                source_path = collection.path
                dest_path = local_collections / collection.name

                logger.info(
                    f"Migrating collection {collection.name} ({collection.size} bytes)"
                )

                if dest_path.exists():
                    logger.warning(f"Destination {dest_path} exists, removing...")
                    shutil.rmtree(dest_path)

                # Use shutil.move for atomic move within same filesystem
                shutil.move(str(source_path), str(dest_path))
                logger.info(f"✅ Successfully migrated {collection.name}")

            # Verify migration integrity
            if not await self._verify_migration_integrity(
                collections, local_collections
            ):
                raise RuntimeError("Migration integrity verification failed")

            logger.info(f"Successfully migrated {len(collections)} collections")

        except Exception as e:
            logger.error(f"Migration failed, attempting rollback: {e}")
            await self._rollback_migration(backup_dir, collections)
            raise

    async def _create_migration_backup(self, collections: List[CollectionInfo]) -> Path:
        """Create backup of collections before migration"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = Path(f"/tmp/qdrant_migration_backup_{timestamp}")
        backup_dir.mkdir(parents=True)

        for collection in collections:
            backup_path = backup_dir / collection.name
            shutil.copytree(collection.path, backup_path)

        logger.info(f"Backup created at {backup_dir}")
        return backup_dir

    async def _verify_migration_integrity(
        self, source_collections: List[CollectionInfo], target_dir: Path
    ) -> bool:
        """Verify all collections migrated successfully"""
        for collection in source_collections:
            target_path = target_dir / collection.name

            if not target_path.exists():
                logger.error(f"Collection {collection.name} not found in target")
                return False

            # Verify size matches approximately (allow for small differences)
            target_size = self._get_directory_size(target_path)
            size_diff = abs(target_size - collection.size)
            if size_diff > 1024:  # Allow 1KB difference
                logger.error(
                    f"Size mismatch for {collection.name}: {target_size} != {collection.size}"
                )
                return False

        return True

    async def _rollback_migration(
        self, backup_dir: Path, collections: List[CollectionInfo]
    ):
        """Rollback migration if something goes wrong"""
        if not backup_dir.exists():
            logger.error("Cannot rollback: backup directory not found")
            return

        logger.info(f"Rolling back migration from backup {backup_dir}")

        try:
            global_storage_path = await self._get_global_storage_path()
            if not global_storage_path:
                logger.error("Cannot rollback: global storage path not found")
                return

            collections_dir = global_storage_path / "collections"
            collections_dir.mkdir(parents=True, exist_ok=True)

            for backup_collection in backup_dir.iterdir():
                if backup_collection.is_dir():
                    target_path = collections_dir / backup_collection.name
                    if target_path.exists():
                        shutil.rmtree(target_path)
                    shutil.copytree(backup_collection, target_path)

            logger.info("Migration rollback completed")

        except Exception as e:
            logger.error(f"Rollback failed: {e}")


# Global middleware instance
migration_middleware = MigrationMiddleware()
