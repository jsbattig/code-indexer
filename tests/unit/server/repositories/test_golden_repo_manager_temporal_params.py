"""
Unit tests for GoldenRepoManager.add_golden_repo with temporal parameters.

Tests that the add_golden_repo method accepts and passes temporal parameters
to the _execute_post_clone_workflow method.
"""

import pytest
import tempfile
from unittest.mock import patch


class TestGoldenRepoManagerTemporalParams:
    """Test add_golden_repo method with temporal parameters."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def golden_repo_manager(self, temp_data_dir):
        """Create GoldenRepoManager instance with temp directory."""
        from code_indexer.server.repositories.golden_repo_manager import (
            GoldenRepoManager,
        )

        return GoldenRepoManager(data_dir=temp_data_dir)

    def test_add_golden_repo_accepts_enable_temporal_parameter(
        self, golden_repo_manager
    ):
        """Test that add_golden_repo accepts enable_temporal parameter."""
        repo_url = "https://github.com/test/repo.git"
        alias = "test-repo"

        with patch.object(
            golden_repo_manager, "_validate_git_repository"
        ) as mock_validate:
            mock_validate.return_value = True
            with patch.object(golden_repo_manager, "_clone_repository") as mock_clone:
                mock_clone.return_value = "/path/to/cloned/repo"
                with patch.object(
                    golden_repo_manager, "_execute_post_clone_workflow"
                ) as mock_workflow:
                    mock_workflow.return_value = None

                    # Act - call with enable_temporal parameter
                    result = golden_repo_manager.add_golden_repo(
                        repo_url=repo_url, alias=alias, enable_temporal=True
                    )

                    # Assert
                    assert result["success"] is True
                    mock_workflow.assert_called_once()

                    # Verify that enable_temporal was passed to workflow
                    call_args = mock_workflow.call_args
                    assert call_args is not None
                    kwargs = call_args[1]
                    assert "enable_temporal" in kwargs
                    assert kwargs["enable_temporal"] is True

    def test_add_golden_repo_persists_temporal_configuration_in_metadata(
        self, golden_repo_manager, temp_data_dir
    ):
        """Test that temporal configuration is persisted in metadata file."""
        import json
        import os

        repo_url = "https://github.com/test/repo.git"
        alias = "test-repo"
        temporal_options = {"max_commits": 100, "diff_context": 10}

        with patch.object(
            golden_repo_manager, "_validate_git_repository"
        ) as mock_validate:
            mock_validate.return_value = True
            with patch.object(golden_repo_manager, "_clone_repository") as mock_clone:
                mock_clone.return_value = "/path/to/cloned/repo"
                with patch.object(
                    golden_repo_manager, "_execute_post_clone_workflow"
                ) as mock_workflow:
                    mock_workflow.return_value = None

                    # Act - add golden repo with temporal settings
                    golden_repo_manager.add_golden_repo(
                        repo_url=repo_url,
                        alias=alias,
                        enable_temporal=True,
                        temporal_options=temporal_options,
                    )

                    # Assert - check metadata file contains temporal configuration
                    metadata_file = os.path.join(
                        temp_data_dir, "golden-repos", "metadata.json"
                    )
                    assert os.path.exists(metadata_file)

                    with open(metadata_file, "r") as f:
                        metadata = json.load(f)

                    assert alias in metadata
                    repo_metadata = metadata[alias]
                    assert "enable_temporal" in repo_metadata
                    assert repo_metadata["enable_temporal"] is True
                    assert "temporal_options" in repo_metadata
                    assert repo_metadata["temporal_options"] == temporal_options
