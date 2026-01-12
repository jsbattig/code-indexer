"""
Unit tests for Issue #716 Bug 3: Token decryption failure handling.

When token decryption fails (e.g., token encrypted on different machine),
get_token() should return None gracefully instead of crashing the config page.

Tests are written FIRST following TDD methodology.
"""

import json
import pytest


class TestTokenDecryptionFailureHandling:
    """Tests for Bug 3: get_token should handle decryption failures gracefully."""

    def test_get_token_returns_none_on_decryption_failure(self, tmp_path):
        """
        Bug 3: get_token should return None when decryption fails.

        Given a token that cannot be decrypted (corrupted data)
        When get_token is called
        Then it should return None instead of crashing
        """
        from src.code_indexer.server.services.ci_token_manager import CITokenManager

        server_dir = tmp_path / ".cidx-server"
        server_dir.mkdir()
        manager = CITokenManager(server_dir_path=str(server_dir))

        # Save a valid token
        valid_token = "ghp_" + "a" * 36
        manager.save_token("github", valid_token)

        # Corrupt the token in the file
        token_file = server_dir / "ci_tokens.json"
        with open(token_file, "r") as f:
            data = json.load(f)
        data["github"]["token"] = "YWJjZGVmZ2hpamtsbW5vcA=="
        with open(token_file, "w") as f:
            json.dump(data, f)

        # This should NOT raise an exception - should return None
        result = manager.get_token("github")
        assert result is None, "get_token should return None when decryption fails"

    def test_get_token_returns_none_on_invalid_iv_size(self, tmp_path):
        """
        Bug 3: get_token should handle 'Invalid IV size' error gracefully.

        Given a token with corrupted IV (empty base64)
        When get_token is called
        Then it should return None (not raise ValueError)
        """
        from src.code_indexer.server.services.ci_token_manager import CITokenManager

        server_dir = tmp_path / ".cidx-server"
        server_dir.mkdir()
        manager = CITokenManager(server_dir_path=str(server_dir))

        # Save a valid token
        valid_token = "glpat-" + "a" * 20
        manager.save_token("gitlab", valid_token)

        # Corrupt the token to cause "Invalid IV size" error
        token_file = server_dir / "ci_tokens.json"
        with open(token_file, "r") as f:
            data = json.load(f)
        data["gitlab"]["token"] = ""
        with open(token_file, "w") as f:
            json.dump(data, f)

        # This should NOT raise ValueError: Invalid IV size (0) for CBC
        result = manager.get_token("gitlab")
        assert result is None, "get_token should return None for corrupted token"
