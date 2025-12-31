"""Tests for OIDC state manager implementation."""


class TestStateManager:
    """Test OIDC state manager class."""

    def test_state_manager_initialization(self):
        """Test that StateManager can be initialized."""
        from code_indexer.server.auth.oidc.state_manager import StateManager

        manager = StateManager()

        assert manager is not None

    def test_create_state_returns_token(self):
        """Test that create_state() returns a state token."""
        from code_indexer.server.auth.oidc.state_manager import StateManager

        manager = StateManager()
        state_data = {"code_verifier": "test-verifier", "redirect_uri": "/admin"}

        state_token = manager.create_state(state_data)

        assert isinstance(state_token, str)
        assert len(state_token) > 0

    def test_validate_state_returns_data_for_valid_token(self):
        """Test that validate_state() returns data for valid state token."""
        from code_indexer.server.auth.oidc.state_manager import StateManager

        manager = StateManager()
        state_data = {"code_verifier": "test-verifier", "redirect_uri": "/admin"}

        # Create state
        state_token = manager.create_state(state_data)

        # Validate state
        retrieved_data = manager.validate_state(state_token)

        assert retrieved_data == state_data
