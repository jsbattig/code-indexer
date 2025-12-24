"""
Unit tests for CompositeRepoValidator.

Tests validation of operations on composite repositories to ensure
unsupported operations are properly blocked with clear error messages.
"""

import json
import pytest
from pathlib import Path
from fastapi import HTTPException

from code_indexer.server.validators.composite_repo_validator import (
    CompositeRepoValidator,
)


class TestCompositeRepoValidator:
    """Test suite for CompositeRepoValidator class."""

    @pytest.fixture
    def temp_composite_repo(self, tmp_path: Path) -> Path:
        """Create a temporary composite repository with config."""
        repo_path = tmp_path / "composite_repo"
        repo_path.mkdir()
        config_dir = repo_path / ".code-indexer"
        config_dir.mkdir()

        config = {"proxy_mode": True, "embedding_provider": "voyage-ai"}

        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps(config, indent=2))

        return repo_path

    @pytest.fixture
    def temp_single_repo(self, tmp_path: Path) -> Path:
        """Create a temporary single repository with config."""
        repo_path = tmp_path / "single_repo"
        repo_path.mkdir()
        config_dir = repo_path / ".code-indexer"
        config_dir.mkdir()

        config = {"proxy_mode": False, "embedding_provider": "voyage-ai"}

        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps(config, indent=2))

        return repo_path

    @pytest.fixture
    def temp_repo_no_config(self, tmp_path: Path) -> Path:
        """Create a temporary repository without config."""
        repo_path = tmp_path / "no_config_repo"
        repo_path.mkdir()
        return repo_path

    def test_branch_switch_blocked_on_composite_repo(self, temp_composite_repo: Path):
        """Test that branch switch raises 400 for composite repos."""
        with pytest.raises(HTTPException) as exc_info:
            CompositeRepoValidator.check_operation(temp_composite_repo, "branch_switch")

        assert exc_info.value.status_code == 400
        assert (
            "Branch operations are not supported for composite repositories"
            in exc_info.value.detail
        )

    def test_branch_list_blocked_on_composite_repo(self, temp_composite_repo: Path):
        """Test that branch list raises 400 for composite repos."""
        with pytest.raises(HTTPException) as exc_info:
            CompositeRepoValidator.check_operation(temp_composite_repo, "branch_list")

        assert exc_info.value.status_code == 400
        assert (
            "Branch operations are not supported for composite repositories"
            in exc_info.value.detail
        )

    def test_sync_blocked_on_composite_repo(self, temp_composite_repo: Path):
        """Test that sync raises 400 for composite repos."""
        with pytest.raises(HTTPException) as exc_info:
            CompositeRepoValidator.check_operation(temp_composite_repo, "sync")

        assert exc_info.value.status_code == 400
        assert (
            "Sync is not supported for composite repositories" in exc_info.value.detail
        )

    def test_index_blocked_on_composite_repo(self, temp_composite_repo: Path):
        """Test that index raises 400 for composite repos."""
        with pytest.raises(HTTPException) as exc_info:
            CompositeRepoValidator.check_operation(temp_composite_repo, "index")

        assert exc_info.value.status_code == 400
        assert (
            "Indexing must be done on individual golden repositories"
            in exc_info.value.detail
        )

    def test_reconcile_blocked_on_composite_repo(self, temp_composite_repo: Path):
        """Test that reconcile raises 400 for composite repos."""
        with pytest.raises(HTTPException) as exc_info:
            CompositeRepoValidator.check_operation(temp_composite_repo, "reconcile")

        assert exc_info.value.status_code == 400
        assert (
            "Reconciliation is not supported for composite repositories"
            in exc_info.value.detail
        )

    def test_init_blocked_on_composite_repo(self, temp_composite_repo: Path):
        """Test that init raises 400 for composite repos."""
        with pytest.raises(HTTPException) as exc_info:
            CompositeRepoValidator.check_operation(temp_composite_repo, "init")

        assert exc_info.value.status_code == 400
        assert "Composite repositories cannot be initialized" in exc_info.value.detail

    def test_branch_switch_allowed_on_single_repo(self, temp_single_repo: Path):
        """Test that branch switch does not raise for single repos."""
        # Should not raise any exception
        CompositeRepoValidator.check_operation(temp_single_repo, "branch_switch")

    def test_branch_list_allowed_on_single_repo(self, temp_single_repo: Path):
        """Test that branch list does not raise for single repos."""
        # Should not raise any exception
        CompositeRepoValidator.check_operation(temp_single_repo, "branch_list")

    def test_sync_allowed_on_single_repo(self, temp_single_repo: Path):
        """Test that sync does not raise for single repos."""
        # Should not raise any exception
        CompositeRepoValidator.check_operation(temp_single_repo, "sync")

    def test_operation_allowed_on_repo_without_config(self, temp_repo_no_config: Path):
        """Test that operations are allowed on repos without config (not composite)."""
        # Should not raise any exception
        CompositeRepoValidator.check_operation(temp_repo_no_config, "branch_switch")
        CompositeRepoValidator.check_operation(temp_repo_no_config, "sync")

    def test_unknown_operation_on_composite_repo_not_blocked(
        self, temp_composite_repo: Path
    ):
        """Test that unknown operations don't raise error (not in UNSUPPORTED_OPERATIONS)."""
        # Should not raise any exception for unknown operations
        CompositeRepoValidator.check_operation(temp_composite_repo, "unknown_operation")

    def test_error_messages_are_clear_and_specific(self, temp_composite_repo: Path):
        """Test that error messages are clear and explain the limitation."""
        operations_to_messages = {
            "branch_switch": "Branch operations are not supported for composite repositories",
            "branch_list": "Branch operations are not supported for composite repositories",
            "sync": "Sync is not supported for composite repositories",
            "index": "Indexing must be done on individual golden repositories",
            "reconcile": "Reconciliation is not supported for composite repositories",
            "init": "Composite repositories cannot be initialized",
        }

        for operation, expected_message in operations_to_messages.items():
            with pytest.raises(HTTPException) as exc_info:
                CompositeRepoValidator.check_operation(temp_composite_repo, operation)

            assert exc_info.value.status_code == 400
            assert expected_message in exc_info.value.detail

    def test_validator_has_all_unsupported_operations_defined(self):
        """Test that UNSUPPORTED_OPERATIONS dictionary contains all expected operations."""
        expected_operations = {
            "branch_switch",
            "branch_list",
            "sync",
            "index",
            "reconcile",
            "init",
        }

        assert (
            set(CompositeRepoValidator.UNSUPPORTED_OPERATIONS.keys())
            == expected_operations
        )
