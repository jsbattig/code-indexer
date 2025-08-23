"""
E2E tests for git indexing consistency - prevents regression to legacy fallbacks.

These tests verify that:
1. Git projects always use git-aware indexing (no fallbacks)
2. All points created have consistent schema with 'type' field
3. Reconcile operations maintain git-aware consistency
4. System fails fast rather than falling back to legacy processing

Uses CLI commands only - no mocking or monkey patching.
"""

import subprocess
import time
import json
from pathlib import Path
from typing import Dict, List, Any

import pytest
import requests  # type: ignore

from tests.conftest import shared_container_test_environment
from .infrastructure import EmbeddingProvider


pytestmark = [pytest.mark.e2e, pytest.mark.slow]


def create_git_test_repo(project_path: Path) -> Path:
    """Create a git repository for testing in the given path."""
    # Initialize git repo
    subprocess.run(["git", "init"], cwd=project_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=project_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=project_path, check=True
    )

    # Create initial project structure
    (project_path / "src").mkdir(exist_ok=True)
    (project_path / "tests").mkdir(exist_ok=True)

    # Add initial files
    (project_path / "src" / "main.py").write_text(
        "def main():\n    print('Hello World')\n"
    )
    (project_path / "src" / "utils.py").write_text(
        "def helper():\n    return 'helper'\n"
    )
    (project_path / "tests" / "test_main.py").write_text(
        "def test_main():\n    assert True\n"
    )
    (project_path / "README.md").write_text("# Test Project\n\nThis is a test.\n")

    # Create .gitignore to prevent committing .code-indexer directory
    (project_path / ".gitignore").write_text(
        """.code-indexer/
__pycache__/
*.pyc
.pytest_cache/
venv/
.env
"""
    )

    # Initial commit
    subprocess.run(["git", "add", "."], cwd=project_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"], cwd=project_path, check=True
    )

    return project_path


def run_cli_command(
    cmd: List[str], cwd: Path, expect_success: bool = True
) -> subprocess.CompletedProcess:
    """Run a CLI command and optionally verify success."""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,  # 2 minute timeout
    )

    if expect_success and result.returncode != 0:
        pytest.fail(
            f"Command {' '.join(cmd)} failed with code {result.returncode}.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )

    return result


def get_qdrant_points(qdrant_url: str, collection_name: str) -> List[Dict[str, Any]]:
    """Get all points from Qdrant collection via HTTP API."""
    scroll_url = f"{qdrant_url}/collections/{collection_name}/points/scroll"

    all_points = []
    offset = None

    while True:
        payload = {"limit": 1000, "with_payload": True, "with_vector": False}
        if offset:
            payload["offset"] = offset

        response = requests.post(scroll_url, json=payload, timeout=30)
        response.raise_for_status()

        data = response.json()
        points = data.get("result", {}).get("points", [])

        if not points:
            break

        all_points.extend(points)
        offset = data.get("result", {}).get("next_page_offset")

        if offset is None:
            break

    return all_points


def categorize_points_by_schema(
    points: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Categorize points by their schema type."""
    modern_points = []
    legacy_points = []
    unknown_points = []

    for point in points:
        payload = point.get("payload", {})

        # Modern architecture: has 'type' field
        if "type" in payload:
            modern_points.append(point)
        # Legacy architecture: has 'git_branch' but no 'type' field
        elif "git_branch" in payload:
            legacy_points.append(point)
        else:
            unknown_points.append(point)

    return {"modern": modern_points, "legacy": legacy_points, "unknown": unknown_points}


def get_qdrant_config(repo_path: Path) -> Dict[str, Any]:
    """Get Qdrant configuration from project config."""
    config_path = repo_path / ".code-indexer" / "config.json"
    with open(config_path, "r") as f:
        config = json.load(f)
    return config["qdrant"]  # type: ignore


def get_actual_collection_name(
    qdrant_url: str, expected_suffix: str = "voyage_code_3"
) -> str:
    """Get the actual collection name from Qdrant, matching the expected suffix."""
    try:
        response = requests.get(f"{qdrant_url}/collections", timeout=30)
        response.raise_for_status()
        collections = response.json().get("result", {}).get("collections", [])

        # Find collection with expected suffix
        for collection in collections:
            name = str(collection.get("name", ""))
            if name.endswith(expected_suffix):
                return name

        # Fallback to default if not found
        return f"code_index__{expected_suffix}"
    except Exception:
        # Fallback to default if API call fails
        return f"code_index__{expected_suffix}"


class TestGitIndexingConsistency:
    """Test git indexing consistency using CLI commands only."""

    def test_git_project_creates_only_modern_points(self):
        """Test that git projects create only modern points with 'type' field."""
        with shared_container_test_environment(
            "test_git_project_creates_only_modern_points", EmbeddingProvider.VOYAGE_AI
        ) as project_path:
            # Create git repository in the shared project path
            create_git_test_repo(project_path)

            # Shared container environment already handles init, start, and cleanup

            # Perform initial indexing (cleanup handled by shared environment)
            result = run_cli_command(["code-indexer", "index"], project_path)

            # Get configuration after indexing (ensures config file exists)
            qdrant_config = get_qdrant_config(project_path)
            qdrant_url = qdrant_config["host"]
            collection_name = get_actual_collection_name(qdrant_url)

            # Check if we have vector dimension mismatch and need to recreate collection
            if "Collection vector size mismatch" in result.stdout:
                # Force collection deletion to ensure correct dimensions
                delete_url = f"{qdrant_url}/collections/{collection_name}"
                try:
                    requests.delete(delete_url, timeout=30)
                    print("Deleted collection due to vector size mismatch")
                except Exception:
                    pass  # Collection might not exist
                time.sleep(2)

                # Re-index with clean collection
                run_cli_command(["code-indexer", "index"], project_path)

            # Get all points from Qdrant
            points = get_qdrant_points(qdrant_url, collection_name)
            assert len(points) > 0, "Should have created some points"

            # Categorize points by schema
            categorized = categorize_points_by_schema(points)

            # CRITICAL: Git projects should ONLY create modern points
            assert len(categorized["legacy"]) == 0, (
                f"Found {len(categorized['legacy'])} legacy points in git project! "
                f"This indicates fallback to legacy processing occurred."
            )

            assert (
                len(categorized["modern"]) > 0
            ), "Should have created modern points with 'type' field"

            # Verify all modern points have required fields
            for point in categorized["modern"]:
                payload = point["payload"]
                assert "type" in payload, "Modern points must have 'type' field"
                assert (
                    payload["type"] == "content"
                ), "Git projects should create content points"
                # Modern content points don't have git_branch field
                # They use hidden_branches array for branch visibility management
                assert (
                    "git_commit" in payload
                ), "Git projects should have git_commit field"
                assert (
                    "hidden_branches" in payload
                ), "Git projects should have hidden_branches field"

    def test_reconcile_maintains_git_aware_consistency(self):
        """Test that reconcile operations maintain git-aware consistency."""
        with shared_container_test_environment(
            "test_reconcile_maintains_git_aware_consistency",
            EmbeddingProvider.VOYAGE_AI,
        ) as project_path:
            # Create git repository in the shared project path
            create_git_test_repo(project_path)

            # Shared container environment already handles init and start

            # Get configuration before cleaning
            qdrant_config = get_qdrant_config(project_path)
            qdrant_url = qdrant_config["host"]
            collection_name = get_actual_collection_name(qdrant_url)

            # Shared environment handles cleanup - no manual cleaning needed

            # Perform initial indexing
            run_cli_command(["code-indexer", "index"], project_path)

            # Get initial point count
            initial_points = get_qdrant_points(qdrant_url, collection_name)
            initial_categorized = categorize_points_by_schema(initial_points)

            # Verify initial state is all modern
            assert (
                len(initial_categorized["legacy"]) == 0
            ), "Should start with no legacy points"

            # Verify we have some points from initial indexing
            assert (
                len(initial_points) > 0
            ), f"Initial indexing should create points. Collection: {collection_name}, URL: {qdrant_url}"

            # Modify existing file
            test_file = project_path / "src" / "main.py"
            test_file.write_text(
                "def main():\n    print('Modified Hello World')\n    return 'modified'\n"
            )

            # Wait for filesystem timestamp resolution
            time.sleep(1.1)

            # Perform reconcile
            run_cli_command(["code-indexer", "index", "--reconcile"], project_path)

            # Get points after reconcile
            reconcile_points = get_qdrant_points(qdrant_url, collection_name)
            reconcile_categorized = categorize_points_by_schema(reconcile_points)

            # CRITICAL: Reconcile should NOT create legacy points
            assert len(reconcile_categorized["legacy"]) == 0, (
                f"Reconcile created {len(reconcile_categorized['legacy'])} legacy points! "
                f"This indicates BranchAwareIndexer failed and fell back to legacy processing."
            )

            # Should still have modern points
            assert (
                len(reconcile_categorized["modern"]) > 0
            ), f"Should maintain modern points after reconcile. Found {len(reconcile_points)} total points, {len(reconcile_categorized['modern'])} modern, {len(reconcile_categorized['legacy'])} legacy"

    def test_git_indexing_handles_git_errors_without_fallback(self):
        """Test that git indexing handles git errors without falling back to legacy processing."""
        with shared_container_test_environment(
            "test_git_indexing_handles_git_errors_without_fallback",
            EmbeddingProvider.VOYAGE_AI,
        ) as project_path:
            # Create git repository in the shared project path
            create_git_test_repo(project_path)

            # Shared container environment already handles init, start, and cleanup

            # Perform initial indexing
            result = run_cli_command(["code-indexer", "index"], project_path)

            # Get configuration after indexing (ensures config file exists)
            qdrant_config = get_qdrant_config(project_path)
            qdrant_url = qdrant_config["host"]
            collection_name = get_actual_collection_name(qdrant_url)

            # Check if we have vector dimension mismatch and need to recreate collection
            if "Collection vector size mismatch" in result.stdout:
                # Force collection deletion to ensure correct dimensions
                delete_url = f"{qdrant_url}/collections/{collection_name}"
                try:
                    requests.delete(delete_url, timeout=30)
                    print("Deleted collection due to vector size mismatch")
                except Exception:
                    pass  # Collection might not exist
                time.sleep(2)

                # Re-index with clean collection
                run_cli_command(["code-indexer", "index"], project_path)

            # Create a condition where git-aware indexing might encounter issues
            # by corrupting the git repository state temporarily
            git_dir = project_path / ".git"
            git_backup = project_path / ".git_backup"

            # Backup git directory and remove it to simulate git failure
            subprocess.run(
                ["mv", str(git_dir), str(git_backup)], cwd=project_path, check=True
            )

            # Modify file
            test_file = project_path / "src" / "utils.py"
            test_file.write_text("def helper():\n    return 'modified helper'\n")

            # Indexing should handle git unavailability gracefully
            # but should not fall back to legacy processing
            result = run_cli_command(
                ["code-indexer", "index", "--reconcile"],
                project_path,
                expect_success=False,
            )

            # Should either succeed with proper handling or fail fast
            # but NOT create legacy points
            if result.returncode == 0:
                # If it succeeds, verify no legacy points were created
                points = get_qdrant_points(qdrant_url, collection_name)
                categorized = categorize_points_by_schema(points)

                assert len(categorized["legacy"]) == 0, (
                    f"Found {len(categorized['legacy'])} legacy points! "
                    f"Git failure should not trigger legacy fallback."
                )
            else:
                # If it fails, that's also acceptable - we just don't want legacy fallback
                print(f"Indexing failed as expected: {result.stderr}")

            # Restore git repository for next test (shared container strategy)
            subprocess.run(
                ["mv", str(git_backup), str(git_dir)], cwd=project_path, check=True
            )

    def test_branch_operations_maintain_consistency(self):
        """Test that branch operations maintain git-aware consistency."""
        with shared_container_test_environment(
            "test_branch_operations_maintain_consistency", EmbeddingProvider.VOYAGE_AI
        ) as project_path:
            # Create git repository in the shared project path
            create_git_test_repo(project_path)

            # Shared container environment already handles init, start, and cleanup

            # Perform initial indexing
            result = run_cli_command(["code-indexer", "index"], project_path)

            # Get configuration after indexing (ensures config file exists)
            qdrant_config = get_qdrant_config(project_path)
            qdrant_url = qdrant_config["host"]
            collection_name = get_actual_collection_name(qdrant_url)

            # Check if we have vector dimension mismatch and need to recreate collection
            if "Collection vector size mismatch" in result.stdout:
                # Force collection deletion to ensure correct dimensions
                delete_url = f"{qdrant_url}/collections/{collection_name}"
                try:
                    requests.delete(delete_url, timeout=30)
                    print("Deleted collection due to vector size mismatch")
                except Exception:
                    pass  # Collection might not exist
                time.sleep(2)

                # Re-index with clean collection
                run_cli_command(["code-indexer", "index"], project_path)

            # Create and switch to feature branch
            subprocess.run(
                ["git", "checkout", "-b", "feature"], cwd=project_path, check=True
            )

            # Add feature-specific file
            feature_file = project_path / "src" / "feature.py"
            feature_file.write_text("def feature_function():\n    return 'feature'\n")

            subprocess.run(
                ["git", "add", "src/feature.py"], cwd=project_path, check=True
            )
            subprocess.run(
                ["git", "commit", "-m", "Add feature"], cwd=project_path, check=True
            )

            # Index on feature branch
            run_cli_command(["code-indexer", "index"], project_path)

            # Switch back to master
            subprocess.run(["git", "checkout", "master"], cwd=project_path, check=True)

            # Index on master (should trigger branch transition)
            run_cli_command(["code-indexer", "index"], project_path)

            # Verify all points are still modern
            points = get_qdrant_points(qdrant_url, collection_name)
            categorized = categorize_points_by_schema(points)

            # All points should still be modern after branch operations
            assert len(categorized["legacy"]) == 0, (
                f"Branch operations created {len(categorized['legacy'])} legacy points! "
                f"This indicates fallback to legacy processing."
            )

            assert (
                len(categorized["modern"]) > 0
            ), "Should have modern points after branch operations"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
