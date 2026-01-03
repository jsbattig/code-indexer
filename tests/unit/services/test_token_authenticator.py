"""
Unit tests for TokenAuthenticator.resolve_token() method.

Tests verify proper token resolution with decryption support via CITokenManager.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.code_indexer.server.services.ci_token_manager import CITokenManager
from src.code_indexer.server.services.git_state_manager import TokenAuthenticator


class TestTokenAuthenticatorResolveToken:
    """Test suite for TokenAuthenticator.resolve_token() method."""

    @pytest.fixture
    def temp_server_dir(self):
        """Create temporary server directory for token storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_home(self, temp_server_dir):
        """Mock Path.home() to use temporary directory."""
        with patch("pathlib.Path.home") as mock:
            mock.return_value = temp_server_dir.parent
            # Ensure .cidx-server exists in temp location
            server_dir = temp_server_dir.parent / ".cidx-server"
            server_dir.mkdir(parents=True, exist_ok=True)

            # Clean up any existing token file for test isolation
            token_file = server_dir / "ci_tokens.json"
            if token_file.exists():
                token_file.unlink()

            yield server_dir

    def test_resolve_token_from_encrypted_file_storage(self, mock_home):
        """
        Test that resolve_token() properly decrypts tokens from file storage.

        This test proves the BUG: Current implementation returns encrypted gibberish
        instead of decrypted token when reading from file storage.
        """
        # Arrange: Save encrypted GitHub token using CITokenManager
        platform = "github"
        plaintext_token = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"  # 40 total (36 after prefix)

        token_manager = CITokenManager(server_dir_path=str(mock_home))
        token_manager.save_token(platform, plaintext_token)

        # Act: Resolve token using TokenAuthenticator
        resolved_token = TokenAuthenticator.resolve_token(platform)

        # Assert: Should return DECRYPTED token, not encrypted gibberish
        assert resolved_token is not None, "Token should be resolved from file"
        assert resolved_token == plaintext_token, (
            f"Expected decrypted token '{plaintext_token}', "
            f"but got '{resolved_token}' (likely encrypted gibberish)"
        )
        # Additional assertion: Ensure we didn't get base64-encoded encrypted data
        assert not resolved_token.startswith("eyJ"), (
            "Resolved token appears to be encrypted (base64-encoded)"
        )

    def test_resolve_token_priority_env_over_file(self, mock_home):
        """
        Test that environment variables take priority over encrypted file storage.
        """
        # Arrange: Set up both env var and encrypted file token
        platform = "github"
        env_token = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"  # 40 total (36 after prefix)
        file_token = "ghp_0987654321zyxwvutsrqponmlkjihgfedcba"  # 40 total (36 after prefix)

        # Save encrypted token to file
        token_manager = CITokenManager(server_dir_path=str(mock_home))
        token_manager.save_token(platform, file_token)

        # Set environment variable
        with patch.dict(os.environ, {"GH_TOKEN": env_token}, clear=False):
            # Act: Resolve token
            resolved_token = TokenAuthenticator.resolve_token(platform)

            # Assert: Should return env var token, not file token
            assert resolved_token == env_token, (
                f"Environment variable should take priority. "
                f"Expected '{env_token}', got '{resolved_token}'"
            )

    def test_resolve_token_gitlab_from_encrypted_file(self, mock_home):
        """
        Test GitLab token resolution from encrypted file storage.
        """
        # Arrange: Save encrypted GitLab token
        platform = "gitlab"
        plaintext_token = "glpat-abcdefghijklmnopqrst"

        token_manager = CITokenManager(server_dir_path=str(mock_home))
        token_manager.save_token(platform, plaintext_token)

        # Act: Resolve token
        resolved_token = TokenAuthenticator.resolve_token(platform)

        # Assert: Should return decrypted GitLab token
        assert resolved_token is not None, "GitLab token should be resolved"
        assert resolved_token == plaintext_token, (
            f"Expected decrypted GitLab token '{plaintext_token}', "
            f"got '{resolved_token}'"
        )

    def test_resolve_token_missing_returns_none(self, mock_home):
        """
        Test that resolve_token() returns None when no token is configured.
        """
        # Arrange: No environment variables, no file storage
        with patch.dict(os.environ, {}, clear=True):
            # Act: Resolve token for platform with no configured token
            resolved_token = TokenAuthenticator.resolve_token("github")

            # Assert: Should return None
            assert resolved_token is None, (
                "Should return None when no token is configured"
            )

    def test_resolve_token_handles_corrupted_file_gracefully(self, mock_home):
        """
        Test that resolve_token() handles corrupted token files gracefully.
        """
        # Arrange: Create corrupted token file (invalid JSON)
        token_file = mock_home / "ci_tokens.json"
        token_file.write_text("{ invalid json }")

        with patch.dict(os.environ, {}, clear=True):
            # Act: Resolve token
            resolved_token = TokenAuthenticator.resolve_token("github")

            # Assert: Should return None, not raise exception
            assert resolved_token is None, (
                "Should return None gracefully for corrupted file"
            )

    def test_resolve_token_environment_variable_names(self, mock_home):
        """
        Test that resolve_token() recognizes both GH_TOKEN and GITHUB_TOKEN.
        """
        github_token = "ghp_testtokenabcdefghijklmnopqrstuvwxy"  # 40 total (36 after prefix)

        # Test GH_TOKEN
        with patch.dict(os.environ, {"GH_TOKEN": github_token}, clear=True):
            resolved = TokenAuthenticator.resolve_token("github")
            assert resolved == github_token, "Should resolve from GH_TOKEN"

        # Test GITHUB_TOKEN
        with patch.dict(os.environ, {"GITHUB_TOKEN": github_token}, clear=True):
            resolved = TokenAuthenticator.resolve_token("github")
            assert resolved == github_token, "Should resolve from GITHUB_TOKEN"

        # Test GITLAB_TOKEN
        gitlab_token = "glpat-testtokenabcdefghijklmnop"  # 20+ chars after glpat-
        with patch.dict(os.environ, {"GITLAB_TOKEN": gitlab_token}, clear=True):
            resolved = TokenAuthenticator.resolve_token("gitlab")
            assert resolved == gitlab_token, "Should resolve from GITLAB_TOKEN"
