"""
Unit tests for activated repository configuration creation (Issue #499).

Tests that activated repositories are created with proper .code-indexer/config.json
containing FilesystemVectorStore and VoyageAI configuration to ensure search works.
"""

import json
import os
import subprocess
import tempfile
import yaml
from pathlib import Path
from unittest.mock import MagicMock
from datetime import datetime, timezone

import pytest

from src.code_indexer.server.repositories.activated_repo_manager import (
    ActivatedRepoManager,
)
from src.code_indexer.server.repositories.golden_repo_manager import GoldenRepo


class TestActivatedRepoConfigCreation:
    """Test suite for activated repository config.json creation (Issue #499)."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def golden_repo_with_git(self, temp_data_dir):
        """Create a real git repository to use as golden repo."""
        golden_path = Path(temp_data_dir) / "golden" / "test-repo"
        golden_path.mkdir(parents=True, exist_ok=True)

        # Initialize git repo
        os.system(f"cd {golden_path} && git init")
        os.system(f"cd {golden_path} && git config user.email 'test@example.com'")
        os.system(f"cd {golden_path} && git config user.name 'Test User'")

        # Create a test file and commit
        test_file = golden_path / "test.py"
        test_file.write_text("def hello():\n    pass\n")
        os.system(f"cd {golden_path} && git add test.py")
        os.system(f"cd {golden_path} && git commit -m 'Initial commit'")

        # Initialize .code-indexer/ (required after Issue #500 fix - CoW clone copies .code-indexer/)
        subprocess.run(
            ["cidx", "init"],
            cwd=golden_path,
            check=True,
            capture_output=True,
        )

        return golden_path

    @pytest.fixture
    def golden_repo_manager_mock(self, golden_repo_with_git):
        """Mock golden repo manager with real git repo."""
        mock = MagicMock()

        golden_repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/example/test-repo.git",
            default_branch="master",  # git init creates 'master' by default
            clone_path=str(golden_repo_with_git),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        mock.golden_repos = {"test-repo": golden_repo}
        return mock

    @pytest.fixture
    def background_job_manager_mock(self):
        """Mock background job manager."""
        mock = MagicMock()
        mock.submit_job.return_value = "job-123"
        return mock

    @pytest.fixture
    def activated_repo_manager(
        self, temp_data_dir, golden_repo_manager_mock, background_job_manager_mock
    ):
        """Create ActivatedRepoManager instance with temp directory."""
        return ActivatedRepoManager(
            data_dir=temp_data_dir,
            golden_repo_manager=golden_repo_manager_mock,
            background_job_manager=background_job_manager_mock,
        )

    def test_activated_repo_has_config_yml_after_activation(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test that activated repository contains .code-indexer/config.json after activation.

        This is the failing test for Issue #499 - activated repos must have config.json
        to ensure FilesystemVectorStore backend is used instead of defaulting to Filesystem.
        """
        username = "testuser"
        golden_repo_alias = "test-repo"
        user_alias = "my-repo"

        # Execute the actual activation (not background job)
        activated_repo_manager._do_activate_repository(
            username=username,
            golden_repo_alias=golden_repo_alias,
            branch_name="master",
            user_alias=user_alias,
        )

        # Verify config.json exists
        activated_repo_path = (
            Path(temp_data_dir) / "activated-repos" / username / user_alias
        )
        config_yml_path = activated_repo_path / ".code-indexer" / "config.json"

        assert config_yml_path.exists(), (
            f"Config file missing at {config_yml_path}. "
            "Activated repositories must have .code-indexer/config.json "
            "to ensure FilesystemVectorStore is used (Issue #499)"
        )

    def test_config_yml_contains_filesystem_vector_store(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test that config.json specifies FilesystemVectorStore provider.

        Without this, backend_factory defaults to FilesystemContainerBackend,
        causing search to return 0 results (Issue #499).
        """
        username = "testuser"
        golden_repo_alias = "test-repo"
        user_alias = "my-repo"

        # Execute activation
        activated_repo_manager._do_activate_repository(
            username=username,
            golden_repo_alias=golden_repo_alias,
            branch_name="master",
            user_alias=user_alias,
        )

        # Read config.json
        activated_repo_path = (
            Path(temp_data_dir) / "activated-repos" / username / user_alias
        )
        config_yml_path = activated_repo_path / ".code-indexer" / "config.json"

        with open(config_yml_path, "r") as f:
            config_data = yaml.safe_load(f)

        # Verify vector_store configuration
        assert (
            "vector_store" in config_data
        ), "config.json must contain 'vector_store' section"
        assert (
            config_data["vector_store"]["provider"] == "filesystem"
        ), "vector_store provider must be 'filesystem' to avoid defaulting to Filesystem"

    def test_config_yml_contains_voyage_ai_configuration(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test that config.json specifies VoyageAI embedding provider.

        Server mode should use VoyageAI (production provider) by default.
        """
        username = "testuser"
        golden_repo_alias = "test-repo"
        user_alias = "my-repo"

        # Execute activation
        activated_repo_manager._do_activate_repository(
            username=username,
            golden_repo_alias=golden_repo_alias,
            branch_name="master",
            user_alias=user_alias,
        )

        # Read config.json
        activated_repo_path = (
            Path(temp_data_dir) / "activated-repos" / username / user_alias
        )
        config_yml_path = activated_repo_path / ".code-indexer" / "config.json"

        with open(config_yml_path, "r") as f:
            config_data = yaml.safe_load(f)

        # Verify embedding provider configuration
        assert (
            "embedding_provider" in config_data
        ), "config.json must contain 'embedding_provider' field"
        assert (
            config_data["embedding_provider"] == "voyage-ai"
        ), "embedding_provider must be 'voyage-ai' for server mode"

        # Verify voyage_ai section exists
        assert (
            "voyage_ai" in config_data
        ), "config.json must contain 'voyage_ai' configuration section"
        assert (
            config_data["voyage_ai"]["model"] == "voyage-code-3"
        ), "voyage_ai model must be 'voyage-code-3' (production default)"

    def test_config_yml_has_correct_yaml_structure(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test that config.json is valid JSON and has expected structure."""
        username = "testuser"
        golden_repo_alias = "test-repo"
        user_alias = "my-repo"

        # Execute activation
        activated_repo_manager._do_activate_repository(
            username=username,
            golden_repo_alias=golden_repo_alias,
            branch_name="master",
            user_alias=user_alias,
        )

        # Read config.json
        activated_repo_path = (
            Path(temp_data_dir) / "activated-repos" / username / user_alias
        )
        config_yml_path = activated_repo_path / ".code-indexer" / "config.json"

        # Verify YAML is valid
        with open(config_yml_path, "r") as f:
            config_data = yaml.safe_load(f)

        assert isinstance(
            config_data, dict
        ), "config.json must be a valid JSON dictionary"

        # Verify expected keys are present
        expected_keys = ["vector_store", "embedding_provider", "voyage_ai"]
        for key in expected_keys:
            assert key in config_data, f"config.json must contain '{key}' key"

    def test_backend_factory_selects_filesystem_with_config(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test that backend_factory selects FilesystemBackend when config.json exists.

        This is the integration test verifying the fix works end-to-end.
        """
        from src.code_indexer.backends.backend_factory import BackendFactory
        from src.code_indexer.backends.filesystem_backend import FilesystemBackend
        from src.code_indexer.config import ConfigManager

        username = "testuser"
        golden_repo_alias = "test-repo"
        user_alias = "my-repo"

        # Execute activation
        activated_repo_manager._do_activate_repository(
            username=username,
            golden_repo_alias=golden_repo_alias,
            branch_name="master",
            user_alias=user_alias,
        )

        # Load config from activated repo
        activated_repo_path = (
            Path(temp_data_dir) / "activated-repos" / username / user_alias
        )
        config_path = activated_repo_path / ".code-indexer" / "config.json"

        # Convert YAML to JSON for ConfigManager (it expects JSON)
        config_json_path = activated_repo_path / ".code-indexer" / "config.json"
        with open(config_path, "r") as f:
            config_data = yaml.safe_load(f)
        with open(config_json_path, "w") as f:
            json.dump(config_data, f)

        # Load config and create backend
        config_manager = ConfigManager(config_path=config_json_path)
        config = config_manager.load()

        # Create backend using factory
        backend = BackendFactory.create(config, activated_repo_path)

        # Verify FilesystemBackend is selected
        assert isinstance(backend, FilesystemBackend), (
            f"Expected FilesystemBackend, got {type(backend).__name__}. "
            "Backend factory must select FilesystemBackend when config.json exists "
            "with vector_store.provider='filesystem' (Issue #499)"
        )

    def test_existing_repos_can_be_migrated(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test that existing activated repos without config can be migrated.

        This test verifies the migration path for repos activated before the fix.
        """
        username = "testuser"
        user_alias = "existing-repo"

        # Create an existing activated repo WITHOUT config.json (simulating pre-fix state)
        user_dir = Path(temp_data_dir) / "activated-repos" / username
        repo_dir = user_dir / user_alias
        repo_dir.mkdir(parents=True, exist_ok=True)

        # Create git repo
        os.system(f"cd {repo_dir} && git init")

        # Create metadata file
        metadata = {
            "user_alias": user_alias,
            "golden_repo_alias": "test-repo",
            "current_branch": "master",
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
        }
        metadata_file = user_dir / f"{user_alias}_metadata.json"
        with open(metadata_file, "w") as f:
            json.dump(metadata, f)

        # Verify config.json does NOT exist yet
        config_yml_path = repo_dir / ".code-indexer" / "config.json"
        assert (
            not config_yml_path.exists()
        ), "Test setup: config.json should not exist initially"

        # TODO: Implement migration function that adds config.json to existing repos
        # This will be implemented as part of the fix
        # For now, this test documents the requirement

        # After migration, config.json should exist
        # activated_repo_manager._migrate_repo_config(username, user_alias)
        # assert config_yml_path.exists(), "Migration must create config.json for existing repos"
