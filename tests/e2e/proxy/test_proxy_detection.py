"""Integration tests for proxy mode detection.

Tests the end-to-end behavior of proxy mode detection in real directory structures
with actual file system operations.
"""

import json
import tempfile
from pathlib import Path


from code_indexer.config import ConfigManager


class TestProxyDetectionIntegration:
    """Integration tests for proxy mode detection in real scenarios."""

    def test_detection_from_various_subdirectory_depths(self):
        """Test detection works from various subdirectory depths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create proxy root config
            config_dir = root / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"
            config_data = {"codebase_dir": str(root), "proxy_mode": True}
            with open(config_file, "w") as f:
                json.dump(config_data, f)

            # Test from root
            config_path, mode = ConfigManager.detect_mode(root)
            assert config_path == root
            assert mode == "proxy"

            # Test from depth 1
            depth1 = root / "level1"
            depth1.mkdir()
            config_path, mode = ConfigManager.detect_mode(depth1)
            assert config_path == root
            assert mode == "proxy"

            # Test from depth 3
            depth3 = root / "level1" / "level2" / "level3"
            depth3.mkdir(parents=True)
            config_path, mode = ConfigManager.detect_mode(depth3)
            assert config_path == root
            assert mode == "proxy"

            # Test from depth 5
            depth5 = depth3 / "level4" / "level5"
            depth5.mkdir(parents=True)
            config_path, mode = ConfigManager.detect_mode(depth5)
            assert config_path == root
            assert mode == "proxy"

    def test_mixed_regular_and_proxy_configurations(self):
        """Test behavior with mixed regular and proxy configurations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create proxy root config
            proxy_config_dir = root / ".code-indexer"
            proxy_config_dir.mkdir()
            proxy_config_file = proxy_config_dir / "config.json"
            proxy_config_data = {
                "codebase_dir": str(root),
                "proxy_mode": True,
                "discovered_repos": ["repo1", "repo2"],
            }
            with open(proxy_config_file, "w") as f:
                json.dump(proxy_config_data, f)

            # Create regular repo inside proxy root
            repo1 = root / "repo1"
            repo1.mkdir()
            repo1_config_dir = repo1 / ".code-indexer"
            repo1_config_dir.mkdir()
            repo1_config_file = repo1_config_dir / "config.json"
            repo1_config_data = {"codebase_dir": str(repo1), "proxy_mode": False}
            with open(repo1_config_file, "w") as f:
                json.dump(repo1_config_data, f)

            # Detection from proxy root should be proxy
            config_path, mode = ConfigManager.detect_mode(root)
            assert config_path == root
            assert mode == "proxy"

            # Detection from repo1 should be regular (closest config wins)
            config_path, mode = ConfigManager.detect_mode(repo1)
            assert config_path == repo1
            assert mode == "regular"

            # Detection from subdirectory of repo1 should be regular
            repo1_sub = repo1 / "src" / "main"
            repo1_sub.mkdir(parents=True)
            config_path, mode = ConfigManager.detect_mode(repo1_sub)
            assert config_path == repo1
            assert mode == "regular"

    def test_real_world_proxy_structure(self):
        """Test detection in realistic proxy directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create proxy root
            proxy_root = root / "multi-repo-workspace"
            proxy_root.mkdir()
            proxy_config_dir = proxy_root / ".code-indexer"
            proxy_config_dir.mkdir()
            proxy_config_file = proxy_config_dir / "config.json"
            proxy_config_data = {
                "codebase_dir": str(proxy_root),
                "proxy_mode": True,
                "discovered_repos": [
                    "frontend/react-app",
                    "backend/api-service",
                    "shared/utils",
                ],
            }
            with open(proxy_config_file, "w") as f:
                json.dump(proxy_config_data, f)

            # Create multiple repositories
            frontend_repo = proxy_root / "frontend" / "react-app"
            frontend_repo.mkdir(parents=True)
            frontend_config_dir = frontend_repo / ".code-indexer"
            frontend_config_dir.mkdir()
            frontend_config_file = frontend_config_dir / "config.json"
            frontend_config_data = {
                "codebase_dir": str(frontend_repo),
                "proxy_mode": False,
            }
            with open(frontend_config_file, "w") as f:
                json.dump(frontend_config_data, f)

            backend_repo = proxy_root / "backend" / "api-service"
            backend_repo.mkdir(parents=True)
            backend_config_dir = backend_repo / ".code-indexer"
            backend_config_dir.mkdir()
            backend_config_file = backend_config_dir / "config.json"
            backend_config_data = {
                "codebase_dir": str(backend_repo),
                "proxy_mode": False,
            }
            with open(backend_config_file, "w") as f:
                json.dump(backend_config_data, f)

            # Test detection from proxy root
            config_path, mode = ConfigManager.detect_mode(proxy_root)
            assert config_path == proxy_root
            assert mode == "proxy"

            # Test detection from frontend workspace (outside any repo)
            frontend_workspace = proxy_root / "frontend"
            config_path, mode = ConfigManager.detect_mode(frontend_workspace)
            assert config_path == proxy_root
            assert mode == "proxy"

            # Test detection from inside frontend repo
            frontend_src = frontend_repo / "src" / "components"
            frontend_src.mkdir(parents=True)
            config_path, mode = ConfigManager.detect_mode(frontend_src)
            assert config_path == frontend_repo
            assert mode == "regular"

            # Test detection from inside backend repo
            backend_src = backend_repo / "src" / "controllers"
            backend_src.mkdir(parents=True)
            config_path, mode = ConfigManager.detect_mode(backend_src)
            assert config_path == backend_repo
            assert mode == "regular"

    def test_detection_with_no_config_anywhere(self):
        """Test detection when no config exists in entire hierarchy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create directory structure without any configs
            project = root / "project" / "src" / "main"
            project.mkdir(parents=True)

            # Detection will search upward and may find system-level configs
            config_path, mode = ConfigManager.detect_mode(project)

            # If a config is found, it should be outside our test directory
            if config_path is not None:
                assert not str(config_path).startswith(str(project))
            else:
                # No config found - also valid
                assert mode is None

    def test_detection_across_mount_points(self):
        """Test detection behavior at filesystem boundaries."""
        # This test documents expected behavior at mount points
        # In practice, detection walks up to filesystem root
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create deep structure without config
            deep_path = root / "a" / "b" / "c" / "d" / "e"
            deep_path.mkdir(parents=True)

            # Detection walks up the tree
            config_path, mode = ConfigManager.detect_mode(deep_path)

            # Might find a config in system directories or return None
            if config_path is not None:
                # If found, should be outside our temp directory
                assert not str(config_path).startswith(str(deep_path))
            else:
                assert mode is None

    def test_detection_preserves_existing_find_config_path_behavior(self):
        """Test that detect_mode doesn't break existing find_config_path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create config
            config_dir = root / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"
            config_data = {"codebase_dir": str(root), "proxy_mode": True}
            with open(config_file, "w") as f:
                json.dump(config_data, f)

            # Create subdirectory
            subdir = root / "sub1" / "sub2"
            subdir.mkdir(parents=True)

            # Both methods should find the same config
            found_by_find = ConfigManager.find_config_path(subdir)
            detected_path, _ = ConfigManager.detect_mode(subdir)

            assert found_by_find == config_file
            assert detected_path == root  # detect_mode returns root, not config file

    def test_detection_with_workspace_patterns(self):
        """Test detection in typical workspace patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Pattern 1: Monorepo with proxy at root
            monorepo = root / "monorepo"
            monorepo.mkdir()
            monorepo_config_dir = monorepo / ".code-indexer"
            monorepo_config_dir.mkdir()
            monorepo_config_file = monorepo_config_dir / "config.json"
            monorepo_config_data = {"codebase_dir": str(monorepo), "proxy_mode": True}
            with open(monorepo_config_file, "w") as f:
                json.dump(monorepo_config_data, f)

            # Create packages
            packages = monorepo / "packages"
            packages.mkdir()
            pkg1 = packages / "package1"
            pkg1.mkdir()
            pkg2 = packages / "package2"
            pkg2.mkdir()

            # Detection from packages should find proxy
            config_path, mode = ConfigManager.detect_mode(pkg1)
            assert config_path == monorepo
            assert mode == "proxy"

            config_path, mode = ConfigManager.detect_mode(pkg2)
            assert config_path == monorepo
            assert mode == "proxy"

            # Pattern 2: Individual repos not in proxy
            standalone = root / "standalone-repo"
            standalone.mkdir()
            standalone_config_dir = standalone / ".code-indexer"
            standalone_config_dir.mkdir()
            standalone_config_file = standalone_config_dir / "config.json"
            standalone_config_data = {
                "codebase_dir": str(standalone),
                "proxy_mode": False,
            }
            with open(standalone_config_file, "w") as f:
                json.dump(standalone_config_data, f)

            # Detection should find regular mode
            config_path, mode = ConfigManager.detect_mode(standalone)
            assert config_path == standalone
            assert mode == "regular"
