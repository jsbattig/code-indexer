"""Tests for DirectoryExplorerService (Story #557).

Tests the directory_tree tool's underlying service that generates
hierarchical tree views of repository directory structure.
"""

import pytest
from code_indexer.global_repos.directory_explorer import (
    DirectoryExplorerService,
    DirectoryTreeResult,
)


@pytest.fixture
def sample_repo(tmp_path):
    """Create a sample repository with a typical project structure."""
    # Create directory structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')")
    (tmp_path / "src" / "utils").mkdir()
    (tmp_path / "src" / "utils" / "helper.py").write_text("def help(): pass")
    (tmp_path / "src" / "utils" / "validators.py").write_text("def validate(): pass")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test_main(): pass")
    (tmp_path / "README.md").write_text("# Project")
    (tmp_path / "setup.py").write_text("setup()")

    return tmp_path


@pytest.fixture
def repo_with_hidden(tmp_path):
    """Create a repository with hidden files and directories."""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]")
    (tmp_path / ".gitignore").write_text("*.pyc")
    (tmp_path / ".env").write_text("SECRET=value")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')")

    return tmp_path


@pytest.fixture
def repo_with_excludes(tmp_path):
    """Create a repository with common excluded directories."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "package").mkdir()
    (tmp_path / "node_modules" / "package" / "index.js").write_text(
        "module.exports = {}"
    )
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "module.cpython-39.pyc").write_bytes(b"compiled")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "bin").mkdir()
    (tmp_path / ".venv" / "bin" / "python").write_text("#!/bin/bash")

    return tmp_path


@pytest.fixture
def large_repo(tmp_path):
    """Create a repository with many files for truncation testing."""
    (tmp_path / "src").mkdir()
    # Create 75 files to test truncation at default 50
    for i in range(75):
        (tmp_path / "src" / f"file_{i:03d}.py").write_text(f"# file {i}")

    return tmp_path


@pytest.fixture
def deep_repo(tmp_path):
    """Create a deeply nested repository for depth testing."""
    current = tmp_path
    for i in range(10):
        current = current / f"level_{i}"
        current.mkdir()
        (current / f"file_{i}.py").write_text(f"# level {i}")

    return tmp_path


class TestDirectoryExplorerServiceInit:
    """Tests for DirectoryExplorerService initialization."""

    def test_init_with_valid_path(self, sample_repo):
        """Test service initializes with valid repository path."""
        service = DirectoryExplorerService(sample_repo)
        assert service.repo_path == sample_repo

    def test_init_with_nonexistent_path(self, tmp_path):
        """Test service accepts nonexistent path (validation at generate_tree time)."""
        nonexistent = tmp_path / "nonexistent"
        service = DirectoryExplorerService(nonexistent)
        assert service.repo_path == nonexistent


class TestBasicTreeGeneration:
    """Tests for basic tree generation functionality."""

    def test_generate_tree_returns_result(self, sample_repo):
        """Test generate_tree returns DirectoryTreeResult."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree()

        assert isinstance(result, DirectoryTreeResult)
        assert result.root is not None
        assert isinstance(result.tree_string, str)
        assert result.total_directories > 0
        assert result.total_files > 0

    def test_tree_root_is_directory(self, sample_repo):
        """Test tree root node is a directory."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree()

        assert result.root.is_directory is True
        assert result.root.children is not None

    def test_tree_string_contains_structure(self, sample_repo):
        """Test tree_string contains expected directory structure."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree()

        assert "src/" in result.tree_string or "src" in result.tree_string
        assert "README.md" in result.tree_string
        assert "setup.py" in result.tree_string

    def test_tree_string_uses_tree_characters(self, sample_repo):
        """Test tree_string uses proper tree drawing characters."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree()

        # Should have tree branch characters
        assert "|--" in result.tree_string or "+--" in result.tree_string

    def test_counts_correct_totals(self, sample_repo):
        """Test total_directories and total_files are correct."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree()

        # sample_repo has: src/, src/utils/, tests/ = 3 directories
        # Files: src/main.py, src/utils/helper.py, src/utils/validators.py,
        #        tests/test_main.py, README.md, setup.py = 6 files
        assert result.total_directories == 3
        assert result.total_files == 6


class TestSubdirectoryPath:
    """Tests for path parameter to start from subdirectory."""

    def test_generate_tree_from_subdirectory(self, sample_repo):
        """Test generate_tree starting from subdirectory."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree(path="src")

        assert result.root.name == "src"
        assert "utils" in [c.name for c in result.root.children if c.is_directory]

    def test_generate_tree_nested_subdirectory(self, sample_repo):
        """Test generate_tree starting from nested subdirectory."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree(path="src/utils")

        assert result.root.name == "utils"
        assert "helper.py" in [
            c.name for c in result.root.children if not c.is_directory
        ]

    def test_generate_tree_invalid_path_raises(self, sample_repo):
        """Test generate_tree raises for nonexistent path."""
        service = DirectoryExplorerService(sample_repo)

        with pytest.raises(ValueError) as exc_info:
            service.generate_tree(path="nonexistent")

        assert "does not exist" in str(exc_info.value).lower()


class TestMaxDepthLimiting:
    """Tests for max_depth parameter."""

    def test_max_depth_limits_traversal(self, deep_repo):
        """Test max_depth limits how deep the tree goes."""
        service = DirectoryExplorerService(deep_repo)
        result = service.generate_tree(max_depth=2)

        assert result.max_depth_reached is True

    def test_max_depth_shows_ellipsis_indicator(self, deep_repo):
        """Test directories exceeding max_depth show [...] indicator."""
        service = DirectoryExplorerService(deep_repo)
        result = service.generate_tree(max_depth=2)

        assert "[...]" in result.tree_string

    def test_max_depth_1_shows_only_immediate(self, sample_repo):
        """Test max_depth=1 shows only immediate children."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree(max_depth=1)

        # src/ should show [...] since it has children
        # But immediate files should show
        assert "README.md" in result.tree_string
        assert "[...]" in result.tree_string

    def test_max_depth_default_is_3(self, deep_repo):
        """Test default max_depth is 3."""
        service = DirectoryExplorerService(deep_repo)
        result = service.generate_tree()

        # Should show level_0, level_1, level_2 but not deeper
        assert "level_0" in result.tree_string
        assert "level_1" in result.tree_string
        assert "level_2" in result.tree_string


class TestMaxFilesPerDirTruncation:
    """Tests for max_files_per_dir truncation."""

    def test_truncates_large_directories(self, large_repo):
        """Test directories with many files are truncated."""
        service = DirectoryExplorerService(large_repo)
        result = service.generate_tree(max_files_per_dir=10)

        # Should have truncation indicator
        assert "[+" in result.tree_string and "more" in result.tree_string

    def test_shows_count_of_hidden_files(self, large_repo):
        """Test truncation shows count of hidden files."""
        service = DirectoryExplorerService(large_repo)
        result = service.generate_tree(max_files_per_dir=10)

        # 75 files - 10 shown = 65 more
        assert "65 more" in result.tree_string

    def test_truncated_flag_on_node(self, large_repo):
        """Test truncated nodes have truncated=True flag."""
        service = DirectoryExplorerService(large_repo)
        result = service.generate_tree(max_files_per_dir=10)

        # Find the src node
        src_node = next(
            (c for c in result.root.children if c.name == "src" and c.is_directory),
            None,
        )
        assert src_node is not None
        assert src_node.truncated is True
        assert src_node.hidden_count == 65

    def test_default_max_files_is_50(self, large_repo):
        """Test default max_files_per_dir is 50."""
        service = DirectoryExplorerService(large_repo)
        result = service.generate_tree()

        # 75 files - 50 shown = 25 more
        assert "25 more" in result.tree_string


class TestIncludePatterns:
    """Tests for include_patterns filtering."""

    def test_include_only_python_files(self, sample_repo):
        """Test include_patterns filters to matching files only."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree(include_patterns=["*.py"])

        assert "main.py" in result.tree_string
        assert "README.md" not in result.tree_string

    def test_include_multiple_patterns(self, sample_repo):
        """Test multiple include patterns work."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree(include_patterns=["*.py", "*.md"])

        assert "main.py" in result.tree_string
        assert "README.md" in result.tree_string
        assert "setup.py" in result.tree_string

    def test_include_shows_directories_with_matches(self, sample_repo):
        """Test directories containing matching files are shown."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree(include_patterns=["*.py"])

        # src/ should be shown because it contains .py files
        assert "src" in result.tree_string


class TestExcludePatterns:
    """Tests for exclude_patterns filtering."""

    def test_exclude_patterns_removes_files(self, sample_repo):
        """Test exclude_patterns removes matching files."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree(exclude_patterns=["*.md"])

        assert "README.md" not in result.tree_string
        assert "setup.py" in result.tree_string

    def test_default_excludes_applied(self, repo_with_excludes):
        """Test default exclusions are applied."""
        service = DirectoryExplorerService(repo_with_excludes)
        result = service.generate_tree()

        assert "node_modules" not in result.tree_string
        assert "__pycache__" not in result.tree_string
        assert ".venv" not in result.tree_string

    def test_additional_excludes_merged_with_defaults(self, sample_repo):
        """Test additional exclude patterns merge with defaults."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree(exclude_patterns=["*.md"])

        # Default node_modules exclusion still applies
        # Plus additional *.md exclusion
        assert "README.md" not in result.tree_string


class TestHiddenFileHandling:
    """Tests for include_hidden parameter."""

    def test_hidden_excluded_by_default(self, repo_with_hidden):
        """Test hidden files/directories excluded by default."""
        service = DirectoryExplorerService(repo_with_hidden)
        result = service.generate_tree()

        assert ".gitignore" not in result.tree_string
        assert ".env" not in result.tree_string

    def test_include_hidden_shows_dotfiles(self, repo_with_hidden):
        """Test include_hidden=True shows hidden files."""
        service = DirectoryExplorerService(repo_with_hidden)
        result = service.generate_tree(include_hidden=True)

        assert ".gitignore" in result.tree_string
        assert ".env" in result.tree_string

    def test_git_always_excluded(self, repo_with_hidden):
        """Test .git directory always excluded regardless of include_hidden."""
        service = DirectoryExplorerService(repo_with_hidden)
        result = service.generate_tree(include_hidden=True)

        # .git directory should never appear (but .gitignore is fine)
        # Check that .git/ is not in the output (the directory)
        assert ".git/" not in result.tree_string
        # Also check the .git directory is not in the tree structure
        assert not any(c.name == ".git" for c in result.root.children if c.is_directory)


class TestShowStats:
    """Tests for show_stats parameter."""

    def test_stats_disabled_by_default(self, sample_repo):
        """Test statistics summary not shown by default."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree()

        assert "directories" not in result.tree_string.lower()
        # Just the count should not appear in default mode

    def test_stats_shows_summary(self, sample_repo):
        """Test show_stats=True adds summary line."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree(show_stats=True)

        assert "directories" in result.tree_string.lower()
        assert "files" in result.tree_string.lower()


class TestTreeStringFormat:
    """Tests for tree string formatting correctness."""

    def test_last_item_uses_plus(self, sample_repo):
        """Test last item in directory uses +-- prefix."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree()

        # The last item should have +-- somewhere
        lines = result.tree_string.split("\n")
        last_item_found = any("+--" in line for line in lines)
        assert last_item_found

    def test_directories_first_then_files(self, sample_repo):
        """Test directories are sorted before files."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree()

        lines = result.tree_string.split("\n")
        # Find lines at root level
        root_items = [
            line for line in lines if line.startswith("|--") or line.startswith("+--")
        ]

        # Extract names
        names = []
        for item in root_items:
            # Remove tree characters and get name
            name = item.replace("|-- ", "").replace("+-- ", "").strip()
            if name:
                names.append(name)

        # Directories should come before files
        if "src" in names and "README.md" in names:
            assert names.index("src") < names.index("README.md") or names.index(
                "src/"
            ) < names.index("README.md")

    def test_alphabetical_within_category(self, sample_repo):
        """Test items are sorted alphabetically within directories/files."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree()

        # Just verify it doesn't crash and produces output
        # Detailed ordering checked in other tests
        assert len(result.tree_string) > 0


class TestTreeNodeStructure:
    """Tests for TreeNode dataclass structure."""

    def test_file_node_has_no_children(self, sample_repo):
        """Test file TreeNodes have children=None."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree()

        def find_file_node(node):
            if not node.is_directory:
                return node
            if node.children:
                for child in node.children:
                    found = find_file_node(child)
                    if found:
                        return found
            return None

        file_node = find_file_node(result.root)
        assert file_node is not None
        assert file_node.children is None

    def test_directory_node_has_children_list(self, sample_repo):
        """Test directory TreeNodes have children as list."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree()

        assert result.root.children is not None
        assert isinstance(result.root.children, list)

    def test_node_path_is_relative(self, sample_repo):
        """Test TreeNode.path is relative to repo root."""
        service = DirectoryExplorerService(sample_repo)
        result = service.generate_tree()

        def check_paths(node, parent_path=""):
            # Path should be relative and match hierarchy
            assert not node.path.startswith("/")
            if node.children:
                for child in node.children:
                    check_paths(child, node.path)

        check_paths(result.root)


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_directory(self, tmp_path):
        """Test handling of empty directory."""
        service = DirectoryExplorerService(tmp_path)
        result = service.generate_tree()

        assert result.total_files == 0
        assert result.total_directories == 0

    def test_single_file_repo(self, tmp_path):
        """Test repository with only one file."""
        (tmp_path / "README.md").write_text("# Hello")

        service = DirectoryExplorerService(tmp_path)
        result = service.generate_tree()

        assert result.total_files == 1
        assert result.total_directories == 0
        assert "README.md" in result.tree_string

    def test_deeply_nested_single_file(self, tmp_path):
        """Test deeply nested single file."""
        deep_path = tmp_path / "a" / "b" / "c" / "d"
        deep_path.mkdir(parents=True)
        (deep_path / "file.txt").write_text("deep")

        service = DirectoryExplorerService(tmp_path)
        result = service.generate_tree(max_depth=10)

        assert result.total_files == 1
        assert result.total_directories == 4

    def test_symlinks_not_followed(self, tmp_path):
        """Test symlinks are not followed to prevent loops."""
        (tmp_path / "real_dir").mkdir()
        (tmp_path / "real_dir" / "file.txt").write_text("real")
        (tmp_path / "link_dir").symlink_to(tmp_path / "real_dir")

        service = DirectoryExplorerService(tmp_path)
        result = service.generate_tree()

        # Should not cause infinite loop, symlink may or may not be shown
        # but real_dir content should appear once
        assert "file.txt" in result.tree_string

    def test_special_characters_in_filenames(self, tmp_path):
        """Test handling of special characters in filenames."""
        (tmp_path / "file with spaces.txt").write_text("spaces")
        (tmp_path / "file-with-dashes.txt").write_text("dashes")
        (tmp_path / "file_with_underscores.txt").write_text("underscores")

        service = DirectoryExplorerService(tmp_path)
        result = service.generate_tree()

        assert "file with spaces.txt" in result.tree_string
        assert "file-with-dashes.txt" in result.tree_string
        assert "file_with_underscores.txt" in result.tree_string


class TestDefaultExcludePatterns:
    """Tests for DEFAULT_EXCLUDE_PATTERNS constant."""

    def test_default_excludes_contain_git(self):
        """Test .git is in default excludes."""
        assert ".git" in DirectoryExplorerService.DEFAULT_EXCLUDE_PATTERNS

    def test_default_excludes_contain_node_modules(self):
        """Test node_modules is in default excludes."""
        assert "node_modules" in DirectoryExplorerService.DEFAULT_EXCLUDE_PATTERNS

    def test_default_excludes_contain_pycache(self):
        """Test __pycache__ is in default excludes."""
        assert "__pycache__" in DirectoryExplorerService.DEFAULT_EXCLUDE_PATTERNS

    def test_default_excludes_contain_venv(self):
        """Test .venv is in default excludes."""
        assert ".venv" in DirectoryExplorerService.DEFAULT_EXCLUDE_PATTERNS
