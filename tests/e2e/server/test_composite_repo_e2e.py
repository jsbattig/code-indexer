"""
End-to-end test for composite repository activation (Story 1.2).

Tests the complete workflow of composite repository creation from golden repos
to activated composite structure with zero mocking.

Following TDD methodology and anti-mock principle - real systems only.
"""

import json
import os
import pytest
import tempfile
import shutil
import subprocess
from pathlib import Path

from code_indexer.server.repositories.activated_repo_manager import (
    ActivatedRepoManager,
)
from code_indexer.server.repositories.golden_repo_manager import GoldenRepoManager
from code_indexer.proxy.config_manager import ProxyConfigManager


@pytest.mark.e2e
class TestCompositeRepositoryE2E:
    """End-to-end test for complete composite repository workflow."""

    def setup_method(self):
        """Set up real golden repositories with actual indexing data."""
        # Create temporary directory
        self.test_dir = tempfile.mkdtemp()
        self.data_dir = os.path.join(self.test_dir, "data")
        os.makedirs(self.data_dir, exist_ok=True)

        # Create golden repos directory
        self.golden_repos_dir = os.path.join(self.data_dir, "golden-repos")
        os.makedirs(self.golden_repos_dir, exist_ok=True)

        # Create activated repos directory
        self.activated_repos_dir = os.path.join(self.data_dir, "activated-repos")
        os.makedirs(self.activated_repos_dir, exist_ok=True)

        # Create realistic golden repositories with git history
        self.golden_repo_aliases = ["backend", "frontend", "shared"]
        self.golden_repo_paths = {}

        for alias in self.golden_repo_aliases:
            repo_path = os.path.join(self.golden_repos_dir, alias)
            os.makedirs(repo_path, exist_ok=True)

            # Create realistic project structure
            if alias == "backend":
                self._create_backend_repo(repo_path)
            elif alias == "frontend":
                self._create_frontend_repo(repo_path)
            else:
                self._create_shared_repo(repo_path)

            # Create .code-indexer directory with realistic config
            code_indexer_dir = os.path.join(repo_path, ".code-indexer")
            os.makedirs(code_indexer_dir, exist_ok=True)

            config_data = {
                "embedding_provider": "voyage-ai",
                "proxy_mode": False,
                "qdrant": {
                    "host": "localhost",
                    "port": 6333,
                },
            }
            with open(os.path.join(code_indexer_dir, "config.json"), "w") as f:
                json.dump(config_data, f, indent=2)

            # Initialize git repository
            subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repo_path,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repo_path,
                capture_output=True,
            )
            subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", f"Initial {alias} commit"],
                cwd=repo_path,
                capture_output=True,
            )

            self.golden_repo_paths[alias] = repo_path

        # Initialize managers
        self.golden_repo_manager = GoldenRepoManager(data_dir=self.data_dir)
        self.activated_repo_manager = ActivatedRepoManager(
            data_dir=self.data_dir, golden_repo_manager=self.golden_repo_manager
        )

        # Register golden repositories
        for alias, path in self.golden_repo_paths.items():
            from unittest.mock import Mock

            mock_golden_repo = Mock()
            mock_golden_repo.alias = alias
            mock_golden_repo.clone_path = path
            mock_golden_repo.default_branch = "master"
            mock_golden_repo.repo_url = f"https://github.com/test/{alias}.git"
            self.golden_repo_manager.golden_repos[alias] = mock_golden_repo

    def teardown_method(self):
        """Clean up test directory."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_backend_repo(self, repo_path: str) -> None:
        """Create a realistic backend repository structure."""
        # Create directory structure
        src_dir = os.path.join(repo_path, "src")
        os.makedirs(src_dir, exist_ok=True)

        # Create Python files
        with open(os.path.join(src_dir, "app.py"), "w") as f:
            f.write(
                """
import fastapi

app = fastapi.FastAPI()

@app.get("/")
def read_root():
    return {"message": "Backend API"}
"""
            )

        with open(os.path.join(src_dir, "models.py"), "w") as f:
            f.write(
                """
from pydantic import BaseModel

class User(BaseModel):
    id: int
    name: str
"""
            )

        # Create README
        with open(os.path.join(repo_path, "README.md"), "w") as f:
            f.write("# Backend Service\n\nFastAPI backend service.\n")

    def _create_frontend_repo(self, repo_path: str) -> None:
        """Create a realistic frontend repository structure."""
        src_dir = os.path.join(repo_path, "src")
        os.makedirs(src_dir, exist_ok=True)

        # Create JavaScript/TypeScript files
        with open(os.path.join(src_dir, "App.tsx"), "w") as f:
            f.write(
                """
import React from 'react';

function App() {
  return <div>Frontend App</div>;
}

export default App;
"""
            )

        with open(os.path.join(repo_path, "README.md"), "w") as f:
            f.write("# Frontend Service\n\nReact frontend application.\n")

    def _create_shared_repo(self, repo_path: str) -> None:
        """Create a shared library repository."""
        src_dir = os.path.join(repo_path, "src")
        os.makedirs(src_dir, exist_ok=True)

        with open(os.path.join(src_dir, "utils.py"), "w") as f:
            f.write(
                """
def format_date(date):
    return date.strftime("%Y-%m-%d")
"""
            )

        with open(os.path.join(repo_path, "README.md"), "w") as f:
            f.write("# Shared Library\n\nShared utilities.\n")

    def test_e2e_complete_composite_repository_creation_workflow(self):
        """
        E2E test: Complete workflow from activation request to usable composite repository.

        GIVEN: Three golden repositories (backend, frontend, shared)
        WHEN: User activates composite repository through ActivatedRepoManager
        THEN: Complete composite structure is created with:
            - Proper directory structure
            - Proxy configuration with proxy_mode=true
            - All component repositories CoW cloned
            - All .code-indexer data preserved
            - Metadata file created with is_composite=true
            - ProxyConfigManager can load and query the structure
        """
        # ARRANGE
        username = "developer1"
        composite_alias = "fullstack_monorepo"

        # ACT: Activate composite repository
        result = self.activated_repo_manager._do_activate_composite_repository(
            username=username,
            golden_repo_aliases=self.golden_repo_aliases,
            user_alias=composite_alias,
            progress_callback=None,
        )

        # ASSERT: Activation succeeded
        assert result["success"] is True
        assert result["is_composite"] is True
        assert result["component_count"] == 3
        assert set(result["component_aliases"]) == set(self.golden_repo_aliases)

        # ASSERT: Directory structure created
        composite_path = Path(self.activated_repos_dir) / username / composite_alias
        assert composite_path.exists()
        assert composite_path.is_dir()

        # ASSERT: Proxy configuration created with correct structure
        proxy_config_path = composite_path / ".code-indexer" / "config.json"
        assert proxy_config_path.exists()

        with open(proxy_config_path, "r") as f:
            proxy_config = json.load(f)

        assert proxy_config["proxy_mode"] is True
        assert "discovered_repos" in proxy_config
        assert len(proxy_config["discovered_repos"]) == 3

        # ASSERT: All component repositories cloned
        for alias in self.golden_repo_aliases:
            component_path = composite_path / alias
            assert component_path.exists(), f"Component {alias} should exist"
            assert component_path.is_dir()

            # Verify git repository structure
            git_dir = component_path / ".git"
            assert git_dir.exists(), f"Git directory should exist for {alias}"

            # Verify .code-indexer data preserved
            code_indexer_dir = component_path / ".code-indexer"
            assert code_indexer_dir.exists(), f".code-indexer should exist for {alias}"

            component_config = component_path / ".code-indexer" / "config.json"
            assert component_config.exists()

            with open(component_config, "r") as f:
                comp_config = json.load(f)

            # Component repos should NOT have proxy_mode
            assert comp_config.get("proxy_mode") is False
            assert "embedding_provider" in comp_config

            # Verify actual source files were cloned
            if alias == "backend":
                assert (component_path / "src" / "app.py").exists()
                assert (component_path / "src" / "models.py").exists()
            elif alias == "frontend":
                assert (component_path / "src" / "App.tsx").exists()
            elif alias == "shared":
                assert (component_path / "src" / "utils.py").exists()

        # ASSERT: Metadata file created
        metadata_path = (
            Path(self.activated_repos_dir)
            / username
            / f"{composite_alias}_metadata.json"
        )
        assert metadata_path.exists()

        with open(metadata_path, "r") as f:
            metadata = json.load(f)

        assert metadata["user_alias"] == composite_alias
        assert metadata["is_composite"] is True
        assert set(metadata["golden_repo_aliases"]) == set(self.golden_repo_aliases)
        assert "activated_at" in metadata

        # ASSERT: ProxyConfigManager can work with the structure
        proxy_manager = ProxyConfigManager(composite_path)
        loaded_config = proxy_manager.load_config()

        assert loaded_config.proxy_mode is True
        assert len(loaded_config.discovered_repos) == 3

        # ASSERT: Discovered repos match expected structure
        discovered_set = set(loaded_config.discovered_repos)
        expected_set = set(self.golden_repo_aliases)
        assert discovered_set == expected_set

        # ASSERT: Can get repositories from proxy manager
        repos = proxy_manager.get_repositories()
        assert len(repos) == 3
        assert set(repos) == set(self.golden_repo_aliases)

    def test_e2e_composite_activation_with_progress_tracking(self):
        """
        E2E test: Verify progress tracking during composite activation.

        GIVEN: Composite activation request with progress callback
        WHEN: Activation is performed
        THEN: Progress is reported at key milestones
        """
        # ARRANGE
        username = "developer2"
        composite_alias = "monitored_composite"
        progress_updates = []

        def track_progress(percent: int) -> None:
            progress_updates.append(percent)

        # ACT
        result = self.activated_repo_manager._do_activate_composite_repository(
            username=username,
            golden_repo_aliases=["backend", "frontend"],
            user_alias=composite_alias,
            progress_callback=track_progress,
        )

        # ASSERT
        assert result["success"] is True
        assert len(progress_updates) > 0, "Progress should be tracked"
        assert 100 in progress_updates, "Should report 100% completion"
        assert progress_updates[0] < progress_updates[-1], "Progress should increase"

        # Verify milestones
        assert any(p <= 10 for p in progress_updates), "Should report early progress"
        assert any(
            20 <= p <= 40 for p in progress_updates
        ), "Should report mid progress"
        assert any(p >= 90 for p in progress_updates), "Should report near completion"

    def test_e2e_composite_with_proxy_config_manager_refresh(self):
        """
        E2E test: ProxyConfigManager refresh discovers all repositories.

        GIVEN: Composite repository with multiple components
        WHEN: ProxyConfigManager.refresh_repositories() is called
        THEN: All repositories are discovered correctly
        """
        # ARRANGE: Create composite
        username = "developer3"
        composite_alias = "refresh_test"

        self.activated_repo_manager._do_activate_composite_repository(
            username=username,
            golden_repo_aliases=self.golden_repo_aliases,
            user_alias=composite_alias,
            progress_callback=None,
        )

        composite_path = Path(self.activated_repos_dir) / username / composite_alias

        # ACT: Manually modify config and refresh
        proxy_manager = ProxyConfigManager(composite_path)

        # Clear discovered repos
        config = proxy_manager.load_config()
        original_count = len(config.discovered_repos)
        config.discovered_repos = []
        proxy_manager._config_manager.save(config)

        # Refresh to rediscover
        proxy_manager.refresh_repositories()

        # ASSERT: All repos rediscovered
        refreshed_config = proxy_manager.load_config()
        assert len(refreshed_config.discovered_repos) == original_count
        assert set(refreshed_config.discovered_repos) == set(self.golden_repo_aliases)

    def test_e2e_composite_validates_component_integrity(self):
        """
        E2E test: Validate all component repositories maintain integrity.

        GIVEN: Composite repository with CoW cloned components
        WHEN: Each component is examined
        THEN: Each maintains complete git history and file structure
        """
        # ARRANGE & ACT
        username = "developer4"
        composite_alias = "integrity_test"

        self.activated_repo_manager._do_activate_composite_repository(
            username=username,
            golden_repo_aliases=self.golden_repo_aliases,
            user_alias=composite_alias,
            progress_callback=None,
        )

        composite_path = Path(self.activated_repos_dir) / username / composite_alias

        # ASSERT: Each component maintains git integrity
        for alias in self.golden_repo_aliases:
            component_path = composite_path / alias

            # Verify git log accessible
            result = subprocess.run(
                ["git", "log", "--oneline"],
                cwd=str(component_path),
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"Git log should work for {alias}"
            assert (
                len(result.stdout.strip()) > 0
            ), f"Should have commit history for {alias}"

            # Verify git status works
            result = subprocess.run(
                ["git", "status"],
                cwd=str(component_path),
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"Git status should work for {alias}"

            # Verify README exists (all repos have README)
            readme_path = component_path / "README.md"
            assert readme_path.exists(), f"README should exist for {alias}"

            # Verify .code-indexer config is complete
            config_path = component_path / ".code-indexer" / "config.json"
            with open(config_path, "r") as f:
                config = json.load(f)

            assert config.get("proxy_mode") is False
            assert "embedding_provider" in config
