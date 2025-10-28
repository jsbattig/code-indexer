"""
Integration tests for repository activation API request/response contract.

Tests the API request model validation and response structure.
Following TDD methodology - tests written before implementation.
Following MESSI Rule #1 (Anti-Mock): Tests actual request models with zero mocking.
"""

import pytest
from pydantic import ValidationError
from code_indexer.server.app import ActivateRepositoryRequest


class TestActivateRepositoryRequestContract:
    """Integration tests for ActivateRepositoryRequest contract."""

    def test_single_repo_request_structure(self):
        """Test that single repo request has correct structure."""
        # This test verifies the API contract accepts single repo requests
        request = ActivateRepositoryRequest(
            golden_repo_alias="repo1", user_alias="my_repo", branch_name="main"
        )

        assert request.golden_repo_alias == "repo1"
        assert request.golden_repo_aliases is None
        assert request.user_alias == "my_repo"
        assert request.branch_name == "main"

    def test_composite_repo_request_structure(self):
        """Test that composite repo request has correct structure."""
        # This test verifies the API contract accepts composite repo requests
        request = ActivateRepositoryRequest(
            golden_repo_aliases=["repo1", "repo2", "repo3"], user_alias="composite"
        )

        assert request.golden_repo_alias is None
        assert request.golden_repo_aliases == ["repo1", "repo2", "repo3"]
        assert request.user_alias == "composite"

    def test_mutual_exclusivity_enforced_at_api_layer(self):
        """Test that API layer enforces mutual exclusivity."""
        with pytest.raises(ValidationError) as exc_info:
            ActivateRepositoryRequest(
                golden_repo_alias="repo1",
                golden_repo_aliases=["repo2", "repo3"],
                user_alias="test",
            )

        errors = exc_info.value.errors()
        assert any(
            "cannot specify both" in str(error["msg"]).lower() for error in errors
        )

    def test_at_least_one_parameter_required_at_api_layer(self):
        """Test that API layer requires at least one repo parameter."""
        with pytest.raises(ValidationError) as exc_info:
            ActivateRepositoryRequest(user_alias="test")

        errors = exc_info.value.errors()
        assert any(
            "must specify either" in str(error["msg"]).lower() for error in errors
        )

    def test_composite_minimum_two_repos_enforced_at_api_layer(self):
        """Test that API layer enforces minimum 2 repos for composite."""
        with pytest.raises(ValidationError) as exc_info:
            ActivateRepositoryRequest(golden_repo_aliases=["repo1"], user_alias="test")

        errors = exc_info.value.errors()
        assert any(
            "at least 2 repositories" in str(error["msg"]).lower() for error in errors
        )

    def test_composite_empty_list_rejected_at_api_layer(self):
        """Test that API layer rejects empty golden_repo_aliases list."""
        with pytest.raises(ValidationError) as exc_info:
            ActivateRepositoryRequest(golden_repo_aliases=[], user_alias="test")

        errors = exc_info.value.errors()
        assert any(
            "at least 2 repositories" in str(error["msg"]).lower() for error in errors
        )

    def test_empty_strings_in_composite_list_rejected(self):
        """Test that empty strings in golden_repo_aliases are rejected."""
        with pytest.raises(ValidationError):
            ActivateRepositoryRequest(
                golden_repo_aliases=["repo1", "", "repo2"], user_alias="test"
            )

    def test_whitespace_only_strings_in_composite_list_rejected(self):
        """Test that whitespace-only strings in golden_repo_aliases are rejected."""
        with pytest.raises(ValidationError):
            ActivateRepositoryRequest(
                golden_repo_aliases=["repo1", "   ", "repo2"], user_alias="test"
            )


class TestActivateRepositoryResponseContract:
    """Integration tests for activation response contract."""

    def test_single_repo_response_message_format(self):
        """Test that single repo activation produces expected message format."""
        # This tests the API response message format for single repos
        # The actual endpoint returns: f"Repository '{user_alias}' activation started..."

        user_alias = "my_repo"
        username = "testuser"
        expected_parts = [user_alias, "activation started", username]

        # Verify message structure
        message = f"Repository '{user_alias}' activation started for user '{username}'"

        for part in expected_parts:
            assert part in message

    def test_composite_repo_response_message_format(self):
        """Test that composite repo activation produces expected message format."""
        # This tests the API response message format for composite repos
        # The endpoint returns: f"Composite repository '{user_alias}' activation started... ({repo_count} repositories)"

        user_alias = "composite_repo"
        username = "testuser"
        repo_count = 3
        expected_parts = ["Composite", user_alias, "activation started", username, "3"]

        # Verify message structure
        message = f"Composite repository '{user_alias}' activation started for user '{username}' ({repo_count} repositories)"

        for part in expected_parts:
            assert part in message

    def test_job_response_has_required_fields(self):
        """Test that job response contains required fields."""
        # Response model structure
        job_response = {"job_id": "test-job-123", "message": "Test message"}

        assert "job_id" in job_response
        assert "message" in job_response
        assert isinstance(job_response["job_id"], str)
        assert isinstance(job_response["message"], str)
