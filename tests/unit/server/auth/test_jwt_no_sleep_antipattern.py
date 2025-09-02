"""
Test JWT manager does not use time.sleep() anti-pattern.

These tests verify that JWT token extension works properly without
using time.sleep() and handles timestamp precision correctly.
"""

from unittest.mock import patch

from src.code_indexer.server.auth.jwt_manager import JWTManager


class TestJWTNoSleepAntiPattern:
    """Test JWT manager avoids time.sleep() anti-pattern."""

    def test_jwt_extension_does_not_use_time_sleep(self):
        """Test that JWT token extension doesn't use time.sleep()."""
        jwt_manager = JWTManager(
            secret_key="test-secret-key", token_expiration_minutes=10
        )

        # Create initial token
        user_data = {
            "username": "testuser",
            "role": "normal_user",
            "created_at": "2024-01-01T00:00:00+00:00",
        }
        original_token = jwt_manager.create_token(user_data)

        # Mock time.sleep to ensure it's not called
        with patch("time.sleep") as mock_sleep:
            extended_token = jwt_manager.extend_token_expiration(original_token)

            # Verify time.sleep was not called
            mock_sleep.assert_not_called()

        # Verify token extension still works
        payload = jwt_manager.validate_token(extended_token)
        assert payload["username"] == "testuser"
        assert payload["role"] == "normal_user"

    def test_jwt_extension_handles_timestamp_precision_correctly(self):
        """Test that JWT extension handles timestamp precision without sleep."""
        jwt_manager = JWTManager(
            secret_key="test-secret-key", token_expiration_minutes=10
        )

        # Create initial token
        user_data = {
            "username": "testuser",
            "role": "normal_user",
            "created_at": "2024-01-01T00:00:00+00:00",
        }
        original_token = jwt_manager.create_token(user_data)

        # Get original payload
        original_payload = jwt_manager.validate_token(original_token)
        original_exp = original_payload["exp"]
        original_iat = original_payload["iat"]

        # Extend token
        extended_token = jwt_manager.extend_token_expiration(original_token)

        # Get extended payload
        extended_payload = jwt_manager.validate_token(extended_token)
        extended_exp = extended_payload["exp"]
        extended_iat = extended_payload["iat"]

        # Verify expiration was extended
        assert extended_exp > original_exp, "Token expiration should be extended"

        # Verify issued at time was updated
        assert extended_iat > original_iat, "Token issued at should be updated"

        # Verify user data remains the same
        assert extended_payload["username"] == original_payload["username"]
        assert extended_payload["role"] == original_payload["role"]

    def test_jwt_extension_microsecond_precision(self):
        """Test that JWT extension works with microsecond precision timestamps."""
        jwt_manager = JWTManager(
            secret_key="test-secret-key", token_expiration_minutes=10
        )

        user_data = {
            "username": "testuser",
            "role": "normal_user",
            "created_at": "2024-01-01T00:00:00+00:00",
        }

        # Create multiple tokens in quick succession
        tokens = []
        for i in range(5):
            token = jwt_manager.create_token(user_data)
            tokens.append(token)

        # Verify all tokens are valid and have different timestamps
        timestamps = []
        for token in tokens:
            payload = jwt_manager.validate_token(token)
            timestamps.append(payload["iat"])

        # All timestamps should be different (microsecond precision)
        assert len(set(timestamps)) == len(
            timestamps
        ), "All token timestamps should be unique"

    def test_jwt_extension_rapid_succession(self):
        """Test that JWT extension works properly in rapid succession without sleep."""
        jwt_manager = JWTManager(
            secret_key="test-secret-key", token_expiration_minutes=10
        )

        user_data = {
            "username": "testuser",
            "role": "normal_user",
            "created_at": "2024-01-01T00:00:00+00:00",
        }
        original_token = jwt_manager.create_token(user_data)

        # Extend token multiple times in rapid succession
        current_token = original_token
        previous_exp = None

        for i in range(10):
            current_token = jwt_manager.extend_token_expiration(current_token)
            payload = jwt_manager.validate_token(current_token)
            current_exp = payload["exp"]

            if previous_exp is not None:
                # Each extension should increase expiration time
                assert (
                    current_exp > previous_exp
                ), f"Extension {i}: expiration should increase"

            previous_exp = current_exp

        # Final token should still be valid with correct user data
        final_payload = jwt_manager.validate_token(current_token)
        assert final_payload["username"] == "testuser"
        assert final_payload["role"] == "normal_user"
