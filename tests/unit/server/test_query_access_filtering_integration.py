"""
Service layer tests for AccessFilteringService with GroupAccessManager.

Story #707: Query-Time Access Enforcement and Repo Visibility Filtering

Tests that AccessFilteringService correctly integrates with GroupAccessManager
at the service layer, ensuring the wiring between components works correctly.

TDD: These tests verify the service layer integration works correctly.
"""

import pytest
import tempfile
from pathlib import Path

from code_indexer.server.services.group_access_manager import GroupAccessManager
from code_indexer.server.services.access_filtering_service import (
    AccessFilteringService,
)


@pytest.fixture
def temp_db_path():
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


class TestAccessFilteringServiceWithGroupManager:
    """Tests for AccessFilteringService integration with GroupAccessManager."""

    def test_can_create_service_with_group_manager(self, temp_db_path):
        """Test that AccessFilteringService initializes with GroupAccessManager."""
        group_manager = GroupAccessManager(temp_db_path)
        service = AccessFilteringService(group_manager)

        assert service is not None
        assert service.group_manager == group_manager

    def test_service_uses_group_manager_for_access_checks(self, temp_db_path):
        """Test that service correctly uses group manager for access decisions."""
        group_manager = GroupAccessManager(temp_db_path)
        service = AccessFilteringService(group_manager)

        # Assign user to admins
        admins = group_manager.get_group_by_name("admins")
        group_manager.assign_user_to_group("admin_user", admins.id, "system")
        group_manager.grant_repo_access("test-repo", admins.id, "system")

        # Verify service sees the repo
        accessible = service.get_accessible_repos("admin_user")
        assert "test-repo" in accessible

    def test_service_respects_cidx_meta_always_accessible(self, temp_db_path):
        """Test that cidx-meta is always accessible regardless of group."""
        group_manager = GroupAccessManager(temp_db_path)
        service = AccessFilteringService(group_manager)

        # Unassigned user
        accessible = service.get_accessible_repos("random_user")
        assert "cidx-meta" in accessible

    def test_service_admin_detection(self, temp_db_path):
        """Test that service correctly detects admin users."""
        group_manager = GroupAccessManager(temp_db_path)
        service = AccessFilteringService(group_manager)

        # Non-admin user
        users = group_manager.get_group_by_name("users")
        group_manager.assign_user_to_group("regular_user", users.id, "admin")
        assert not service.is_admin_user("regular_user")

        # Admin user
        admins = group_manager.get_group_by_name("admins")
        group_manager.assign_user_to_group("admin_user", admins.id, "admin")
        assert service.is_admin_user("admin_user")
