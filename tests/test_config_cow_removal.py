"""
TDD tests for ConfigManager CoW removal.
These tests define expected behavior after removing CoW configuration methods.
"""

import tempfile
import json
from pathlib import Path
from code_indexer.config import ConfigManager, Config


class TestConfigManagerCoWRemoval:
    """Test ConfigManager without CoW complexity."""

    def test_save_should_use_absolute_paths_after_cow_removal(self):
        """Test that save method uses absolute paths after CoW removal."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = temp_path / ".code-indexer"
            config_dir.mkdir()
            config_path = config_dir / "config.json"

            manager = ConfigManager(config_path)
            config = Config(codebase_dir=temp_path)

            manager.save(config)

            # Read the saved config directly to check format
            with open(config_path, "r") as f:
                saved_data = json.load(f)

            # Should be an absolute path, not relative
            assert Path(saved_data["codebase_dir"]).is_absolute()
            assert saved_data["codebase_dir"] == str(temp_path)

    def test_load_should_work_with_absolute_paths_after_cow_removal(self):
        """Test that load method works with absolute paths after CoW removal."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = temp_path / ".code-indexer"
            config_dir.mkdir()
            config_path = config_dir / "config.json"

            # Save config with absolute path directly
            config_data = {
                "codebase_dir": str(temp_path),
                "exclude_dirs": ["*.log"],
                "file_extensions": ["py", "js"],
            }

            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=2)

            manager = ConfigManager(config_path)
            loaded_config = manager.load()

            # Should load correctly with absolute path
            assert loaded_config.codebase_dir == temp_path

    def test_cow_methods_should_not_exist_after_removal(self):
        """Test that CoW configuration methods don't exist after removal."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = temp_path / ".code-indexer"
            config_dir.mkdir()
            config_path = config_dir / "config.json"

            manager = ConfigManager(config_path)

            cow_methods = [
                "migrate_to_relative_paths",
                "_make_relative_to_config",
                "_resolve_relative_path",
            ]

            for method_name in cow_methods:
                assert not hasattr(
                    manager, method_name
                ), f"CoW configuration method {method_name} should be removed but still exists"

    def test_save_method_simplified_without_cow_comments(self):
        """Test that save method is simplified without CoW compatibility comments."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = temp_path / ".code-indexer"
            config_dir.mkdir()
            config_path = config_dir / "config.json"

            manager = ConfigManager(config_path)
            config = Config(codebase_dir=temp_path)

            # This should work without any CoW complexity
            manager.save(config)

            # Should be able to load it back
            loaded_config = manager.load()
            assert loaded_config.codebase_dir == temp_path

    def test_configuration_round_trip_without_cow(self):
        """Test that configuration round-trip works without CoW complexity."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = temp_path / ".code-indexer"
            config_dir.mkdir()
            config_path = config_dir / "config.json"

            # Create config with various paths
            original_config = Config(
                codebase_dir=temp_path,
                exclude_dirs=["*.log", "*.tmp"],
                file_extensions=["py", "js", "ts"],
            )

            manager = ConfigManager(config_path)

            # Save and load should be identical
            manager.save(original_config)
            loaded_config = manager.load()

            # All fields should match
            assert loaded_config.codebase_dir == original_config.codebase_dir
            assert loaded_config.exclude_dirs == original_config.exclude_dirs
            assert loaded_config.file_extensions == original_config.file_extensions


class TestConfigManagerSimplifiedPaths:
    """Test that ConfigManager uses simplified path handling."""

    def test_absolute_paths_preserved_without_conversion(self):
        """Test that absolute paths are preserved without CoW conversion."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = temp_path / ".code-indexer"
            config_dir.mkdir()
            config_path = config_dir / "config.json"

            manager = ConfigManager(config_path)

            # Use an absolute path
            absolute_codebase = temp_path / "src"
            absolute_codebase.mkdir()

            config = Config(codebase_dir=absolute_codebase)
            manager.save(config)

            # Read raw file to verify absolute path is stored
            with open(config_path, "r") as f:
                raw_data = json.load(f)

            # Should be stored as absolute path
            assert raw_data["codebase_dir"] == str(absolute_codebase)
            assert Path(raw_data["codebase_dir"]).is_absolute()

    def test_no_cow_comments_in_save_method_docstring(self):
        """Test that save method docstring doesn't mention CoW after removal."""
        manager = ConfigManager(Path("/tmp/config.json"))

        # After CoW removal, docstring should not mention CoW
        save_docstring = manager.save.__doc__ or ""
        assert "CoW" not in save_docstring
        assert "clone compatibility" not in save_docstring.lower()

    def test_load_method_simplified_without_cow_resolution(self):
        """Test that load method is simplified without CoW path resolution."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = temp_path / ".code-indexer"
            config_dir.mkdir()
            config_path = config_dir / "config.json"

            # Create a config file with absolute path
            config_data = {
                "codebase_dir": str(temp_path / "project"),
                "ignore_patterns": ["*.log"],
            }

            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=2)

            manager = ConfigManager(config_path)
            loaded_config = manager.load()

            # Should load the path as-is (absolute)
            expected_path = temp_path / "project"
            assert loaded_config.codebase_dir == expected_path
