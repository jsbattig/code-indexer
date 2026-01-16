"""
Unit tests for Issue #716 Bug 2a: Token whitespace stripping.

Tokens with leading/trailing whitespace should be accepted after stripping.
The stripping should happen at the routes layer (save_api_key function).

Tests are written FIRST following TDD methodology.
"""


class TestTokenWhitespaceStripping:
    """Tests for Bug 2a: Whitespace should be stripped before token validation."""

    def test_save_token_strips_whitespace_before_validation(self, tmp_path):
        """
        Bug 2a: Token with whitespace should be saved after stripping.

        Given a valid token with leading/trailing whitespace
        When save_token is called (after strip in routes layer)
        Then the token should be saved successfully without whitespace

        Note: The actual stripping happens in routes.py save_api_key().
        This test verifies the clean token works after stripping.
        """
        from src.code_indexer.server.services.ci_token_manager import CITokenManager

        server_dir = tmp_path / ".cidx-server"
        server_dir.mkdir()
        manager = CITokenManager(server_dir_path=str(server_dir))

        # Token with whitespace - simulating what user might paste
        token_with_whitespace = " ghp_" + "a" * 36 + " "
        clean_token = token_with_whitespace.strip()

        # After stripping (done in routes.py), save should work
        manager.save_token("github", clean_token)

        # Verify token was saved correctly
        token_data = manager.get_token("github")
        assert token_data is not None
        assert token_data.token == clean_token
        assert token_data.token == "ghp_" + "a" * 36
