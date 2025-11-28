"""
End-to-end tests for global repo query integration (AC2).

Tests that users can query global repos immediately after registration
using the {repo-name}-global alias.
"""

import os
import subprocess
import tempfile
from pathlib import Path
import pytest

from code_indexer.global_repos.alias_manager import AliasManager
from code_indexer.global_repos.global_registry import GlobalRegistry
from code_indexer.global_repos.global_activation import GlobalActivator


class TestGlobalQueryE2E:
    """
    E2E tests for AC2: Immediate Query Availability.

    These tests verify that after a golden repo is registered and globally
    activated, users can immediately query it using the global alias.
    """

    def test_query_global_alias_resolves_to_index_path(self):
        """
        Test that query resolution recognizes global aliases and resolves them.

        AC2 Requirement: Query resolution recognizes "-global" suffix aliases
        and reads alias pointer to locate index directory.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup directories
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            index_dir = Path(tmpdir) / "index"
            index_dir.mkdir(parents=True)

            # Create a global activation for a test repo
            activator = GlobalActivator(str(golden_repos_dir))
            activator.activate_golden_repo(
                repo_name="test-repo",
                repo_url="https://github.com/test/repo.git",
                clone_path=str(index_dir),
            )

            # Verify alias was created
            alias_manager = AliasManager(str(golden_repos_dir / "aliases"))
            resolved_path = alias_manager.read_alias("test-repo-global")

            # This is the key assertion for AC2
            assert resolved_path is not None
            assert resolved_path == str(index_dir)

    def test_global_alias_in_registry(self):
        """
        Test that global activation registers the alias in the global registry.

        AC2 Requirement: Global repo appears in the global repos list.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup directories
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            index_dir = Path(tmpdir) / "index"
            index_dir.mkdir(parents=True)

            # Create a global activation
            activator = GlobalActivator(str(golden_repos_dir))
            activator.activate_golden_repo(
                repo_name="test-repo",
                repo_url="https://github.com/test/repo.git",
                clone_path=str(index_dir),
            )

            # Verify in registry
            registry = GlobalRegistry(str(golden_repos_dir))
            global_repos = registry.list_global_repos()

            assert len(global_repos) == 1
            assert global_repos[0]["alias_name"] == "test-repo-global"
            assert global_repos[0]["repo_name"] == "test-repo"
            assert global_repos[0]["index_path"] == str(index_dir)

    def test_multiple_global_aliases_resolve_correctly(self):
        """
        Test that multiple global repos can coexist and resolve correctly.

        AC2 Requirement: Multiple global aliases don't conflict.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup directories
            golden_repos_dir = Path(tmpdir) / "golden-repos"

            # Create multiple global activations
            activator = GlobalActivator(str(golden_repos_dir))

            for i in range(3):
                index_dir = Path(tmpdir) / f"index-{i}"
                index_dir.mkdir(parents=True)

                activator.activate_golden_repo(
                    repo_name=f"test-repo-{i}",
                    repo_url=f"https://github.com/test/repo{i}.git",
                    clone_path=str(index_dir),
                )

            # Verify all aliases resolve correctly
            alias_manager = AliasManager(str(golden_repos_dir / "aliases"))

            for i in range(3):
                resolved_path = alias_manager.read_alias(f"test-repo-{i}-global")
                expected_path = str(Path(tmpdir) / f"index-{i}")

                assert resolved_path == expected_path

            # Verify all in registry
            registry = GlobalRegistry(str(golden_repos_dir))
            global_repos = registry.list_global_repos()

            assert len(global_repos) == 3
            for i in range(3):
                assert any(
                    repo["alias_name"] == f"test-repo-{i}-global"
                    for repo in global_repos
                )

    @pytest.mark.skipif(
        not os.environ.get("VOYAGE_API_KEY"),
        reason="Requires VOYAGE_API_KEY for embedding-based test",
    )
    def test_query_with_repo_flag_uses_global_alias(self):
        """
        Test that cidx query --repo flag resolves global aliases correctly.

        AC2 Requirement: Query integration with --repo flag for CLI.
        This test proves the complete vertical slice:
        1. Register global repo (create alias)
        2. Query using --repo flag
        3. Verify results are returned from global repo
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup: Create a real git repo with indexed content
            repo_dir = Path(tmpdir) / "test-repo"
            repo_dir.mkdir(parents=True)

            # Initialize git repo
            subprocess.run(
                ["git", "init"], cwd=repo_dir, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=repo_dir,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repo_dir,
                check=True,
                capture_output=True,
            )

            # Create some test files with content
            test_file = repo_dir / "auth.py"
            test_file.write_text(
                "def authenticate_user(username, password):\n    pass\n"
            )

            subprocess.run(
                ["git", "add", "."], cwd=repo_dir, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=repo_dir,
                check=True,
                capture_output=True,
            )

            # Index the repository
            subprocess.run(
                ["cidx", "init"], cwd=repo_dir, check=True, capture_output=True
            )

            subprocess.run(
                ["cidx", "index"], cwd=repo_dir, check=True, capture_output=True
            )

            # Setup global activation
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            activator = GlobalActivator(str(golden_repos_dir))
            activator.activate_golden_repo(
                repo_name="test-repo",
                repo_url="https://github.com/test/repo.git",
                clone_path=str(repo_dir / ".code-indexer" / "index"),
            )

            # Test: Query using --repo flag from a different directory
            query_dir = Path(tmpdir) / "query-from-here"
            query_dir.mkdir(parents=True)

            # CRITICAL: Set CIDX_GOLDEN_REPOS_DIR env var so cidx knows where to find global repos
            env = {
                **subprocess.os.environ,
                "CIDX_GOLDEN_REPOS_DIR": str(golden_repos_dir),
            }

            result = subprocess.run(
                [
                    "cidx",
                    "query",
                    "authenticate",
                    "--repo",
                    "test-repo-global",
                    "--quiet",
                ],
                cwd=query_dir,
                capture_output=True,
                text=True,
                env=env,
            )

            # Verify: Query succeeded and returned results
            assert (
                result.returncode == 0
            ), f"Query failed: stdout={result.stdout}, stderr={result.stderr}"
            assert (
                "authenticate_user" in result.stdout
            ), f"Expected function not found in results: {result.stdout}"
            assert (
                "auth.py" in result.stdout
            ), f"Expected file not found in results: {result.stdout}"


# NOTE: The actual MCP/REST query integration will be tested after CLI implementation.
# CLI integration is the foundation - MCP/REST will follow the same pattern.
