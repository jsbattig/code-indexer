"""Tests for YAML-based language mapping functionality."""

import pytest
import tempfile
import shutil
from pathlib import Path
import yaml
import os

from code_indexer.services.language_mapper import LanguageMapper
from code_indexer.utils.yaml_utils import (
    create_language_mappings_yaml,
    load_language_mappings_yaml,
    DEFAULT_LANGUAGE_MAPPINGS,
)


class TestYAMLLanguageMappings:
    """Test YAML persistence for language mappings."""

    def setup_method(self):
        """Create temporary directory for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

        # Clear singleton cache
        LanguageMapper._instance = None
        LanguageMapper._mappings_cache = None

    def teardown_method(self):
        """Clean up temporary directory and restore CWD."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)

        # Clear singleton cache
        LanguageMapper._instance = None
        LanguageMapper._mappings_cache = None

    def test_proactive_yaml_creation(self):
        """Test proactive YAML creation during init."""
        config_dir = Path(self.temp_dir) / ".code-indexer"

        # Create YAML file
        created = create_language_mappings_yaml(config_dir)
        assert created is True

        # Verify file exists
        yaml_path = config_dir / "language-mappings.yaml"
        assert yaml_path.exists()

        # Verify content
        with open(yaml_path, "r") as f:
            content = f.read()
            assert "# Language Mappings Configuration" in content
            assert "python:" in content
            assert "javascript:" in content

    def test_reactive_yaml_creation(self):
        """Test reactive YAML creation on first use."""
        # Create config directory without YAML file
        config_dir = Path(self.temp_dir) / ".code-indexer"
        config_dir.mkdir()

        # Instantiate mapper (should trigger reactive creation)
        mapper = LanguageMapper()

        # Verify YAML was created
        yaml_path = config_dir / "language-mappings.yaml"
        assert yaml_path.exists()

        # Verify mapper works correctly
        assert mapper.get_extensions("python") == {"py", "pyw", "pyi"}

    def test_no_config_dir_fallback(self):
        """Test fallback when no .code-indexer directory exists."""
        # Don't create any config directory
        mapper = LanguageMapper()

        # Should still work with defaults
        assert mapper.get_extensions("python") == {"py", "pyw", "pyi"}
        assert mapper.get_extensions("javascript") == {"js", "jsx"}

    def test_yaml_loading_persistence(self):
        """Test that custom YAML mappings are loaded correctly."""
        config_dir = Path(self.temp_dir) / ".code-indexer"
        config_dir.mkdir()

        # Create custom YAML
        yaml_path = config_dir / "language-mappings.yaml"
        custom_mappings = {
            "python": ["py", "pyw", "pyi", "py3"],  # Added py3
            "customlang": ["cst", "custom"],  # New language
        }

        with open(yaml_path, "w") as f:
            yaml.dump(custom_mappings, f)

        # Create mapper and verify custom mappings
        mapper = LanguageMapper()
        assert mapper.get_extensions("python") == {"py", "pyw", "pyi", "py3"}
        assert mapper.get_extensions("customlang") == {"cst", "custom"}

    def test_yaml_corruption_fallback(self):
        """Test graceful fallback on corrupted YAML."""
        config_dir = Path(self.temp_dir) / ".code-indexer"
        config_dir.mkdir()

        # Create corrupted YAML
        yaml_path = config_dir / "language-mappings.yaml"
        with open(yaml_path, "w") as f:
            f.write("invalid: yaml: content: {broken")

        # Should fallback to defaults without crashing
        mapper = LanguageMapper()
        assert mapper.get_extensions("python") == {"py", "pyw", "pyi"}

    def test_singleton_caching(self):
        """Test that singleton pattern caches mappings efficiently."""
        config_dir = Path(self.temp_dir) / ".code-indexer"
        create_language_mappings_yaml(config_dir)

        # Create first instance
        mapper1 = LanguageMapper()

        # Modify YAML file
        yaml_path = config_dir / "language-mappings.yaml"
        with open(yaml_path, "a") as f:
            f.write("\ntestlang: [tst]\n")

        # Create second instance (should use cache)
        mapper2 = LanguageMapper()

        # Both should be same instance
        assert mapper1 is mapper2

        # Should not see the modification (cached)
        assert mapper2.is_supported_language("testlang") is False

        # Force reload
        mapper2.reload_mappings()

        # Now should see the modification
        assert mapper2.get_extensions("testlang") == {"tst"}

    def test_thread_safety_initialization(self):
        """Test thread-safe initialization of singleton."""
        import threading
        import time

        config_dir = Path(self.temp_dir) / ".code-indexer"
        config_dir.mkdir()

        instances = []

        def create_mapper():
            time.sleep(0.01)  # Small delay to increase chance of race
            mapper = LanguageMapper()
            instances.append(mapper)

        # Create multiple threads
        threads = [threading.Thread(target=create_mapper) for _ in range(10)]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for completion
        for t in threads:
            t.join()

        # All instances should be the same
        assert all(inst is instances[0] for inst in instances)

    def test_permission_error_handling(self):
        """Test handling of permission errors during YAML operations."""
        import stat

        config_dir = Path(self.temp_dir) / ".code-indexer"
        config_dir.mkdir()

        # Make directory read-only
        os.chmod(config_dir, stat.S_IRUSR | stat.S_IXUSR)

        try:
            # Should fallback gracefully
            mapper = LanguageMapper()
            assert mapper.get_extensions("python") == {"py", "pyw", "pyi"}
        finally:
            # Restore permissions for cleanup
            os.chmod(config_dir, stat.S_IRWXU)


class TestYAMLUtilities:
    """Test YAML utility functions."""

    def setup_method(self):
        """Create temporary directory for tests."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_create_language_mappings_yaml_new_file(self):
        """Test creating new YAML file."""
        config_dir = Path(self.temp_dir) / "config"

        result = create_language_mappings_yaml(config_dir)
        assert result is True

        yaml_path = config_dir / "language-mappings.yaml"
        assert yaml_path.exists()

        # Verify content structure
        with open(yaml_path, "r") as f:
            content = f.read()
            assert "# Language Mappings Configuration" in content

        # Verify YAML parsing
        data = yaml.safe_load(yaml_path.read_text())
        assert "python" in data
        assert "javascript" in data
        assert data["python"] == ["py", "pyw", "pyi"]

    def test_create_language_mappings_yaml_existing_file_no_force(self):
        """Test not overwriting existing file without force."""
        config_dir = Path(self.temp_dir) / "config"
        yaml_path = config_dir / "language-mappings.yaml"

        # Create initial file
        create_language_mappings_yaml(config_dir)

        # Modify file
        with open(yaml_path, "w") as f:
            f.write("custom: modified\n")

        # Try to create again without force
        result = create_language_mappings_yaml(config_dir, force=False)
        assert result is False

        # Verify file wasn't overwritten
        with open(yaml_path, "r") as f:
            content = f.read()
            assert "custom: modified" in content

    def test_create_language_mappings_yaml_existing_file_with_force(self):
        """Test overwriting existing file with force."""
        config_dir = Path(self.temp_dir) / "config"
        yaml_path = config_dir / "language-mappings.yaml"

        # Create initial file
        create_language_mappings_yaml(config_dir)

        # Modify file
        with open(yaml_path, "w") as f:
            f.write("custom: modified\n")

        # Create again with force
        result = create_language_mappings_yaml(config_dir, force=True)
        assert result is True

        # Verify file was reset
        with open(yaml_path, "r") as f:
            content = f.read()
            assert "custom: modified" not in content
            assert "python:" in content

    def test_load_language_mappings_yaml_success(self):
        """Test successful YAML loading."""
        config_dir = Path(self.temp_dir) / "config"
        yaml_path = config_dir / "language-mappings.yaml"

        # Create YAML file
        create_language_mappings_yaml(config_dir)

        # Load mappings
        mappings = load_language_mappings_yaml(yaml_path)

        assert isinstance(mappings, dict)
        assert "python" in mappings
        assert mappings["python"] == {"py", "pyw", "pyi"}  # Should be set, not list
        assert "javascript" in mappings
        assert mappings["javascript"] == {"js", "jsx"}

    def test_load_language_mappings_yaml_file_not_found(self):
        """Test FileNotFoundError for missing file."""
        yaml_path = Path(self.temp_dir) / "nonexistent.yaml"

        with pytest.raises(FileNotFoundError):
            load_language_mappings_yaml(yaml_path)

    def test_load_language_mappings_yaml_parse_error(self):
        """Test YAML parsing error handling."""
        yaml_path = Path(self.temp_dir) / "broken.yaml"

        # Create broken YAML
        with open(yaml_path, "w") as f:
            f.write("invalid: yaml: {broken")

        with pytest.raises(yaml.YAMLError):
            load_language_mappings_yaml(yaml_path)

    def test_load_language_mappings_yaml_string_extensions(self):
        """Test handling single string extension."""
        yaml_path = Path(self.temp_dir) / "test.yaml"

        # Create YAML with string extensions
        test_data = {
            "singlelang": "ext",  # Single string
            "multilang": ["ext1", "ext2"],  # List
        }

        with open(yaml_path, "w") as f:
            yaml.dump(test_data, f)

        mappings = load_language_mappings_yaml(yaml_path)

        assert mappings["singlelang"] == {"ext"}  # Converted to set
        assert mappings["multilang"] == {"ext1", "ext2"}  # Converted to set

    def test_default_language_mappings_completeness(self):
        """Test that default mappings are comprehensive."""
        # Test a sampling of important languages
        expected_languages = [
            "python",
            "javascript",
            "typescript",
            "java",
            "csharp",
            "cpp",
            "c",
            "go",
            "rust",
            "php",
            "ruby",
            "swift",
            "html",
            "css",
            "markdown",
            "yaml",
            "json",
            "sql",
        ]

        for lang in expected_languages:
            assert lang in DEFAULT_LANGUAGE_MAPPINGS
            assert isinstance(DEFAULT_LANGUAGE_MAPPINGS[lang], list)
            assert len(DEFAULT_LANGUAGE_MAPPINGS[lang]) > 0
