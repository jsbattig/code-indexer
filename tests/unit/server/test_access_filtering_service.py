"""
Unit tests for AccessFilteringService - Part 1.

Story #707: Query-Time Access Enforcement and Repo Visibility Filtering

This file covers:
- AC1: Query Results Filtered by Group Membership
- AC2: Admins See All Repository Results

TDD: These tests are written FIRST, before implementation.
"""

import pytest
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any

from code_indexer.server.services.group_access_manager import GroupAccessManager

# This import will fail initially - that's the TDD approach
from code_indexer.server.services.access_filtering_service import (
    AccessFilteringService,
)


@dataclass
class MockQueryResult:
    """Mock QueryResult for testing access filtering."""

    file_path: str
    line_number: int
    code_snippet: str
    similarity_score: float
    repository_alias: str  # This is the repo_name used for filtering
    source_repo: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@pytest.fixture
def temp_db_path():
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def group_access_manager(temp_db_path):
    """Create a GroupAccessManager with test data."""
    manager = GroupAccessManager(temp_db_path)
    admins = manager.get_group_by_name("admins")
    powerusers = manager.get_group_by_name("powerusers")

    # Grant repo access
    manager.grant_repo_access("repo-a", admins.id, "system:test")
    manager.grant_repo_access("repo-b", admins.id, "system:test")
    manager.grant_repo_access("repo-c", admins.id, "system:test")
    manager.grant_repo_access("repo-a", powerusers.id, "system:test")
    manager.grant_repo_access("repo-b", powerusers.id, "system:test")

    return manager


@pytest.fixture
def access_filtering_service(group_access_manager):
    """Create an AccessFilteringService with test data."""
    return AccessFilteringService(group_access_manager)


class TestGetAccessibleRepos:
    """Tests for get_accessible_repos method - AC1 and AC2."""

    def test_user_in_users_group_only_sees_cidx_meta(
        self, group_access_manager, access_filtering_service
    ):
        """AC1: User in users group only has access to cidx-meta."""
        users = group_access_manager.get_group_by_name("users")
        group_access_manager.assign_user_to_group("test_user", users.id, "admin")

        accessible_repos = access_filtering_service.get_accessible_repos("test_user")

        assert "cidx-meta" in accessible_repos
        assert len(accessible_repos) == 1

    def test_user_in_admins_group_sees_all_repos(
        self, group_access_manager, access_filtering_service
    ):
        """AC2: User in admins group sees all repositories."""
        admins = group_access_manager.get_group_by_name("admins")
        group_access_manager.assign_user_to_group("admin_user", admins.id, "admin")

        accessible_repos = access_filtering_service.get_accessible_repos("admin_user")

        assert "cidx-meta" in accessible_repos
        assert "repo-a" in accessible_repos
        assert "repo-b" in accessible_repos
        assert "repo-c" in accessible_repos

    def test_unassigned_user_only_sees_cidx_meta(
        self, group_access_manager, access_filtering_service
    ):
        """Unassigned user (no group) defaults to cidx-meta only."""
        accessible = access_filtering_service.get_accessible_repos("unassigned_user")

        assert "cidx-meta" in accessible
        assert len(accessible) == 1


class TestFilterQueryResultsAC1AC2:
    """Tests for filter_query_results - AC1 and AC2."""

    def test_users_group_filters_out_inaccessible_repos(
        self, group_access_manager, access_filtering_service
    ):
        """AC1: User in users group only sees results from cidx-meta."""
        users = group_access_manager.get_group_by_name("users")
        group_access_manager.assign_user_to_group("test_user", users.id, "admin")

        results = [
            MockQueryResult("f1.py", 10, "code1", 0.95, "cidx-meta"),
            MockQueryResult("f2.py", 20, "code2", 0.90, "repo-a"),
            MockQueryResult("f3.py", 30, "code3", 0.85, "repo-b"),
        ]

        filtered = access_filtering_service.filter_query_results(results, "test_user")

        assert len(filtered) == 1
        assert filtered[0].repository_alias == "cidx-meta"

    def test_admins_see_all_results(
        self, group_access_manager, access_filtering_service
    ):
        """AC2: User in admins group sees results from ALL repositories."""
        admins = group_access_manager.get_group_by_name("admins")
        group_access_manager.assign_user_to_group("admin_user", admins.id, "admin")

        results = [
            MockQueryResult("f1.py", 10, "code1", 0.95, "cidx-meta"),
            MockQueryResult("f2.py", 20, "code2", 0.90, "repo-a"),
            MockQueryResult("f3.py", 30, "code3", 0.85, "repo-c"),
        ]

        filtered = access_filtering_service.filter_query_results(results, "admin_user")

        assert len(filtered) == 3

    def test_filter_works_with_dict_results(
        self, group_access_manager, access_filtering_service
    ):
        """Test that filtering works with dictionary results (API format)."""
        users = group_access_manager.get_group_by_name("users")
        group_access_manager.assign_user_to_group("test_user", users.id, "admin")

        # API returns dict format, not dataclass
        results = [
            {"file_path": "f1.py", "repository_alias": "cidx-meta", "score": 0.95},
            {"file_path": "f2.py", "repository_alias": "repo-a", "score": 0.90},
            {"file_path": "f3.py", "repository_alias": "repo-b", "score": 0.85},
        ]

        filtered = access_filtering_service.filter_query_results(results, "test_user")

        assert len(filtered) == 1
        assert filtered[0]["repository_alias"] == "cidx-meta"


class TestFilterRepoListing:
    """Tests for AC4: Repository Listing Filtered."""

    def test_repo_listing_filtered_by_group(
        self, group_access_manager, access_filtering_service
    ):
        """AC4: Repository listing only returns repos user's group can access."""
        users = group_access_manager.get_group_by_name("users")
        group_access_manager.assign_user_to_group("test_user", users.id, "admin")

        all_repos = ["cidx-meta", "repo-a", "repo-b", "repo-c"]

        filtered = access_filtering_service.filter_repo_listing(all_repos, "test_user")

        assert "cidx-meta" in filtered
        assert len(filtered) == 1

    def test_admins_see_all_repos_in_listing(
        self, group_access_manager, access_filtering_service
    ):
        """AC4: Admin users see all repos in listing."""
        admins = group_access_manager.get_group_by_name("admins")
        group_access_manager.assign_user_to_group("admin_user", admins.id, "admin")

        all_repos = ["cidx-meta", "repo-a", "repo-b", "repo-c"]

        filtered = access_filtering_service.filter_repo_listing(all_repos, "admin_user")

        assert len(filtered) == 4


class TestFilterCidxMetaResults:
    """Tests for AC3: cidx-meta Summary Filtering."""

    def test_cidx_meta_summaries_filtered_by_accessible_repos(
        self, group_access_manager, access_filtering_service
    ):
        """AC3: Summaries referencing inaccessible repos are filtered."""
        users = group_access_manager.get_group_by_name("users")
        group_access_manager.assign_user_to_group("test_user", users.id, "admin")

        results = [
            MockQueryResult(
                "sum1.md",
                1,
                "Summary of cidx-meta",
                0.95,
                "cidx-meta",
                metadata={"referenced_repo": "cidx-meta"},
            ),
            MockQueryResult(
                "sum2.md",
                1,
                "Summary of repo-a",
                0.90,
                "cidx-meta",
                metadata={"referenced_repo": "repo-a"},
            ),
        ]

        filtered = access_filtering_service.filter_cidx_meta_results(
            results, "test_user"
        )

        assert len(filtered) == 1
        assert filtered[0].metadata["referenced_repo"] == "cidx-meta"

    def test_cidx_meta_results_without_metadata_pass_through(
        self, group_access_manager, access_filtering_service
    ):
        """Results without referenced_repo metadata should pass through."""
        users = group_access_manager.get_group_by_name("users")
        group_access_manager.assign_user_to_group("test_user", users.id, "admin")

        results = [
            MockQueryResult(
                "general.md", 1, "General content", 0.95, "cidx-meta", metadata=None
            ),
        ]

        filtered = access_filtering_service.filter_cidx_meta_results(
            results, "test_user"
        )

        assert len(filtered) == 1


class TestInvisibleRepoPattern:
    """Tests for AC5: Invisible Repo Pattern Enforced."""

    def test_no_403_errors_on_inaccessible_repo(
        self, group_access_manager, access_filtering_service
    ):
        """AC5: NO 403 errors returned when filtering inaccessible repos."""
        users = group_access_manager.get_group_by_name("users")
        group_access_manager.assign_user_to_group("test_user", users.id, "admin")

        results = [
            MockQueryResult("secret.py", 1, "secret code", 0.99, "repo-secret"),
        ]

        # Should NOT raise any exception - just silently filter
        filtered = access_filtering_service.filter_query_results(results, "test_user")
        assert filtered == []

    def test_no_existence_indication_in_accessible_repos(
        self, group_access_manager, access_filtering_service
    ):
        """AC5: No indication that filtered repos exist."""
        users = group_access_manager.get_group_by_name("users")
        group_access_manager.assign_user_to_group("test_user", users.id, "admin")

        accessible = access_filtering_service.get_accessible_repos("test_user")

        # Should not contain any repos the user can't access
        assert "repo-a" not in accessible
        assert "repo-secret" not in accessible


class TestFilterAppliedAfterHNSW:
    """Tests for AC6: Filter Applied After HNSW Search."""

    def test_filter_preserves_result_order(
        self, group_access_manager, access_filtering_service
    ):
        """AC6: Filter applied after HNSW, preserving similarity order."""
        powerusers = group_access_manager.get_group_by_name("powerusers")
        group_access_manager.assign_user_to_group("power_user", powerusers.id, "admin")

        # Results ordered by similarity score (as from HNSW)
        results = [
            MockQueryResult("f1.py", 10, "code1", 0.95, "repo-a"),
            MockQueryResult("f2.py", 20, "code2", 0.90, "repo-c"),  # Not accessible
            MockQueryResult("f3.py", 30, "code3", 0.85, "repo-b"),
        ]

        filtered = access_filtering_service.filter_query_results(results, "power_user")

        # repo-c should be filtered out, order preserved
        assert len(filtered) == 2
        assert filtered[0].similarity_score == 0.95
        assert filtered[1].similarity_score == 0.85

    def test_returned_count_less_than_requested_limit(
        self, group_access_manager, access_filtering_service
    ):
        """AC6: Returned count may be less than requested limit."""
        users = group_access_manager.get_group_by_name("users")
        group_access_manager.assign_user_to_group("test_user", users.id, "admin")

        # 5 results all from inaccessible repos
        results = [
            MockQueryResult(f"f{i}.py", i, f"code{i}", 0.9 - i * 0.1, "repo-a")
            for i in range(5)
        ]

        filtered = access_filtering_service.filter_query_results(results, "test_user")

        assert len(filtered) == 0  # All filtered out


class TestGroupMembershipAtQueryTime:
    """Tests for AC7: Group Membership Checked at Query Time."""

    def test_group_change_applies_immediately(
        self, group_access_manager, access_filtering_service
    ):
        """AC7: When user's group changes, new permissions apply immediately."""
        users = group_access_manager.get_group_by_name("users")
        powerusers = group_access_manager.get_group_by_name("powerusers")

        # Start in users group
        group_access_manager.assign_user_to_group("changing_user", users.id, "admin")

        accessible_before = access_filtering_service.get_accessible_repos(
            "changing_user"
        )
        assert "repo-a" not in accessible_before

        # Change to powerusers group
        group_access_manager.assign_user_to_group(
            "changing_user", powerusers.id, "admin"
        )

        # New permissions should apply immediately - no cache
        accessible_after = access_filtering_service.get_accessible_repos(
            "changing_user"
        )
        assert "repo-a" in accessible_after

    def test_filter_reflects_current_membership(
        self, group_access_manager, access_filtering_service
    ):
        """AC7: Filter results reflect current group membership."""
        powerusers = group_access_manager.get_group_by_name("powerusers")
        users = group_access_manager.get_group_by_name("users")

        group_access_manager.assign_user_to_group("test_user", powerusers.id, "admin")

        results = [MockQueryResult("f1.py", 10, "code1", 0.95, "repo-a")]

        # Poweruser can see repo-a
        filtered_before = access_filtering_service.filter_query_results(
            results, "test_user"
        )
        assert len(filtered_before) == 1

        # Reassign to users group (no cache invalidation needed)
        group_access_manager.assign_user_to_group("test_user", users.id, "admin")

        # Users cannot see repo-a
        filtered_after = access_filtering_service.filter_query_results(
            results, "test_user"
        )
        assert len(filtered_after) == 0
