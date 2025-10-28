"""E2E tests for cidx init --vector-store CLI integration.

Tests verify that the --vector-store flag correctly creates configurations
and initializes backends for both filesystem and qdrant options.
"""

import json
import subprocess
from pathlib import Path


class TestCidxInitVectorStoreIntegration:
    """E2E tests for cidx init command with --vector-store flag."""

    def test_cidx_init_defaults_to_filesystem_with_explicit_config(
        self, tmp_path: Path
    ):
        """cidx init (no flag) should create filesystem backend config by default."""
        test_dir = tmp_path / "test_project"
        test_dir.mkdir()

        # Run cidx init without --vector-store flag
        result = subprocess.run(
            ["cidx", "init", "--codebase-dir", str(test_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Verify config file created
        config_path = test_dir / ".code-indexer" / "config.json"
        assert config_path.exists(), "Config file should be created"

        # Verify vector_store configuration
        with open(config_path) as f:
            config_data = json.load(f)

        assert "vector_store" in config_data, "Config should have vector_store field"
        assert config_data["vector_store"]["provider"] == "filesystem"

        # Verify backend initialized (directory structure created)
        index_dir = test_dir / ".code-indexer" / "index"
        assert index_dir.exists(), "Filesystem backend should create index directory"

    def test_cidx_init_with_filesystem_flag(self, tmp_path: Path):
        """cidx init --vector-store filesystem should create filesystem config."""
        test_dir = tmp_path / "test_project"
        test_dir.mkdir()

        result = subprocess.run(
            [
                "cidx",
                "init",
                "--codebase-dir",
                str(test_dir),
                "--vector-store",
                "filesystem",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Init failed: {result.stderr}"

        config_path = test_dir / ".code-indexer" / "config.json"
        with open(config_path) as f:
            config_data = json.load(f)

        assert config_data["vector_store"]["provider"] == "filesystem"

        # Verify no port allocations for filesystem backend
        # project_ports should exist but have None values
        assert "project_ports" in config_data, "project_ports should exist in config"
        assert (
            config_data["project_ports"]["qdrant_port"] is None
        ), "Qdrant port should be None for filesystem"
        assert (
            config_data["project_ports"]["ollama_port"] is None
        ), "Ollama port should be None for filesystem"
        assert (
            config_data["project_ports"]["data_cleaner_port"] is None
        ), "Data cleaner port should be None for filesystem"

        index_dir = test_dir / ".code-indexer" / "index"
        assert index_dir.exists(), "Backend should be initialized"

    def test_cidx_init_with_qdrant_flag(self, tmp_path: Path):
        """cidx init --vector-store qdrant should create qdrant config."""
        test_dir = tmp_path / "test_project"
        test_dir.mkdir()

        result = subprocess.run(
            [
                "cidx",
                "init",
                "--codebase-dir",
                str(test_dir),
                "--vector-store",
                "qdrant",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Init failed: {result.stderr}"

        config_path = test_dir / ".code-indexer" / "config.json"
        with open(config_path) as f:
            config_data = json.load(f)

        assert config_data["vector_store"]["provider"] == "qdrant"

        # Qdrant backend initialization is a stub, so we just verify config correctness
