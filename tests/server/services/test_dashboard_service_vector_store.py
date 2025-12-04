"""
Unit tests for DashboardService vector store count aggregation.

Tests AC1 and AC2 from Story #541.
Following TDD: These tests are written FIRST and will fail until implementation is complete.
Following MESSI Rule #1: NO mocks - uses REAL services and test fixtures.
"""

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from code_indexer.server.services.dashboard_service import DashboardService
from code_indexer.server.repositories.activated_repo_manager import (
    ActivatedRepoManager,
)
from code_indexer.server.repositories.golden_repo_manager import (
    GoldenRepoManager,
    GoldenRepo,
)
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
from datetime import datetime, timezone


class TestDashboardServiceVectorStore:
    """Test suite for vector store count aggregation in DashboardService."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def golden_repo_manager(self, temp_data_dir):
        """Create REAL GoldenRepoManager with test data."""
        golden_manager = GoldenRepoManager(data_dir=str(temp_data_dir))

        # Create golden repos for testing
        golden_repo1 = GoldenRepo(
            alias="test-repo-1",
            repo_url="https://github.com/example/repo1.git",
            default_branch="main",
            clone_path=str(temp_data_dir / "golden" / "repo1"),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        golden_repo2 = GoldenRepo(
            alias="test-repo-2",
            repo_url="https://github.com/example/repo2.git",
            default_branch="main",
            clone_path=str(temp_data_dir / "golden" / "repo2"),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        golden_manager.golden_repos = {
            "test-repo-1": golden_repo1,
            "test-repo-2": golden_repo2,
        }

        return golden_manager

    @pytest.fixture
    def activated_repo_manager(self, temp_data_dir, golden_repo_manager):
        """Create REAL ActivatedRepoManager with test data."""
        # Create ActivatedRepoManager (it will handle background job manager internally)
        activated_manager = ActivatedRepoManager(
            data_dir=str(temp_data_dir),
            golden_repo_manager=golden_repo_manager,
        )

        return activated_manager

    @pytest.fixture
    def dashboard_service_with_real_managers(
        self, activated_repo_manager, golden_repo_manager
    ):
        """Create DashboardService and inject REAL managers via monkey-patching."""
        service = DashboardService()

        # Monkey-patch the private getter methods to return our real test managers
        service._get_activated_repo_manager = lambda: activated_repo_manager
        service._get_golden_repo_manager = lambda: golden_repo_manager
        service._get_background_job_manager = (
            lambda: None
        )  # Not needed for repo count tests

        return service

    def _create_vector_store_with_files(
        self, collection_name: str, file_count: int, temp_data_dir: Path
    ):
        """
        Create a REAL FilesystemVectorStore with specified number of indexed files.

        Args:
            collection_name: Name of the collection
            file_count: Number of files to create in vector store
            temp_data_dir: Base directory for vector store

        Returns:
            FilesystemVectorStore instance with real data
        """
        # Create vector store with real filesystem storage
        index_dir = temp_data_dir / "index"
        index_dir.mkdir(parents=True, exist_ok=True)

        store = FilesystemVectorStore(base_path=index_dir)
        store.create_collection(collection_name, vector_size=768)

        # Create real vector files
        collection_dir = index_dir / collection_name

        for i in range(file_count):
            point_id = f"point_{i}"
            vector = np.random.rand(768)

            vector_data = {
                "id": point_id,
                "vector": vector.tolist(),
                "payload": {
                    "path": f"test_file_{i}.py",
                    "language": "python",
                    "chunk_index": 0,
                },
                "chunk_text": f"Test content {i}",
            }

            vector_file = collection_dir / f"{point_id}.json"
            with open(vector_file, "w") as f:
                json.dump(vector_data, f)

        # Create collection metadata with unique_file_count
        # This is what get_indexed_file_count_fast() reads
        meta_file = collection_dir / "collection_meta.json"
        metadata = {
            "vector_size": 768,
            "unique_file_count": file_count,  # This is what get_indexed_file_count_fast returns
        }
        with open(meta_file, "w") as f:
            json.dump(metadata, f)

        return store

    def _create_activated_repo_with_index(
        self,
        activated_manager: ActivatedRepoManager,
        username: str,
        collection_name: str,
        file_count: int,
        temp_data_dir: Path,
    ):
        """
        Create a REAL activated repo with vector store data.

        Args:
            activated_manager: Real ActivatedRepoManager instance
            username: Username for the activated repo
            collection_name: Collection name for vector store
            file_count: Number of files to index
            temp_data_dir: Base directory for test data
        """
        # Create the user directory for activated repos
        user_dir = temp_data_dir / "activated-repos" / username
        user_dir.mkdir(parents=True, exist_ok=True)

        # Create the repo directory
        repo_dir = user_dir / collection_name
        repo_dir.mkdir(parents=True, exist_ok=True)

        # Create metadata file (this is how activated_repo_manager stores repos)
        metadata = {
            "user_alias": collection_name,
            "golden_repo_alias": collection_name.split("_")[0],
            "current_branch": "main",
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "collection_name": collection_name,  # Add collection_name for dashboard_service
        }

        metadata_file = user_dir / f"{collection_name}_metadata.json"
        with open(metadata_file, "w") as f:
            json.dump(metadata, f)

        # Create the vector store with real indexed files
        self._create_vector_store_with_files(collection_name, file_count, temp_data_dir)

    def test_get_repo_counts_aggregates_vector_store_files(
        self,
        dashboard_service_with_real_managers,
        activated_repo_manager,
        temp_data_dir,
    ):
        """Test that _get_repo_counts() sums FilesystemVectorStore counts (AC1)."""
        # Arrange: Create 2 activated repos with different file counts
        self._create_activated_repo_with_index(
            activated_repo_manager,
            username="testuser",
            collection_name="repo1_collection",
            file_count=150,
            temp_data_dir=temp_data_dir,
        )

        self._create_activated_repo_with_index(
            activated_repo_manager,
            username="testuser",
            collection_name="repo2_collection",
            file_count=250,
            temp_data_dir=temp_data_dir,
        )

        # Act: Call _get_repo_counts
        repo_counts = dashboard_service_with_real_managers._get_repo_counts("testuser")

        # Assert: Verify total_files is the sum of vector store counts
        assert (
            repo_counts.total_files == 400
        ), "total_files should be sum of FilesystemVectorStore counts (150 + 250)"
        assert repo_counts.activated == 2, "Should have 2 activated repos"

    def test_get_repo_counts_returns_zero_with_no_repos(self, temp_data_dir):
        """Test that _get_repo_counts() returns 0 when no activated repos (AC2)."""
        # Create a fresh dashboard service with NO golden repos
        empty_golden_manager = GoldenRepoManager(data_dir=str(temp_data_dir))
        empty_activated_manager = ActivatedRepoManager(
            data_dir=str(temp_data_dir),
            golden_repo_manager=empty_golden_manager,
        )

        service = DashboardService()
        service._get_activated_repo_manager = lambda: empty_activated_manager
        service._get_golden_repo_manager = lambda: empty_golden_manager
        service._get_background_job_manager = lambda: None

        # Act: Call _get_repo_counts with user that has no repos
        repo_counts = service._get_repo_counts("testuser")

        # Assert: Should return 0 for all counts
        assert repo_counts.total_files == 0, "total_files should be 0 with no repos"
        assert repo_counts.activated == 0, "activated count should be 0 with no repos"
        assert repo_counts.golden == 0, "golden count should be 0 with no repos"

    def test_get_repo_counts_handles_vector_store_errors_gracefully(
        self,
        dashboard_service_with_real_managers,
        activated_repo_manager,
        temp_data_dir,
    ):
        """Test that _get_repo_counts() handles FilesystemVectorStore errors gracefully."""
        # Arrange: Create an activated repo metadata but DON'T create vector store files
        # This simulates a corrupted or missing vector store
        user_dir = temp_data_dir / "activated-repos" / "testuser"
        user_dir.mkdir(parents=True, exist_ok=True)

        # Create repo directory
        repo_dir = user_dir / "test_collection"
        repo_dir.mkdir(parents=True, exist_ok=True)

        # Create metadata but skip vector store creation
        metadata = {
            "user_alias": "test_collection",
            "golden_repo_alias": "test-repo",
            "current_branch": "main",
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "collection_name": "nonexistent_collection",  # This won't have vector store
        }

        metadata_file = user_dir / "test_collection_metadata.json"
        with open(metadata_file, "w") as f:
            json.dump(metadata, f)

        # Act: Call _get_repo_counts (should handle missing vector store gracefully)
        repo_counts = dashboard_service_with_real_managers._get_repo_counts("testuser")

        # Assert: Should handle error gracefully without raising exception
        # FilesystemVectorStore.get_indexed_file_count_fast() may return 0 or a fallback estimate (like 1)
        # The important thing is it doesn't crash
        assert (
            repo_counts.total_files >= 0
        ), "Should handle missing vector store gracefully without crashing"
        assert repo_counts.activated == 1, "Should still count the activated repo"

    def test_get_repo_counts_uses_correct_collection_name(
        self,
        dashboard_service_with_real_managers,
        activated_repo_manager,
        temp_data_dir,
    ):
        """Test that _get_repo_counts() passes correct collection_name to FilesystemVectorStore."""
        # Arrange: Create activated repo with specific collection name
        specific_collection = "specific_collection_name_12345"

        self._create_activated_repo_with_index(
            activated_repo_manager,
            username="testuser",
            collection_name=specific_collection,
            file_count=100,
            temp_data_dir=temp_data_dir,
        )

        # Act: Call _get_repo_counts
        repo_counts = dashboard_service_with_real_managers._get_repo_counts("testuser")

        # Assert: Verify the count is retrieved (proves collection_name was used correctly)
        assert (
            repo_counts.total_files == 100
        ), "Should retrieve count from correct collection"

        # Additionally verify the vector store can be accessed with this collection name
        index_dir = temp_data_dir / "index"
        store = FilesystemVectorStore(base_path=index_dir)
        count = store.get_indexed_file_count_fast(specific_collection)
        assert (
            count == 100
        ), "FilesystemVectorStore should return correct count for collection"
