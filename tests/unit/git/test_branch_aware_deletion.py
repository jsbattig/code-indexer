"""
Test cases for branch-aware deletion functionality.

These tests verify that _hide_file_in_branch works correctly and
that deletion strategies are properly selected based on project type.
"""

import pytest

from ...conftest import local_temporary_directory
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

from code_indexer.services.branch_aware_indexer import BranchAwareIndexer
from code_indexer.services.smart_indexer import SmartIndexer
from code_indexer.config import Config


class TestBranchAwareDeletion:
    """Test the branch-aware deletion functionality."""

    @pytest.fixture
    def mock_qdrant_client(self):
        """Create a mock QdrantClient for testing."""
        mock_client = MagicMock()
        mock_client._batch_update_points.return_value = True
        # Mock scroll_points to return content points with hidden_branches field
        mock_client.scroll_points.return_value = (
            [
                {
                    "id": "content_point_1",
                    "payload": {
                        "type": "content",
                        "path": "src/test_file.py",
                        "hidden_branches": [],
                    },
                }
            ],
            None,
        )
        return mock_client

    @pytest.fixture
    def branch_aware_indexer(self, local_tmp_path, mock_qdrant_client):
        """Create a BranchAwareIndexer for testing."""
        config = Config(codebase_dir=local_tmp_path)

        # Mock embedding provider
        mock_embedding_provider = MagicMock()
        mock_embedding_provider.get_embedding_dimensions.return_value = 768

        # Mock text chunker
        mock_text_chunker = MagicMock()

        indexer = BranchAwareIndexer(
            qdrant_client=mock_qdrant_client,
            embedding_provider=mock_embedding_provider,
            text_chunker=mock_text_chunker,
            config=config,
        )

        return indexer

    def test_hide_file_in_branch_functionality(
        self, branch_aware_indexer, mock_qdrant_client
    ):
        """
        Test that _hide_file_in_branch works correctly with hidden_branches schema.

        This test verifies that the branch is added to hidden_branches array.
        """
        file_path = "src/test_file.py"
        branch = "feature"
        collection_name = "test_collection"

        # Call _hide_file_in_branch
        branch_aware_indexer._hide_file_in_branch(file_path, branch, collection_name)

        # Verify scroll_points was called to find content points
        expected_filter = {
            "must": [
                {"key": "type", "match": {"value": "content"}},
                {"key": "path", "match": {"value": file_path}},
            ]
        }
        mock_qdrant_client.scroll_points.assert_called_once_with(
            filter_conditions=expected_filter,
            limit=1000,
            collection_name=collection_name,
        )

        # Verify _batch_update_points was called to add branch to hidden_branches
        expected_update = [
            {"id": "content_point_1", "payload": {"hidden_branches": ["feature"]}}
        ]
        mock_qdrant_client._batch_update_points.assert_called_once_with(
            expected_update, collection_name
        )

    def test_hide_file_in_branch_preserves_content_points(
        self, branch_aware_indexer, mock_qdrant_client
    ):
        """
        Test that _hide_file_in_branch updates content points with hidden_branches but preserves content.

        This test verifies that content points are updated, not deleted.
        """
        file_path = "src/test_file.py"
        branch = "main"
        collection_name = "test_collection"

        # Call _hide_file_in_branch
        branch_aware_indexer._hide_file_in_branch(file_path, branch, collection_name)

        # Verify the filter specifically targets content points
        call_args = mock_qdrant_client.scroll_points.call_args
        filter_conditions = call_args[1]["filter_conditions"]

        # Should target content points
        type_filter = next(f for f in filter_conditions["must"] if f["key"] == "type")
        assert type_filter["match"]["value"] == "content"

        # Should not delete points, only update them
        mock_qdrant_client.delete_by_filter.assert_not_called()
        mock_qdrant_client.delete_points.assert_not_called()

        # Should call _batch_update_points to update hidden_branches
        mock_qdrant_client._batch_update_points.assert_called_once()

    def test_hide_file_in_branch_different_branches_isolated(
        self, branch_aware_indexer, mock_qdrant_client
    ):
        """
        Test that hiding files in different branches accumulates correctly in hidden_branches.

        This test verifies that multiple branches can be added to hidden_branches array.
        """
        file_path = "src/test_file.py"
        collection_name = "test_collection"

        # Mock content point that starts with feature branch already hidden
        mock_qdrant_client.scroll_points.side_effect = [
            # First call for feature branch hiding
            (
                [
                    {
                        "id": "content_point_1",
                        "payload": {
                            "type": "content",
                            "path": file_path,
                            "hidden_branches": [],
                        },
                    }
                ],
                None,
            ),
            # Second call for main branch hiding
            (
                [
                    {
                        "id": "content_point_1",
                        "payload": {
                            "type": "content",
                            "path": file_path,
                            "hidden_branches": ["feature"],  # feature already hidden
                        },
                    }
                ],
                None,
            ),
        ]

        # Hide file in feature branch
        branch_aware_indexer._hide_file_in_branch(file_path, "feature", collection_name)

        # Hide same file in main branch
        branch_aware_indexer._hide_file_in_branch(file_path, "main", collection_name)

        # Verify two separate calls were made to scroll_points
        assert mock_qdrant_client.scroll_points.call_count == 2

        # Verify _batch_update_points was called twice with accumulated hidden_branches
        calls = mock_qdrant_client._batch_update_points.call_args_list
        assert len(calls) == 2

        # First call should add feature to hidden_branches
        first_update = calls[0][0][0][0]  # First arg, first update item
        assert first_update["payload"]["hidden_branches"] == ["feature"]

        # Second call should add main to existing hidden_branches
        second_update = calls[1][0][0][0]  # First arg, first update item
        assert second_update["payload"]["hidden_branches"] == ["feature", "main"]

    def test_hide_file_in_branch_idempotent_operation(
        self, branch_aware_indexer, mock_qdrant_client
    ):
        """
        Test that hiding the same file multiple times is safe with hidden_branches.

        This test verifies that adding the same branch multiple times doesn't duplicate entries.
        """
        file_path = "src/test_file.py"
        branch = "feature"
        collection_name = "test_collection"

        # Mock that first call finds empty hidden_branches, subsequent calls find branch already hidden
        mock_qdrant_client.scroll_points.side_effect = [
            # First call - branch not yet hidden
            (
                [
                    {
                        "id": "content_point_1",
                        "payload": {
                            "type": "content",
                            "path": file_path,
                            "hidden_branches": [],
                        },
                    }
                ],
                None,
            ),
            # Second call - branch already hidden
            (
                [
                    {
                        "id": "content_point_1",
                        "payload": {
                            "type": "content",
                            "path": file_path,
                            "hidden_branches": ["feature"],
                        },
                    }
                ],
                None,
            ),
            # Third call - branch already hidden
            (
                [
                    {
                        "id": "content_point_1",
                        "payload": {
                            "type": "content",
                            "path": file_path,
                            "hidden_branches": ["feature"],
                        },
                    }
                ],
                None,
            ),
        ]

        # Hide file multiple times
        branch_aware_indexer._hide_file_in_branch(file_path, branch, collection_name)
        branch_aware_indexer._hide_file_in_branch(file_path, branch, collection_name)
        branch_aware_indexer._hide_file_in_branch(file_path, branch, collection_name)

        # Should make three calls to scroll_points
        assert mock_qdrant_client.scroll_points.call_count == 3

        # Should only make one call to _batch_update_points (when branch wasn't already hidden)
        assert mock_qdrant_client._batch_update_points.call_count == 1

        # The update should add the branch to hidden_branches
        update_call = mock_qdrant_client._batch_update_points.call_args[0][0][0]
        assert update_call["payload"]["hidden_branches"] == ["feature"]

    def test_deletion_strategy_selection_git_aware(self):
        """
        Test that is_git_aware method correctly detects git-aware projects.

        This test should now PASS since we implemented the functionality.
        """
        with local_temporary_directory() as tmp_dir:
            repo_path = Path(tmp_dir)

            # Initialize git repo
            subprocess.run(["git", "init"], cwd=repo_path, check=True)

            config = Config(codebase_dir=repo_path)

            # Mock required dependencies for SmartIndexer
            mock_embedding_provider = MagicMock()
            mock_qdrant_client = MagicMock()
            metadata_path = repo_path / ".code-indexer" / "metadata.json"
            metadata_path.parent.mkdir(exist_ok=True)

            smart_indexer = SmartIndexer(
                config, mock_embedding_provider, mock_qdrant_client, metadata_path
            )

            # Should now work since we implemented the method
            is_git_aware = smart_indexer.is_git_aware()
            assert is_git_aware is True

    def test_deletion_strategy_selection_non_git_aware(self):
        """
        Test that is_git_aware method correctly detects non git-aware projects.

        This test should now PASS since we implemented the functionality.
        """
        with local_temporary_directory() as tmp_dir:
            repo_path = Path(tmp_dir)
            # Don't initialize git repo - non git-aware

            config = Config(codebase_dir=repo_path)

            # Mock required dependencies for SmartIndexer
            mock_embedding_provider = MagicMock()
            mock_qdrant_client = MagicMock()
            metadata_path = repo_path / ".code-indexer" / "metadata.json"
            metadata_path.parent.mkdir(exist_ok=True)

            smart_indexer = SmartIndexer(
                config, mock_embedding_provider, mock_qdrant_client, metadata_path
            )

            # Should now detect non git-aware project
            is_git_aware = smart_indexer.is_git_aware()
            assert is_git_aware is False

    def test_multi_branch_deletion_isolation(self):
        """
        FAILING TEST: Should verify deletion isolation across multiple branches.

        This will be an integration test once the infrastructure is in place.
        """
        # This test will be implemented once we have the infrastructure
        # for testing multi-branch scenarios with real Qdrant operations
        assert True, "Integration test to be implemented"

    def test_branch_aware_deletion_with_chunks(
        self, branch_aware_indexer, mock_qdrant_client
    ):
        """
        Test hiding files with multiple chunks using hidden_branches schema.

        This test verifies that all content points for a file get updated.
        """
        file_path = "src/large_file.py"
        branch = "feature"
        collection_name = "test_collection"

        # Mock multiple content points (chunks) for the same file
        mock_qdrant_client.scroll_points.return_value = (
            [
                {
                    "id": "content_point_1",
                    "payload": {
                        "type": "content",
                        "path": file_path,
                        "chunk_index": 0,
                        "hidden_branches": [],
                    },
                },
                {
                    "id": "content_point_2",
                    "payload": {
                        "type": "content",
                        "path": file_path,
                        "chunk_index": 1,
                        "hidden_branches": [],
                    },
                },
                {
                    "id": "content_point_3",
                    "payload": {
                        "type": "content",
                        "path": file_path,
                        "chunk_index": 2,
                        "hidden_branches": [],
                    },
                },
            ],
            None,
        )

        # Call _hide_file_in_branch
        branch_aware_indexer._hide_file_in_branch(file_path, branch, collection_name)

        # Should call scroll_points to find all content points for the file
        expected_filter = {
            "must": [
                {"key": "type", "match": {"value": "content"}},
                {"key": "path", "match": {"value": file_path}},
            ]
        }
        mock_qdrant_client.scroll_points.assert_called_once_with(
            filter_conditions=expected_filter,
            limit=1000,
            collection_name=collection_name,
        )

        # Should update all content points to add branch to hidden_branches
        expected_updates = [
            {"id": "content_point_1", "payload": {"hidden_branches": ["feature"]}},
            {"id": "content_point_2", "payload": {"hidden_branches": ["feature"]}},
            {"id": "content_point_3", "payload": {"hidden_branches": ["feature"]}},
        ]
        mock_qdrant_client._batch_update_points.assert_called_once_with(
            expected_updates, collection_name
        )


class TestDeletionStrategySelection:
    """Test cases for deletion strategy selection logic (not yet implemented)."""

    def test_delete_file_branch_aware_method_git_project(self):
        """
        Test that delete_file_branch_aware method works for git projects.

        This test should now PASS since we implemented the functionality.
        """
        with local_temporary_directory() as tmp_dir:
            repo_path = Path(tmp_dir)

            # Initialize git repo to make it git-aware
            subprocess.run(["git", "init"], cwd=repo_path, check=True)

            config = Config(codebase_dir=repo_path)

            # Mock required dependencies
            mock_embedding_provider = MagicMock()
            mock_qdrant_client = MagicMock()
            metadata_path = repo_path / ".code-indexer" / "metadata.json"
            metadata_path.parent.mkdir(exist_ok=True)

            smart_indexer = SmartIndexer(
                config, mock_embedding_provider, mock_qdrant_client, metadata_path
            )

            # Mock dependencies
            mock_branch_aware = MagicMock()
            smart_indexer.branch_aware_indexer = mock_branch_aware

            # Mock git topology to return current branch
            mock_git_topology = MagicMock()
            mock_git_topology.get_current_branch.return_value = "main"
            smart_indexer.git_topology_service = mock_git_topology

            # Should now work since we implemented the method
            smart_indexer.delete_file_branch_aware("test.py", "collection")
            mock_branch_aware._hide_file_in_branch.assert_called_once_with(
                "test.py", "main", "collection"
            )

    def test_delete_file_branch_aware_method_non_git_project(self):
        """
        Test that delete_file_branch_aware method works for non-git projects.

        This test should now PASS since we implemented the functionality.
        """
        with local_temporary_directory() as tmp_dir:
            repo_path = Path(tmp_dir)
            # Don't initialize git repo - non git-aware

            config = Config(codebase_dir=repo_path)

            # Mock required dependencies
            mock_embedding_provider = MagicMock()
            mock_qdrant_client = MagicMock()
            metadata_path = repo_path / ".code-indexer" / "metadata.json"
            metadata_path.parent.mkdir(exist_ok=True)

            smart_indexer = SmartIndexer(
                config, mock_embedding_provider, mock_qdrant_client, metadata_path
            )

            # Should now work since we implemented the method
            smart_indexer.delete_file_branch_aware("test.py", "collection")
            mock_qdrant_client.delete_by_filter.assert_called_once_with(
                {"must": [{"key": "path", "match": {"value": "test.py"}}]},
                "collection",
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
