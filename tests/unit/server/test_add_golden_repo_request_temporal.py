"""
Unit tests for AddGoldenRepoRequest model with temporal fields.

Tests that AddGoldenRepoRequest properly accepts and validates temporal indexing options.
"""


class TestAddGoldenRepoRequestTemporalFields:
    """Test AddGoldenRepoRequest temporal field handling."""

    def test_add_golden_repo_request_without_temporal_options(self):
        """Test that AddGoldenRepoRequest works without temporal options."""
        # Import here to avoid early failure
        from code_indexer.server.app import AddGoldenRepoRequest

        request = AddGoldenRepoRequest(
            repo_url="https://github.com/test/repo.git", alias="test-repo"
        )

        assert request.enable_temporal is False
        assert request.temporal_options is None
