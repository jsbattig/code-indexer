"""
Decorator for automatic legacy detection before Qdrant operations.

This module provides the @requires_qdrant_access decorator that automatically
detects legacy containers and guides users to run clean-legacy.
"""

import asyncio
import functools
import logging
from pathlib import Path
from typing import Callable, Optional

from .legacy_detector import legacy_detector

logger = logging.getLogger(__name__)


def requires_qdrant_access(operation_name: str, project_path: Optional[Path] = None):
    """
    Decorator to detect legacy containers before Qdrant operations.

    This decorator should be applied to any function that requires access to Qdrant
    collections. It will automatically check for legacy containers and provide
    clear guidance to users.

    Args:
        operation_name: Human-readable name of the operation being performed
        project_path: Optional project path, defaults to current working directory

    Example:
        @requires_qdrant_access("query")
        async def query_collections(query_text: str):
            # This function will only run after legacy check passes
            pass
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Check for legacy containers
            try:
                is_legacy = await legacy_detector.check_legacy_container()
                if is_legacy:
                    error_message = legacy_detector.get_legacy_error_message()
                    raise RuntimeError(error_message)
            except Exception as e:
                if "Legacy container detected" in str(e):
                    # Re-raise legacy detection errors as-is
                    raise
                logger.error(f"Legacy detection failed for {operation_name}: {e}")
                # For other errors, continue with operation (fail-open)

            # Execute original function
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For synchronous functions, we need to handle async legacy detection
            import asyncio

            async def _check_legacy():
                is_legacy = await legacy_detector.check_legacy_container()
                if is_legacy:
                    error_message = legacy_detector.get_legacy_error_message()
                    raise RuntimeError(error_message)

            try:
                # Try to run legacy check in existing event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Create a new task in the existing loop
                        logger.warning(
                            f"Sync function {func.__name__} requires legacy check in async context"
                        )
                        # For now, skip the check in this case
                    else:
                        loop.run_until_complete(_check_legacy())
                except RuntimeError:
                    # No event loop running, create one
                    asyncio.run(_check_legacy())

            except Exception as e:
                if "Legacy container detected" in str(e):
                    # Re-raise legacy detection errors as-is
                    raise
                logger.error(f"Legacy detection failed for {operation_name}: {e}")
                # For other errors, continue with operation (fail-open)

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
    the Qdrant service is started after legacy check passes.
    """

    def decorator(func: Callable) -> Callable:
        @requires_qdrant_access(operation_name)
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Ensure Qdrant service is running
            from .docker_manager import DockerManager

            docker_manager = DockerManager()
            # Check if any qdrant container is running (new approach: find any cidx qdrant container)
            import subprocess

            container_engine = "docker" if docker_manager.force_docker else "podman"
            try:
                list_cmd = [container_engine, "ps", "--format", "{{.Names}}"]
                result = subprocess.run(
                    list_cmd, capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    running_containers = (
                        result.stdout.strip().split("\n")
                        if result.stdout.strip()
                        else []
                    )
                    qdrant_containers = [
                        name
                        for name in running_containers
                        if "qdrant" in name and name.startswith("cidx-")
                    ]
                    container_exists = len(qdrant_containers) > 0
                else:
                    container_exists = False
            except Exception:
                container_exists = False

            if not container_exists:
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
                # Check if any qdrant container is running (new approach: find any cidx qdrant container)
                import subprocess

                container_engine = "docker" if docker_manager.force_docker else "podman"
                try:
                    list_cmd = [container_engine, "ps", "--format", "{{.Names}}"]
                    result = subprocess.run(
                        list_cmd, capture_output=True, text=True, timeout=10
                    )
                    if result.returncode == 0:
                        running_containers = (
                            result.stdout.strip().split("\n")
                            if result.stdout.strip()
                            else []
                        )
                        qdrant_containers = [
                            name
                            for name in running_containers
                            if "qdrant" in name and name.startswith("cidx-")
                        ]
                        container_exists = len(qdrant_containers) > 0
                    else:
                        container_exists = False
                except Exception:
                    container_exists = False

                if not container_exists:
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
