"""
Unit tests for migration middleware functionality.

These tests verify the migration detection, state tracking, and automatic migration
capabilities work correctly in isolation.
"""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

from code_indexer.services.migration_middleware import (
    MigrationMiddleware,
    MigrationStateTracker,
    MigrationInfo,
    CollectionInfo,
)
from code_indexer.services.migration_decorator import (
    requires_qdrant_access,
    MigrationAwareQdrantClient,
)


class TestMigrationStateTracker:
    """Test migration state tracking functionality"""

    @pytest.fixture
    def temp_home(self):
        """Create temporary home directory for testing"""
        with tempfile.TemporaryDirectory() as temp_dir:
            home_path = Path(temp_dir) / "test_home"
            home_path.mkdir()
            with patch("pathlib.Path.home", return_value=home_path):
                yield home_path

    @pytest.fixture
    def state_tracker(self, temp_home):
        """Create state tracker with temporary home"""
        return MigrationStateTracker()

    @pytest.mark.asyncio
    async def test_default_state_creation(self, state_tracker):
        """Test that default state is created correctly"""
        state = await state_tracker.load_state()

        assert state["container_migrated"] is False
        assert state["migrated_projects"] == []
        assert state["migration_version"] == "1.0"
        assert state["last_check"] is None
        assert state["failed_migrations"] == []

    @pytest.mark.asyncio
    async def test_state_persistence(self, state_tracker, temp_home):
        """Test that state is saved and loaded correctly"""
        # Mark container as migrated
        await state_tracker.mark_container_migrated()

        # Create new tracker instance to test persistence
        new_tracker = MigrationStateTracker()
        state = await new_tracker.load_state()

        assert state["container_migrated"] is True
        assert state["last_check"] is not None

    @pytest.mark.asyncio
    async def test_project_migration_tracking(self, state_tracker):
        """Test project migration state tracking"""
        project_path = Path("/test/project")

        # Initially should need migration
        assert await state_tracker.needs_project_migration(project_path) is True

        # Mark as migrated
        await state_tracker.mark_project_migrated(project_path)

        # Should no longer need migration
        assert await state_tracker.needs_project_migration(project_path) is False

    @pytest.mark.asyncio
    async def test_migration_failure_tracking(self, state_tracker):
        """Test that migration failures are tracked"""
        project_path = Path("/test/project")
        error_msg = "Test migration error"

        await state_tracker.mark_migration_failed(project_path, error_msg)

        state = await state_tracker.load_state()
        failures = state["failed_migrations"]

        assert len(failures) == 1
        assert failures[0]["project"] == str(project_path.resolve())
        assert failures[0]["error"] == error_msg
        assert "timestamp" in failures[0]

    @pytest.mark.asyncio
    async def test_state_reset(self, state_tracker):
        """Test state reset functionality"""
        # Make some changes
        await state_tracker.mark_container_migrated()
        await state_tracker.mark_project_migrated(Path("/test"))

        # Reset state
        await state_tracker.reset_migration_state()

        # Verify reset
        state = await state_tracker.load_state()
        assert state["container_migrated"] is False
        assert state["migrated_projects"] == []

    @pytest.mark.asyncio
    async def test_corrupted_state_file_handling(self, state_tracker, temp_home):
        """Test handling of corrupted state file"""
        state_file = temp_home / ".code-indexer" / "migration_state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)

        # Write corrupted JSON
        with open(state_file, "w") as f:
            f.write("invalid json {")

        # Should handle corruption gracefully
        state = await state_tracker.load_state()
        assert state["container_migrated"] is False  # Default state


class TestMigrationMiddleware:
    """Test migration middleware functionality"""

    @pytest.fixture
    def temp_project(self):
        """Create temporary project for testing"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "test_project"
            project_path.mkdir()

            # Create .code-indexer directory
            code_indexer_dir = project_path / ".code-indexer"
            code_indexer_dir.mkdir()

            # Create basic config
            config_file = code_indexer_dir / "config.json"
            with open(config_file, "w") as f:
                json.dump({"codebase_dir": str(project_path)}, f)

            yield project_path

    @pytest.fixture
    def middleware(self):
        """Create migration middleware instance"""
        return MigrationMiddleware()

    @pytest.mark.asyncio
    async def test_session_check_caching(self, middleware, temp_project):
        """Test that migration checks are cached per session"""
        operation_name = "test_operation"

        with patch.object(
            middleware, "_check_container_migration_needed", return_value=False
        ) as mock_container_check:
            with patch.object(
                middleware, "_check_project_migration_needed", return_value=False
            ) as mock_project_check:

                # First call should check
                await middleware.ensure_migration_compatibility(
                    operation_name, temp_project
                )
                assert mock_container_check.call_count == 1
                assert mock_project_check.call_count == 1

                # Second call should be cached
                await middleware.ensure_migration_compatibility(
                    operation_name, temp_project
                )
                assert mock_container_check.call_count == 1  # No additional calls
                assert mock_project_check.call_count == 1

    @pytest.mark.asyncio
    async def test_container_migration_detection(self, middleware):
        """Test container migration detection logic"""
        with patch.object(
            middleware.state_tracker, "needs_container_migration", return_value=False
        ):
            # If state tracker says no migration needed, should return False
            result = await middleware._check_container_migration_needed()
            assert result is False

        with patch.object(
            middleware.state_tracker, "needs_container_migration", return_value=True
        ):
            with patch(
                "code_indexer.services.migration_middleware.DockerManager"
            ) as mock_dm:
                mock_dm_instance = Mock()
                mock_dm.return_value = mock_dm_instance
                mock_dm_instance._container_exists.return_value = False

                # If no container exists, should need migration
                result = await middleware._check_container_migration_needed()
                assert result is True

    @pytest.mark.asyncio
    async def test_project_migration_detection_with_local_storage(
        self, middleware, temp_project
    ):
        """Test project migration detection when local storage exists"""
        # Create local storage directory
        local_storage = temp_project / ".code-indexer" / "qdrant-data"
        local_storage.mkdir(parents=True)

        # Should detect no migration needed
        result = await middleware._check_project_migration_needed(temp_project)
        assert result is False

    @pytest.mark.asyncio
    async def test_project_migration_detection_without_config(self, middleware):
        """Test project migration detection for uninitialized project"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "uninit_project"
            project_path.mkdir()

            # Should detect no migration needed for uninitialized project
            result = await middleware._check_project_migration_needed(project_path)
            assert result is False

    @pytest.mark.asyncio
    async def test_collection_finding_in_global_storage(self, middleware, temp_project):
        """Test finding project collections in global storage"""
        with patch.object(middleware, "_get_global_storage_path") as mock_get_path:
            # Create mock global storage
            with tempfile.TemporaryDirectory() as temp_dir:
                global_storage = Path(temp_dir)
                collections_dir = global_storage / "collections"
                collections_dir.mkdir(parents=True)

                # Create mock collection with project ID
                project_id = "test_project_id"
                collection_name = f"code_index_{project_id}_test"
                collection_dir = collections_dir / collection_name
                collection_dir.mkdir()

                # Add some files to collection
                (collection_dir / "test_file").write_text("test data")

                mock_get_path.return_value = global_storage

                with patch(
                    "code_indexer.services.embedding_factory.EmbeddingProviderFactory"
                ) as mock_factory:
                    mock_factory.generate_project_id.return_value = project_id

                    collections = (
                        await middleware._find_project_collections_in_global_storage(
                            temp_project
                        )
                    )

                    assert len(collections) == 1
                    assert collections[0].name == collection_name
                    assert collections[0].project_id == project_id
                    assert collections[0].size > 0

    @pytest.mark.asyncio
    async def test_migration_execution_flow(self, middleware, temp_project):
        """Test complete migration execution flow"""
        with patch.object(
            middleware, "_migrate_container_configuration"
        ) as mock_container_migration:
            with patch.object(
                middleware, "_migrate_project_collections"
            ) as mock_project_migration:
                with patch.object(
                    middleware.state_tracker, "mark_container_migrated"
                ) as mock_mark_container:
                    with patch.object(
                        middleware.state_tracker, "mark_project_migrated"
                    ) as mock_mark_project:

                        await middleware._perform_migration(
                            "test_operation",
                            temp_project,
                            container_migration_needed=True,
                            project_migration_needed=True,
                        )

                        mock_container_migration.assert_called_once()
                        mock_project_migration.assert_called_once_with(temp_project)
                        mock_mark_container.assert_called_once()
                        mock_mark_project.assert_called_once_with(temp_project)

    @pytest.mark.asyncio
    async def test_migration_failure_handling(self, middleware, temp_project):
        """Test migration failure handling and rollback"""
        with patch.object(
            middleware,
            "_migrate_container_configuration",
            side_effect=Exception("Container migration failed"),
        ):
            with patch.object(
                middleware.state_tracker, "mark_migration_failed"
            ) as mock_mark_failed:

                with pytest.raises(Exception, match="Container migration failed"):
                    await middleware._perform_migration(
                        "test_operation",
                        temp_project,
                        container_migration_needed=True,
                        project_migration_needed=False,
                    )

                mock_mark_failed.assert_called_once_with(
                    temp_project, "Container migration failed"
                )

    @pytest.mark.asyncio
    async def test_collection_migration_with_backup(self, middleware, temp_project):
        """Test collection migration creates backup and handles rollback"""
        # Create temporary collection directory
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_collection_path = Path(temp_dir) / "test_collection"
            fake_collection_path.mkdir()

            # Create some test files in the collection
            (fake_collection_path / "test_file.dat").write_text("test data")

            collections = [
                CollectionInfo(
                    name="test_collection",
                    path=fake_collection_path,
                    size=1024,
                    project_id="test_id",
                )
            ]

            with patch.object(
                middleware,
                "_find_project_collections_in_global_storage",
                return_value=collections,
            ):
                with patch.object(
                    middleware, "_create_migration_backup"
                ) as mock_backup:
                    with patch.object(
                        middleware, "_verify_migration_integrity", return_value=False
                    ):  # Force verification failure
                        with patch.object(
                            middleware, "_rollback_migration"
                        ) as mock_rollback:
                            with patch(
                                "code_indexer.services.migration_middleware.DockerManager"
                            ):

                                backup_dir = Path("/fake/backup")
                                mock_backup.return_value = backup_dir

                                with pytest.raises(
                                    RuntimeError,
                                    match="Migration integrity verification failed",
                                ):
                                    await middleware._migrate_project_collections(
                                        temp_project
                                    )

                                mock_backup.assert_called_once()
                                mock_rollback.assert_called_once_with(
                                    backup_dir, collections
                                )


class TestMigrationDecorator:
    """Test migration decorator functionality"""

    @pytest.mark.asyncio
    async def test_requires_qdrant_access_async(self):
        """Test @requires_qdrant_access decorator with async function"""
        call_log = []

        @requires_qdrant_access("test_operation")
        async def test_function():
            call_log.append("function_called")
            return "success"

        with patch(
            "code_indexer.services.migration_decorator.migration_middleware"
        ) as mock_middleware:
            mock_middleware.ensure_migration_compatibility = AsyncMock()

            result = await test_function()

            assert result == "success"
            assert call_log == ["function_called"]
            mock_middleware.ensure_migration_compatibility.assert_called_once()

    @pytest.mark.asyncio
    async def test_migration_failure_in_decorator(self):
        """Test decorator behavior when migration fails"""

        @requires_qdrant_access("test_operation")
        async def test_function():
            return "should_not_reach"

        with patch(
            "code_indexer.services.migration_decorator.migration_middleware"
        ) as mock_middleware:
            mock_middleware.ensure_migration_compatibility = AsyncMock(
                side_effect=Exception("Migration failed")
            )

            with pytest.raises(
                RuntimeError,
                match="Cannot proceed with test_operation: migration failed",
            ):
                await test_function()

    @pytest.mark.asyncio
    async def test_migration_aware_qdrant_client(self):
        """Test MigrationAwareQdrantClient functionality"""
        config = Mock()
        project_path = Path("/test/project")

        client = MigrationAwareQdrantClient(config, project_path)

        with patch(
            "code_indexer.services.migration_decorator.migration_middleware"
        ) as mock_middleware:
            mock_middleware.ensure_migration_compatibility = AsyncMock()

            with patch("code_indexer.services.qdrant.QdrantClient") as mock_qdrant:
                mock_qdrant_instance = AsyncMock()
                mock_qdrant.return_value = mock_qdrant_instance
                mock_qdrant_instance.search_points.return_value = "search_result"

                result = await client.search_points("test_collection", [1, 2, 3])

                assert result == "search_result"
                mock_middleware.ensure_migration_compatibility.assert_called_once_with(
                    "search_points", project_path
                )
                mock_qdrant_instance.search_points.assert_called_once_with(
                    "test_collection", [1, 2, 3]
                )

    @pytest.mark.asyncio
    async def test_migration_aware_client_caching(self):
        """Test that MigrationAwareQdrantClient caches migration checks"""
        config = Mock()
        client = MigrationAwareQdrantClient(config)

        with patch(
            "code_indexer.services.migration_decorator.migration_middleware"
        ) as mock_middleware:
            mock_middleware.ensure_migration_compatibility = AsyncMock()

            with patch("code_indexer.services.qdrant.QdrantClient") as mock_qdrant:
                mock_qdrant_instance = AsyncMock()
                mock_qdrant.return_value = mock_qdrant_instance

                # First call
                await client.search_points("test1", [1])
                # Second call
                await client.upsert_points("test2", [])

                # Migration should only be checked once
                assert mock_middleware.ensure_migration_compatibility.call_count == 1
                # But QdrantClient should be reused
                assert mock_qdrant.call_count == 1


class TestCollectionInfo:
    """Test CollectionInfo dataclass"""

    def test_collection_info_creation(self):
        """Test CollectionInfo dataclass creation"""
        path = Path("/test/collection")
        collection = CollectionInfo(
            name="test_collection", path=path, size=1024, project_id="test_id"
        )

        assert collection.name == "test_collection"
        assert collection.path == path
        assert collection.size == 1024
        assert collection.project_id == "test_id"


class TestMigrationInfo:
    """Test MigrationInfo dataclass"""

    def test_migration_info_creation(self):
        """Test MigrationInfo dataclass creation"""
        info = MigrationInfo(
            needed=True,
            reason="Test migration needed",
            project_id="test_id",
            collections=["col1", "col2"],
            migration_type="container",
        )

        assert info.needed is True
        assert info.reason == "Test migration needed"
        assert info.project_id == "test_id"
        assert info.collections == ["col1", "col2"]
        assert info.migration_type == "container"

    def test_migration_info_minimal(self):
        """Test MigrationInfo with minimal parameters"""
        info = MigrationInfo(needed=False, reason="No migration needed")

        assert info.needed is False
        assert info.reason == "No migration needed"
        assert info.project_id is None
        assert info.collections is None
        assert info.migration_type is None


if __name__ == "__main__":
    pytest.main([__file__])
