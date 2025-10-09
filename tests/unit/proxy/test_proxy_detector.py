"""Unit tests for proxy mode detection logic.

Tests the automatic detection of proxy mode based on configuration file discovery
and the proxy_mode flag in the configuration.
"""

import json
import tempfile
from pathlib import Path

import pytest

from code_indexer.config import ConfigManager


class TestProxyModeDetection:
    """Test automatic proxy mode detection from configuration."""

    def test_detect_proxy_mode_when_flag_true(self):
        """Test detection of proxy mode when proxy_mode is true."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"

            # Create config with proxy_mode: true
            config_data = {
                "codebase_dir": str(root),
                "proxy_mode": True,
                "discovered_repos": ["repo1", "repo2"],
            }
            with open(config_file, "w") as f:
                json.dump(config_data, f)

            # Detect mode from root directory
            config_path, mode = ConfigManager.detect_mode(root)

            assert config_path == root
            assert mode == "proxy"

    def test_detect_regular_mode_when_flag_false(self):
        """Test detection of regular mode when proxy_mode is false."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"

            # Create config with proxy_mode: false
            config_data = {"codebase_dir": str(root), "proxy_mode": False}
            with open(config_file, "w") as f:
                json.dump(config_data, f)

            # Detect mode from root directory
            config_path, mode = ConfigManager.detect_mode(root)

            assert config_path == root
            assert mode == "regular"

    def test_detect_regular_mode_when_flag_missing(self):
        """Test detection of regular mode when proxy_mode key is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"

            # Create config without proxy_mode key
            config_data = {"codebase_dir": str(root)}
            with open(config_file, "w") as f:
                json.dump(config_data, f)

            # Detect mode from root directory
            config_path, mode = ConfigManager.detect_mode(root)

            assert config_path == root
            assert mode == "regular"

    def test_detect_none_when_no_config_exists(self):
        """Test detection returns None when no config file found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create a subdirectory to test from
            # This avoids finding any configs in parent directories
            test_dir = root / "test_project"
            test_dir.mkdir()

            # No .code-indexer directory exists in test_dir or tmpdir
            config_path, mode = ConfigManager.detect_mode(test_dir)

            # Should walk up to tmpdir and beyond, but we can't control
            # what exists in system directories. The key behavior is:
            # if we find a config, it should be valid.
            # For this test, we'll verify behavior when confined to our temp space

            # Alternative: Test that it returns something reasonable or None
            if config_path is not None:
                # If a config was found, it must be outside our temp directory
                # This is expected behavior - searches all the way up
                assert not str(config_path).startswith(str(test_dir))
            else:
                # No config found anywhere - this is also valid
                assert mode is None

    def test_detect_from_subdirectory_walks_up(self):
        """Test detection walks up directory tree from subdirectory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"

            # Create config with proxy_mode: true
            config_data = {"codebase_dir": str(root), "proxy_mode": True}
            with open(config_file, "w") as f:
                json.dump(config_data, f)

            # Create nested subdirectories
            sub1 = root / "sub1"
            sub2 = sub1 / "sub2"
            sub3 = sub2 / "sub3"
            sub3.mkdir(parents=True)

            # Detect from deep subdirectory
            config_path, mode = ConfigManager.detect_mode(sub3)

            assert config_path == root
            assert mode == "proxy"

    def test_detect_uses_current_dir_when_no_start_path(self):
        """Test detection uses current directory when start_path is None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"

            # Create config with proxy_mode: true
            config_data = {"codebase_dir": str(root), "proxy_mode": True}
            with open(config_file, "w") as f:
                json.dump(config_data, f)

            # Change to tmpdir and detect without start_path
            import os

            original_cwd = os.getcwd()
            try:
                os.chdir(root)
                config_path, mode = ConfigManager.detect_mode()

                assert config_path == root
                assert mode == "proxy"
            finally:
                os.chdir(original_cwd)

    def test_detect_topmost_config_like_git(self):
        """Test detection uses topmost config when multiple configs exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create topmost config (proxy mode)
            top_config_dir = root / ".code-indexer"
            top_config_dir.mkdir()
            top_config_file = top_config_dir / "config.json"
            top_config_data = {"codebase_dir": str(root), "proxy_mode": True}
            with open(top_config_file, "w") as f:
                json.dump(top_config_data, f)

            # Create nested config (regular mode)
            nested = root / "nested"
            nested.mkdir()
            nested_config_dir = nested / ".code-indexer"
            nested_config_dir.mkdir()
            nested_config_file = nested_config_dir / "config.json"
            nested_config_data = {"codebase_dir": str(nested), "proxy_mode": False}
            with open(nested_config_file, "w") as f:
                json.dump(nested_config_data, f)

            # Create deep subdirectory under nested
            deep = nested / "deep" / "path"
            deep.mkdir(parents=True)

            # Detect from deep subdirectory - should find nested first (closest)
            # This matches git behavior: closest .git wins
            config_path, mode = ConfigManager.detect_mode(deep)

            # CORRECTION: Git finds the CLOSEST config, not topmost
            # The test name is misleading - should be "closest config like git"
            assert config_path == nested
            assert mode == "regular"

    def test_detect_handles_corrupted_config_gracefully(self):
        """Test detection handles corrupted JSON gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"

            # Create corrupted JSON
            with open(config_file, "w") as f:
                f.write("{invalid json content")

            # Detection should handle error gracefully
            # Could either raise exception or return None - TBD during implementation
            with pytest.raises(ValueError):
                ConfigManager.detect_mode(root)

    def test_detect_handles_permission_errors_gracefully(self):
        """Test detection handles permission errors gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"

            # Create valid config
            config_data = {"codebase_dir": str(root), "proxy_mode": True}
            with open(config_file, "w") as f:
                json.dump(config_data, f)

            # Remove read permissions
            import os
            import stat

            os.chmod(config_file, 0o000)

            try:
                # Detection should handle permission error
                with pytest.raises((PermissionError, OSError)):
                    ConfigManager.detect_mode(root)
            finally:
                # Restore permissions for cleanup
                os.chmod(config_file, stat.S_IRUSR | stat.S_IWUSR)

    def test_detect_stops_at_filesystem_root(self):
        """Test detection stops at filesystem root and doesn't infinite loop."""
        # Start from a non-existent subdirectory path
        # This ensures we walk all the way up to filesystem root
        nonexistent = Path("/nonexistent/deep/path/that/does/not/exist")

        # Should return None without infinite loop
        config_path, mode = ConfigManager.detect_mode(nonexistent)

        assert config_path is None
        assert mode is None


class TestProxyModeDetectionWithSymlinks:
    """Test proxy mode detection with symbolic links."""

    def test_detect_follows_symlinks_to_config(self):
        """Test detection follows symlinks to find config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create actual config in one location
            real_config_dir = root / "real" / ".code-indexer"
            real_config_dir.mkdir(parents=True)
            config_file = real_config_dir / "config.json"
            config_data = {
                "codebase_dir": str(root / "real"),
                "proxy_mode": True,
            }
            with open(config_file, "w") as f:
                json.dump(config_data, f)

            # Create symlink to directory containing config
            link = root / "link"
            link.symlink_to(root / "real")

            # Detect from symlinked location
            config_path, mode = ConfigManager.detect_mode(link)

            # Should find the config through symlink
            assert mode == "proxy"

    def test_detect_handles_broken_symlinks(self):
        """Test detection handles broken symlinks gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create broken symlink
            broken_link = root / "broken"
            broken_link.symlink_to("/nonexistent/path")

            # Detection should handle broken symlink
            config_path, mode = ConfigManager.detect_mode(broken_link)

            # Should return None for broken symlink
            assert config_path is None
            assert mode is None


class TestProxyModeDetectionEdgeCases:
    """Test edge cases for proxy mode detection."""

    def test_detect_with_empty_config_file(self):
        """Test detection with empty config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"

            # Create empty file
            config_file.touch()

            # Should raise error for invalid JSON
            with pytest.raises(ValueError):
                ConfigManager.detect_mode(root)

    def test_detect_with_directory_named_config_json(self):
        """Test detection when config.json is a directory not a file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / ".code-indexer"
            config_dir.mkdir()

            # Create directory named config.json
            (config_dir / "config.json").mkdir()

            # Should handle gracefully by skipping and continuing search
            config_path, mode = ConfigManager.detect_mode(root)

            # Should skip the directory and continue searching upward
            # It won't find our invalid config, but might find one higher up
            if config_path is not None:
                # If found, it should be outside our test directory
                assert config_path != root
            # If None, that's also valid - no config found

    def test_detect_with_very_deep_nesting(self):
        """Test detection works with very deep directory nesting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"

            # Create config
            config_data = {"codebase_dir": str(root), "proxy_mode": True}
            with open(config_file, "w") as f:
                json.dump(config_data, f)

            # Create very deep nesting (20 levels)
            current = root
            for i in range(20):
                current = current / f"level{i}"
            current.mkdir(parents=True)

            # Detect from deep location
            config_path, mode = ConfigManager.detect_mode(current)

            assert config_path == root
            assert mode == "proxy"
