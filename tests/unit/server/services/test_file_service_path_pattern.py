"""
Unit tests for FileService path_pattern filtering with recursive glob patterns.

Tests the fix for the bug where fnmatch.fnmatch() doesn't support ** recursive
glob patterns. These tests verify that Path.match() correctly handles:
- ** recursive directory matching
- Simple * glob patterns (backward compatibility)
- Nested directory structures
"""

import pytest

from src.code_indexer.server.services.file_service import FileListingService
from src.code_indexer.server.models.api_models import FileListQueryParams


class TestPathPatternRecursiveGlob:
    """Test path_pattern filtering with ** recursive glob patterns."""

    @pytest.fixture
    def temp_repo(self, tmp_path):
        """Create a temporary repository with nested directory structure."""
        # Create nested directory structure
        (tmp_path / "src" / "main" / "java" / "com" / "example").mkdir(parents=True)
        (tmp_path / "src" / "test" / "java" / "com" / "example").mkdir(parents=True)
        (tmp_path / "lib" / "external").mkdir(parents=True)
        (tmp_path / "docs").mkdir(parents=True)

        # Create test files with "Synchronizer" in name at various depths
        files = [
            "src/main/java/com/example/ROMajorUnitSynchronizer.java",
            "src/main/java/com/example/DataSynchronizer.java",
            "src/test/java/com/example/TestSynchronizer.java",
            "lib/external/FileSynchronizer.java",
            # Non-matching files
            "src/main/java/com/example/Controller.java",
            "src/main/java/com/example/Service.java",
            # Python files for other pattern tests
            "src/main/script.py",
            "src/test/test_utils.py",
            "lib/helper.py",
            # Root level files
            "README.md",
            "setup.py",
        ]

        for file_path in files:
            full_path = tmp_path / file_path
            full_path.write_text(f"// Content of {file_path}\n")

        return tmp_path

    @pytest.fixture
    def service(self):
        """Create FileListingService instance without database dependency."""
        service = FileListingService.__new__(FileListingService)
        service.activated_repo_manager = None
        service._config_manager = None
        return service

    def test_recursive_glob_pattern_double_star_prefix(self, temp_repo, service):
        """
        Test that **/*Synchronizer* pattern matches files in ANY subdirectory.

        This is the PRIMARY bug case - fnmatch.fnmatch() treats ** as literal
        asterisks, while Path.match() correctly treats ** as "any directories".
        """
        query_params = FileListQueryParams(
            path_pattern="**/*Synchronizer*", page=1, limit=100
        )

        result = service.list_files_by_path(
            repo_path=str(temp_repo), query_params=query_params
        )

        # Should match all 4 Synchronizer files regardless of depth
        file_paths = sorted([f.path for f in result.files])
        expected_files = [
            "lib/external/FileSynchronizer.java",
            "src/main/java/com/example/DataSynchronizer.java",
            "src/main/java/com/example/ROMajorUnitSynchronizer.java",
            "src/test/java/com/example/TestSynchronizer.java",
        ]

        assert file_paths == expected_files, (
            f"Pattern '**/*Synchronizer*' should match all Synchronizer files.\n"
            f"Expected: {expected_files}\n"
            f"Got: {file_paths}"
        )

    def test_recursive_glob_pattern_with_directory_prefix(self, temp_repo, service):
        """Test that src/**/*.py pattern matches Python files under src/ only."""
        query_params = FileListQueryParams(
            path_pattern="src/**/*.py", page=1, limit=100
        )

        result = service.list_files_by_path(
            repo_path=str(temp_repo), query_params=query_params
        )

        file_paths = sorted([f.path for f in result.files])
        expected_files = [
            "src/main/script.py",
            "src/test/test_utils.py",
        ]

        assert file_paths == expected_files, (
            f"Pattern 'src/**/*.py' should match Python files under src/ only.\n"
            f"Expected: {expected_files}\n"
            f"Got: {file_paths}"
        )

    def test_simple_glob_pattern_backward_compatibility(self, temp_repo, service):
        """Test that simple *.py pattern matches files at any depth (backward compatibility)."""
        query_params = FileListQueryParams(path_pattern="*.py", page=1, limit=100)

        result = service.list_files_by_path(
            repo_path=str(temp_repo), query_params=query_params
        )

        file_paths = sorted([f.path for f in result.files])
        expected_files = [
            "lib/helper.py",
            "setup.py",
            "src/main/script.py",
            "src/test/test_utils.py",
        ]

        assert file_paths == expected_files, (
            f"Pattern '*.py' should match .py files at ANY depth (fnmatch/pathspec behavior).\n"
            f"Expected: {expected_files}\n"
            f"Got: {file_paths}"
        )

    def test_pattern_matches_deeply_nested_files(self, temp_repo, service):
        """Test that **/*.java matches files 5+ levels deep."""
        query_params = FileListQueryParams(path_pattern="**/*.java", page=1, limit=100)

        result = service.list_files_by_path(
            repo_path=str(temp_repo), query_params=query_params
        )

        # Should match all .java files at any depth
        file_paths = sorted([f.path for f in result.files])

        # Verify we have files from deep paths (5 levels: src/main/java/com/example/)
        assert any(
            "src/main/java/com/example/" in p for p in file_paths
        ), "Should match deeply nested .java files (5+ levels)"

        # Verify we got all .java files
        assert (
            len(file_paths) == 6
        ), f"Should match 6 .java files, got {len(file_paths)}"

    def test_pattern_with_middle_directory_wildcard(self, temp_repo, service):
        """Test pattern src/**/example/*.java matches with middle wildcards."""
        query_params = FileListQueryParams(
            path_pattern="src/**/example/*.java", page=1, limit=100
        )

        result = service.list_files_by_path(
            repo_path=str(temp_repo), query_params=query_params
        )

        file_paths = sorted([f.path for f in result.files])

        # Should match all files under src/.../example/ directories
        expected_count = 5  # All .java files under src/*/java/com/example/
        assert len(file_paths) == expected_count, (
            f"Pattern 'src/**/example/*.java' should match {expected_count} files, "
            f"got {len(file_paths)}: {file_paths}"
        )

    def test_no_pattern_returns_all_files(self, temp_repo, service):
        """Test that omitting path_pattern returns all files."""
        query_params = FileListQueryParams(page=1, limit=100)

        result = service.list_files_by_path(
            repo_path=str(temp_repo), query_params=query_params
        )

        # Should return all 11 files created in fixture
        assert len(result.files) == 11, (
            f"Should return all 11 files when no pattern specified, "
            f"got {len(result.files)}"
        )

    def test_pattern_with_no_matches(self, temp_repo, service):
        """Test that non-matching pattern returns empty results."""
        query_params = FileListQueryParams(
            path_pattern="**/*.cpp", page=1, limit=100  # No .cpp files exist
        )

        result = service.list_files_by_path(
            repo_path=str(temp_repo), query_params=query_params
        )

        assert (
            len(result.files) == 0
        ), "Pattern with no matches should return empty list"

    def test_case_sensitive_pattern_matching(self, temp_repo, service):
        """Test that pattern matching is case-sensitive."""
        query_params = FileListQueryParams(
            path_pattern="**/*synchronizer*", page=1, limit=100  # lowercase 's'
        )

        result = service.list_files_by_path(
            repo_path=str(temp_repo), query_params=query_params
        )

        # Should not match files with uppercase 'Synchronizer'
        assert len(result.files) == 0, (
            "Case-sensitive pattern '**/*synchronizer*' should not match "
            "'*Synchronizer*' files"
        )


class TestPathPatternEdgeCases:
    """Test edge cases for path pattern filtering."""

    @pytest.fixture
    def service(self):
        """Create FileListingService instance without database dependency."""
        service = FileListingService.__new__(FileListingService)
        service.activated_repo_manager = None
        service._config_manager = None
        return service

    def test_pattern_with_special_characters(self, tmp_path, service):
        """Test patterns handle special characters correctly."""
        # Create files with special characters
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "test-file.py").write_text("content")
        (tmp_path / "src" / "test_file.py").write_text("content")

        query_params = FileListQueryParams(
            path_pattern="src/*test*file*.py", page=1, limit=100
        )

        result = service.list_files_by_path(
            repo_path=str(tmp_path), query_params=query_params
        )

        # Should match both files
        assert (
            len(result.files) == 2
        ), f"Should match both test files, got {len(result.files)}"

    def test_empty_pattern_same_as_no_pattern(self, tmp_path, service):
        """Test that empty pattern is treated same as no pattern."""
        (tmp_path / "file.txt").write_text("content")

        # Query with no pattern
        no_pattern_result = service.list_files_by_path(
            repo_path=str(tmp_path), query_params=FileListQueryParams(page=1, limit=100)
        )

        # Query with empty pattern
        empty_pattern_result = service.list_files_by_path(
            repo_path=str(tmp_path),
            query_params=FileListQueryParams(path_pattern="", page=1, limit=100),
        )

        # Should return same results
        assert len(no_pattern_result.files) == len(
            empty_pattern_result.files
        ), "Empty pattern should behave same as no pattern"
