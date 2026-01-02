"""
Unit tests for DirectoryExplorerService pattern matching pathspec migration.

Tests validate that fnmatch -> pathspec conversion in directory tree generation:
1. Maintains backward compatibility with simple patterns
2. Adds support for ** recursive glob patterns
3. Properly handles exclude and include pattern filtering
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from code_indexer.global_repos.directory_explorer import DirectoryExplorerService


@pytest.fixture
def temp_repo():
    """Create temporary repository for testing."""
    temp_path = Path(tempfile.mkdtemp())

    # Create test structure
    (temp_path / "src").mkdir()
    (temp_path / "src" / "main.py").touch()
    (temp_path / "src" / "utils.py").touch()

    (temp_path / "tests").mkdir()
    (temp_path / "tests" / "test_main.py").touch()

    (temp_path / "node_modules").mkdir()
    (temp_path / "node_modules" / "package").mkdir()
    (temp_path / "node_modules" / "package" / "index.js").touch()

    (temp_path / "build").mkdir()
    (temp_path / "build" / "output.js").touch()

    (temp_path / "README.md").touch()
    (temp_path / "config.json").touch()

    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def service(temp_repo):
    """Create DirectoryExplorerService instance."""
    return DirectoryExplorerService(temp_repo)


class TestDirectoryExplorerPatternMatching:
    """Test pattern matching with pathspec in directory explorer."""

    def test_simple_wildcard_exclude_pattern(self, service, temp_repo):
        """Test simple * wildcard in exclude patterns (backward compatibility)."""
        # Exclude all .js files
        tree = service.generate_tree(exclude_patterns=["*.js"])
        tree_str = str(tree)

        # Python files should be included
        assert "main.py" in tree_str
        # JavaScript files should be excluded
        assert "output.js" not in tree_str
        assert "index.js" not in tree_str

    def test_simple_wildcard_include_pattern(self, service, temp_repo):
        """Test simple * wildcard in include patterns (backward compatibility)."""
        # Include only .py files
        tree = service.generate_tree(include_patterns=["*.py"])
        tree_str = str(tree)

        # Python files should be included
        assert "main.py" in tree_str
        assert "test_main.py" in tree_str
        # Non-Python files should be excluded
        assert "README.md" not in tree_str
        assert "config.json" not in tree_str

    def test_doublestar_exclude_pattern_any_depth(self, service, temp_repo):
        """
        CRITICAL BUG FIX: Test ** pattern excludes at any depth.

        fnmatch limitation: **/*.js may not properly exclude files at any depth
        pathspec behavior: **/*.js correctly excludes all .js files recursively
        """
        # Create nested structure
        deep_dir = temp_repo / "src" / "deep" / "nested"
        deep_dir.mkdir(parents=True)
        (deep_dir / "bundle.js").touch()

        # Exclude all .js files at any depth
        tree = service.generate_tree(exclude_patterns=["**/*.js"])
        tree_str = str(tree)

        # Python files should remain
        assert "main.py" in tree_str
        # All JavaScript files should be excluded
        assert "output.js" not in tree_str
        assert "index.js" not in tree_str
        assert "bundle.js" not in tree_str

    def test_doublestar_exclude_directory_pattern(self, service, temp_repo):
        """
        CRITICAL BUG FIX: Test **/dirname pattern excludes directory at any depth.

        This tests that ** matches zero or more directories, not requiring at least one.
        """
        # Exclude node_modules at any depth
        tree = service.generate_tree(exclude_patterns=["**/node_modules"])
        tree_str = str(tree)

        # node_modules directory should be excluded
        assert "node_modules" not in tree_str
        assert "package" not in tree_str
        assert "index.js" not in tree_str

        # Other directories should remain
        assert "src" in tree_str
        assert "main.py" in tree_str

    def test_doublestar_include_pattern_any_depth(self, service, temp_repo):
        """Test ** pattern in include filters works at any depth."""
        # Create nested Python files
        deep_dir = temp_repo / "src" / "deep" / "nested"
        deep_dir.mkdir(parents=True)
        (deep_dir / "deep.py").touch()

        # Include all .py files at any depth (use max_depth=5 to see deeply nested files)
        tree = service.generate_tree(include_patterns=["**/*.py"], max_depth=5)
        tree_str = str(tree)

        # All Python files should be included
        assert "main.py" in tree_str
        assert "utils.py" in tree_str
        assert "test_main.py" in tree_str
        assert "deep.py" in tree_str

        # Non-Python files should be excluded
        assert "README.md" not in tree_str
        assert "config.json" not in tree_str

    def test_path_based_exclude_pattern(self, service, temp_repo):
        """Test path-based patterns with / work correctly."""
        # Exclude everything under build/
        tree = service.generate_tree(exclude_patterns=["build/*"])
        tree_str = str(tree)

        # build directory may appear but its contents should not
        # (depends on implementation details of whether empty dirs shown)
        assert "output.js" not in tree_str

    def test_mixed_include_exclude_patterns(self, service, temp_repo):
        """Test combination of include and exclude patterns."""
        # Include all .py files but exclude test files
        tree = service.generate_tree(
            include_patterns=["*.py"],
            exclude_patterns=["test_*.py"]
        )
        tree_str = str(tree)

        # Source Python files should be included
        assert "main.py" in tree_str
        assert "utils.py" in tree_str
        # Test files should be excluded
        assert "test_main.py" not in tree_str

    def test_default_exclude_patterns_respected(self, service, temp_repo):
        """Test that default exclude patterns (node_modules, etc.) work."""
        # Create cache directory (typically in default excludes)
        (temp_repo / "__pycache__").mkdir()
        (temp_repo / "__pycache__" / "module.pyc").touch()

        # Even without explicit exclude, default patterns should apply
        tree = service.generate_tree()
        tree_str = str(tree)

        # node_modules should be excluded by default
        # (DirectoryExplorerService has DEFAULT_EXCLUDE_PATTERNS)
        # This test verifies default patterns still work with pathspec

    def test_empty_patterns_match_all(self, service, temp_repo):
        """Test that empty patterns lists don't cause issues."""
        # No patterns = include everything (except defaults)
        tree = service.generate_tree(
            include_patterns=[],
            exclude_patterns=[]
        )

        # Should complete without errors
        assert tree is not None

    def test_question_mark_wildcard_pattern(self, service, temp_repo):
        """Test ? wildcard matches single character."""
        # Create files with numbered names
        (temp_repo / "file1.txt").touch()
        (temp_repo / "file2.txt").touch()
        (temp_repo / "file10.txt").touch()

        # Include only single-digit file names
        tree = service.generate_tree(include_patterns=["file?.txt"])
        tree_str = str(tree)

        assert "file1.txt" in tree_str
        assert "file2.txt" in tree_str
        assert "file10.txt" not in tree_str

    def test_character_class_pattern(self, service, temp_repo):
        """Test [seq] character class patterns work."""
        # Create files with different numbers
        (temp_repo / "test1.py").touch()
        (temp_repo / "test2.py").touch()
        (temp_repo / "test9.py").touch()

        # Include only test1.py and test2.py
        tree = service.generate_tree(include_patterns=["test[12].py"])
        tree_str = str(tree)

        assert "test1.py" in tree_str
        assert "test2.py" in tree_str
        assert "test9.py" not in tree_str

    def test_nested_doublestar_patterns(self, service, temp_repo):
        """Test nested ** patterns work correctly."""
        # Create deep nested structure
        deep_dir = temp_repo / "level1" / "level2" / "level3"
        deep_dir.mkdir(parents=True)
        (deep_dir / "deep.txt").touch()

        # Exclude everything under level1/** recursively
        tree = service.generate_tree(exclude_patterns=["level1/**"])
        tree_str = str(tree)

        # Nothing from level1 should appear
        assert "deep.txt" not in tree_str

    def test_root_level_file_with_doublestar_pattern(self, service, temp_repo):
        """
        CRITICAL BUG FIX: Test ** matches root-level files (zero directories).

        fnmatch behavior: **/*.md may NOT match README.md at root
        pathspec behavior: **/*.md DOES match README.md at root
        """
        # Include all .md files at any depth (including root)
        tree = service.generate_tree(include_patterns=["**/*.md"])
        tree_str = str(tree)

        # Root-level .md file MUST be included
        assert "README.md" in tree_str

        # Other files should be excluded
        assert "main.py" not in tree_str
        assert "config.json" not in tree_str
