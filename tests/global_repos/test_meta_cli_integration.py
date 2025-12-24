"""
CLI Integration Tests for Meta-Directory Initialization.

Tests the complete workflow via CLI: initialize meta-directory,
register repos, query meta-directory.
"""

import subprocess


class TestMetaDirectoryCLIIntegration:
    """CLI integration test suite for meta-directory."""

    def test_global_init_meta_command_creates_meta_directory(self, tmp_path):
        """
        Test that 'cidx global init-meta' command creates meta-directory.

        This test will FAIL until the CLI command is implemented.
        """
        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        # Set environment variable for test isolation
        env = {"CIDX_GOLDEN_REPOS_DIR": str(golden_repos_dir)}

        # Run CLI command
        result = subprocess.run(
            ["cidx", "global", "init-meta"],
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
        )

        # Command should succeed
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Verify meta-directory created
        meta_dir = golden_repos_dir / "cidx-meta"
        assert meta_dir.exists(), "Meta-directory not created"
        assert meta_dir.is_dir(), "Meta-directory is not a directory"

    def test_init_meta_registers_meta_directory_in_registry(self, tmp_path):
        """
        Test that meta-directory is registered in global registry.

        This test will FAIL until the CLI command properly registers.
        """
        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        env = {"CIDX_GOLDEN_REPOS_DIR": str(golden_repos_dir)}

        # Run init-meta command
        result = subprocess.run(
            ["cidx", "global", "init-meta"],
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Verify registry entry exists
        registry_file = golden_repos_dir / "global_registry.json"
        assert registry_file.exists(), "Registry file not created"

        import json

        with open(registry_file) as f:
            registry_data = json.load(f)

        assert "cidx-meta-global" in registry_data, "Meta-directory not registered"
        meta_entry = registry_data["cidx-meta-global"]
        assert (
            meta_entry["repo_url"] is None
        ), "Meta-directory should have repo_url=None"
        assert meta_entry["repo_name"] == "cidx-meta"

    def test_init_meta_generates_descriptions_for_existing_repos(self, tmp_path):
        """
        Test that init-meta generates descriptions for pre-existing repos.

        This test will FAIL until migration logic is triggered by CLI.
        """
        from code_indexer.global_repos.global_registry import GlobalRegistry

        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        # Pre-register a test repo
        registry = GlobalRegistry(str(golden_repos_dir))

        test_repo = tmp_path / "test-repo"
        test_repo.mkdir()
        (test_repo / "README.md").write_text("# Test Repo\n\nA test repository.")

        registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://github.com/org/test-repo",
            index_path=str(test_repo),
        )

        env = {"CIDX_GOLDEN_REPOS_DIR": str(golden_repos_dir)}

        # Run init-meta command
        result = subprocess.run(
            ["cidx", "global", "init-meta"],
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Verify description file created
        meta_dir = golden_repos_dir / "cidx-meta"
        desc_file = meta_dir / "test-repo.md"
        assert desc_file.exists(), "Description file not created for existing repo"

        desc_content = desc_file.read_text()
        assert "test-repo" in desc_content, "Description should contain repo name"

    def test_init_meta_idempotent_can_run_multiple_times(self, tmp_path):
        """
        Test that init-meta is idempotent and can be run multiple times.

        This test will FAIL until proper idempotency is implemented.
        """
        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        env = {"CIDX_GOLDEN_REPOS_DIR": str(golden_repos_dir)}

        # Run init-meta first time
        result1 = subprocess.run(
            ["cidx", "global", "init-meta"],
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
        )
        assert result1.returncode == 0, f"First run failed: {result1.stderr}"

        # Run init-meta second time
        result2 = subprocess.run(
            ["cidx", "global", "init-meta"],
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
        )
        assert result2.returncode == 0, f"Second run failed: {result2.stderr}"

        # Both runs should succeed
        meta_dir = golden_repos_dir / "cidx-meta"
        assert meta_dir.exists(), "Meta-directory should exist after both runs"
