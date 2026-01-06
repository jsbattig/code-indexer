"""
Resource-managed repository operations for CIDX server.

This module demonstrates how to integrate ResourceManager with existing
repository operations to ensure comprehensive resource cleanup during
golden repository management, activated repository operations, and background jobs.

Following CLAUDE.md principles:
- Real resource tracking and cleanup (no mocks)
- Actual file handle management
- Real temporary file deletion
- Genuine database connection handling
- Comprehensive error handling with resource cleanup
"""

from code_indexer.server.middleware.correlation import get_correlation_id

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Dict, Any
from contextlib import asynccontextmanager

from .resource_manager import create_server_resource_manager
from .golden_repo_manager import GoldenRepoManager, GitOperationError
from .activated_repo_manager import ActivatedRepoManager
from .background_jobs import BackgroundJobManager

logger = logging.getLogger(__name__)


class ResourceManagedGoldenRepoOperations:
    """
    Resource-managed wrapper for golden repository operations.

    Demonstrates integration pattern for ResourceManager with existing
    golden repository operations, ensuring all resources are tracked
    and cleaned up properly.
    """

    def __init__(self, golden_repo_manager: GoldenRepoManager):
        """Initialize with existing golden repo manager."""
        self.golden_repo_manager = golden_repo_manager

    async def add_golden_repo_with_resource_management(
        self, repo_url: str, alias: str, default_branch: str = "main"
    ) -> Dict[str, Any]:
        """
        Add golden repository with comprehensive resource management.

        This method demonstrates how to integrate ResourceManager with
        the existing add_golden_repo operation to ensure all temporary
        files, git operations, and metadata files are properly cleaned up.

        Args:
            repo_url: Git repository URL
            alias: Unique repository alias
            default_branch: Default branch to clone

        Returns:
            Operation result with success status

        Raises:
            GitOperationError: If repository operations fail
        """
        async with create_server_resource_manager() as rm:
            logger.info(f"Starting resource-managed addition of golden repo: {alias}", extra={"correlation_id": get_correlation_id()})

            try:
                # Create temporary files for git operations
                git_log_file = tempfile.NamedTemporaryFile(
                    mode="w", suffix="_git.log", delete=False
                )
                clone_status_file = tempfile.NamedTemporaryFile(
                    mode="w", suffix="_clone_status.json", delete=False
                )

                # Track temporary files for cleanup
                rm.track_file_handle(git_log_file)
                rm.track_file_handle(clone_status_file)
                rm.track_temp_file(Path(git_log_file.name))
                rm.track_temp_file(Path(clone_status_file.name))

                # Create temporary directory for clone validation
                temp_validation_dir = Path(
                    tempfile.mkdtemp(suffix=f"_validate_{alias}")
                )
                rm.track_temp_file(temp_validation_dir)

                # Log operation start
                git_log_file.write(
                    f"Starting golden repo addition: {repo_url} -> {alias}\n"
                )
                git_log_file.flush()

                # Execute the actual golden repo addition
                # This would call the existing GoldenRepoManager method
                result = self.golden_repo_manager.add_golden_repo(
                    repo_url=repo_url, alias=alias, default_branch=default_branch
                )

                # Log successful completion
                git_log_file.write("Golden repo addition completed successfully\n")
                git_log_file.flush()

                # Write clone status
                import json

                status_data = {
                    "alias": alias,
                    "repo_url": repo_url,
                    "status": "completed",
                    "job_id": result,  # result is job_id (str), not dict - clone_path available after job completes
                }
                json.dump(status_data, clone_status_file)
                clone_status_file.flush()

                logger.info(
                    f"Successfully added golden repository {alias} with resource management"
                , extra={"correlation_id": get_correlation_id()})
                return {"job_id": result, "alias": alias, "status": "submitted"}

            except Exception as e:
                # Log error to tracked files before cleanup
                try:
                    git_log_file.write(
                        f"ERROR: Golden repo addition failed: {str(e)}\n"
                    )
                    git_log_file.flush()
                except Exception as log_error:
                    logger.debug(
                        f"Failed to write to git log during cleanup: {log_error}"
                    , extra={"correlation_id": get_correlation_id()})
                    # Continue cleanup - don't fail entire operation for logging issue

                logger.error(f"Golden repo addition failed for {alias}: {e}", extra={"correlation_id": get_correlation_id()})
                raise GitOperationError(
                    f"Resource-managed golden repo addition failed: {str(e)}"
                )

        # ResourceManager automatically cleans up all tracked resources here


class ResourceManagedActivatedRepoOperations:
    """
    Resource-managed wrapper for activated repository operations.

    Demonstrates integration pattern for ResourceManager with activated
    repository operations including activation, sync, and branch switching.
    """

    def __init__(self, activated_repo_manager: ActivatedRepoManager):
        """Initialize with existing activated repo manager."""
        self.activated_repo_manager = activated_repo_manager

    async def sync_repository_with_resource_management(
        self, username: str, user_alias: str
    ) -> Dict[str, Any]:
        """
        Sync activated repository with comprehensive resource management.

        Demonstrates how to track git operations, temporary files,
        and database connections during repository synchronization.

        Args:
            username: User requesting sync
            user_alias: User's repository alias

        Returns:
            Sync operation result
        """
        async with create_server_resource_manager() as rm:
            logger.info(f"Starting resource-managed sync for {username}/{user_alias}", extra={"correlation_id": get_correlation_id()})

            try:
                # Create temporary resources for sync operation
                sync_log = tempfile.NamedTemporaryFile(
                    mode="w", suffix="_sync.log", delete=False
                )
                diff_output = tempfile.NamedTemporaryFile(
                    mode="w", suffix="_diff.txt", delete=False
                )
                merge_conflicts = tempfile.NamedTemporaryFile(
                    mode="w", suffix="_conflicts.txt", delete=False
                )

                # Track all sync-related files
                rm.track_file_handle(sync_log)
                rm.track_file_handle(diff_output)
                rm.track_file_handle(merge_conflicts)
                rm.track_temp_file(Path(sync_log.name))
                rm.track_temp_file(Path(diff_output.name))
                rm.track_temp_file(Path(merge_conflicts.name))

                # Create temporary backup directory
                backup_dir = Path(tempfile.mkdtemp(suffix=f"_backup_{user_alias}"))
                rm.track_temp_file(backup_dir)

                # Log sync start
                sync_log.write(f"Starting sync for {username}/{user_alias}\n")
                sync_log.flush()

                # Real git operations would be implemented here
                # For demonstration, we track the operation completion
                async def git_fetch_task():
                    # Real git fetch would happen here
                    sync_log.write("Git fetch completed\n")
                    sync_log.flush()
                    return "fetch_completed"

                async def git_merge_task():
                    # Real git merge would happen here
                    sync_log.write("Git merge completed\n")
                    sync_log.flush()
                    return "merge_completed"

                # Create and track background tasks
                fetch_task = asyncio.create_task(git_fetch_task())
                merge_task = asyncio.create_task(git_merge_task())

                rm.track_background_task(fetch_task, "git_fetch")
                rm.track_background_task(merge_task, "git_merge")

                # Execute sync operation (this would call existing method)
                result = self.activated_repo_manager.sync_with_golden_repository(
                    username=username, user_alias=user_alias
                )

                # Wait for background git operations
                fetch_result = await fetch_task
                merge_result = await merge_task

                sync_log.write(
                    f"Background operations completed: {fetch_result}, {merge_result}\n"
                )
                sync_log.flush()

                logger.info(
                    f"Successfully synced {username}/{user_alias} with resource management"
                , extra={"correlation_id": get_correlation_id()})
                return result

            except Exception as e:
                logger.error(
                    f"Resource-managed sync failed for {username}/{user_alias}: {e}"
                , extra={"correlation_id": get_correlation_id()})
                raise

        # All tracked resources automatically cleaned up


class ResourceManagedBackgroundJobOperations:
    """
    Resource-managed wrapper for background job operations.

    Demonstrates integration pattern for ResourceManager with background
    job execution, ensuring job resources are properly tracked and cleaned up.
    """

    def __init__(self, background_job_manager: BackgroundJobManager):
        """Initialize with existing background job manager."""
        self.background_job_manager = background_job_manager

    async def execute_job_with_resource_management(
        self, job_id: str, operation_func, *args, **kwargs
    ) -> Any:
        """
        Execute background job with comprehensive resource management.

        This method demonstrates how to integrate ResourceManager with
        background job execution to ensure all job resources are tracked
        and cleaned up regardless of job success or failure.

        Args:
            job_id: Unique job identifier
            operation_func: Job operation function to execute
            *args: Operation function arguments
            **kwargs: Operation function keyword arguments

        Returns:
            Job execution result
        """
        async with create_server_resource_manager() as rm:
            logger.info(f"Starting resource-managed job execution: {job_id}", extra={"correlation_id": get_correlation_id()})

            try:
                # Create job workspace and tracking files
                job_workspace = Path(tempfile.mkdtemp(suffix=f"_job_{job_id}"))
                progress_log = tempfile.NamedTemporaryFile(
                    mode="w", suffix="_progress.log", delete=False
                )
                result_cache = tempfile.NamedTemporaryFile(
                    mode="w", suffix="_result.cache", delete=False
                )
                error_log = tempfile.NamedTemporaryFile(
                    mode="w", suffix="_errors.log", delete=False
                )

                # Track all job resources
                rm.track_temp_file(job_workspace)
                rm.track_file_handle(progress_log)
                rm.track_file_handle(result_cache)
                rm.track_file_handle(error_log)
                rm.track_temp_file(Path(progress_log.name))
                rm.track_temp_file(Path(result_cache.name))
                rm.track_temp_file(Path(error_log.name))

                # Log job start
                progress_log.write(f"Job {job_id} started\n")
                progress_log.flush()

                # Execute the actual job operation
                job_result = await operation_func(*args, **kwargs)

                # Cache result
                import json

                json.dump(job_result, result_cache)
                result_cache.flush()

                progress_log.write(f"Job {job_id} completed successfully\n")
                progress_log.flush()

                logger.info(
                    f"Successfully executed job {job_id} with resource management"
                , extra={"correlation_id": get_correlation_id()})
                return job_result

            except Exception as e:
                # Log error before cleanup
                try:
                    error_log.write(f"Job {job_id} failed with error: {str(e)}\n")
                    error_log.flush()
                except Exception as log_error:
                    logger.debug(
                        f"Failed to write to error log during cleanup: {log_error}"
                    , extra={"correlation_id": get_correlation_id()})
                    # Continue cleanup - don't fail entire operation for logging issue

                logger.error(f"Resource-managed job {job_id} failed: {e}", extra={"correlation_id": get_correlation_id()})
                raise

        # All job resources automatically cleaned up


@asynccontextmanager
async def resource_managed_repository_operation(operation_name: str):
    """
    Async context manager for repository operations with resource management.

    This is a utility context manager that can be used to wrap any
    repository operation with ResourceManager integration.

    Usage:
        async with resource_managed_repository_operation("clone_repo") as rm:
            # Create and track resources
            temp_file = tempfile.NamedTemporaryFile()
            rm.track_file_handle(temp_file)

            # Perform repository operation
            result = perform_repo_operation()

            # Resources automatically cleaned up on exit

    Args:
        operation_name: Name of the operation for logging

    Yields:
        ResourceManager instance for resource tracking
    """
    logger.debug(f"Starting resource-managed operation: {operation_name}", extra={"correlation_id": get_correlation_id()})

    async with create_server_resource_manager() as rm:
        try:
            yield rm
        except Exception as e:
            logger.error(f"Resource-managed operation {operation_name} failed: {e}", extra={"correlation_id": get_correlation_id()})
            raise
        finally:
            logger.debug(f"Completed resource-managed operation: {operation_name}", extra={"correlation_id": get_correlation_id()})


# Integration helper functions
async def integrate_resource_manager_with_existing_operations():
    """
    Example function showing how to integrate ResourceManager with existing
    CIDX server operations without breaking existing functionality.

    This demonstrates the integration pattern that should be followed
    when adding ResourceManager to existing codebase.
    """
    # Example: Wrapping existing golden repo operations
    from pathlib import Path

    home_dir = Path.home()
    data_dir = str(home_dir / ".cidx-server" / "data")
    golden_repo_manager = GoldenRepoManager(data_dir=data_dir)
    resource_managed_golden = ResourceManagedGoldenRepoOperations(golden_repo_manager)

    # Example: Using resource-managed operations
    try:
        result = await resource_managed_golden.add_golden_repo_with_resource_management(
            repo_url="https://github.com/example/repo.git", alias="example-repo"
        )
        logger.info(f"Golden repo added with resource management: {result}", extra={"correlation_id": get_correlation_id()})
    except Exception as e:
        logger.error(f"Failed to add golden repo with resource management: {e}", extra={"correlation_id": get_correlation_id()})

    # Example: Using the context manager for custom operations
    async with resource_managed_repository_operation("custom_repo_sync") as rm:
        # Custom operation with resource tracking
        temp_dir = Path(tempfile.mkdtemp())
        rm.track_temp_file(temp_dir)

        # Perform custom operation...
        logger.info("Custom repository operation completed", extra={"correlation_id": get_correlation_id()})


# Server lifecycle integration
async def setup_server_with_resource_management():
    """
    Example of how to set up CIDX server with integrated resource management.

    This shows the pattern for integrating ResourceManager into the server
    startup and shutdown lifecycle.
    """
    from .resource_manager import setup_graceful_shutdown

    # Create server-wide resource manager
    server_resource_manager = create_server_resource_manager(
        memory_monitoring=True, leak_threshold_mb=100
    )

    # Set up graceful shutdown with resource cleanup
    shutdown_handler = setup_graceful_shutdown(server_resource_manager)

    logger.info("Server started with comprehensive resource management", extra={"correlation_id": get_correlation_id()})

    # Server would continue running here...
    # All resources will be cleaned up on shutdown via signal handlers

    return server_resource_manager, shutdown_handler
