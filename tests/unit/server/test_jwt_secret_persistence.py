"""
Test JWT secret key persistence functionality.

These tests verify that JWT secret keys are stored persistently
and tokens remain valid across server restarts.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.code_indexer.server.app import create_app


import pytest


@pytest.mark.e2e
class TestJWTSecretPersistence:
    """Test JWT secret key persistence across server restarts."""

    def test_jwt_secret_key_persists_across_restarts(self):
        """Test that JWT secret key is stored and reused across server restarts."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock the home directory to use our temp directory
            with patch("pathlib.Path.home", return_value=Path(temp_dir)):
                # Create first app instance
                create_app()

                # Get the JWT manager from the first instance
                from src.code_indexer.server.app import jwt_manager as jwt_manager1

                assert jwt_manager1 is not None, "JWT manager should be initialized"
                secret_key1 = jwt_manager1.secret_key

                # Verify secret was saved to file
                secret_file = Path(temp_dir) / ".cidx-server" / ".jwt_secret"
                assert secret_file.exists(), "JWT secret file should be created"

                # Create token with first app
                user_data = {
                    "username": "testuser",
                    "role": "normal_user",
                    "created_at": "2024-01-01T00:00:00+00:00",
                }
                token1 = jwt_manager1.create_token(user_data)

                # Create second app instance (simulating server restart)
                create_app()

                # Get the JWT manager from the second instance
                from src.code_indexer.server.app import jwt_manager as jwt_manager2

                assert jwt_manager2 is not None, "JWT manager should be initialized"
                secret_key2 = jwt_manager2.secret_key

                # Verify secret keys are the same
                assert (
                    secret_key1 == secret_key2
                ), "JWT secret should persist across restarts"

                # Verify token from first instance works with second instance
                payload = jwt_manager2.validate_token(token1)
                assert payload["username"] == "testuser"
                assert payload["role"] == "normal_user"

    def test_jwt_secret_file_created_with_proper_permissions(self):
        """Test that JWT secret file is created with secure permissions."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("pathlib.Path.home", return_value=Path(temp_dir)):
                # Create app instance
                create_app()

                # Check secret file exists and has proper permissions
                secret_file = Path(temp_dir) / ".cidx-server" / ".jwt_secret"
                assert secret_file.exists()

                # File should be readable only by owner (600 permissions)
                file_mode = secret_file.stat().st_mode & 0o777
                assert (
                    file_mode == 0o600
                ), f"Expected 0o600 permissions, got {oct(file_mode)}"

    def test_jwt_secret_reused_if_file_exists(self):
        """Test that existing JWT secret file is reused rather than overwritten."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("pathlib.Path.home", return_value=Path(temp_dir)):
                # Manually create secret file with known content
                cidx_server_dir = Path(temp_dir) / ".cidx-server"
                cidx_server_dir.mkdir(exist_ok=True)
                secret_file = cidx_server_dir / ".jwt_secret"

                known_secret = "test-secret-key-12345"
                secret_file.write_text(known_secret)
                secret_file.chmod(0o600)

                # Create app instance
                create_app()

                # Verify the known secret was used
                from src.code_indexer.server.app import jwt_manager

                assert jwt_manager is not None, "JWT manager should be initialized"
                assert jwt_manager.secret_key == known_secret

    def test_jwt_secret_fallback_to_env_var(self):
        """Test that JWT secret falls back to environment variable if file doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("pathlib.Path.home", return_value=Path(temp_dir)):
                env_secret = "env-secret-key-67890"
                with patch.dict(os.environ, {"JWT_SECRET_KEY": env_secret}):
                    # Create app instance
                    create_app()

                    # Verify environment variable was used and saved to file
                    from src.code_indexer.server.app import jwt_manager

                    assert jwt_manager is not None, "JWT manager should be initialized"
                    assert jwt_manager.secret_key == env_secret

                    # Verify secret was saved to file for future use
                    secret_file = Path(temp_dir) / ".cidx-server" / ".jwt_secret"
                    assert secret_file.exists()
                    assert secret_file.read_text().strip() == env_secret
