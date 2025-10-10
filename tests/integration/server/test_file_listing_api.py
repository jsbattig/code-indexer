"""
Integration tests for file listing API endpoint.

Tests the GET /api/repositories/{id}/files endpoint for both single
and composite repositories (Story 3.3).
"""

import pytest
from pathlib import Path
from datetime import datetime
from fastapi.testclient import TestClient


class TestFileListingAPIEndpoint:
    """Test file listing API endpoint integration."""

    def test_list_composite_repo_files_basic(
        self, test_client, mock_composite_repo, auth_headers
    ):
        """Test listing files from composite repository."""
        # Create composite repo with test files
        composite_path, repo_id = mock_composite_repo

        # Create component repos
        repo1 = composite_path / "backend-api"
        repo1.mkdir()
        (repo1 / "main.py").write_text("test")

        repo2 = composite_path / "frontend-app"
        repo2.mkdir()
        (repo2 / "app.js").write_text("test")

        # GET file listing
        response = test_client.get(
            f"/api/repositories/{repo_id}/files", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should include files from both components
        file_paths = [f["full_path"] for f in data["files"]]
        assert any("backend-api/main.py" in path for path in file_paths)
        assert any("frontend-app/app.js" in path for path in file_paths)

    def test_list_composite_repo_files_shows_component_repo(
        self, test_client, mock_composite_repo, auth_headers
    ):
        """Test file listing includes component_repo field."""
        composite_path, repo_id = mock_composite_repo

        # Create component repo
        repo1 = composite_path / "backend-api"
        repo1.mkdir()
        (repo1 / "main.py").write_text("test")

        # GET file listing
        response = test_client.get(
            f"/api/repositories/{repo_id}/files", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Every file should have component_repo field
        for file_info in data["files"]:
            assert "component_repo" in file_info
            assert file_info["component_repo"] in ["backend-api"]

    def test_list_composite_repo_files_recursive_mode(
        self, test_client, mock_composite_repo, auth_headers
    ):
        """Test listing files recursively through nested directories."""
        composite_path, repo_id = mock_composite_repo

        # Create nested structure
        repo1 = composite_path / "backend"
        repo1.mkdir()
        (repo1 / "root.py").write_text("test")
        src_dir = repo1 / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("test")
        nested_dir = src_dir / "nested"
        nested_dir.mkdir()
        (nested_dir / "deep.py").write_text("test")

        # GET with recursive=true
        response = test_client.get(
            f"/api/repositories/{repo_id}/files?recursive=true", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should include nested files
        file_paths = [f["full_path"] for f in data["files"]]
        assert any("root.py" in path for path in file_paths)
        assert any("src/main.py" in path for path in file_paths)
        assert any("nested/deep.py" in path for path in file_paths)

    def test_list_composite_repo_files_non_recursive_mode(
        self, test_client, mock_composite_repo, auth_headers
    ):
        """Test listing files non-recursively only shows top level."""
        composite_path, repo_id = mock_composite_repo

        # Create nested structure
        repo1 = composite_path / "backend"
        repo1.mkdir()
        (repo1 / "root.py").write_text("test")
        src_dir = repo1 / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("test")

        # GET with recursive=false (default)
        response = test_client.get(
            f"/api/repositories/{repo_id}/files?recursive=false", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should only include top-level items
        file_paths = [f["full_path"] for f in data["files"]]
        assert any("root.py" in path for path in file_paths)
        # Should include directory itself but not nested files
        assert not any("src/main.py" in path for path in file_paths)

    def test_list_composite_repo_files_excludes_git_directory(
        self, test_client, mock_composite_repo, auth_headers
    ):
        """Test file listing excludes .git directories."""
        composite_path, repo_id = mock_composite_repo

        # Create repo with .git directory
        repo1 = composite_path / "backend"
        repo1.mkdir()
        (repo1 / "main.py").write_text("test")
        git_dir = repo1 / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("test")

        # GET file listing
        response = test_client.get(
            f"/api/repositories/{repo_id}/files?recursive=true", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should not include .git files
        file_paths = [f["full_path"] for f in data["files"]]
        assert any("main.py" in path for path in file_paths)
        assert not any(".git" in path for path in file_paths)

    def test_list_composite_repo_files_excludes_code_indexer_directory(
        self, test_client, mock_composite_repo, auth_headers
    ):
        """Test file listing excludes .code-indexer directories."""
        composite_path, repo_id = mock_composite_repo

        # Create repo with .code-indexer directory
        repo1 = composite_path / "backend"
        repo1.mkdir()
        (repo1 / "main.py").write_text("test")
        # Note: .code-indexer already exists from mock_composite_repo

        # GET file listing
        response = test_client.get(
            f"/api/repositories/{repo_id}/files?recursive=true", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should not include .code-indexer files
        file_paths = [f["full_path"] for f in data["files"]]
        assert any("main.py" in path for path in file_paths)
        assert not any(".code-indexer" in path for path in file_paths)

    def test_list_composite_repo_files_with_path_filter(
        self, test_client, mock_composite_repo, auth_headers
    ):
        """Test file listing with path parameter for filtering."""
        composite_path, repo_id = mock_composite_repo

        # Create repo with subdirectories
        repo1 = composite_path / "backend"
        repo1.mkdir()
        (repo1 / "root.py").write_text("test")
        src_dir = repo1 / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("test")

        # GET files in specific path
        response = test_client.get(
            f"/api/repositories/{repo_id}/files?path=src", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should only include files from src directory
        file_paths = [f["full_path"] for f in data["files"]]
        assert any("src/main.py" in path for path in file_paths)
        assert not any("root.py" in path for path in file_paths)

    def test_list_composite_repo_files_sorted_by_path(
        self, test_client, mock_composite_repo, auth_headers
    ):
        """Test file listing returns files sorted by full_path."""
        composite_path, repo_id = mock_composite_repo

        # Create repos with multiple files
        repo1 = composite_path / "zeta-repo"
        repo1.mkdir()
        (repo1 / "file.py").write_text("test")

        repo2 = composite_path / "alpha-repo"
        repo2.mkdir()
        (repo2 / "file.py").write_text("test")

        # Update proxy config
        proxy_config = composite_path / ".code-indexer" / "proxy-config.yaml"
        proxy_config.write_text(
            """discovered_repositories:
  - zeta-repo
  - alpha-repo
"""
        )

        # GET file listing
        response = test_client.get(
            f"/api/repositories/{repo_id}/files", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Files should be sorted alphabetically
        file_paths = [f["full_path"] for f in data["files"]]
        assert file_paths == sorted(file_paths)
        assert file_paths[0].startswith("alpha-repo")

    def test_list_single_repo_files_still_works(
        self, test_client, mock_single_repo, auth_headers
    ):
        """Test single repository file listing unchanged."""
        single_path, repo_id = mock_single_repo

        # Create test files
        (single_path / "main.py").write_text("test")
        (single_path / "test.py").write_text("test")

        # GET file listing
        response = test_client.get(
            f"/api/repositories/{repo_id}/files", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should work exactly as before
        # Note: This assumes existing file listing returns similar structure
        assert "files" in data or len(data) > 0

    def test_list_files_nonexistent_repo_returns_404(self, test_client, auth_headers):
        """Test listing files for nonexistent repository returns 404."""
        response = test_client.get(
            "/api/repositories/nonexistent-repo/files", headers=auth_headers
        )

        assert response.status_code == 404


@pytest.fixture
def test_client():
    """Create FastAPI test client."""
    from code_indexer.server.app import app

    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Create authentication headers for testing."""
    # TODO: Implement proper auth token generation
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def mock_composite_repo(tmp_path):
    """Create mock composite repository for testing."""
    from code_indexer.server.repositories.activated_repo_manager import (
        ActivatedRepoManager,
    )

    # Create composite repository structure
    composite_path = tmp_path / "composite-repo"
    composite_path.mkdir()

    # Create .code-indexer directory with proxy config
    config_dir = composite_path / ".code-indexer"
    config_dir.mkdir()

    proxy_config = config_dir / "proxy-config.yaml"
    proxy_config.write_text(
        """discovered_repositories:
  - backend-api
  - frontend-app
"""
    )

    # Register repository
    manager = ActivatedRepoManager()
    repo_id = f"composite-{composite_path.name}"

    # Create activated repository metadata
    from code_indexer.server.models.activated_repository import ActivatedRepository

    repo = ActivatedRepository(
        user_alias=repo_id,
        username="testuser",
        path=composite_path,
        activated_at=datetime.now(),
        last_accessed=datetime.now(),
        is_composite=True,
        golden_repo_aliases=["backend-api", "frontend-app"],
        discovered_repos=["backend-api", "frontend-app"],
    )

    # Save to manager
    manager._save_repository_metadata(repo)

    yield composite_path, repo_id

    # Cleanup
    manager._delete_repository_metadata(repo_id, "testuser")


@pytest.fixture
def mock_single_repo(tmp_path):
    """Create mock single repository for testing."""
    from code_indexer.server.repositories.activated_repo_manager import (
        ActivatedRepoManager,
    )

    # Create single repository
    single_path = tmp_path / "single-repo"
    single_path.mkdir()

    # Register repository
    manager = ActivatedRepoManager()
    repo_id = f"single-{single_path.name}"

    # Create activated repository metadata
    from code_indexer.server.models.activated_repository import ActivatedRepository

    repo = ActivatedRepository(
        user_alias=repo_id,
        username="testuser",
        path=single_path,
        activated_at=datetime.now(),
        last_accessed=datetime.now(),
        is_composite=False,
        golden_repo_alias="test-golden-repo",
        current_branch="main",
    )

    # Save to manager
    manager._save_repository_metadata(repo)

    yield single_path, repo_id

    # Cleanup
    manager._delete_repository_metadata(repo_id, "testuser")
