"""
Unit test for RepositoryDetailsResponse model with temporal fields.

Tests that the response model accepts and returns temporal status fields.
"""


class TestRepositoryDetailsResponseTemporalFields:
    """Test that RepositoryDetailsResponse accepts temporal fields."""

    def test_repository_details_response_accepts_temporal_fields(self):
        """Test that RepositoryDetailsResponse model accepts temporal fields."""
        from code_indexer.server.app import RepositoryDetailsResponse

        # Act - create response with temporal fields
        response = RepositoryDetailsResponse(
            alias="test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path="/path/to/repo",
            created_at="2025-11-11T00:00:00Z",
            activation_status="activated",
            branches_list=["main", "develop"],
            file_count=100,
            index_size=1024,
            last_updated="2025-11-11T00:00:00Z",
            enable_temporal=True,
            temporal_status={
                "enabled": True,
                "last_commit": "abc123def456",
                "diff_context": 5,
            },
        )

        # Assert
        assert response.enable_temporal is True
        assert response.temporal_status is not None
        assert response.temporal_status["enabled"] is True
        assert response.temporal_status["last_commit"] == "abc123def456"
        assert response.temporal_status["diff_context"] == 5
