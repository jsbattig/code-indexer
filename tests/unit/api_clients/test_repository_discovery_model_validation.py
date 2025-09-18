"""Test repository discovery model validation failures.

This test reproduces the exact model validation issues found in the API client tests.
Following TDD methodology - write failing tests first, then fix the fixtures.
"""

import pytest
from pydantic import ValidationError

from code_indexer.api_clients.repository_linking_client import (
    RepositoryDiscoveryResponse,
)


class TestRepositoryDiscoveryModelValidation:
    """Test cases to reproduce the model validation failures."""

    def test_repository_discovery_response_model_validation_fails_with_old_format(self):
        """Test that old format mock data fails validation (this should fail initially)."""
        old_format_data = {
            "matches": [
                {
                    "alias": "cidx-main",
                    "display_name": "CIDX Main Repository",
                    "description": "Main CIDX codebase",
                    "git_url": "https://github.com/example/cidx.git",
                    "default_branch": "master",
                    "available_branches": ["master", "develop"],
                    "last_updated": "2024-01-15T10:30:00Z",
                    "access_level": "read",
                }
            ],
            "total_matches": 1,
        }

        # This should fail because required fields are missing
        with pytest.raises(ValidationError) as exc_info:
            RepositoryDiscoveryResponse.model_validate(old_format_data)

        # Verify we're getting the expected missing field errors
        error_details = str(exc_info.value)
        assert "query_url" in error_details
        assert "normalized_url" in error_details
        assert "golden_repositories" in error_details
        assert "activated_repositories" in error_details
        assert "Field required" in error_details

    def test_repository_discovery_response_model_validation_succeeds_with_correct_format(
        self,
    ):
        """Test that correct format passes validation (this should pass after we understand the model)."""
        correct_format_data = {
            "query_url": "https://github.com/example/cidx.git",
            "normalized_url": "https://github.com/example/cidx.git",
            "golden_repositories": [
                {
                    "alias": "cidx-main",
                    "repository_type": "golden",
                    "git_url": "https://github.com/example/cidx.git",
                    "available_branches": ["master", "develop"],
                    "default_branch": "master",
                    "last_indexed": "2024-01-15T10:30:00Z",
                    "display_name": "CIDX Main Repository",
                    "description": "Main CIDX codebase",
                }
            ],
            "activated_repositories": [],
            "total_matches": 1,
        }

        # This should succeed with the correct model structure
        response = RepositoryDiscoveryResponse.model_validate(correct_format_data)
        assert response.query_url == "https://github.com/example/cidx.git"
        assert response.normalized_url == "https://github.com/example/cidx.git"
        assert len(response.golden_repositories) == 1
        assert len(response.activated_repositories) == 0
        assert response.total_matches == 1

    def test_repository_match_model_requires_repository_type_field(self):
        """Test that RepositoryMatch requires the repository_type field."""
        incomplete_repository_data = {
            "alias": "test-repo",
            "git_url": "https://github.com/test/repo.git",
            "available_branches": ["main"],
            "display_name": "Test Repository",
            "description": "A test repository",
            # Missing repository_type field
        }

        correct_format_data = {
            "query_url": "https://github.com/test/repo.git",
            "normalized_url": "https://github.com/test/repo.git",
            "golden_repositories": [incomplete_repository_data],
            "activated_repositories": [],
            "total_matches": 1,
        }

        # This should fail because repository_type is missing
        with pytest.raises(ValidationError) as exc_info:
            RepositoryDiscoveryResponse.model_validate(correct_format_data)

        error_details = str(exc_info.value)
        assert "repository_type" in error_details
        assert "Field required" in error_details
