"""
Unit tests for composite repository details functionality.

Tests the ComponentRepoInfo and CompositeRepositoryDetails models,
as well as the analysis and aggregation functions.
"""

import json
from datetime import datetime, timezone

from code_indexer.server.models.activated_repository import ActivatedRepository


class TestComponentRepoInfoModel:
    """Tests for ComponentRepoInfo model."""

    def test_component_repo_info_creation(self):
        """Test creating ComponentRepoInfo with all fields."""
        from code_indexer.server.app import ComponentRepoInfo

        info = ComponentRepoInfo(
            name="backend-api",
            path="/path/to/backend-api",
            has_index=True,
            collection_exists=True,
            indexed_files=245,
            last_indexed=datetime.now(timezone.utc),
            size_mb=12.5,
        )

        assert info.name == "backend-api"
        assert info.path == "/path/to/backend-api"
        assert info.has_index is True
        assert info.collection_exists is True
        assert info.indexed_files == 245
        assert info.last_indexed is not None
        assert info.size_mb == 12.5

    def test_component_repo_info_no_index(self):
        """Test ComponentRepoInfo for repo without index."""
        from code_indexer.server.app import ComponentRepoInfo

        info = ComponentRepoInfo(
            name="frontend-app",
            path="/path/to/frontend-app",
            has_index=False,
            collection_exists=False,
            indexed_files=0,
            last_indexed=None,
            size_mb=8.3,
        )

        assert info.has_index is False
        assert info.collection_exists is False
        assert info.indexed_files == 0
        assert info.last_indexed is None


class TestCompositeRepositoryDetailsModel:
    """Tests for CompositeRepositoryDetails model."""

    def test_composite_details_creation(self):
        """Test creating CompositeRepositoryDetails with components."""
        from code_indexer.server.app import (
            ComponentRepoInfo,
            CompositeRepositoryDetails,
        )

        component1 = ComponentRepoInfo(
            name="repo1",
            path="/path/repo1",
            has_index=True,
            collection_exists=True,
            indexed_files=100,
            last_indexed=None,
            size_mb=5.0,
        )

        component2 = ComponentRepoInfo(
            name="repo2",
            path="/path/repo2",
            has_index=True,
            collection_exists=True,
            indexed_files=150,
            last_indexed=None,
            size_mb=7.5,
        )

        activated_at = datetime.now(timezone.utc)
        last_accessed = datetime.now(timezone.utc)

        details = CompositeRepositoryDetails(
            user_alias="my-composite",
            is_composite=True,
            activated_at=activated_at,
            last_accessed=last_accessed,
            component_repositories=[component1, component2],
            total_files=250,
            total_size_mb=12.5,
        )

        assert details.user_alias == "my-composite"
        assert details.is_composite is True
        assert details.activated_at == activated_at
        assert details.last_accessed == last_accessed
        assert len(details.component_repositories) == 2
        assert details.total_files == 250
        assert details.total_size_mb == 12.5


class TestAnalyzeComponentRepo:
    """Tests for _analyze_component_repo function."""

    def test_analyze_repo_with_index(self, tmp_path):
        """Test analyzing a repository with existing index."""
        from code_indexer.server.app import _analyze_component_repo

        # Create mock repository structure
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        # Create .code-indexer directory with metadata
        index_dir = repo_path / ".code-indexer"
        index_dir.mkdir()

        metadata = {"indexed_files": 42, "last_indexed": "2024-01-15T10:00:00Z"}
        metadata_file = index_dir / "metadata.json"
        metadata_file.write_text(json.dumps(metadata))

        # Create some test files
        (repo_path / "file1.py").write_text("print('hello')")
        (repo_path / "file2.py").write_text("print('world')")

        # Analyze the repository
        info = _analyze_component_repo(repo_path, "test-repo")

        assert info.name == "test-repo"
        assert info.path == str(repo_path)
        assert info.has_index is True
        assert info.collection_exists is True
        assert info.indexed_files == 42
        assert info.size_mb > 0  # Should have calculated some size

    def test_analyze_repo_without_index(self, tmp_path):
        """Test analyzing a repository without index."""
        from code_indexer.server.app import _analyze_component_repo

        # Create mock repository without .code-indexer
        repo_path = tmp_path / "no-index-repo"
        repo_path.mkdir()

        # Create some test files
        (repo_path / "file1.txt").write_text("content")

        # Analyze the repository
        info = _analyze_component_repo(repo_path, "no-index-repo")

        assert info.name == "no-index-repo"
        assert info.has_index is False
        assert info.collection_exists is False
        assert info.indexed_files == 0
        assert info.size_mb > 0

    def test_analyze_repo_missing_metadata(self, tmp_path):
        """Test analyzing repo with .code-indexer but missing metadata."""
        from code_indexer.server.app import _analyze_component_repo

        # Create repository with .code-indexer but no metadata
        repo_path = tmp_path / "partial-index-repo"
        repo_path.mkdir()
        (repo_path / ".code-indexer").mkdir()

        # Analyze the repository
        info = _analyze_component_repo(repo_path, "partial-index-repo")

        assert info.has_index is True
        assert info.indexed_files == 0  # No metadata means 0 files


class TestGetCompositeDetails:
    """Tests for _get_composite_details function."""

    def test_get_composite_details_aggregates_components(self, tmp_path):
        """Test that composite details aggregates all component repos."""
        from code_indexer.server.app import _get_composite_details

        # Create mock composite repository structure
        composite_path = tmp_path / "composite-repo"
        composite_path.mkdir()

        # Create .code-indexer with proxy config
        index_dir = composite_path / ".code-indexer"
        index_dir.mkdir()

        config = {
            "proxy_mode": True,
            "discovered_repos": ["repo1", "repo2"],
        }
        (index_dir / "config.json").write_text(json.dumps(config))

        # Create component repositories
        for repo_name in ["repo1", "repo2"]:
            repo_path = composite_path / repo_name
            repo_path.mkdir()

            # Add .code-indexer with metadata
            repo_index_dir = repo_path / ".code-indexer"
            repo_index_dir.mkdir()

            metadata = {"indexed_files": 100 if repo_name == "repo1" else 150}
            (repo_index_dir / "metadata.json").write_text(json.dumps(metadata))

            # Add some files
            (repo_path / "file.txt").write_text("content")

        # Create mock ActivatedRepository
        activated_at = datetime.now(timezone.utc)
        last_accessed = datetime.now(timezone.utc)

        repo = ActivatedRepository(
            user_alias="my-composite",
            username="testuser",
            path=composite_path,
            activated_at=activated_at,
            last_accessed=last_accessed,
            is_composite=True,
            golden_repo_aliases=["golden1", "golden2"],
            discovered_repos=["repo1", "repo2"],
        )

        # Get composite details
        details = _get_composite_details(repo)

        assert details.user_alias == "my-composite"
        assert details.is_composite is True
        assert len(details.component_repositories) == 2
        assert details.total_files == 250  # 100 + 150
        assert details.total_size_mb > 0

    def test_get_composite_details_empty_components(self, tmp_path):
        """Test composite details with no component repositories."""
        from code_indexer.server.app import _get_composite_details

        # Create empty composite repository
        composite_path = tmp_path / "empty-composite"
        composite_path.mkdir()

        index_dir = composite_path / ".code-indexer"
        index_dir.mkdir()

        config = {"proxy_mode": True, "discovered_repos": []}
        (index_dir / "config.json").write_text(json.dumps(config))

        activated_at = datetime.now(timezone.utc)

        repo = ActivatedRepository(
            user_alias="empty-composite",
            username="testuser",
            path=composite_path,
            activated_at=activated_at,
            last_accessed=activated_at,
            is_composite=True,
            golden_repo_aliases=[],
            discovered_repos=[],
        )

        # Get composite details
        details = _get_composite_details(repo)

        assert len(details.component_repositories) == 0
        assert details.total_files == 0
        assert details.total_size_mb == 0


class TestCompositeDetailsCalculations:
    """Tests for calculation accuracy in composite details."""

    def test_total_files_calculation(self, tmp_path):
        """Test that total files are calculated correctly."""
        from code_indexer.server.app import _get_composite_details

        composite_path = tmp_path / "calc-test"
        composite_path.mkdir()

        index_dir = composite_path / ".code-indexer"
        index_dir.mkdir()

        # Create 3 repos with different file counts
        config = {"proxy_mode": True, "discovered_repos": ["repo1", "repo2", "repo3"]}
        (index_dir / "config.json").write_text(json.dumps(config))

        file_counts = [50, 100, 200]
        for idx, repo_name in enumerate(["repo1", "repo2", "repo3"]):
            repo_path = composite_path / repo_name
            repo_path.mkdir()

            repo_index_dir = repo_path / ".code-indexer"
            repo_index_dir.mkdir()

            metadata = {"indexed_files": file_counts[idx]}
            (repo_index_dir / "metadata.json").write_text(json.dumps(metadata))

            (repo_path / "dummy.txt").write_text("x")

        activated_at = datetime.now(timezone.utc)

        repo = ActivatedRepository(
            user_alias="calc-test",
            username="testuser",
            path=composite_path,
            activated_at=activated_at,
            last_accessed=activated_at,
            is_composite=True,
            golden_repo_aliases=["g1", "g2", "g3"],
            discovered_repos=["repo1", "repo2", "repo3"],
        )

        details = _get_composite_details(repo)

        assert details.total_files == 350  # 50 + 100 + 200
        assert len(details.component_repositories) == 3
