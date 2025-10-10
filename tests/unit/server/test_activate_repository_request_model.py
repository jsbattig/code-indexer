"""
Unit tests for ActivateRepositoryRequest model validation.

Tests the extended API model that accepts both single and array golden repository parameters.
Following TDD methodology - these tests are written FIRST before implementation.
"""

import pytest
from pydantic import ValidationError
from code_indexer.server.app import ActivateRepositoryRequest


class TestActivateRepositoryRequestSingleRepo:
    """Test single repository activation (existing functionality)."""

    def test_single_repo_activation_valid(self):
        """Test valid single repository activation request."""
        request = ActivateRepositoryRequest(
            golden_repo_alias="repo1", branch_name="main", user_alias="my_repo"
        )
        assert request.golden_repo_alias == "repo1"
        assert request.branch_name == "main"
        assert request.user_alias == "my_repo"

    def test_single_repo_activation_minimal(self):
        """Test single repository activation with minimal params."""
        request = ActivateRepositoryRequest(golden_repo_alias="repo1")
        assert request.golden_repo_alias == "repo1"
        assert request.branch_name is None
        assert request.user_alias is None


class TestActivateRepositoryRequestCompositeRepo:
    """Test composite repository activation (NEW functionality)."""

    def test_composite_repo_activation_valid(self):
        """Test valid composite repository activation request."""
        request = ActivateRepositoryRequest(
            golden_repo_aliases=["repo1", "repo2", "repo3"], user_alias="composite"
        )
        assert request.golden_repo_aliases == ["repo1", "repo2", "repo3"]
        assert request.golden_repo_alias is None
        assert request.user_alias == "composite"

    def test_composite_repo_activation_minimal(self):
        """Test composite repository activation with minimal params."""
        request = ActivateRepositoryRequest(golden_repo_aliases=["repo1", "repo2"])
        assert request.golden_repo_aliases == ["repo1", "repo2"]
        assert request.golden_repo_alias is None

    def test_composite_repo_requires_minimum_two_repos(self):
        """Test that composite activation requires at least 2 repositories."""
        with pytest.raises(ValidationError) as exc_info:
            ActivateRepositoryRequest(golden_repo_aliases=["repo1"])

        errors = exc_info.value.errors()
        assert any(
            "at least 2 repositories" in str(error["msg"]).lower() for error in errors
        )

    def test_composite_repo_empty_list_fails(self):
        """Test that empty list for golden_repo_aliases fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ActivateRepositoryRequest(golden_repo_aliases=[])

        errors = exc_info.value.errors()
        assert any(
            "at least 2 repositories" in str(error["msg"]).lower() for error in errors
        )


class TestActivateRepositoryRequestMutualExclusivity:
    """Test mutual exclusivity between golden_repo_alias and golden_repo_aliases."""

    def test_both_parameters_fails_validation(self):
        """Test that providing both parameters raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ActivateRepositoryRequest(
                golden_repo_alias="repo1", golden_repo_aliases=["repo2", "repo3"]
            )

        errors = exc_info.value.errors()
        assert any(
            "cannot specify both" in str(error["msg"]).lower() for error in errors
        )

    def test_neither_parameter_fails_validation(self):
        """Test that providing neither parameter raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ActivateRepositoryRequest(user_alias="my_repo")

        # Should fail because at least one repo parameter is required
        assert exc_info.value.errors()


class TestActivateRepositoryRequestEdgeCases:
    """Test edge cases for the request model."""

    def test_composite_with_duplicate_repos(self):
        """Test composite activation with duplicate repository aliases."""
        # This should be allowed at model level - business logic validates
        request = ActivateRepositoryRequest(
            golden_repo_aliases=["repo1", "repo1", "repo2"]
        )
        assert request.golden_repo_aliases == ["repo1", "repo1", "repo2"]

    def test_composite_with_empty_string_in_list(self):
        """Test that empty strings in golden_repo_aliases are handled."""
        # Validation should prevent empty strings
        with pytest.raises(ValidationError):
            ActivateRepositoryRequest(golden_repo_aliases=["repo1", "", "repo2"])

    def test_composite_with_whitespace_only_in_list(self):
        """Test that whitespace-only strings in golden_repo_aliases fail validation."""
        with pytest.raises(ValidationError):
            ActivateRepositoryRequest(golden_repo_aliases=["repo1", "   ", "repo2"])
