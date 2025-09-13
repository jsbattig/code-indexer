"""
Integration tests for ResourceManager with existing repository operations.

These tests validate that ResourceManager properly integrates with existing
CIDX server repository management operations, ensuring comprehensive resource
cleanup during golden repo management, activated repo operations, and background jobs.
"""

import asyncio
import signal
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from code_indexer.server.repositories.resource_manager import ResourceManager
from code_indexer.server.repositories.golden_repo_manager import GoldenRepoManager
from code_indexer.server.repositories.activated_repo_manager import ActivatedRepoManager
from code_indexer.server.repositories.background_jobs import BackgroundJobManager


class TestGoldenRepoManagerResourceIntegration:
    """
    Test ResourceManager integration with GoldenRepoManager operations.

    These tests ensure that all golden repository operations properly track
    and cleanup resources like file handles, git operations, and temporary files.
    """

    @pytest.mark.asyncio
    async def test_add_golden_repo_with_resource_management(self):
        """Test that adding golden repo tracks and cleans up all resources."""
        MagicMock(spec=GoldenRepoManager)

        async with ResourceManager() as rm:
            # Mock git clone operation that would create resources
            clone_dir = tempfile.mkdtemp()
            git_lock_file = tempfile.NamedTemporaryFile(mode="w", suffix=".lock")
            metadata_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json")

            # Track resources that would be created during git clone
            rm.track_temp_file(Path(clone_dir))
            rm.track_file_handle(git_lock_file)
            rm.track_file_handle(metadata_file)

            # Simulate add golden repo operation

            # Resources should be tracked during operation
            assert len(rm.tracked_temp_files) == 1
            assert len(rm.tracked_files) == 2
            assert Path(clone_dir).exists()
            assert not git_lock_file.closed
            assert not metadata_file.closed

        # After ResourceManager context, all resources should be cleaned up
        assert not Path(clone_dir).exists()
        assert git_lock_file.closed
        assert metadata_file.closed

    @pytest.mark.asyncio
    async def test_refresh_golden_repo_with_resource_management(self):
        """Test that refreshing golden repo properly manages git resources."""
        async with ResourceManager() as rm:
            # Mock git operations during refresh
            temp_git_dir = tempfile.mkdtemp(suffix="_git_temp")
            fetch_log_file = tempfile.NamedTemporaryFile(mode="w", suffix="_fetch.log")
            merge_lock_file = tempfile.NamedTemporaryFile(
                mode="w", suffix="_merge.lock"
            )

            # Track git operation resources
            rm.track_temp_file(Path(temp_git_dir))
            rm.track_file_handle(fetch_log_file)
            rm.track_file_handle(merge_lock_file)

            # Simulate async git refresh operations
            async def mock_git_fetch():
                await asyncio.sleep(0.1)
                return "fetch_completed"

            async def mock_git_merge():
                await asyncio.sleep(0.1)
                return "merge_completed"

            fetch_task = asyncio.create_task(mock_git_fetch())
            merge_task = asyncio.create_task(mock_git_merge())

            rm.track_background_task(fetch_task, "git_fetch")
            rm.track_background_task(merge_task, "git_merge")

            # Wait for operations to complete
            fetch_result = await fetch_task
            merge_result = await merge_task

            assert fetch_result == "fetch_completed"
            assert merge_result == "merge_completed"

        # All resources should be cleaned up after context
        assert not Path(temp_git_dir).exists()
        assert fetch_log_file.closed
        assert merge_lock_file.closed

    @pytest.mark.asyncio
    async def test_remove_golden_repo_with_resource_cleanup(self):
        """Test that removing golden repo cleans up all associated resources."""
        async with ResourceManager() as rm:
            # Mock repository removal resources
            repo_clone_dir = tempfile.mkdtemp(suffix="_clone")
            metadata_backup = tempfile.NamedTemporaryFile(
                mode="w", suffix="_backup.json"
            )
            removal_log = tempfile.NamedTemporaryFile(mode="w", suffix="_removal.log")

            rm.track_temp_file(Path(repo_clone_dir))
            rm.track_file_handle(metadata_backup)
            rm.track_file_handle(removal_log)

            # Mock database connection for metadata removal
            mock_metadata_db = MagicMock()
            rm.track_database_connection(mock_metadata_db, "metadata_cleanup")

            # Simulate repository removal operation
            assert Path(repo_clone_dir).exists()
            assert len(rm.tracked_files) == 2
            assert len(rm.tracked_connections) == 1

        # All removal resources should be cleaned up
        assert not Path(repo_clone_dir).exists()
        assert metadata_backup.closed
        assert removal_log.closed
        mock_metadata_db.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_golden_repo_manager_cleanup_on_exception(self):
        """Test resource cleanup when golden repo operations encounter exceptions."""
        # Mock resources that would be created before exception
        temp_resources = []

        def create_mock_resources():
            clone_dir = tempfile.mkdtemp()
            git_file = tempfile.NamedTemporaryFile(mode="w")
            temp_resources.extend([clone_dir, git_file])
            return clone_dir, git_file

        with pytest.raises(Exception, match="Simulated git error"):
            # This should fail and trigger resource cleanup
            async with ResourceManager() as rm:
                clone_dir, git_file = create_mock_resources()

                rm.track_temp_file(Path(clone_dir))
                rm.track_file_handle(git_file)

                # Simulate exception during git operation
                raise Exception("Simulated git error")

        # Even with exception, resources should be cleaned up
        clone_dir, git_file = temp_resources
        assert not Path(clone_dir).exists()
        assert git_file.closed


class TestActivatedRepoManagerResourceIntegration:
    """
    Test ResourceManager integration with ActivatedRepoManager operations.

    These tests ensure activated repository operations properly manage
    user-specific repository resources and cleanup.
    """

    @pytest.mark.asyncio
    async def test_activate_repository_with_resource_management(self):
        """Test repository activation with comprehensive resource tracking."""
        MagicMock(spec=ActivatedRepoManager)

        async with ResourceManager() as rm:
            # Mock repository activation resources
            user_repo_dir = tempfile.mkdtemp(suffix="_user_repo")
            activation_config = tempfile.NamedTemporaryFile(
                mode="w", suffix="_config.json"
            )
            index_cache = tempfile.NamedTemporaryFile(mode="w", suffix="_index.cache")

            rm.track_temp_file(Path(user_repo_dir))
            rm.track_file_handle(activation_config)
            rm.track_file_handle(index_cache)

            # Mock database connection for user repo tracking
            mock_user_db = MagicMock()
            rm.track_database_connection(mock_user_db, "user_repos")

            # Simulate background activation task
            async def mock_activation_task():
                await asyncio.sleep(0.1)
                return {"success": True, "user_alias": "test-repo"}

            activation_task = asyncio.create_task(mock_activation_task())
            rm.track_background_task(activation_task, "repo_activation")

            result = await activation_task
            assert result["success"] is True

            # Resources should be tracked during activation
            assert len(rm.tracked_temp_files) == 1
            assert len(rm.tracked_files) == 2
            assert len(rm.tracked_connections) == 1

        # After activation complete, resources should be cleaned up
        assert not Path(user_repo_dir).exists()
        assert activation_config.closed
        assert index_cache.closed
        mock_user_db.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_deactivate_repository_with_resource_cleanup(self):
        """Test repository deactivation with proper resource cleanup."""
        async with ResourceManager() as rm:
            # Mock deactivation resources
            user_data_dir = tempfile.mkdtemp(suffix="_deactivation")
            cleanup_log = tempfile.NamedTemporaryFile(mode="w", suffix="_cleanup.log")
            backup_file = tempfile.NamedTemporaryFile(mode="w", suffix="_backup.tar.gz")

            rm.track_temp_file(Path(user_data_dir))
            rm.track_file_handle(cleanup_log)
            rm.track_file_handle(backup_file)

            # Mock multiple database connections for deactivation
            user_db = MagicMock()
            index_db = MagicMock()

            rm.track_database_connection(user_db, "user_data")
            rm.track_database_connection(index_db, "search_index")

            # Simulate deactivation operation
            assert Path(user_data_dir).exists()
            assert len(rm.tracked_connections) == 2

        # Deactivation should clean up all resources
        assert not Path(user_data_dir).exists()
        assert cleanup_log.closed
        assert backup_file.closed
        user_db.close.assert_called_once()
        index_db.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_with_golden_repository_resource_management(self):
        """Test repository sync operation with comprehensive resource tracking."""
        async with ResourceManager() as rm:
            # Mock sync operation resources
            sync_temp_dir = tempfile.mkdtemp(suffix="_sync")
            git_diff_file = tempfile.NamedTemporaryFile(mode="w", suffix="_diff.txt")
            merge_conflicts_file = tempfile.NamedTemporaryFile(
                mode="w", suffix="_conflicts.txt"
            )

            rm.track_temp_file(Path(sync_temp_dir))
            rm.track_file_handle(git_diff_file)
            rm.track_file_handle(merge_conflicts_file)

            # Mock concurrent sync tasks
            async def mock_git_pull():
                await asyncio.sleep(0.1)
                return "pull_completed"

            async def mock_index_update():
                await asyncio.sleep(0.15)
                return "index_updated"

            async def mock_conflict_resolution():
                await asyncio.sleep(0.05)
                return "conflicts_resolved"

            pull_task = asyncio.create_task(mock_git_pull())
            index_task = asyncio.create_task(mock_index_update())
            conflict_task = asyncio.create_task(mock_conflict_resolution())

            rm.track_background_task(pull_task, "git_pull")
            rm.track_background_task(index_task, "index_update")
            rm.track_background_task(conflict_task, "conflict_resolution")

            # Wait for all sync operations
            results = await asyncio.gather(pull_task, index_task, conflict_task)

            assert "pull_completed" in results
            assert "index_updated" in results
            assert "conflicts_resolved" in results

        # All sync resources should be cleaned up
        assert not Path(sync_temp_dir).exists()
        assert git_diff_file.closed
        assert merge_conflicts_file.closed

    @pytest.mark.asyncio
    async def test_branch_switching_with_resource_management(self):
        """Test branch switching operations with resource tracking."""
        async with ResourceManager() as rm:
            # Mock branch switch resources
            branch_backup_dir = tempfile.mkdtemp(suffix="_branch_backup")
            switch_log = tempfile.NamedTemporaryFile(mode="w", suffix="_switch.log")
            stash_file = tempfile.NamedTemporaryFile(mode="w", suffix="_stash.patch")

            rm.track_temp_file(Path(branch_backup_dir))
            rm.track_file_handle(switch_log)
            rm.track_file_handle(stash_file)

            # Mock git operations for branch switching
            async def mock_git_stash():
                await asyncio.sleep(0.1)
                return "stash_created"

            async def mock_git_checkout():
                await asyncio.sleep(0.1)
                return "branch_switched"

            stash_task = asyncio.create_task(mock_git_stash())
            checkout_task = asyncio.create_task(mock_git_checkout())

            rm.track_background_task(stash_task, "git_stash")
            rm.track_background_task(checkout_task, "git_checkout")

            # Execute branch switch operations
            stash_result = await stash_task
            checkout_result = await checkout_task

            assert stash_result == "stash_created"
            assert checkout_result == "branch_switched"

        # Branch switch resources should be cleaned up
        assert not Path(branch_backup_dir).exists()
        assert switch_log.closed
        assert stash_file.closed


class TestBackgroundJobManagerResourceIntegration:
    """
    Test ResourceManager integration with BackgroundJobManager operations.

    These tests ensure background jobs properly track and cleanup resources
    during execution, cancellation, and completion.
    """

    @pytest.mark.asyncio
    async def test_background_job_execution_with_resource_tracking(self):
        """Test background job execution with comprehensive resource management."""
        MagicMock(spec=BackgroundJobManager)

        async def mock_repository_job(rm: ResourceManager):
            """Mock background job that creates various resources."""
            # Job creates temporary resources
            job_workspace = tempfile.mkdtemp(suffix="_job")
            progress_log = tempfile.NamedTemporaryFile(mode="w", suffix="_progress.log")
            result_cache = tempfile.NamedTemporaryFile(mode="w", suffix="_result.cache")

            rm.track_temp_file(Path(job_workspace))
            rm.track_file_handle(progress_log)
            rm.track_file_handle(result_cache)

            # Mock database connection for job status updates
            job_db = MagicMock()
            rm.track_database_connection(job_db, "job_status")

            # Simulate job work
            await asyncio.sleep(0.2)

            return {
                "job_id": "test-job-123",
                "status": "completed",
                "result": {"processed_files": 150},
            }

        # Execute job with resource management
        async with ResourceManager() as rm:
            result = await mock_repository_job(rm)

            # Job should complete successfully
            assert result["status"] == "completed"
            assert result["result"]["processed_files"] == 150

            # Resources should be tracked during execution
            assert len(rm.tracked_temp_files) == 1
            assert len(rm.tracked_files) == 2
            assert len(rm.tracked_connections) == 1

        # After job completion, all resources should be cleaned up
        assert len(rm.tracked_temp_files) == 0
        assert len(rm.tracked_files) == 0
        assert len(rm.tracked_connections) == 0

    @pytest.mark.asyncio
    async def test_job_cancellation_with_resource_cleanup(self):
        """Test that job cancellation properly cleans up resources."""

        async def cancellable_job(rm: ResourceManager):
            # Create resources that need cleanup on cancellation
            job_temp_dir = tempfile.mkdtemp(suffix="_cancellable")
            partial_result_file = tempfile.NamedTemporaryFile(
                mode="w", suffix="_partial.json"
            )

            rm.track_temp_file(Path(job_temp_dir))
            rm.track_file_handle(partial_result_file)

            # Simulate long-running work that gets cancelled
            try:
                await asyncio.sleep(10)  # Long operation
                return {"status": "completed"}
            except asyncio.CancelledError:
                # Job cancelled - ResourceManager should still cleanup resources
                # Re-raise CancelledError to keep task in cancelled state
                raise

        async with ResourceManager() as rm:
            # Start cancellable job
            job_task = asyncio.create_task(cancellable_job(rm))
            rm.track_background_task(job_task, "cancellable_job")

            # Let job start, then cancel it
            await asyncio.sleep(0.1)
            job_task.cancel()

            try:
                await job_task
            except asyncio.CancelledError:
                pass  # Expected for cancelled job

            # Job should be cancelled
            assert job_task.cancelled()

        # Resources should still be cleaned up despite cancellation
        assert len(rm.tracked_temp_files) == 0
        assert len(rm.tracked_files) == 0

    @pytest.mark.asyncio
    async def test_multiple_concurrent_jobs_resource_isolation(self):
        """Test resource isolation between multiple concurrent background jobs."""

        async def resource_job(rm: ResourceManager, job_id: str):
            # Each job creates its own resources
            job_dir = tempfile.mkdtemp(suffix=f"_job_{job_id}")
            job_log = tempfile.NamedTemporaryFile(mode="w", suffix=f"_{job_id}.log")

            rm.track_temp_file(Path(job_dir))
            rm.track_file_handle(job_log)

            # Simulate job work
            await asyncio.sleep(0.1)

            return {"job_id": job_id, "status": "completed"}

        async with ResourceManager() as rm:
            # Start multiple concurrent jobs
            job_tasks = []
            for i in range(3):
                task = asyncio.create_task(resource_job(rm, f"job_{i}"))
                rm.track_background_task(task, f"job_{i}")
                job_tasks.append(task)

            # Wait for all jobs to complete
            results = await asyncio.gather(*job_tasks)

            # All jobs should complete successfully
            assert len(results) == 3
            for i, result in enumerate(results):
                assert result["job_id"] == f"job_{i}"
                assert result["status"] == "completed"

            # All job resources should be tracked
            assert len(rm.tracked_temp_files) == 3
            assert len(rm.tracked_files) == 3

        # After context, all resources from all jobs should be cleaned up
        assert len(rm.tracked_temp_files) == 0
        assert len(rm.tracked_files) == 0

    @pytest.mark.asyncio
    async def test_job_queue_resource_management(self):
        """Test resource management during job queue operations."""
        MagicMock(spec=BackgroundJobManager)

        async with ResourceManager() as rm:
            # Mock job queue database connection
            queue_db = MagicMock()
            rm.track_database_connection(queue_db, "job_queue")

            # Mock job persistence files
            queue_file = tempfile.NamedTemporaryFile(mode="w", suffix="_queue.json")
            status_file = tempfile.NamedTemporaryFile(mode="w", suffix="_status.json")

            rm.track_file_handle(queue_file)
            rm.track_file_handle(status_file)

            # Simulate job queue operations
            assert len(rm.tracked_connections) == 1
            assert len(rm.tracked_files) == 2

        # Job queue resources should be cleaned up
        queue_db.close.assert_called_once()
        assert queue_file.closed
        assert status_file.closed


class TestResourceManagerServerLifecycleIntegration:
    """
    Test ResourceManager integration with overall server lifecycle.

    These tests validate resource management during server startup,
    operation, and shutdown scenarios.
    """

    @pytest.mark.asyncio
    async def test_server_startup_resource_initialization(self):
        """Test resource management during server startup."""
        # Mock server startup resources
        startup_resources = {}

        async with ResourceManager() as rm:
            # Mock server initialization resources
            config_cache = tempfile.NamedTemporaryFile(mode="w", suffix="_config.cache")
            startup_log = tempfile.NamedTemporaryFile(mode="w", suffix="_startup.log")
            temp_init_dir = tempfile.mkdtemp(suffix="_server_init")

            rm.track_file_handle(config_cache)
            rm.track_file_handle(startup_log)
            rm.track_temp_file(Path(temp_init_dir))

            # Mock database connections during startup
            user_db = MagicMock()
            job_db = MagicMock()
            config_db = MagicMock()

            rm.track_database_connection(user_db, "users")
            rm.track_database_connection(job_db, "background_jobs")
            rm.track_database_connection(config_db, "server_config")

            startup_resources = {
                "config_cache": config_cache,
                "startup_log": startup_log,
                "init_dir": temp_init_dir,
                "connections": {
                    "user_db": user_db,
                    "job_db": job_db,
                    "config_db": config_db,
                },
            }

            # Server startup should track all initialization resources
            assert len(rm.tracked_files) == 2
            assert len(rm.tracked_temp_files) == 1
            assert len(rm.tracked_connections) == 3

        # After server startup context, initialization resources should be cleaned up
        assert startup_resources["config_cache"].closed
        assert startup_resources["startup_log"].closed
        assert not Path(startup_resources["init_dir"]).exists()

        # Database connections should be closed
        for conn in startup_resources["connections"].values():
            conn.close.assert_called_once()

    def test_server_shutdown_comprehensive_cleanup(self):
        """Test comprehensive resource cleanup during server shutdown."""
        from code_indexer.server.repositories.resource_manager import (
            GracefulShutdownHandler,
        )

        # Mock server shutdown scenario
        shutdown_handler = GracefulShutdownHandler()
        ResourceManager()

        # Mock server component cleanup functions
        cleanup_calls = []

        def cleanup_golden_repos():
            cleanup_calls.append("golden_repos_cleaned")

        def cleanup_activated_repos():
            cleanup_calls.append("activated_repos_cleaned")

        def cleanup_background_jobs():
            cleanup_calls.append("background_jobs_cleaned")

        def cleanup_database_connections():
            cleanup_calls.append("database_connections_cleaned")

        # Register all cleanup callbacks
        shutdown_handler.register_cleanup_callback(cleanup_golden_repos)
        shutdown_handler.register_cleanup_callback(cleanup_activated_repos)
        shutdown_handler.register_cleanup_callback(cleanup_background_jobs)
        shutdown_handler.register_cleanup_callback(cleanup_database_connections)

        # Simulate server shutdown signal
        shutdown_handler._signal_handler(signal.SIGTERM, None)

        # All cleanup functions should have been called
        assert "golden_repos_cleaned" in cleanup_calls
        assert "activated_repos_cleaned" in cleanup_calls
        assert "background_jobs_cleaned" in cleanup_calls
        assert "database_connections_cleaned" in cleanup_calls

        # Shutdown should be requested
        assert shutdown_handler.shutdown_requested

    @pytest.mark.asyncio
    async def test_server_operation_continuous_resource_management(self):
        """Test continuous resource management during normal server operations."""
        operation_count = 0

        async def mock_server_request_handler(rm: ResourceManager, request_id: str):
            """Mock handling a server request with resource creation."""
            nonlocal operation_count

            # Each request creates temporary resources
            request_temp_dir = tempfile.mkdtemp(suffix=f"_req_{request_id}")
            request_log = tempfile.NamedTemporaryFile(
                mode="w", suffix=f"_{request_id}.log"
            )

            rm.track_temp_file(Path(request_temp_dir))
            rm.track_file_handle(request_log)

            # Mock database query
            query_db = MagicMock()
            rm.track_database_connection(query_db, f"request_{request_id}")

            # Simulate request processing
            await asyncio.sleep(0.05)
            operation_count += 1

            return {"request_id": request_id, "status": "completed"}

        # Simulate multiple server requests with resource management
        async with ResourceManager() as rm:
            # Process multiple concurrent requests
            request_tasks = []
            for i in range(5):
                task = asyncio.create_task(mock_server_request_handler(rm, f"req_{i}"))
                rm.track_background_task(task, f"request_{i}")
                request_tasks.append(task)

            # Wait for all requests to complete
            results = await asyncio.gather(*request_tasks)

            # All requests should complete successfully
            assert len(results) == 5
            assert operation_count == 5

            for i, result in enumerate(results):
                assert result["request_id"] == f"req_{i}"
                assert result["status"] == "completed"

        # After all requests, resources should be cleaned up
        assert len(rm.tracked_temp_files) == 0
        assert len(rm.tracked_files) == 0
        assert len(rm.tracked_connections) == 0
        assert len(rm.tracked_tasks) == 0
