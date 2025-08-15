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
import tempfile
import time
import json
from pathlib import Path
from typing import Dict, List, Any

import pytest
import requests  # type: ignore


pytestmark = [pytest.mark.e2e, pytest.mark.slow]


@pytest.fixture
def git_test_repo():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir)

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
        )

        # Create initial project structure
        (repo_path / "src").mkdir()
        (repo_path / "tests").mkdir()

        # Add initial files
        (repo_path / "src" / "main.py").write_text(
            "def main():\n    print('Hello World')\n"
        )
        (repo_path / "src" / "utils.py").write_text(
            "def helper():\n    return 'helper'\n"
        )
        (repo_path / "tests" / "test_main.py").write_text(
            "def test_main():\n    assert True\n"
        )
        (repo_path / "README.md").write_text("# Test Project\n\nThis is a test.\n")

        # Create .gitignore to prevent committing .code-indexer directory
        (repo_path / ".gitignore").write_text(
            """.code-indexer/
__pycache__/
*.pyc
.pytest_cache/
venv/
.env
"""
        )

        # Initial commit
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True
        )

        yield repo_path


def run_cli_command(
    cmd: List[str], cwd: Path, expect_success: bool = True
) -> subprocess.CompletedProcess:
    """Run a CLI command and optionally verify success."""
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=120  # 2 minute timeout
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


class TestGitIndexingConsistency:
    """Test git indexing consistency using CLI commands only."""

    def test_git_project_creates_only_modern_points(self, git_test_repo):
        """Test that git projects create only modern points with 'type' field."""
        # Initialize code-indexer
        run_cli_command(
            ["code-indexer", "init", "--embedding-provider", "voyage-ai"], git_test_repo
        )

        # Start services
        run_cli_command(["code-indexer", "start"], git_test_repo)

        try:
            # Perform initial indexing
            run_cli_command(["code-indexer", "index"], git_test_repo)

            # Get Qdrant configuration
            qdrant_config = get_qdrant_config(git_test_repo)
            qdrant_url = qdrant_config["host"]
            collection_name = "code_index__voyage_code_3"

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

        finally:
            # Stop services
            run_cli_command(
                ["code-indexer", "stop"], git_test_repo, expect_success=False
            )

    def test_reconcile_maintains_git_aware_consistency(self, git_test_repo):
        """Test that reconcile operations maintain git-aware consistency."""
        # Initialize and start services
        run_cli_command(
            ["code-indexer", "init", "--embedding-provider", "voyage-ai"], git_test_repo
        )
        run_cli_command(["code-indexer", "start"], git_test_repo)

        try:
            # Initial indexing
            run_cli_command(["code-indexer", "index"], git_test_repo)

            # Get initial point count
            qdrant_config = get_qdrant_config(git_test_repo)
            qdrant_url = qdrant_config["host"]
            collection_name = "code_index__voyage_code_3"

            initial_points = get_qdrant_points(qdrant_url, collection_name)
            initial_categorized = categorize_points_by_schema(initial_points)

            # Verify initial state is all modern
            assert (
                len(initial_categorized["legacy"]) == 0
            ), "Should start with no legacy points"

            # Modify existing file
            test_file = git_test_repo / "src" / "main.py"
            test_file.write_text(
                "def main():\n    print('Modified Hello World')\n    return 'modified'\n"
            )

            # Wait for filesystem timestamp resolution
            time.sleep(1.1)

            # Perform reconcile
            run_cli_command(["code-indexer", "index", "--reconcile"], git_test_repo)

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
            ), "Should maintain modern points after reconcile"

        finally:
            # Stop services
            run_cli_command(
                ["code-indexer", "stop"], git_test_repo, expect_success=False
            )

    def test_git_indexing_fails_fast_on_errors(self, git_test_repo):
        """Test that git indexing fails fast rather than falling back to legacy processing."""
        # Initialize and start services
        run_cli_command(
            ["code-indexer", "init", "--embedding-provider", "voyage-ai"], git_test_repo
        )
        run_cli_command(["code-indexer", "start"], git_test_repo)

        try:
            # Initial indexing should work
            run_cli_command(["code-indexer", "index"], git_test_repo)

            # Stop Qdrant service to simulate failure
            run_cli_command(["code-indexer", "stop"], git_test_repo)

            # Modify file
            test_file = git_test_repo / "src" / "utils.py"
            test_file.write_text("def helper():\n    return 'modified helper'\n")

            # Indexing should fail fast, not fall back
            result = run_cli_command(
                ["code-indexer", "index", "--reconcile"],
                git_test_repo,
                expect_success=False,
            )

            # Should fail with clear error, not succeed with legacy fallback
            assert result.returncode != 0, "Should fail when services unavailable"
            error_text = (result.stderr + result.stdout).lower()
            assert (
                "git-aware" in error_text
                or "failed" in error_text
                or "not available" in error_text
                or "qdrant" in error_text
            ), f"Should fail with clear error message. Got: stdout='{result.stdout}', stderr='{result.stderr}'"

        finally:
            # Restart services for cleanup
            run_cli_command(
                ["code-indexer", "start"], git_test_repo, expect_success=False
            )
            run_cli_command(
                ["code-indexer", "stop"], git_test_repo, expect_success=False
            )

    def test_branch_operations_maintain_consistency(self, git_test_repo):
        """Test that branch operations maintain git-aware consistency."""
        # Initialize and start services
        run_cli_command(
            ["code-indexer", "init", "--embedding-provider", "voyage-ai"], git_test_repo
        )
        run_cli_command(["code-indexer", "start"], git_test_repo)

        try:
            # Initial indexing on master
            run_cli_command(["code-indexer", "index"], git_test_repo)

            # Create and switch to feature branch
            subprocess.run(
                ["git", "checkout", "-b", "feature"], cwd=git_test_repo, check=True
            )

            # Add feature-specific file
            feature_file = git_test_repo / "src" / "feature.py"
            feature_file.write_text("def feature_function():\n    return 'feature'\n")

            subprocess.run(
                ["git", "add", "src/feature.py"], cwd=git_test_repo, check=True
            )
            subprocess.run(
                ["git", "commit", "-m", "Add feature"], cwd=git_test_repo, check=True
            )

            # Index on feature branch
            run_cli_command(["code-indexer", "index"], git_test_repo)

            # Switch back to master
            subprocess.run(["git", "checkout", "master"], cwd=git_test_repo, check=True)

            # Index on master (should trigger branch transition)
            run_cli_command(["code-indexer", "index"], git_test_repo)

            # Verify all points are still modern
            qdrant_config = get_qdrant_config(git_test_repo)
            qdrant_url = qdrant_config["host"]
            collection_name = "code_index__voyage_code_3"

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

        finally:
            # Stop services
            run_cli_command(
                ["code-indexer", "stop"], git_test_repo, expect_success=False
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
