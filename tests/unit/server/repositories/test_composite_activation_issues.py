"""
Tests for composite repository activation issues discovered during manual testing.

This test module validates fixes for three critical issues:
1. Repository discovery failure - discovered_repos is empty after activation
2. Repository listing validation error - GET /api/repos fails with Pydantic errors
3. Query execution anomaly - queries search wrong number of repositories

These tests follow TDD methodology - they are written to fail first, then
implementation fixes will make them pass.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_indexer.server.repositories.activated_repo_manager import (
    ActivatedRepoManager,
)
from code_indexer.server.repositories.golden_repo_manager import (
    GoldenRepoManager,
    GoldenRepo,
)


@pytest.fixture
def temp_data_dir():
    """Create temporary data directory for testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def golden_repo_manager(temp_data_dir):
    """Create golden repo manager with two test repositories."""
    manager = GoldenRepoManager(temp_data_dir)

    # Create two fake golden repositories
    golden_repos_dir = os.path.join(temp_data_dir, "golden-repos")
    os.makedirs(golden_repos_dir, exist_ok=True)

    # Create click repository
    click_repo_path = os.path.join(golden_repos_dir, "click")
    os.makedirs(click_repo_path, exist_ok=True)

    # Create .code-indexer directory with config.json (simulates indexed repository)
    click_config_dir = os.path.join(click_repo_path, ".code-indexer")
    os.makedirs(click_config_dir, exist_ok=True)
    click_config = {
        "embedding_provider": "voyage-ai",
        "proxy_mode": False,
        "discovered_repos": [],
    }
    with open(os.path.join(click_config_dir, "config.json"), "w") as f:
        json.dump(click_config, f)

    # Initialize as a proper git repository
    import subprocess

    subprocess.run(
        ["git", "init"], cwd=click_repo_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=click_repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=click_repo_path,
        check=True,
        capture_output=True,
    )

    # Create a dummy file and commit it
    dummy_file = os.path.join(click_repo_path, "README.md")
    with open(dummy_file, "w") as f:
        f.write("# Click Repository\n")
    subprocess.run(
        ["git", "add", "."], cwd=click_repo_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=click_repo_path,
        check=True,
        capture_output=True,
    )

    # Add to manager
    manager.golden_repos["click"] = GoldenRepo(
        alias="click",
        repo_url="https://github.com/pallets/click.git",
        clone_path=click_repo_path,
        default_branch="main",
        created_at="2025-01-01T00:00:00Z",
    )

    # Create hello-world-test repository
    hello_repo_path = os.path.join(golden_repos_dir, "hello-world-test")
    os.makedirs(hello_repo_path, exist_ok=True)

    # Create .code-indexer directory with config.json
    hello_config_dir = os.path.join(hello_repo_path, ".code-indexer")
    os.makedirs(hello_config_dir, exist_ok=True)
    hello_config = {
        "embedding_provider": "voyage-ai",
        "proxy_mode": False,
        "discovered_repos": [],
    }
    with open(os.path.join(hello_config_dir, "config.json"), "w") as f:
        json.dump(hello_config, f)

    # Initialize as a proper git repository
    subprocess.run(
        ["git", "init"], cwd=hello_repo_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=hello_repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=hello_repo_path,
        check=True,
        capture_output=True,
    )

    # Create a dummy file and commit it
    dummy_file = os.path.join(hello_repo_path, "hello.py")
    with open(dummy_file, "w") as f:
        f.write("print('Hello, World!')\n")
    subprocess.run(
        ["git", "add", "."], cwd=hello_repo_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=hello_repo_path,
        check=True,
        capture_output=True,
    )

    # Add to manager
    manager.golden_repos["hello-world-test"] = GoldenRepo(
        alias="hello-world-test",
        repo_url="https://github.com/test/hello-world.git",
        clone_path=hello_repo_path,
        default_branch="main",
        created_at="2025-01-01T00:00:00Z",
    )

    return manager


@pytest.fixture
def activated_repo_manager(temp_data_dir, golden_repo_manager):
    """Create activated repo manager with golden repo manager."""
    return ActivatedRepoManager(
        data_dir=temp_data_dir, golden_repo_manager=golden_repo_manager
    )


@pytest.mark.e2e
class TestIssue1RepositoryDiscoveryFailure:
    """
    Test Issue #1: Repository discovery failure after composite activation.

    Problem: discovered_repos is empty in metadata after composite activation.
    Expected: discovered_repos should contain ["click", "hello-world-test"].

    Root Cause: .code-indexer directories not copied from golden repos to components.
    """

    def test_composite_activation_populates_discovered_repos(
        self, activated_repo_manager, temp_data_dir
    ):
        """
        Test that composite activation properly populates discovered_repos.

        This test will FAIL initially because _do_activate_composite_repository
        does not copy .code-indexer directories from golden repos to component
        directories during CoW cloning.

        Expected behavior:
        1. CoW clone each golden repo into composite directory
        2. Copy .code-indexer directory from golden repo to component directory
        3. ProxyConfigManager.refresh_repositories() discovers components
        4. Metadata contains discovered_repos: ["click", "hello-world-test"]
        """
        # Activate composite repository
        result = activated_repo_manager._do_activate_composite_repository(
            username="testuser",
            golden_repo_aliases=["click", "hello-world-test"],
            user_alias="composite-test",
        )

        # Verify activation succeeded
        assert result["success"] is True
        assert result["is_composite"] is True

        # Load metadata
        metadata_file = os.path.join(
            temp_data_dir, "activated-repos", "testuser", "composite-test_metadata.json"
        )
        assert os.path.exists(metadata_file), "Metadata file should exist"

        with open(metadata_file, "r") as f:
            metadata = json.load(f)

        # CRITICAL ASSERTION: This will FAIL initially
        # discovered_repos should be populated with component repository names
        assert "discovered_repos" in metadata, "Metadata should have discovered_repos"
        assert (
            len(metadata["discovered_repos"]) == 2
        ), f"Expected 2 discovered repos, got {len(metadata['discovered_repos'])}"
        assert set(metadata["discovered_repos"]) == {
            "click",
            "hello-world-test",
        }, f"Expected ['click', 'hello-world-test'], got {metadata['discovered_repos']}"

    def test_component_directories_have_code_indexer_config(
        self, activated_repo_manager, temp_data_dir
    ):
        """
        Test that component directories contain .code-indexer directories.

        This test validates the root cause fix: .code-indexer directories
        must be copied from golden repos to component directories for
        ProxyConfigManager to discover them.
        """
        # Activate composite repository
        activated_repo_manager._do_activate_composite_repository(
            username="testuser",
            golden_repo_aliases=["click", "hello-world-test"],
            user_alias="composite-test",
        )

        # Check component directories have .code-indexer
        composite_path = (
            Path(temp_data_dir) / "activated-repos" / "testuser" / "composite-test"
        )

        click_config_dir = composite_path / "click" / ".code-indexer"
        assert (
            click_config_dir.exists()
        ), "click component should have .code-indexer directory"
        assert (
            click_config_dir / "config.json"
        ).exists(), "click component should have config.json"

        hello_config_dir = composite_path / "hello-world-test" / ".code-indexer"
        assert (
            hello_config_dir.exists()
        ), "hello-world-test component should have .code-indexer directory"
        assert (
            hello_config_dir / "config.json"
        ).exists(), "hello-world-test component should have config.json"


@pytest.mark.e2e
class TestIssue2RepositoryListingValidationError:
    """
    Test Issue #2: Repository listing fails with Pydantic validation errors.

    Problem: GET /api/repos fails for composite repos with:
        - "golden_repo_alias - Field required"
        - "current_branch - Field required"

    Expected: API should handle composite repos without these fields.

    Root Cause: ActivatedRepositoryInfo model requires fields that don't
                exist for composite repositories.
    """

    def test_list_repositories_handles_composite_repos(
        self, activated_repo_manager, temp_data_dir
    ):
        """
        Test that list_activated_repositories works with composite repos.

        This test will FAIL initially because the API endpoint uses
        ActivatedRepositoryInfo which requires golden_repo_alias and
        current_branch fields that composite repos don't have.
        """
        # Activate composite repository
        activated_repo_manager._do_activate_composite_repository(
            username="testuser",
            golden_repo_aliases=["click", "hello-world-test"],
            user_alias="composite-test",
        )

        # List repositories should not raise validation errors
        repos = activated_repo_manager.list_activated_repositories("testuser")

        assert len(repos) == 1, "Should have 1 activated repository"

        composite_repo = repos[0]
        assert composite_repo["user_alias"] == "composite-test"
        assert composite_repo["is_composite"] is True
        assert "golden_repo_aliases" in composite_repo
        assert set(composite_repo["golden_repo_aliases"]) == {
            "click",
            "hello-world-test",
        }

        # Composite repos should NOT have these fields (or they should be optional)
        # This is what causes the Pydantic validation error
        assert (
            "golden_repo_alias" not in composite_repo
            or composite_repo["golden_repo_alias"] is None
        )
        assert (
            "current_branch" not in composite_repo
            or composite_repo["current_branch"] is None
        )

    def test_get_repository_returns_composite_metadata(
        self, activated_repo_manager, temp_data_dir
    ):
        """
        Test that get_repository correctly handles composite repos.

        Validates that the metadata structure for composite repos is properly
        handled by get_repository method (which refreshes discovered_repos).
        """
        # Activate composite repository
        activated_repo_manager._do_activate_composite_repository(
            username="testuser",
            golden_repo_aliases=["click", "hello-world-test"],
            user_alias="composite-test",
        )

        # Get repository should work and refresh discovered_repos
        repo_metadata = activated_repo_manager.get_repository(
            "testuser", "composite-test"
        )

        assert repo_metadata is not None
        assert repo_metadata["is_composite"] is True
        assert "discovered_repos" in repo_metadata

        # After Issue #1 fix, this should be populated
        assert len(repo_metadata["discovered_repos"]) == 2
        assert set(repo_metadata["discovered_repos"]) == {"click", "hello-world-test"}


@pytest.mark.e2e
class TestIssue3QueryExecutionAnomaly:
    """
    Test Issue #3: Query execution searches wrong number of repositories.

    Problem: Querying composite repo searches 19 repositories instead of 2.
    Expected: Should search only the 2 component repos.

    Root Cause: Query routing not correctly identifying composite repos
                (likely due to empty discovered_repos from Issue #1).
    """

    def test_composite_query_searches_only_component_repos(
        self, activated_repo_manager, temp_data_dir
    ):
        """
        Test that querying composite repo searches only component repos.

        This test will FAIL initially because:
        1. discovered_repos is empty (Issue #1)
        2. Query routing falls back to searching all user repos

        Expected behavior:
        - Query should detect composite repository
        - Search only the 2 component repos: click, hello-world-test
        - repositories_searched should be 2, not 19
        """
        # Import SemanticQueryManager here to avoid circular imports
        from code_indexer.server.query.semantic_query_manager import (
            SemanticQueryManager,
        )

        # Create query manager
        query_manager = SemanticQueryManager(
            data_dir=temp_data_dir, activated_repo_manager=activated_repo_manager
        )

        # Activate composite repository
        activated_repo_manager._do_activate_composite_repository(
            username="testuser",
            golden_repo_aliases=["click", "hello-world-test"],
            user_alias="composite-test",
        )

        # Get composite repo path
        composite_path = (
            Path(temp_data_dir) / "activated-repos" / "testuser" / "composite-test"
        )

        # Check if repository is detected as composite
        is_composite = query_manager._is_composite_repository(composite_path)
        assert (
            is_composite is True
        ), "Composite repository should be detected by query manager"

        # Mock ProxyConfigManager to return component repos
        with patch(
            "code_indexer.server.query.semantic_query_manager.ProxyConfigManager"
        ) as mock_proxy:
            # Mock config loading
            mock_config = MagicMock()
            mock_config.discovered_repos = ["click", "hello-world-test"]
            mock_proxy.return_value.load_config.return_value = mock_config

            # Mock _execute_query to track which repos are searched
            with patch(
                "code_indexer.server.query.semantic_query_manager._execute_query"
            ) as mock_execute:
                mock_execute.return_value = None  # No output

                # Import asyncio to run async test
                import asyncio

                # Execute query
                asyncio.run(
                    query_manager.search_composite(
                        repo_path=composite_path, query="authentication", limit=10
                    )
                )

                # Verify _execute_query was called
                assert mock_execute.called, "CLI query should be executed"

                # Verify it was called with correct repo paths
                call_args = mock_execute.call_args
                repo_paths = call_args[0][1]  # Second positional arg is repo_paths

                # CRITICAL ASSERTION: Should search only 2 component repos
                assert (
                    len(repo_paths) == 2
                ), f"Should search 2 component repos, got {len(repo_paths)}"

                # Verify repo paths are correct
                expected_paths = [
                    str(composite_path / "click"),
                    str(composite_path / "hello-world-test"),
                ]
                assert set(repo_paths) == set(
                    expected_paths
                ), f"Should search component repos, got {repo_paths}"

    def test_composite_repo_metadata_includes_correct_discovered_repos(
        self, activated_repo_manager, temp_data_dir
    ):
        """
        Test that metadata correctly reflects discovered repos for query routing.

        This validates that the fix for Issue #1 enables proper query routing
        in Issue #3 by providing accurate discovered_repos.
        """
        # Activate composite repository
        activated_repo_manager._do_activate_composite_repository(
            username="testuser",
            golden_repo_aliases=["click", "hello-world-test"],
            user_alias="composite-test",
        )

        # Get repository metadata
        repo_metadata = activated_repo_manager.get_repository(
            "testuser", "composite-test"
        )

        # Verify discovered_repos is populated for query routing
        assert repo_metadata is not None
        assert "discovered_repos" in repo_metadata

        # This is what enables correct query routing
        discovered = repo_metadata["discovered_repos"]
        assert (
            len(discovered) == 2
        ), f"Discovered repos should be 2 for correct query routing, got {len(discovered)}"
        assert set(discovered) == {"click", "hello-world-test"}


# Integration test combining all three issues
@pytest.mark.e2e
class TestCompositeActivationIntegration:
    """
    Integration test validating all three issues are fixed together.

    This test represents the complete user flow from activation to querying.
    """

    def test_complete_composite_activation_and_query_flow(
        self, activated_repo_manager, temp_data_dir
    ):
        """
        Integration test: Activate composite repo, list it, and verify query routing.

        This test validates that all three issues are fixed:
        1. discovered_repos is populated during activation
        2. Repository listing works without validation errors
        3. Query routing searches correct number of repositories
        """
        # Step 1: Activate composite repository (tests Issue #1 fix)
        result = activated_repo_manager._do_activate_composite_repository(
            username="testuser",
            golden_repo_aliases=["click", "hello-world-test"],
            user_alias="composite-test",
        )

        assert result["success"] is True
        assert result["is_composite"] is True

        # Step 2: List repositories (tests Issue #2 fix)
        repos = activated_repo_manager.list_activated_repositories("testuser")
        assert len(repos) == 1

        composite_repo = repos[0]
        assert composite_repo["is_composite"] is True
        assert len(composite_repo["discovered_repos"]) == 2

        # Step 3: Verify query routing setup (tests Issue #3 fix)
        from code_indexer.server.query.semantic_query_manager import (
            SemanticQueryManager,
        )

        query_manager = SemanticQueryManager(
            data_dir=temp_data_dir, activated_repo_manager=activated_repo_manager
        )

        composite_path = (
            Path(temp_data_dir) / "activated-repos" / "testuser" / "composite-test"
        )

        # Verify composite detection works
        is_composite = query_manager._is_composite_repository(composite_path)
        assert is_composite is True

        # Verify discovered repos are available for query routing
        repo_metadata = activated_repo_manager.get_repository(
            "testuser", "composite-test"
        )
        assert set(repo_metadata["discovered_repos"]) == {"click", "hello-world-test"}

        # All three issues fixed: activation, listing, and query routing work correctly
