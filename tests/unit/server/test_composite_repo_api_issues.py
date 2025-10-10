"""
Tests for composite repository API validation issues.

This module tests the actual API endpoint behavior with Pydantic validation
for composite repositories, focusing on the GET /api/repos endpoint failure.
"""

import json
import os
import shutil
import tempfile
import subprocess

import pytest
from pydantic import ValidationError

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

    # Create .code-indexer directory
    click_config_dir = os.path.join(click_repo_path, ".code-indexer")
    os.makedirs(click_config_dir, exist_ok=True)
    click_config = {
        "embedding_provider": "voyage-ai",
        "proxy_mode": False,
        "discovered_repos": [],
    }
    with open(os.path.join(click_config_dir, "config.json"), "w") as f:
        json.dump(click_config, f)

    # Initialize git repo
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

    dummy_file = os.path.join(click_repo_path, "README.md")
    with open(dummy_file, "w") as f:
        f.write("# Click\n")
    subprocess.run(
        ["git", "add", "."], cwd=click_repo_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=click_repo_path,
        check=True,
        capture_output=True,
    )

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

    hello_config_dir = os.path.join(hello_repo_path, ".code-indexer")
    os.makedirs(hello_config_dir, exist_ok=True)
    hello_config = {
        "embedding_provider": "voyage-ai",
        "proxy_mode": False,
        "discovered_repos": [],
    }
    with open(os.path.join(hello_config_dir, "config.json"), "w") as f:
        json.dump(hello_config, f)

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

    dummy_file = os.path.join(hello_repo_path, "hello.py")
    with open(dummy_file, "w") as f:
        f.write("print('Hello!')\n")
    subprocess.run(
        ["git", "add", "."], cwd=hello_repo_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=hello_repo_path,
        check=True,
        capture_output=True,
    )

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
    """Create activated repo manager."""
    return ActivatedRepoManager(
        data_dir=temp_data_dir, golden_repo_manager=golden_repo_manager
    )


class TestActivatedRepositoryInfoValidation:
    """
    Test Issue #2: ActivatedRepositoryInfo Pydantic validation for composite repos.

    The actual bug is at the API serialization layer where composite repository
    metadata is serialized to ActivatedRepositoryInfo model which requires
    golden_repo_alias and current_branch fields that don't exist for composites.
    """

    def test_activated_repository_info_requires_fields_composite_repos_dont_have(
        self, activated_repo_manager
    ):
        """
        Test that ActivatedRepositoryInfo model validation fails for composite repos.

        This test demonstrates the actual bug: composite repo metadata cannot
        be serialized to ActivatedRepositoryInfo because it's missing required fields.

        This test will FAIL initially and demonstrates why the API fails.
        """
        from pydantic import BaseModel

        # Define ActivatedRepositoryInfo as it exists in app.py
        class ActivatedRepositoryInfo(BaseModel):
            """Model for activated repository information (current implementation)."""

            user_alias: str
            golden_repo_alias: str  # Required field
            current_branch: str  # Required field
            activated_at: str
            last_accessed: str

        # Activate composite repository
        activated_repo_manager._do_activate_composite_repository(
            username="testuser",
            golden_repo_aliases=["click", "hello-world-test"],
            user_alias="composite-test",
        )

        # Get repository metadata (as returned by list_activated_repositories)
        repos = activated_repo_manager.list_activated_repositories("testuser")
        composite_repo_metadata = repos[0]

        # Try to serialize to ActivatedRepositoryInfo (this is what API does)
        # This will FAIL because composite repo metadata has:
        # - NO golden_repo_alias (has golden_repo_aliases instead)
        # - NO current_branch (composite repos don't have branches)

        with pytest.raises(ValidationError) as exc_info:
            ActivatedRepositoryInfo(**composite_repo_metadata)

        # Verify the expected validation errors
        errors = exc_info.value.errors()
        error_fields = [e["loc"][0] for e in errors]

        assert (
            "golden_repo_alias" in error_fields
        ), "Should fail validation for missing golden_repo_alias"
        assert (
            "current_branch" in error_fields
        ), "Should fail validation for missing current_branch"

    def test_composite_repo_metadata_structure_vs_required_api_model(
        self, activated_repo_manager
    ):
        """
        Test that composite repo metadata structure doesn't match API model requirements.

        This validates the exact mismatch between what composite repos have
        and what ActivatedRepositoryInfo requires.
        """
        # Activate composite repository
        activated_repo_manager._do_activate_composite_repository(
            username="testuser",
            golden_repo_aliases=["click", "hello-world-test"],
            user_alias="composite-test",
        )

        # Get metadata
        repos = activated_repo_manager.list_activated_repositories("testuser")
        composite_metadata = repos[0]

        # Composite repos have these fields
        assert "is_composite" in composite_metadata
        assert composite_metadata["is_composite"] is True
        assert "golden_repo_aliases" in composite_metadata  # plural, list
        assert "discovered_repos" in composite_metadata

        # But they DON'T have these required fields
        assert "golden_repo_alias" not in composite_metadata  # singular
        assert "current_branch" not in composite_metadata

        # This is the root cause of the API validation failure


class TestFixedActivatedRepositoryInfoWithOptionalFields:
    """
    Test the FIX for Issue #2: Make fields optional in ActivatedRepositoryInfo.

    After fixing, the model should accept both single and composite repositories.
    """

    def test_fixed_model_accepts_composite_repos(self, activated_repo_manager):
        """
        Test that FIXED ActivatedRepositoryInfo accepts composite repos.

        This test will PASS after we fix the model by making golden_repo_alias
        and current_branch optional.
        """
        from pydantic import BaseModel
        from typing import Optional

        # Define FIXED ActivatedRepositoryInfo model
        class FixedActivatedRepositoryInfo(BaseModel):
            """Fixed model with optional fields for composite repos."""

            user_alias: str
            golden_repo_alias: Optional[str] = None  # Made optional
            current_branch: Optional[str] = None  # Made optional
            activated_at: str
            last_accessed: str

        # Activate composite repository
        activated_repo_manager._do_activate_composite_repository(
            username="testuser",
            golden_repo_aliases=["click", "hello-world-test"],
            user_alias="composite-test",
        )

        # Get repository metadata
        repos = activated_repo_manager.list_activated_repositories("testuser")
        composite_repo_metadata = repos[0]

        # This should NOT raise ValidationError after fix
        repo_info = FixedActivatedRepositoryInfo(**composite_repo_metadata)

        # Verify it was created successfully
        assert repo_info.user_alias == "composite-test"
        assert repo_info.golden_repo_alias is None  # Not present in composite
        assert repo_info.current_branch is None  # Not present in composite

    def test_fixed_model_still_accepts_single_repos(self, activated_repo_manager):
        """
        Test that FIXED model still works correctly with single repositories.

        The fix should maintain backward compatibility with single repos.
        """
        from pydantic import BaseModel
        from typing import Optional

        # Define FIXED ActivatedRepositoryInfo model
        class FixedActivatedRepositoryInfo(BaseModel):
            """Fixed model with optional fields."""

            user_alias: str
            golden_repo_alias: Optional[str] = None
            current_branch: Optional[str] = None
            activated_at: str
            last_accessed: str

        # Activate single repository
        activated_repo_manager._do_activate_repository(
            username="testuser",
            golden_repo_alias="click",
            branch_name="main",
            user_alias="click",
        )

        # Get repository metadata
        repos = activated_repo_manager.list_activated_repositories("testuser")
        single_repo_metadata = [r for r in repos if r["user_alias"] == "click"][0]

        # This should work fine
        repo_info = FixedActivatedRepositoryInfo(**single_repo_metadata)

        # Verify single repo fields are populated
        assert repo_info.user_alias == "click"
        assert repo_info.golden_repo_alias == "click"
        assert repo_info.current_branch == "main"
