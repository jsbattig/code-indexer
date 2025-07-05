"""
Decorator for automatic migration checking before Qdrant operations.

This module provides the @requires_qdrant_access decorator that automatically
ensures migration compatibility before any Qdrant-dependent operation.
"""

import asyncio
import functools
import logging
from pathlib import Path
from typing import Callable, Optional, Any

from .migration_middleware import migration_middleware

logger = logging.getLogger(__name__)


def requires_qdrant_access(operation_name: str, project_path: Optional[Path] = None):
    """
    Decorator to ensure migration compatibility before Qdrant operations.

    This decorator should be applied to any function that requires access to Qdrant
    collections. It will automatically check for and perform necessary migrations
    before the decorated function is executed.

    Args:
        operation_name: Human-readable name of the operation being performed
        project_path: Optional project path, defaults to current working directory

    Example:
        @requires_qdrant_access("query")
        async def query_collections(query_text: str):
            # This function will only run after migration is ensured
            pass
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Determine project path
            target_path = project_path or Path.cwd()

            # Ensure migration compatibility
            try:
                await migration_middleware.ensure_migration_compatibility(
                    operation_name, target_path
                )
            except Exception as e:
                logger.error(f"Migration failed for {operation_name}: {e}")
                raise RuntimeError(
                    f"Cannot proceed with {operation_name}: migration failed"
                ) from e

            # Execute original function
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For synchronous functions, we need to handle async migration
            import asyncio

            async def _ensure_migration():
                try:
                    target_path = project_path or Path.cwd()
                except (FileNotFoundError, OSError):
                    # If current working directory doesn't exist (e.g., in tests),
                    # use a safe default or skip migration check
                    if project_path:
                        target_path = project_path
                    else:
                        # Skip migration check if we can't determine the path
                        logger.warning(
                            f"Skipping migration check for {operation_name}: unable to determine path"
                        )
                        return

                await migration_middleware.ensure_migration_compatibility(
                    operation_name, target_path
                )

            try:
                # Try to run migration in existing event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Create a new task in the existing loop
                        # This is a bit tricky - we need to wait for the task
                        # but we're in a sync context with a running loop
                        # For now, we'll assume the caller can handle this
                        logger.warning(
                            f"Sync function {func.__name__} requires migration check in async context"
                        )
                    else:
                        loop.run_until_complete(_ensure_migration())
                except RuntimeError:
                    # No event loop running, create one
                    asyncio.run(_ensure_migration())

            except Exception as e:
                logger.error(f"Migration failed for {operation_name}: {e}")
                raise RuntimeError(
                    f"Cannot proceed with {operation_name}: migration failed"
                ) from e

            # Execute original function
            return func(*args, **kwargs)

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[no-any-return]
        else:
            return sync_wrapper  # type: ignore[no-any-return]

    return decorator


def requires_qdrant_service(operation_name: str):
    """
    Decorator specifically for operations that require Qdrant service to be running.

    This is a specialized version of requires_qdrant_access that also ensures
    the Qdrant service is started after migration.
    """

    def decorator(func: Callable) -> Callable:
        @requires_qdrant_access(operation_name)
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Ensure Qdrant service is running
            from .docker_manager import DockerManager

            docker_manager = DockerManager()
            if not docker_manager._container_exists("qdrant"):
                logger.info(f"Starting Qdrant service for {operation_name}")
                docker_manager.start_services()

            return await func(*args, **kwargs)

        @requires_qdrant_access(operation_name)
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For sync functions, we need async handling
            import asyncio

            async def _ensure_service():
                from .docker_manager import DockerManager

                docker_manager = DockerManager()
                if not docker_manager._container_exists("qdrant"):
                    logger.info(f"Starting Qdrant service for {operation_name}")
                    docker_manager.start_services()

            try:
                asyncio.run(_ensure_service())
            except Exception as e:
                logger.error(
                    f"Failed to start Qdrant service for {operation_name}: {e}"
                )
                raise RuntimeError(
                    f"Cannot proceed with {operation_name}: service start failed"
                ) from e

            return func(*args, **kwargs)

        # Return appropriate wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[no-any-return]
        else:
            return sync_wrapper  # type: ignore[no-any-return]

    return decorator


def with_migration_context(project_path: Path):
    """
    Context manager version for operations that need explicit project path control.

    Usage:
        async with with_migration_context(project_path) as ctx:
            await ctx.ensure_migration("operation_name")
            # Perform operations
    """

    class MigrationContext:
        def __init__(self, path: Path):
            self.project_path = path

        async def ensure_migration(self, operation_name: str):
            """Ensure migration for the specific project path"""
            await migration_middleware.ensure_migration_compatibility(
                operation_name, self.project_path
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    return MigrationContext(project_path)


class MigrationAwareQdrantClient:
    """
    Wrapper for QdrantClient that automatically handles migration.

    This class wraps the standard QdrantClient and ensures migration
    compatibility before any operation.
    """

    def __init__(self, config, project_path: Optional[Path] = None):
        self.config = config
        self.project_path = project_path or Path.cwd()
        self._client: Optional[Any] = None
        self._migration_ensured = False

    async def _ensure_client(self, operation_name: str):
        """Ensure migration and initialize client"""
        if not self._migration_ensured:
            await migration_middleware.ensure_migration_compatibility(
                operation_name, self.project_path
            )
            self._migration_ensured = True

        if self._client is None:
            from .qdrant import QdrantClient

            self._client = QdrantClient(self.config)

        return self._client

    async def search_points(self, collection_name: str, query_vector, **kwargs):
        """Search points with automatic migration"""
        client = await self._ensure_client("search_points")
        return await client.search_points(collection_name, query_vector, **kwargs)

    async def upsert_points(self, collection_name: str, points, **kwargs):
        """Upsert points with automatic migration"""
        client = await self._ensure_client("upsert_points")
        return await client.upsert_points(collection_name, points, **kwargs)

    async def create_collection(self, collection_name: str, vector_config, **kwargs):
        """Create collection with automatic migration"""
        client = await self._ensure_client("create_collection")
        return await client.create_collection(collection_name, vector_config, **kwargs)

    async def delete_collection(self, collection_name: str):
        """Delete collection with automatic migration"""
        client = await self._ensure_client("delete_collection")
        return await client.delete_collection(collection_name)

    async def collection_exists(self, collection_name: str) -> bool:
        """Check if collection exists with automatic migration"""
        client = await self._ensure_client("collection_exists")
        return bool(await client.collection_exists(collection_name))

    async def get_collection_info(self, collection_name: str):
        """Get collection info with automatic migration"""
        client = await self._ensure_client("get_collection_info")
        return await client.get_collection_info(collection_name)

    async def clear_collection(self, collection_name: str):
        """Clear collection with automatic migration"""
        client = await self._ensure_client("clear_collection")
        return await client.clear_collection(collection_name)

    async def force_flush_to_disk(self, collection_name: str) -> bool:
        """Force flush to disk with automatic migration"""
        client = await self._ensure_client("force_flush_to_disk")
        return bool(await client.force_flush_to_disk(collection_name))
