"""
Test-driven development for .code-indexer-override.yaml support.

Tests the OverrideConfig loading, validation, and integration.
"""

import tempfile
import pytest
from pathlib import Path
from dataclasses import dataclass
from typing import List

from code_indexer.config import ConfigManager


@dataclass
class OverrideConfig:
    """Override configuration for file inclusion/exclusion rules."""

    add_extensions: List[str]
    remove_extensions: List[str]
    add_exclude_dirs: List[str]
    add_include_dirs: List[str]
    force_include_patterns: List[str]
    force_exclude_patterns: List[str]


class TestOverrideConfigLoading:
    """Test loading override configuration from YAML."""

    def test_load_valid_override_config(self):
        """Test loading valid override YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            override_path = Path(tmpdir) / ".code-indexer-override.yaml"
            override_content = """
# Test override config
add_extensions:
  - .custom
  - .special
remove_extensions:
  - .tmp
add_exclude_dirs:
  - build-cache
  - temp-files
add_include_dirs:
  - important-build
force_include_patterns:
  - "*.min.js"
  - "dist/critical/**"
force_exclude_patterns:
  - "**/*.log"
  - "debug/**"
"""
            override_path.write_text(override_content)

            # This should not fail yet - we need to implement _load_override_config
            from code_indexer.config import _load_override_config

            config = _load_override_config(override_path)

            assert config.add_extensions == [".custom", ".special"]
            assert config.remove_extensions == [".tmp"]
            assert config.add_exclude_dirs == ["build-cache", "temp-files"]
            assert config.add_include_dirs == ["important-build"]
            assert config.force_include_patterns == ["*.min.js", "dist/critical/**"]
            assert config.force_exclude_patterns == ["**/*.log", "debug/**"]

    def test_load_empty_override_config(self):
        """Test loading override config with all empty arrays."""
        with tempfile.TemporaryDirectory() as tmpdir:
            override_path = Path(tmpdir) / ".code-indexer-override.yaml"
            override_content = """
add_extensions: []
remove_extensions: []
add_exclude_dirs: []
add_include_dirs: []
force_include_patterns: []
force_exclude_patterns: []
"""
            override_path.write_text(override_content)

            from code_indexer.config import _load_override_config

            config = _load_override_config(override_path)

            assert config.add_extensions == []
            assert config.remove_extensions == []
            assert config.add_exclude_dirs == []
            assert config.add_include_dirs == []
            assert config.force_include_patterns == []
            assert config.force_exclude_patterns == []

    def test_load_invalid_yaml_fails_fast(self):
        """Test that invalid YAML fails fast with clear error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            override_path = Path(tmpdir) / ".code-indexer-override.yaml"
            # Invalid YAML - missing colon
            invalid_content = """
add_extensions
  - .custom
"""
            override_path.write_text(invalid_content)

            from code_indexer.config import _load_override_config

            with pytest.raises(Exception) as exc_info:
                _load_override_config(override_path)

            # Should have clear error message about YAML parsing
            assert "YAML" in str(exc_info.value) or "yaml" in str(exc_info.value)

    def test_load_missing_required_fields_fails_fast(self):
        """Test that missing required fields fail fast."""
        with tempfile.TemporaryDirectory() as tmpdir:
            override_path = Path(tmpdir) / ".code-indexer-override.yaml"
            # Missing required fields
            incomplete_content = """
add_extensions:
  - .custom
# Missing other required fields
"""
            override_path.write_text(incomplete_content)

            from code_indexer.config import _load_override_config

            with pytest.raises(Exception) as exc_info:
                _load_override_config(override_path)

            # Should fail on missing fields
            assert any(
                field in str(exc_info.value)
                for field in [
                    "remove_extensions",
                    "add_exclude_dirs",
                    "add_include_dirs",
                    "force_include_patterns",
                    "force_exclude_patterns",
                ]
            )


class TestOverrideConfigDiscovery:
    """Test auto-discovery of override files in directory tree."""

    def test_find_override_file_in_current_dir(self):
        """Test finding override file in current directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            override_path = Path(tmpdir) / ".code-indexer-override.yaml"
            override_path.write_text("add_extensions: []")

            from code_indexer.config import _find_override_file

            found_path = _find_override_file(Path(tmpdir))

            assert found_path == override_path

    def test_find_override_file_walking_up_tree(self):
        """Test finding override file by walking up directory tree."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested directory structure
            root_dir = Path(tmpdir)
            nested_dir = root_dir / "src" / "components"
            nested_dir.mkdir(parents=True)

            # Place override file in root
            override_path = root_dir / ".code-indexer-override.yaml"
            override_path.write_text("add_extensions: []")

            from code_indexer.config import _find_override_file

            found_path = _find_override_file(nested_dir)

            assert found_path == override_path

    def test_find_override_file_not_found(self):
        """Test when no override file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from code_indexer.config import _find_override_file

            found_path = _find_override_file(Path(tmpdir))

            assert found_path is None


class TestConfigIntegration:
    """Test integration of override config with main Config class."""

    def test_config_loads_override_when_present(self):
        """Test that Config class loads override config when file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            config_dir = project_dir / ".code-indexer"
            config_dir.mkdir()

            # Create main config
            config_path = config_dir / "config.json"
            config_content = {
                "codebase_dir": str(project_dir),
                "file_extensions": [".py", ".js"],
                "exclude_dirs": ["node_modules"],
            }

            import json

            with open(config_path, "w") as f:
                json.dump(config_content, f)

            # Create override config
            override_path = project_dir / ".code-indexer-override.yaml"
            override_content = """
add_extensions: [".custom"]
remove_extensions: []
add_exclude_dirs: ["temp"]
add_include_dirs: []
force_include_patterns: []
force_exclude_patterns: []
"""
            override_path.write_text(override_content)

            # Load config - should include override
            config_manager = ConfigManager(config_path)
            config = config_manager.load()

            assert config.override_config is not None
            assert config.override_config.add_extensions == [".custom"]
            assert config.override_config.add_exclude_dirs == ["temp"]

    def test_config_works_without_override_file(self):
        """Test that Config works normally when no override file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            config_dir = project_dir / ".code-indexer"
            config_dir.mkdir()

            # Create main config only
            config_path = config_dir / "config.json"
            config_content = {
                "codebase_dir": str(project_dir),
                "file_extensions": [".py", ".js"],
                "exclude_dirs": ["node_modules"],
            }

            import json

            with open(config_path, "w") as f:
                json.dump(config_content, f)

            # Load config - should work without override
            config_manager = ConfigManager(config_path)
            config = config_manager.load()

            assert config.override_config is None
