"""Manual test script to verify legacy config error messages.

Run this to manually test that legacy configurations are properly rejected
with clear error messages.
"""

import json
import tempfile
from pathlib import Path

from code_indexer.config import ConfigManager


def test_filesystem_config_error():
    """Test Filesystem configuration rejection."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        config_path = Path(tmp_dir) / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True)

        # Create config with legacy filesystem_config
        config_data = {
            "codebase_dir": str(tmp_dir),
            "filesystem_config": {"host": "localhost", "port": 6333},
        }

        with open(config_path, "w") as f:
            json.dump(config_data, f)

        manager = ConfigManager(config_path)
        try:
            manager.load()
            print("❌ FAILED: Filesystem config should have been rejected")
        except ValueError as e:
            print("✅ PASSED: Filesystem config rejected with message:")
            print(f"   {str(e)[:200]}...")


def test_voyage_config_error():
    """Test Voyage configuration rejection."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        config_path = Path(tmp_dir) / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True)

        # Create config with legacy voyage_config
        config_data = {
            "codebase_dir": str(tmp_dir),
            "voyage_config": {"model": "codellama"},
        }

        with open(config_path, "w") as f:
            json.dump(config_data, f)

        manager = ConfigManager(config_path)
        try:
            manager.load()
            print("❌ FAILED: Voyage config should have been rejected")
        except ValueError as e:
            print("✅ PASSED: Voyage config rejected with message:")
            print(f"   {str(e)[:200]}...")


def test_container_config_error():
    """Test container configuration rejection."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        config_path = Path(tmp_dir) / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True)

        # Create config with legacy project_containers
        config_data = {
            "codebase_dir": str(tmp_dir),
            "project_containers": {"project_hash": "abc123"},
        }

        with open(config_path, "w") as f:
            json.dump(config_data, f)

        manager = ConfigManager(config_path)
        try:
            manager.load()
            print("❌ FAILED: Container config should have been rejected")
        except ValueError as e:
            print("✅ PASSED: Container config rejected with message:")
            print(f"   {str(e)[:200]}...")


def test_valid_config():
    """Test that valid filesystem config is accepted."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        config_path = Path(tmp_dir) / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True)

        # Create valid config
        config_data = {
            "codebase_dir": str(tmp_dir),
            "embedding_provider": "voyage-ai",
            "vector_store": {"provider": "filesystem"},
        }

        with open(config_path, "w") as f:
            json.dump(config_data, f)

        manager = ConfigManager(config_path)
        try:
            config = manager.load()
            print("✅ PASSED: Valid filesystem config accepted")
            print(
                f"   Provider: {config.embedding_provider}, Backend: {config.vector_store.provider}"
            )
        except Exception as e:
            print(f"❌ FAILED: Valid config rejected: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("Manual Testing: Legacy Configuration Rejection")
    print("=" * 60)
    print()

    test_filesystem_config_error()
    print()

    test_voyage_config_error()
    print()

    test_container_config_error()
    print()

    test_valid_config()
    print()

    print("=" * 60)
    print("Manual testing complete")
    print("=" * 60)
