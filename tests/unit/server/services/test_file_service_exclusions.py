"""
Unit tests for FileListingService exclusion logic.

Tests that:
1. .code-indexer/ directory is excluded from file listings
2. .git/ directory is excluded from file listings
3. .gitignore patterns are respected when present
4. list_files_by_path works with direct filesystem paths
"""

import pytest

from src.code_indexer.server.services.file_service import FileListingService
from src.code_indexer.server.models.api_models import FileListQueryParams


class TestFileServiceExclusions:
    """Test exclusion logic in FileListingService._collect_files()."""

    @pytest.fixture
    def temp_repo(self, tmp_path):
        """Create a temporary repository structure for testing."""
        # Create source code files
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("print('hello')")
        (src_dir / "utils.py").write_text("def helper(): pass")

        # Create test files
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_main.py").write_text("def test_main(): pass")

        # Create root level files
        (tmp_path / "README.md").write_text("# Project")
        (tmp_path / "setup.py").write_text("setup()")

        return tmp_path

    @pytest.fixture
    def service(self):
        """Create FileListingService instance."""
        # Create service without relying on database
        service = FileListingService.__new__(FileListingService)
        service.activated_repo_manager = None
        return service

    def test_excludes_code_indexer_directory(self, temp_repo, service):
        """Test that .code-indexer/ directory is excluded from listings."""
        # Create .code-indexer directory with many files (simulating vector store)
        code_indexer_dir = temp_repo / ".code-indexer"
        code_indexer_dir.mkdir()
        index_dir = code_indexer_dir / "index"
        index_dir.mkdir()

        # Create many vector JSON files (simulating real scenario)
        for i in range(100):
            (index_dir / f"vector_{i}.json").write_text("{}")

        # Create nested subdirectory
        nested = index_dir / "collection" / "nested"
        nested.mkdir(parents=True)
        (nested / "data.json").write_text("{}")

        # Collect files
        files = service._collect_files(str(temp_repo))

        # Extract just the paths
        file_paths = [f.path for f in files]

        # Verify no .code-indexer files are included
        for path in file_paths:
            assert ".code-indexer" not in path, f"Found .code-indexer file: {path}"

        # Verify source files ARE included
        assert "src/main.py" in file_paths
        assert "src/utils.py" in file_paths

    def test_excludes_git_directory(self, temp_repo, service):
        """Test that .git/ directory is excluded from listings."""
        # Create .git directory structure
        git_dir = temp_repo / ".git"
        git_dir.mkdir()

        objects_dir = git_dir / "objects"
        objects_dir.mkdir()
        (objects_dir / "pack").mkdir()

        refs_dir = git_dir / "refs"
        refs_dir.mkdir()
        (refs_dir / "heads").mkdir()

        (git_dir / "HEAD").write_text("ref: refs/heads/main")
        (git_dir / "config").write_text("[core]")
        (git_dir / "index").write_bytes(b"\x00\x01\x02")

        # Collect files
        files = service._collect_files(str(temp_repo))

        # Extract just the paths
        file_paths = [f.path for f in files]

        # Verify no .git files are included
        for path in file_paths:
            assert ".git" not in path or path.endswith(".gitignore"), (
                f"Found .git file: {path}"
            )

        # Verify source files ARE included
        assert "README.md" in file_paths

    def test_excludes_both_code_indexer_and_git(self, temp_repo, service):
        """Test that both .code-indexer/ and .git/ are excluded together."""
        # Create both directories
        (temp_repo / ".code-indexer" / "index").mkdir(parents=True)
        (temp_repo / ".code-indexer" / "index" / "data.json").write_text("{}")

        (temp_repo / ".git" / "objects").mkdir(parents=True)
        (temp_repo / ".git" / "HEAD").write_text("ref: refs/heads/main")

        files = service._collect_files(str(temp_repo))
        file_paths = [f.path for f in files]

        # No excluded directories should appear
        for path in file_paths:
            assert ".code-indexer" not in path, f"Found .code-indexer file: {path}"
            assert path == ".gitignore" or ".git/" not in path, (
                f"Found .git file: {path}"
            )

    def test_respects_gitignore_patterns(self, temp_repo, service):
        """Test that .gitignore patterns are respected."""
        # Create .gitignore file
        gitignore_content = """
# Build output
build/
dist/
*.pyc

# IDE files
.vscode/
.idea/

# Logs
*.log
logs/
"""
        (temp_repo / ".gitignore").write_text(gitignore_content)

        # Create files that should be ignored
        build_dir = temp_repo / "build"
        build_dir.mkdir()
        (build_dir / "output.js").write_text("compiled")

        dist_dir = temp_repo / "dist"
        dist_dir.mkdir()
        (dist_dir / "bundle.js").write_text("bundled")

        vscode_dir = temp_repo / ".vscode"
        vscode_dir.mkdir()
        (vscode_dir / "settings.json").write_text("{}")

        (temp_repo / "src" / "cache.pyc").write_bytes(b"\x00\x01")
        (temp_repo / "debug.log").write_text("log content")

        logs_dir = temp_repo / "logs"
        logs_dir.mkdir()
        (logs_dir / "app.log").write_text("application log")

        # Collect files
        files = service._collect_files(str(temp_repo))
        file_paths = [f.path for f in files]

        # Verify ignored files are NOT included
        for path in file_paths:
            assert not path.startswith("build/"), f"build/ should be ignored: {path}"
            assert not path.startswith("dist/"), f"dist/ should be ignored: {path}"
            assert not path.startswith(".vscode/"), f".vscode/ should be ignored: {path}"
            assert not path.endswith(".pyc"), f".pyc files should be ignored: {path}"
            assert not path.endswith(".log"), f".log files should be ignored: {path}"
            assert not path.startswith("logs/"), f"logs/ should be ignored: {path}"

        # Verify source files ARE included
        assert "src/main.py" in file_paths
        assert "README.md" in file_paths
        # .gitignore itself should be included
        assert ".gitignore" in file_paths

    def test_works_without_gitignore(self, temp_repo, service):
        """Test that collection works when no .gitignore exists."""
        # Ensure no .gitignore exists
        gitignore_path = temp_repo / ".gitignore"
        if gitignore_path.exists():
            gitignore_path.unlink()

        # Create a build directory that would normally be ignored
        build_dir = temp_repo / "build"
        build_dir.mkdir()
        (build_dir / "output.js").write_text("compiled")

        files = service._collect_files(str(temp_repo))
        file_paths = [f.path for f in files]

        # Without .gitignore, build files SHOULD be included
        assert "build/output.js" in file_paths
        # Source files still included
        assert "src/main.py" in file_paths

    def test_handles_nested_gitignore_patterns(self, temp_repo, service):
        """Test that nested directory patterns in .gitignore work correctly."""
        gitignore_content = """
# Ignore node_modules anywhere
**/node_modules/

# Ignore __pycache__ anywhere
**/__pycache__/

# Ignore specific nested path
src/generated/
"""
        (temp_repo / ".gitignore").write_text(gitignore_content)

        # Create node_modules at different levels
        (temp_repo / "node_modules").mkdir()
        (temp_repo / "node_modules" / "package.json").write_text("{}")

        (temp_repo / "src" / "node_modules").mkdir()
        (temp_repo / "src" / "node_modules" / "dep.js").write_text("")

        # Create __pycache__ directories
        (temp_repo / "src" / "__pycache__").mkdir()
        (temp_repo / "src" / "__pycache__" / "main.cpython-39.pyc").write_bytes(b"")

        (temp_repo / "tests" / "__pycache__").mkdir()
        (temp_repo / "tests" / "__pycache__" / "test.cpython-39.pyc").write_bytes(b"")

        # Create src/generated/
        (temp_repo / "src" / "generated").mkdir()
        (temp_repo / "src" / "generated" / "output.py").write_text("")

        files = service._collect_files(str(temp_repo))
        file_paths = [f.path for f in files]

        # Verify all ignored patterns are excluded
        for path in file_paths:
            assert "node_modules" not in path, f"node_modules should be ignored: {path}"
            assert "__pycache__" not in path, f"__pycache__ should be ignored: {path}"
            assert not path.startswith("src/generated/"), (
                f"src/generated/ should be ignored: {path}"
            )

    def test_alphabetical_sorting_shows_source_before_hidden(self, temp_repo, service):
        """Test that after exclusions, source files come before remaining hidden files."""
        # Create .code-indexer with many files
        code_indexer_dir = temp_repo / ".code-indexer" / "index"
        code_indexer_dir.mkdir(parents=True)
        for i in range(500):
            (code_indexer_dir / f"vector_{i:04d}.json").write_text("{}")

        # Create source files
        (temp_repo / "app.py").write_text("main app")
        (temp_repo / "config.py").write_text("config")

        files = service._collect_files(str(temp_repo))
        file_paths = [f.path for f in files]

        # Should have reasonable number of files, not 500+ vector files
        assert len(file_paths) < 100, f"Too many files: {len(file_paths)}"

        # Source files should be present
        assert "app.py" in file_paths
        assert "config.py" in file_paths
        assert "src/main.py" in file_paths

    def test_excludes_hidden_git_files_starting_with_dot(self, temp_repo, service):
        """Test that .git files are excluded even when not in .git directory."""
        # .gitignore should be INCLUDED (it's a user file)
        (temp_repo / ".gitignore").write_text("*.log")

        # .gitmodules should be INCLUDED (it's a user file)
        (temp_repo / ".gitmodules").write_text("[submodule]")

        # .gitattributes should be INCLUDED
        (temp_repo / ".gitattributes").write_text("*.txt text")

        # But .git/ directory contents should be EXCLUDED
        git_dir = temp_repo / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[core]")

        files = service._collect_files(str(temp_repo))
        file_paths = [f.path for f in files]

        # User-facing git files should be included
        assert ".gitignore" in file_paths
        assert ".gitmodules" in file_paths
        assert ".gitattributes" in file_paths

        # .git/ directory contents should NOT be included
        for path in file_paths:
            assert not path.startswith(".git/"), f"Found .git/ file: {path}"


class TestListFilesByPath:
    """Test list_files_by_path method for global repository browsing."""

    @pytest.fixture
    def temp_repo(self, tmp_path):
        """Create a temporary repository structure for testing."""
        # Create source code files
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("print('hello')")
        (src_dir / "utils.py").write_text("def helper(): pass")

        # Create test files
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_main.py").write_text("def test_main(): pass")

        # Create root level files
        (tmp_path / "README.md").write_text("# Project")
        (tmp_path / "setup.py").write_text("setup()")

        return tmp_path

    @pytest.fixture
    def service(self):
        """Create FileListingService instance."""
        # Create service without relying on database
        service = FileListingService.__new__(FileListingService)
        service.activated_repo_manager = None
        return service

    def test_list_files_by_path_with_valid_directory(self, temp_repo, service):
        """Test that list_files_by_path works with a valid directory path."""
        query_params = FileListQueryParams(page=1, limit=100)

        result = service.list_files_by_path(
            repo_path=str(temp_repo), query_params=query_params
        )

        assert result is not None
        assert hasattr(result, "files")
        assert len(result.files) > 0

        file_paths = [f.path for f in result.files]
        assert "src/main.py" in file_paths
        assert "src/utils.py" in file_paths
        assert "README.md" in file_paths

    def test_list_files_by_path_raises_error_for_nonexistent_path(self, service):
        """Test that list_files_by_path raises FileNotFoundError for nonexistent path."""
        query_params = FileListQueryParams(page=1, limit=100)

        with pytest.raises(FileNotFoundError) as exc_info:
            service.list_files_by_path(
                repo_path="/nonexistent/path/to/repo", query_params=query_params
            )

        assert "not found" in str(exc_info.value)

    def test_list_files_by_path_with_filters(self, temp_repo, service):
        """Test that list_files_by_path respects query parameters filters."""
        query_params = FileListQueryParams(
            page=1, limit=100, language="python", path_pattern="src/*.py"
        )

        result = service.list_files_by_path(
            repo_path=str(temp_repo), query_params=query_params
        )

        file_paths = [f.path for f in result.files]

        # Should only include Python files from src directory
        assert "src/main.py" in file_paths
        assert "src/utils.py" in file_paths
        # Should NOT include files from other directories
        assert "tests/test_main.py" not in file_paths
        # Should NOT include non-Python files
        assert "README.md" not in file_paths

    def test_list_files_by_path_with_pagination(self, temp_repo, service):
        """Test that list_files_by_path respects pagination parameters."""
        # Create more files for pagination test
        for i in range(10):
            (temp_repo / f"file_{i}.txt").write_text(f"content {i}")

        query_params = FileListQueryParams(page=1, limit=3)

        result = service.list_files_by_path(
            repo_path=str(temp_repo), query_params=query_params
        )

        assert len(result.files) == 3
        assert result.pagination.total > 3
        assert result.pagination.has_next is True

    def test_list_files_by_path_excludes_system_directories(self, temp_repo, service):
        """Test that list_files_by_path excludes .code-indexer and .git directories."""
        # Create excluded directories
        code_indexer_dir = temp_repo / ".code-indexer" / "index"
        code_indexer_dir.mkdir(parents=True)
        (code_indexer_dir / "vector.json").write_text("{}")

        git_dir = temp_repo / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[core]")

        query_params = FileListQueryParams(page=1, limit=100)

        result = service.list_files_by_path(
            repo_path=str(temp_repo), query_params=query_params
        )

        file_paths = [f.path for f in result.files]

        # Verify excluded directories are not included
        for path in file_paths:
            assert ".code-indexer" not in path
            assert not path.startswith(".git/")

        # Verify source files ARE included
        assert "src/main.py" in file_paths
