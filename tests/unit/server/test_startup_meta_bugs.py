"""
Unit tests for Bug #1 and Bug #2 in Story #526.

Bug #1: Meta-directory not indexed after population
Bug #2: Wrong directory analyzed for descriptions (index_path instead of source)
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from code_indexer.server.lifecycle.startup_meta_populator import StartupMetaPopulator
from code_indexer.global_repos.meta_directory_updater import MetaDirectoryUpdater


class TestBug1MetaDirectoryIndexing:
    """
    Tests for Bug #1: Meta-directory not indexed after population.

    EXPECTED BEHAVIOR: After updater.update() populates the meta-directory
    with description files, the meta-directory should be indexed so users
    can immediately query for repositories.

    CURRENT BUG: updater.update() is called but indexing never happens.
    """

    @pytest.fixture
    def temp_dirs(self, tmp_path):
        """Create temporary directories for testing."""
        meta_dir = tmp_path / "cidx-meta"
        meta_dir.mkdir()
        golden_repos_dir = tmp_path / "golden-repos"
        golden_repos_dir.mkdir()
        return {
            "meta_dir": meta_dir,
            "golden_repos_dir": golden_repos_dir,
        }

    @pytest.fixture
    def mock_registry(self):
        """Create mock global registry with test repos."""
        registry = Mock()
        registry.list_global_repos.return_value = [
            {
                "repo_name": "test-repo-1",
                "repo_url": "https://github.com/org/repo1",
                "index_path": "/path/to/repo1/.code-indexer/index",
            },
            {
                "repo_name": "test-repo-2",
                "repo_url": "https://github.com/org/repo2",
                "index_path": "/path/to/repo2/.code-indexer/index",
            },
        ]
        return registry

    def test_bug1_meta_directory_not_indexed_after_population(self, temp_dirs, mock_registry):
        """
        Test Bug #1: Meta-directory should be indexed after population.

        FAILING TEST: This test will FAIL until Bug #1 is fixed.

        Given: Server starts with empty meta-directory
        When: Startup populator runs and generates description files
        Then: Meta-directory should be indexed (currently missing)
        And: Users should be able to query for repositories immediately
        """
        with patch(
            "code_indexer.server.lifecycle.startup_meta_populator.MetaDirectoryUpdater"
        ) as MockUpdater:
            # Setup mock updater
            mock_updater = Mock()
            mock_updater.has_changes.return_value = True
            MockUpdater.return_value = mock_updater

            # Act: Run startup population
            populator = StartupMetaPopulator(
                meta_dir=str(temp_dirs["meta_dir"]),
                golden_repos_dir=str(temp_dirs["golden_repos_dir"]),
                registry=mock_registry,
            )

            # Mock the indexing function we expect to be called
            with patch(
                "code_indexer.server.lifecycle.startup_meta_populator.index_meta_directory"
            ) as mock_index:
                result = populator.populate_on_startup()

                # Assert: Meta-directory was populated
                assert result["populated"] is True
                mock_updater.update.assert_called_once()

                # CRITICAL ASSERTION: Indexing should be called after update
                # THIS WILL FAIL - Bug #1: No indexing happens after population
                mock_index.assert_called_once()

                # Verify indexing was called with correct meta-directory path
                call_args = mock_index.call_args
                assert call_args is not None
                assert str(temp_dirs["meta_dir"]) in str(call_args)

    def test_bug1_indexing_uses_correct_path(self, temp_dirs, mock_registry):
        """
        Test Bug #1: Indexing should use meta-directory path.

        Given: Meta-directory is populated with description files
        When: Indexing is triggered after population
        Then: Indexing should use the meta-directory path
        """
        with patch(
            "code_indexer.server.lifecycle.startup_meta_populator.MetaDirectoryUpdater"
        ) as MockUpdater:
            # Setup mock updater
            mock_updater = Mock()
            mock_updater.has_changes.return_value = True
            MockUpdater.return_value = mock_updater

            populator = StartupMetaPopulator(
                meta_dir=str(temp_dirs["meta_dir"]),
                golden_repos_dir=str(temp_dirs["golden_repos_dir"]),
                registry=mock_registry,
            )

            with patch(
                "code_indexer.server.lifecycle.startup_meta_populator.index_meta_directory"
            ) as mock_index:
                result = populator.populate_on_startup()

                # Assert: Indexing called with meta_dir Path object
                mock_index.assert_called_once_with(temp_dirs["meta_dir"])

                # Assert: Result message indicates indexing completed
                assert "indexed" in result["message"].lower()


class TestBug2WrongDirectoryAnalyzed:
    """
    Tests for Bug #2: Wrong directory analyzed for descriptions.

    EXPECTED BEHAVIOR: Should analyze source code directory to generate
    meaningful repository descriptions.

    CURRENT BUG: Uses index_path (.code-indexer/index/) instead of source
    directory, resulting in descriptions based on vector index metadata
    instead of actual source code.
    """

    @pytest.fixture
    def temp_repo_structure(self, tmp_path):
        """
        Create realistic repository structure with source code and index.

        Structure:
        /tmp/test-repo/                    <- SOURCE (what we SHOULD analyze)
        ├── README.md
        ├── src/
        │   ├── main.py
        │   └── utils.py
        └── .code-indexer/
            └── index/                     <- INDEX (what we WRONGLY analyze)
                ├── metadata.json
                └── vectors/
        """
        # Create source repository
        repo_root = tmp_path / "test-repo"
        repo_root.mkdir()

        # Add source code files
        (repo_root / "README.md").write_text(
            "# Test Repository\n\nAuthentication library for Python applications"
        )
        src_dir = repo_root / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("def authenticate(user, password): pass")
        (src_dir / "utils.py").write_text("def hash_password(password): pass")

        # Create index directory (what's wrongly being analyzed)
        index_dir = repo_root / ".code-indexer" / "index"
        index_dir.mkdir(parents=True)
        (index_dir / "metadata.json").write_text('{"version": "8.0.0"}')
        vectors_dir = index_dir / "vectors"
        vectors_dir.mkdir()

        return {
            "repo_root": repo_root,
            "index_path": index_dir,
            "source_path": repo_root,
        }

    @pytest.fixture
    def mock_registry_with_index_path(self, temp_repo_structure):
        """Registry containing index_path pointing to .code-indexer/index/."""
        registry = Mock()
        registry.list_global_repos.return_value = [
            {
                "repo_name": "test-repo",
                "repo_url": "https://github.com/org/test-repo",
                "index_path": str(temp_repo_structure["index_path"]),
            }
        ]
        return registry

    def test_bug2_index_path_wrongly_used_for_analysis(self, tmp_path, temp_repo_structure):
        """
        Test Bug #2: Should use source directory, not index_path.

        FAILING TEST: This test will FAIL until Bug #2 is fixed.

        Given: Repository has index_path = /repo/.code-indexer/index/
        When: MetaDirectoryUpdater creates description
        Then: Should analyze /repo/ (source), not /repo/.code-indexer/index/
        """
        from code_indexer.global_repos.global_registry import GlobalRegistry

        golden_repos_dir = tmp_path / "golden-repos"
        golden_repos_dir.mkdir()
        meta_dir = golden_repos_dir / "cidx-meta"
        meta_dir.mkdir()

        registry = GlobalRegistry(str(golden_repos_dir))
        registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-alias",
            repo_url="https://github.com/org/test-repo",
            index_path=str(temp_repo_structure["index_path"]),  # Points to index dir
        )

        # Mock RepoAnalyzer to capture what path it receives
        with patch(
            "code_indexer.global_repos.meta_directory_updater.RepoAnalyzer"
        ) as MockAnalyzer:
            mock_analyzer = Mock()
            mock_info = Mock()
            mock_info.summary = "Test summary"
            mock_info.technologies = []
            mock_info.purpose = "Test purpose"
            mock_info.features = []
            mock_info.use_cases = []
            mock_analyzer.extract_info.return_value = mock_info
            MockAnalyzer.return_value = mock_analyzer

            # Create updater and run update
            updater = MetaDirectoryUpdater(meta_dir=str(meta_dir), registry=registry)
            updater.update()

            # Assert: RepoAnalyzer should be called with SOURCE directory
            # THIS WILL FAIL - Bug #2: Currently called with index_path
            MockAnalyzer.assert_called_once()
            call_args = MockAnalyzer.call_args[0]
            analyzed_path = Path(call_args[0])

            # CRITICAL ASSERTION: Should analyze source root, not index directory
            # Expected: /tmp/test-repo
            # Actual (BUG): /tmp/test-repo/.code-indexer/index
            assert analyzed_path == temp_repo_structure["source_path"], (
                f"Bug #2: Analyzing wrong directory!\n"
                f"Expected: {temp_repo_structure['source_path']}\n"
                f"Actual: {analyzed_path}\n"
                f"Should analyze SOURCE code, not vector index directory"
            )
            assert analyzed_path.name != "index", (
                "Bug #2: Should not analyze 'index' directory"
            )
            assert ".code-indexer" not in str(analyzed_path), (
                "Bug #2: Should not analyze .code-indexer directory"
            )

    def test_bug2_descriptions_contain_source_code_content(self, tmp_path, temp_repo_structure):
        """
        Test Bug #2: Descriptions should be based on source code, not index metadata.

        FAILING TEST: This test will FAIL until Bug #2 is fixed.

        Given: Repository has meaningful source code (authentication library)
        When: Description is generated
        Then: Description should mention authentication (from source code)
        And: Should NOT mention vector index metadata
        """
        from code_indexer.global_repos.global_registry import GlobalRegistry

        golden_repos_dir = tmp_path / "golden-repos"
        golden_repos_dir.mkdir()
        meta_dir = golden_repos_dir / "cidx-meta"
        meta_dir.mkdir()

        registry = GlobalRegistry(str(golden_repos_dir))
        registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-alias",
            repo_url="https://github.com/org/test-repo",
            index_path=str(temp_repo_structure["index_path"]),
        )

        # Run actual update (no mocking - real integration test)
        updater = MetaDirectoryUpdater(meta_dir=str(meta_dir), registry=registry)
        updater.update()

        # Read generated description
        desc_file = meta_dir / "test-repo.md"
        assert desc_file.exists(), "Description file should be created"

        desc_content = desc_file.read_text()

        # CRITICAL ASSERTIONS: Description should reflect SOURCE code, not index
        # THIS WILL FAIL - Bug #2: Description based on index metadata, not source

        # Should contain content from source code
        assert "authentication" in desc_content.lower() or "auth" in desc_content.lower(), (
            "Bug #2: Description should mention authentication (from README.md/source code)"
        )

        # Should NOT contain index-specific metadata
        assert "vector" not in desc_content.lower(), (
            "Bug #2: Description should not mention vectors (index metadata)"
        )
        assert "metadata.json" not in desc_content.lower(), (
            "Bug #2: Description should not mention metadata.json (index file)"
        )

    def test_bug2_path_extraction_from_index_path(self, tmp_path):
        """
        Test Bug #2: Correct path extraction from index_path.

        UNIT TEST for the fix: Given index_path, extract source directory.

        Given: index_path = /repo/.code-indexer/index
        When: Extracting source directory
        Then: Should return /repo (parent.parent of index_path)
        """
        index_path = tmp_path / "test-repo" / ".code-indexer" / "index"
        index_path.mkdir(parents=True)

        # THIS IS THE FIX WE NEED TO IMPLEMENT:
        # repo_path = Path(index_path).parent.parent

        expected_source = tmp_path / "test-repo"
        actual_source = Path(index_path).parent.parent

        assert actual_source == expected_source, (
            f"Path extraction logic:\n"
            f"index_path: {index_path}\n"
            f"Expected source: {expected_source}\n"
            f"Actual source: {actual_source}"
        )
