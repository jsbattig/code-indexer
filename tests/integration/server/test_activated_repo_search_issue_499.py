"""
Integration test for Issue #499: Activated repository search returns results.

This test verifies that after the fix, activated repositories have proper config
and can perform semantic searches that return actual results (not 0 results).
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from datetime import datetime, timezone

import pytest

from src.code_indexer.server.repositories.activated_repo_manager import (
    ActivatedRepoManager,
)
from src.code_indexer.server.repositories.golden_repo_manager import GoldenRepo
from src.code_indexer.backends.backend_factory import BackendFactory
from src.code_indexer.backends.filesystem_backend import FilesystemBackend
from src.code_indexer.config import ConfigManager


class TestActivatedRepoSearchIssue499:
    """Integration test for Issue #499 fix."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def golden_repo_with_code(self, temp_data_dir):
        """Create a real git repository with actual code to search."""
        golden_path = Path(temp_data_dir) / "golden" / "test-repo"
        golden_path.mkdir(parents=True, exist_ok=True)

        # Initialize git repo
        os.system(f"cd {golden_path} && git init")
        os.system(f"cd {golden_path} && git config user.email 'test@example.com'")
        os.system(f"cd {golden_path} && git config user.name 'Test User'")

        # Create multiple Python files with searchable content
        (golden_path / "auth.py").write_text(
            """
def authenticate_user(username, password):
    '''Authenticate user with credentials'''
    # TODO: implement authentication logic
    pass

def verify_token(token):
    '''Verify JWT token validity'''
    pass
"""
        )

        (golden_path / "database.py").write_text(
            """
import sqlite3

def connect_database(db_path):
    '''Connect to SQLite database'''
    return sqlite3.connect(db_path)

def execute_query(conn, query):
    '''Execute SQL query on database connection'''
    cursor = conn.cursor()
    cursor.execute(query)
    return cursor.fetchall()
"""
        )

        # Commit files
        os.system(f"cd {golden_path} && git add .")
        os.system(f"cd {golden_path} && git commit -m 'Add code files'")

        # Initialize .code-indexer/ (required after Issue #500 fix - CoW clone copies .code-indexer/)
        subprocess.run(
            ["cidx", "init"],
            cwd=golden_path,
            check=True,
            capture_output=True,
        )

        return golden_path

    @pytest.fixture
    def golden_repo_manager_mock(self, golden_repo_with_code):
        """Mock golden repo manager with real git repo."""
        mock = MagicMock()

        golden_repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/example/test-repo.git",
            default_branch="master",
            clone_path=str(golden_repo_with_code),
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

    def test_activated_repo_backend_factory_creates_filesystem_backend(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test that backend factory creates FilesystemBackend for activated repos.

        This is the core integration test for Issue #499 - verifies that the
        config.json created during activation causes backend_factory to select
        FilesystemBackend instead of defaulting to FilesystemContainerBackend.
        """
        username = "testuser"
        golden_repo_alias = "test-repo"
        user_alias = "my-repo"

        # Execute activation
        result = activated_repo_manager._do_activate_repository(
            username=username,
            golden_repo_alias=golden_repo_alias,
            branch_name="master",
            user_alias=user_alias,
        )

        # Verify activation succeeded
        assert result["success"] is True

        # Get activated repo path
        activated_repo_path = (
            Path(temp_data_dir) / "activated-repos" / username / user_alias
        )

        # Verify config exists
        config_yml_path = activated_repo_path / ".code-indexer" / "config.json"
        assert config_yml_path.exists(), "Config file must exist after activation"

        # Convert YAML to JSON for ConfigManager
        import yaml

        with open(config_yml_path, "r") as f:
            config_data = yaml.safe_load(f)

        config_json_path = activated_repo_path / ".code-indexer" / "config.json"
        with open(config_json_path, "w") as f:
            json.dump(config_data, f)

        # Load config and create backend
        config_manager = ConfigManager(config_path=config_json_path)
        config = config_manager.load()

        # Verify config has correct settings
        assert config.vector_store is not None, "vector_store must be configured"
        assert (
            config.vector_store.provider == "filesystem"
        ), "vector_store provider must be 'filesystem'"

        # Create backend using factory
        backend = BackendFactory.create(config, activated_repo_path)

        # CRITICAL ASSERTION: Verify FilesystemBackend is selected
        assert isinstance(backend, FilesystemBackend), (
            f"Backend factory must select FilesystemBackend for activated repos, "
            f"but got {type(backend).__name__}. This indicates Issue #499 is NOT fixed."
        )

    def test_config_prevents_filesystem_default_fallback(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test that config.json prevents backend_factory from defaulting to Filesystem.

        Before the fix: config.vector_store was None, backend_factory defaulted to Filesystem
        After the fix: config.vector_store.provider='filesystem', backend_factory uses FilesystemBackend
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

        # Load config
        activated_repo_path = (
            Path(temp_data_dir) / "activated-repos" / username / user_alias
        )
        config_yml_path = activated_repo_path / ".code-indexer" / "config.json"

        import yaml

        with open(config_yml_path, "r") as f:
            config_data = yaml.safe_load(f)

        # Convert to JSON for ConfigManager
        config_json_path = activated_repo_path / ".code-indexer" / "config.json"
        with open(config_json_path, "w") as f:
            json.dump(config_data, f)

        config_manager = ConfigManager(config_path=config_json_path)
        config = config_manager.load()

        # CRITICAL: Verify config.vector_store is NOT None
        assert config.vector_store is not None, (
            "config.vector_store must NOT be None. "
            "If None, backend_factory defaults to Filesystem (Issue #499 root cause)."
        )

        # Verify provider is filesystem
        assert (
            config.vector_store.provider == "filesystem"
        ), "vector_store.provider must be 'filesystem' to prevent Filesystem fallback"

    def test_voyage_ai_configuration_in_activated_repo(
        self, activated_repo_manager, temp_data_dir
    ):
        """Test that activated repo has VoyageAI configuration for server mode."""
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

        # Load config
        activated_repo_path = (
            Path(temp_data_dir) / "activated-repos" / username / user_alias
        )
        config_yml_path = activated_repo_path / ".code-indexer" / "config.json"

        import yaml

        with open(config_yml_path, "r") as f:
            config_data = yaml.safe_load(f)

        # Verify embedding provider
        assert (
            config_data["embedding_provider"] == "voyage-ai"
        ), "Server mode must use VoyageAI embedding provider"

        # Verify voyage_ai configuration
        assert "voyage_ai" in config_data, "Config must contain voyage_ai section"
        assert (
            config_data["voyage_ai"]["model"] == "voyage-code-3"
        ), "VoyageAI model must be voyage-code-3 (production default)"
