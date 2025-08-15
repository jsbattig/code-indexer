"""
Test-driven development for CLI integration of override system.

Tests init command creation of override files and FileFinder integration.
"""

import tempfile
import subprocess
from pathlib import Path


class TestInitCommandOverrideCreation:
    """Test that init command creates override files."""

    def test_init_creates_override_file_by_default(self):
        """Test that 'code-indexer init' creates .code-indexer-override.yaml by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Run init command
            result = subprocess.run(
                [
                    "code-indexer",
                    "init",
                    "--force",
                    "--embedding-provider",
                    "voyage-ai",
                ],
                cwd=project_dir,
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0

            # Should create override file
            override_path = project_dir / ".code-indexer-override.yaml"
            assert override_path.exists()

            # Should have default structure with comments
            content = override_path.read_text()
            assert "Code-indexer override file" in content
            assert "add_extensions: []" in content
            assert "remove_extensions: []" in content
            assert "add_exclude_dirs: []" in content
            assert "add_include_dirs: []" in content
            assert "force_include_patterns: []" in content
            assert "force_exclude_patterns: []" in content

    def test_init_create_override_file_flag_for_existing_projects(self):
        """Test --create-override-file flag for already initialized projects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # First, initialize project normally
            result = subprocess.run(
                [
                    "code-indexer",
                    "init",
                    "--force",
                    "--embedding-provider",
                    "voyage-ai",
                ],
                cwd=project_dir,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0

            # Remove override file to simulate old project
            override_path = project_dir / ".code-indexer-override.yaml"
            if override_path.exists():
                override_path.unlink()

            # Run init with --create-override-file
            result = subprocess.run(
                ["code-indexer", "init", "--create-override-file"],
                cwd=project_dir,
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0

            # Should create override file
            assert override_path.exists()
            content = override_path.read_text()
            assert "add_extensions: []" in content

    def test_init_does_not_overwrite_existing_override_file(self):
        """Test that init doesn't overwrite existing override file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            override_path = project_dir / ".code-indexer-override.yaml"

            # Create existing override file with custom content
            custom_content = """
# Custom override file
add_extensions: [".custom"]
remove_extensions: []
add_exclude_dirs: []
add_include_dirs: []
force_include_patterns: []
force_exclude_patterns: []
"""
            override_path.write_text(custom_content)

            # Run init command
            result = subprocess.run(
                [
                    "code-indexer",
                    "init",
                    "--force",
                    "--embedding-provider",
                    "voyage-ai",
                ],
                cwd=project_dir,
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0

            # Should not overwrite existing content
            content = override_path.read_text()
            assert "Custom override file" in content
            assert 'add_extensions: [".custom"]' in content


class TestFileFinderIntegration:
    """Test FileFinder integration with override filtering."""

    def test_file_finder_applies_override_filtering(self):
        """Test that FileFinder applies override rules during file discovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create test files
            (project_dir / "main.py").write_text("print('main')")
            (project_dir / "config.custom").write_text("custom config")
            (project_dir / "temp.tmp").write_text("temporary")
            (project_dir / "temp").mkdir()
            (project_dir / "temp" / "cache.py").write_text("cache")
            (project_dir / "important").mkdir()
            (project_dir / "important" / "data.txt").write_text("important data")

            # Create config with override
            config_dir = project_dir / ".code-indexer"
            config_dir.mkdir()

            config_content = {
                "codebase_dir": str(project_dir),
                "file_extensions": [".py"],
                "exclude_dirs": [],
            }

            import json

            with open(config_dir / "config.json", "w") as f:
                json.dump(config_content, f)

            # Create override file
            override_content = """
add_extensions: [".custom"]
remove_extensions: [".tmp"]
add_exclude_dirs: ["temp"]
add_include_dirs: ["important"]
force_include_patterns: []
force_exclude_patterns: []
"""
            (project_dir / ".code-indexer-override.yaml").write_text(override_content)

            # Test FileFinder with override
            from code_indexer.config import ConfigManager
            from code_indexer.indexing.file_finder import FileFinder

            config_manager = ConfigManager(config_dir / "config.json")
            config = config_manager.load()

            file_finder = FileFinder(config)
            found_files = list(file_finder.find_files())
            found_paths = [str(f.relative_to(project_dir)) for f in found_files]

            # Should include .py files (base config)
            assert "main.py" in found_paths

            # Should include .custom files (add_extensions override)
            assert "config.custom" in found_paths

            # Should exclude .tmp files (remove_extensions override)
            assert "temp.tmp" not in found_paths

            # Should exclude files in temp dir (add_exclude_dirs override)
            assert "temp/cache.py" not in found_paths

            # Should include files in important dir (add_include_dirs override)
            assert "important/data.txt" in found_paths

    def test_file_finder_works_without_override_file(self):
        """Test that FileFinder works normally when no override file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create test files
            (project_dir / "main.py").write_text("print('main')")
            (project_dir / "readme.md").write_text("# Readme")

            # Create config without override
            config_dir = project_dir / ".code-indexer"
            config_dir.mkdir()

            config_content = {
                "codebase_dir": str(project_dir),
                "file_extensions": [".py"],
                "exclude_dirs": [],
            }

            import json

            with open(config_dir / "config.json", "w") as f:
                json.dump(config_content, f)

            # Test FileFinder without override (should work normally)
            from code_indexer.config import ConfigManager
            from code_indexer.indexing.file_finder import FileFinder

            config_manager = ConfigManager(config_dir / "config.json")
            config = config_manager.load()

            file_finder = FileFinder(config)
            found_files = list(file_finder.find_files())
            found_paths = [str(f.relative_to(project_dir)) for f in found_files]

            # Should include .py files
            assert "main.py" in found_paths

            # Should not include .md files (not in whitelist)
            assert "readme.md" not in found_paths


class TestEndToEndOverrideWorkflow:
    """Test complete end-to-end workflow with override system."""

    def test_complete_override_workflow(self):
        """Test complete workflow from init to file discovery with overrides."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Step 1: Initialize project (should create override file)
            result = subprocess.run(
                [
                    "code-indexer",
                    "init",
                    "--force",
                    "--embedding-provider",
                    "voyage-ai",
                ],
                cwd=project_dir,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0

            # Step 2: Modify override file
            override_path = project_dir / ".code-indexer-override.yaml"
            override_content = """
# Project-specific overrides
add_extensions: [".config", ".env"]
remove_extensions: []
add_exclude_dirs: ["build", "dist"]
add_include_dirs: []
force_include_patterns: ["important.*"]
force_exclude_patterns: ["**/*.log"]
"""
            override_path.write_text(override_content)

            # Step 3: Create test files
            (project_dir / "main.py").write_text("print('main')")
            (project_dir / "app.config").write_text("config data")
            (project_dir / "build").mkdir()
            (project_dir / "build" / "output.py").write_text("build output")
            (project_dir / "important.tmp").write_text("important temp file")
            (project_dir / "debug.log").write_text("debug logs")

            # Step 4: Test that file discovery respects overrides
            from code_indexer.config import ConfigManager
            from code_indexer.indexing.file_finder import FileFinder

            config_manager = ConfigManager(
                project_dir / ".code-indexer" / "config.json"
            )
            config = config_manager.load()

            file_finder = FileFinder(config)
            found_files = list(file_finder.find_files())
            found_paths = [str(f.relative_to(project_dir)) for f in found_files]

            # Verify override rules are applied
            assert "main.py" in found_paths  # base inclusion
            assert "app.config" in found_paths  # add_extensions
            assert "build/output.py" not in found_paths  # add_exclude_dirs
            assert "important.tmp" in found_paths  # force_include_patterns
            assert "debug.log" not in found_paths  # force_exclude_patterns
