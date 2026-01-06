"""
Unit tests for ClaudeIntegrationService._matches_gitignore_pattern() pathspec migration.

Tests validate that fnmatch -> pathspec conversion:
1. Maintains backward compatibility with simple patterns
2. Adds support for ** recursive glob patterns
3. Properly handles gitignore-style directory patterns (ending with /)
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from code_indexer.services.claude_integration import ClaudeIntegrationService


@pytest.fixture
def temp_dir():
    """Create temporary directory for testing."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def service(temp_dir):
    """Create ClaudeIntegrationService instance."""
    return ClaudeIntegrationService(temp_dir, "test_project")


class TestGitignorePatternMatching:
    """Test gitignore pattern matching with pathspec."""

    def test_simple_wildcard_pattern(self, service, temp_dir):
        """Test simple * wildcard pattern works (backward compatibility)."""
        file_path = temp_dir / "test.py"
        file_path.touch()

        assert service._matches_gitignore_pattern(file_path, "test.py", "*.py")
        assert not service._matches_gitignore_pattern(file_path, "test.py", "*.js")

    def test_simple_filename_pattern(self, service, temp_dir):
        """Test exact filename matching works (backward compatibility)."""
        file_path = temp_dir / "README.md"
        file_path.touch()

        assert service._matches_gitignore_pattern(file_path, "README.md", "README.md")
        assert not service._matches_gitignore_pattern(
            file_path, "README.md", "LICENSE.md"
        )

    def test_directory_pattern_with_slash(self, service, temp_dir):
        """Test directory pattern ending with / works."""
        dir_path = temp_dir / "node_modules"
        dir_path.mkdir()

        assert service._matches_gitignore_pattern(
            dir_path, "node_modules", "node_modules/"
        )
        assert not service._matches_gitignore_pattern(dir_path, "node_modules", "dist/")

    def test_directory_pattern_without_slash(self, service, temp_dir):
        """Test directory pattern without trailing slash works."""
        dir_path = temp_dir / "build"
        dir_path.mkdir()

        assert service._matches_gitignore_pattern(dir_path, "build", "build")
        assert not service._matches_gitignore_pattern(dir_path, "build", "dist")

    def test_recursive_doublestar_pattern_files(self, service, temp_dir):
        """Test ** pattern matches files at any depth (main bug fix)."""
        # Create nested structure
        nested_dir = temp_dir / "src" / "deep" / "nested"
        nested_dir.mkdir(parents=True)
        file_path = nested_dir / "test.py"
        file_path.touch()

        rel_path = "src/deep/nested/test.py"

        # ** should match at any depth
        assert service._matches_gitignore_pattern(file_path, rel_path, "**/*.py")
        assert service._matches_gitignore_pattern(file_path, rel_path, "**/test.py")
        assert service._matches_gitignore_pattern(file_path, rel_path, "src/**/*.py")
        assert not service._matches_gitignore_pattern(file_path, rel_path, "**/*.js")

    def test_recursive_doublestar_pattern_dirs(self, service, temp_dir):
        """Test ** pattern matches directories at any depth."""
        nested_dir = temp_dir / "src" / "node_modules" / "package"
        nested_dir.mkdir(parents=True)

        rel_path = "src/node_modules/package"

        assert service._matches_gitignore_pattern(
            nested_dir, rel_path, "**/node_modules/**"
        )
        assert service._matches_gitignore_pattern(
            nested_dir, rel_path, "src/**/package"
        )

    def test_path_based_pattern_with_slash(self, service, temp_dir):
        """Test path-based patterns containing / work correctly."""
        nested_dir = temp_dir / "tests" / "unit"
        nested_dir.mkdir(parents=True)
        file_path = nested_dir / "test_foo.py"
        file_path.touch()

        rel_path = "tests/unit/test_foo.py"

        assert service._matches_gitignore_pattern(
            file_path, rel_path, "tests/unit/*.py"
        )
        assert service._matches_gitignore_pattern(file_path, rel_path, "tests/**/*.py")
        assert not service._matches_gitignore_pattern(
            file_path, rel_path, "src/**/*.py"
        )

    def test_negation_pattern_not_matched(self, service, temp_dir):
        """Test that patterns starting with ! are handled (gitignore negation)."""
        file_path = temp_dir / "important.log"
        file_path.touch()

        # Negation patterns shouldn't match (they're handled separately in gitignore logic)
        # This test just ensures we don't crash on them
        result = service._matches_gitignore_pattern(
            file_path, "important.log", "!important.log"
        )
        # pathspec will handle negation patterns, result may vary
        assert isinstance(result, bool)

    def test_question_mark_wildcard(self, service, temp_dir):
        """Test ? wildcard matches single character."""
        file_path = temp_dir / "test1.py"
        file_path.touch()

        assert service._matches_gitignore_pattern(file_path, "test1.py", "test?.py")
        assert not service._matches_gitignore_pattern(
            file_path, "test1.py", "test??.py"
        )

    def test_character_class_pattern(self, service, temp_dir):
        """Test [seq] character class patterns work."""
        file_path = temp_dir / "test1.py"
        file_path.touch()

        assert service._matches_gitignore_pattern(file_path, "test1.py", "test[123].py")
        assert not service._matches_gitignore_pattern(
            file_path, "test1.py", "test[456].py"
        )

    def test_deep_nesting_doublestar(self, service, temp_dir):
        """Test ** works with very deep nesting (stress test)."""
        # Create 10-level deep structure
        deep_path = temp_dir
        for i in range(10):
            deep_path = deep_path / f"level{i}"
        deep_path.mkdir(parents=True)
        file_path = deep_path / "deep.txt"
        file_path.touch()

        rel_path = "/".join([f"level{i}" for i in range(10)] + ["deep.txt"])

        # ** should match at any depth
        assert service._matches_gitignore_pattern(file_path, rel_path, "**/*.txt")
        assert service._matches_gitignore_pattern(file_path, rel_path, "**/deep.txt")

    def test_mixed_wildcards_and_doublestar(self, service, temp_dir):
        """Test combination of * and ** in same pattern."""
        nested_dir = temp_dir / "src" / "components" / "ui"
        nested_dir.mkdir(parents=True)
        file_path = nested_dir / "Button.tsx"
        file_path.touch()

        rel_path = "src/components/ui/Button.tsx"

        assert service._matches_gitignore_pattern(
            file_path, rel_path, "src/**/ui/*.tsx"
        )
        assert service._matches_gitignore_pattern(
            file_path, rel_path, "**/components/**/*.tsx"
        )
        assert not service._matches_gitignore_pattern(
            file_path, rel_path, "lib/**/ui/*.tsx"
        )

    def test_root_level_pattern(self, service, temp_dir):
        """Test patterns matching files at root level."""
        file_path = temp_dir / ".gitignore"
        file_path.touch()

        assert service._matches_gitignore_pattern(file_path, ".gitignore", ".gitignore")
        assert service._matches_gitignore_pattern(file_path, ".gitignore", ".*")

    def test_relative_path_matching(self, service, temp_dir):
        """Test pattern matches relative path correctly."""
        nested_dir = temp_dir / "docs" / "api"
        nested_dir.mkdir(parents=True)
        file_path = nested_dir / "reference.md"
        file_path.touch()

        # Pattern should match against relative path
        rel_path = "docs/api/reference.md"
        assert service._matches_gitignore_pattern(file_path, rel_path, "docs/**/*.md")

        # Also test matching just filename
        assert service._matches_gitignore_pattern(file_path, rel_path, "*.md")

    def test_empty_pattern_no_match(self, service, temp_dir):
        """Test empty pattern returns False."""
        file_path = temp_dir / "test.py"
        file_path.touch()

        assert not service._matches_gitignore_pattern(file_path, "test.py", "")

    def test_directory_only_pattern_on_file(self, service, temp_dir):
        """Test directory pattern (ending with /) doesn't match files."""
        file_path = temp_dir / "build"
        file_path.touch()

        # Pattern with / should only match directories
        assert not service._matches_gitignore_pattern(file_path, "build", "build/")

    def test_doublestar_matches_zero_directories_root_file(self, service, temp_dir):
        """
        CRITICAL BUG FIX: Test ** matches files at root level (zero directories).

        fnmatch behavior: **/*.py does NOT match test.py (requires at least one directory)
        pathspec behavior: **/*.py DOES match test.py (zero or more directories)

        This is the key difference and why we need pathspec for gitignore semantics.
        """
        file_path = temp_dir / "test.py"
        file_path.touch()

        # This MUST match - ** means "zero or more directories"
        assert service._matches_gitignore_pattern(file_path, "test.py", "**/*.py")
        assert service._matches_gitignore_pattern(file_path, "test.py", "**/test.py")

    def test_doublestar_matches_zero_subdirectories_immediate_child(
        self, service, temp_dir
    ):
        """
        CRITICAL BUG FIX: Test ** matches immediate children (zero intermediate directories).

        fnmatch behavior: code/src/**/*.java does NOT match code/src/Main.java
        pathspec behavior: code/src/**/*.java DOES match code/src/Main.java

        This is required for correct gitignore behavior.
        """
        nested_dir = temp_dir / "code" / "src"
        nested_dir.mkdir(parents=True)
        file_path = nested_dir / "Main.java"
        file_path.touch()

        rel_path = "code/src/Main.java"

        # This MUST match - ** means "zero or more directories"
        assert service._matches_gitignore_pattern(
            file_path, rel_path, "code/src/**/*.java"
        )
        assert service._matches_gitignore_pattern(
            file_path, rel_path, "**/src/**/*.java"
        )
