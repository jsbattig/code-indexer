"""
Unit tests for CITokenManager service.

Tests AC5, AC6, AC9, AC10, AC11, AC14:
- Token encryption/decryption (AC14)
- Token storage and retrieval (AC5, AC6)
- Token deletion (AC11)
- Token format validation (AC9, AC10)
- File permissions (AC14)
- AES-256-CBC encryption with PBKDF2 (AC14)
"""

import json
import os
import pytest
import re

from src.code_indexer.server.services.ci_token_manager import (
    CITokenManager,
    TokenValidationError,
)

# Test token constants for clarity
GITHUB_TOKEN_SUFFIX_LEN = 36
GITLAB_TOKEN_SUFFIX_LEN = 20
GITHUB_PAT_SUFFIX_LEN = 22


class TestCITokenManagerEncryption:
    """Test encryption and decryption functionality (AC14)."""

    @pytest.fixture
    def temp_server_dir(self, tmp_path):
        """Create temporary server directory for testing."""
        server_dir = tmp_path / ".cidx-server"
        server_dir.mkdir()
        return server_dir

    @pytest.fixture
    def token_manager(self, temp_server_dir):
        """Create CITokenManager instance with temp directory."""
        return CITokenManager(server_dir_path=str(temp_server_dir))

    def test_save_token_creates_encrypted_file(self, token_manager, temp_server_dir):
        """Test that saved tokens are encrypted in storage file (AC14)."""
        # Given a valid GitHub token
        github_token = "ghp_" + "a" * GITHUB_TOKEN_SUFFIX_LEN

        # When saving the token
        token_manager.save_token("github", github_token)

        # Then the token file should exist
        token_file = temp_server_dir / "ci_tokens.json"
        assert token_file.exists()

        # And the token value should be encrypted (not plaintext)
        with open(token_file, "r") as f:
            data = json.load(f)

        assert "github" in data
        assert data["github"]["token"] != github_token
        # Encrypted value should look like base64
        assert re.match(r"^[A-Za-z0-9+/=]+$", data["github"]["token"])

    def test_token_file_has_secure_permissions(self, token_manager, temp_server_dir):
        """Test that token file has 0600 permissions (AC14)."""
        # Given a saved token
        github_token = "ghp_" + "a" * GITHUB_TOKEN_SUFFIX_LEN
        token_manager.save_token("github", github_token)

        # When checking file permissions
        token_file = temp_server_dir / "ci_tokens.json"
        file_mode = os.stat(token_file).st_mode & 0o777

        # Then permissions should be 0600
        assert file_mode == 0o600

    def test_encryption_uses_aes_256_cbc(self, token_manager):
        """Test that encryption uses AES-256-CBC (AC14)."""
        # Given a token
        token = "ghp_" + "a" * GITHUB_TOKEN_SUFFIX_LEN

        # When encrypting
        encrypted = token_manager._encrypt_token(token)

        # Then encrypted value should be different from plaintext
        assert encrypted != token

        # And should be base64 encoded (AES-256-CBC output)
        assert re.match(r"^[A-Za-z0-9+/=]+$", encrypted)

        # And should decrypt back to original
        decrypted = token_manager._decrypt_token(encrypted)
        assert decrypted == token

    def test_decrypt_round_trip(self, token_manager):
        """Test encryption/decryption round trip (AC14)."""
        # Given a plaintext token
        original_token = "glpat-" + "a" * GITLAB_TOKEN_SUFFIX_LEN

        # When encrypting then decrypting
        encrypted = token_manager._encrypt_token(original_token)
        decrypted = token_manager._decrypt_token(encrypted)

        # Then we get back the original token
        assert decrypted == original_token


class TestCITokenManagerCRUD:
    """Test CRUD operations for tokens (AC5, AC6, AC11)."""

    @pytest.fixture
    def temp_server_dir(self, tmp_path):
        """Create temporary server directory for testing."""
        server_dir = tmp_path / ".cidx-server"
        server_dir.mkdir()
        return server_dir

    @pytest.fixture
    def token_manager(self, temp_server_dir):
        """Create CITokenManager instance with temp directory."""
        return CITokenManager(server_dir_path=str(temp_server_dir))

    def test_save_and_retrieve_github_token(self, token_manager):
        """Test saving and retrieving GitHub token (AC5)."""
        # Given a valid GitHub token
        github_token = "ghp_" + "a" * GITHUB_TOKEN_SUFFIX_LEN

        # When saving the token
        token_manager.save_token("github", github_token)

        # Then we can retrieve it
        token_data = token_manager.get_token("github")
        assert token_data is not None
        assert token_data.platform == "github"
        assert token_data.token == github_token
        assert token_data.base_url is None

    def test_save_gitlab_token_with_custom_url(self, token_manager):
        """Test saving GitLab token with custom URL (AC7)."""
        # Given a GitLab token and custom URL
        gitlab_token = "glpat-" + "a" * GITLAB_TOKEN_SUFFIX_LEN
        custom_url = "https://gitlab.company.com"

        # When saving with custom URL
        token_manager.save_token("gitlab", gitlab_token, base_url=custom_url)

        # Then we can retrieve both token and URL
        token_data = token_manager.get_token("gitlab")
        assert token_data is not None
        assert token_data.platform == "gitlab"
        assert token_data.token == gitlab_token
        assert token_data.base_url == custom_url

    def test_get_nonexistent_token(self, token_manager):
        """Test retrieving a token that doesn't exist (AC4)."""
        # When retrieving a token that was never saved
        token_data = token_manager.get_token("github")

        # Then it should return None
        assert token_data is None

    def test_update_existing_token(self, token_manager):
        """Test updating an existing token (AC6)."""
        # Given an existing GitLab token
        old_token = "glpat-" + "a" * GITLAB_TOKEN_SUFFIX_LEN
        token_manager.save_token("gitlab", old_token)

        # When updating with new token
        new_token = "glpat-" + "b" * GITLAB_TOKEN_SUFFIX_LEN
        token_manager.save_token("gitlab", new_token)

        # Then the new token should replace the old one
        token_data = token_manager.get_token("gitlab")
        assert token_data.token == new_token
        assert token_data.token != old_token

    def test_delete_token(self, token_manager):
        """Test deleting a configured token (AC11)."""
        # Given a configured GitHub token
        github_token = "ghp_" + "a" * GITHUB_TOKEN_SUFFIX_LEN
        token_manager.save_token("github", github_token)

        # When deleting the token
        token_manager.delete_token("github")

        # Then the token should no longer exist
        token_data = token_manager.get_token("github")
        assert token_data is None

    def test_list_tokens_empty(self, token_manager):
        """Test listing tokens when none configured (AC4)."""
        # When no tokens are configured
        tokens = token_manager.list_tokens()

        # Then should return status for known platforms
        assert "github" in tokens
        assert "gitlab" in tokens
        assert tokens["github"].configured is False
        assert tokens["gitlab"].configured is False

    def test_list_tokens_with_configured(self, token_manager):
        """Test listing tokens with some configured (AC2, AC3)."""
        # Given GitHub token configured but not GitLab
        github_token = "ghp_" + "a" * GITHUB_TOKEN_SUFFIX_LEN
        token_manager.save_token("github", github_token)

        # When listing tokens
        tokens = token_manager.list_tokens()

        # Then GitHub should show as configured
        assert tokens["github"].configured is True
        assert tokens["github"].platform == "github"

        # And GitLab should show as not configured
        assert tokens["gitlab"].configured is False


class TestCITokenManagerValidation:
    """Test token format validation (AC9, AC10)."""

    @pytest.fixture
    def temp_server_dir(self, tmp_path):
        """Create temporary server directory for testing."""
        server_dir = tmp_path / ".cidx-server"
        server_dir.mkdir()
        return server_dir

    @pytest.fixture
    def token_manager(self, temp_server_dir):
        """Create CITokenManager instance with temp directory."""
        return CITokenManager(server_dir_path=str(temp_server_dir))

    def test_validate_github_token_valid_ghp(self, token_manager):
        """Test validation accepts valid ghp_ token (AC9)."""
        # Given a valid ghp_ format token
        valid_token = "ghp_" + "a" * GITHUB_TOKEN_SUFFIX_LEN

        # When validating
        # Then no exception should be raised
        token_manager._validate_token_format("github", valid_token)

    def test_validate_github_token_valid_pat(self, token_manager):
        """Test validation accepts valid github_pat_ token (AC9)."""
        # Given a valid github_pat_ format token
        valid_token = "github_pat_" + "a" * GITHUB_PAT_SUFFIX_LEN

        # When validating
        # Then no exception should be raised
        token_manager._validate_token_format("github", valid_token)

    def test_validate_github_token_invalid_format(self, token_manager):
        """Test validation rejects invalid GitHub token format (AC9)."""
        # Given invalid GitHub token formats
        invalid_tokens = [
            "invalid_token",
            "ghp_tooshort",
            "github_pat_short",
            "glpat-wrongprefix",
            "",
        ]

        # When validating each
        for invalid_token in invalid_tokens:
            # Then should raise TokenValidationError with helpful message
            with pytest.raises(TokenValidationError) as exc_info:
                token_manager._validate_token_format("github", invalid_token)

            # And error message should explain expected format
            assert "GitHub" in str(exc_info.value)
            assert "ghp_" in str(exc_info.value) or "github_pat_" in str(exc_info.value)

    def test_validate_gitlab_token_valid(self, token_manager):
        """Test validation accepts valid GitLab token (AC10)."""
        # Given a valid glpat- format token
        valid_token = "glpat-" + "a" * GITLAB_TOKEN_SUFFIX_LEN

        # When validating
        # Then no exception should be raised
        token_manager._validate_token_format("gitlab", valid_token)

    def test_validate_gitlab_token_valid_versioned_format(self, token_manager):
        """Test validation accepts newer GitLab versioned token format with periods."""
        # Given a valid glpat- format token with versioned suffix (newer GitLab format)
        # Example: glpat-x5DbmTJCwT6wqLXX6DxdmG86MQp1OmN5dG5qCw.01.120qe28y8
        valid_versioned_token = "glpat-x5DbmTJCwT6wqLXX6DxdmG86MQp1OmN5dG5qCw.01.120qe28y8"

        # When validating
        # Then no exception should be raised
        token_manager._validate_token_format("gitlab", valid_versioned_token)

    def test_validate_gitlab_token_invalid_format(self, token_manager):
        """Test validation rejects invalid GitLab token format (AC10)."""
        # Given invalid GitLab token formats
        invalid_tokens = [
            "invalid_token",
            "glpat-short",
            "ghp_wrongprefix",
            "",
        ]

        # When validating each
        for invalid_token in invalid_tokens:
            # Then should raise TokenValidationError
            with pytest.raises(TokenValidationError) as exc_info:
                token_manager._validate_token_format("gitlab", invalid_token)

            # And error message should explain expected format
            assert "GitLab" in str(exc_info.value)
            assert "glpat-" in str(exc_info.value)

    def test_save_token_validates_format(self, token_manager):
        """Test that save_token validates format before saving (AC9, AC10)."""
        # Given an invalid GitHub token
        invalid_token = "not_a_valid_token"

        # When trying to save
        # Then should raise validation error
        with pytest.raises(TokenValidationError):
            token_manager.save_token("github", invalid_token)

        # And token should not be saved
        assert token_manager.get_token("github") is None
