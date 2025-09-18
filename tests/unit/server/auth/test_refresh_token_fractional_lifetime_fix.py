"""
TDD Test Suite for Fractional Refresh Token Lifetime Fix.

MESSI RULE #1 COMPLIANCE: ZERO MOCKS - REAL SYSTEMS ONLY

This test suite demonstrates the bug where fractional refresh_token_lifetime_days
causes validation errors due to non-integer expires_in values.

RED-GREEN-REFACTOR: Writing failing tests first to reproduce the exact issue.
"""

import tempfile
import shutil
from pathlib import Path
from datetime import timedelta
import pytest

from code_indexer.server.auth.jwt_manager import JWTManager
from code_indexer.server.auth.refresh_token_manager import RefreshTokenManager
from code_indexer.server.utils.jwt_secret_manager import JWTSecretManager


class TestFractionalLifetimeFix:
    """
    TDD test suite for fractional refresh token lifetime calculation fix.

    RED PHASE: These tests should FAIL until the bug is fixed.
    """

    def setup_method(self):
        """Set up real test environment with actual components."""
        # Create temporary directory for test data
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

        # Initialize REAL JWT components
        self.jwt_secret_manager = JWTSecretManager(
            str(self.temp_path / "jwt_secret.key")
        )
        self.jwt_manager = JWTManager(
            secret_key=self.jwt_secret_manager.get_or_create_secret(),
            algorithm="HS256",
            token_expiration_minutes=15,
        )

    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_fractional_lifetime_produces_integer_expires_in(self):
        """
        RED TEST: This should FAIL showing fractional expires_in values.

        When refresh_token_lifetime_days is fractional (0.00001),
        the expires_in calculation should produce an integer, not float.
        """
        # Create refresh token manager with fractional lifetime
        refresh_manager = RefreshTokenManager(
            jwt_manager=self.jwt_manager,
            db_path=str(self.temp_path / "fractional_test.db"),
            refresh_token_lifetime_days=0.00001,  # Very short: ~0.864 seconds
        )

        # Create token family and initial token
        family_id = refresh_manager.create_token_family("testuser")
        user_data = {"username": "testuser", "role": "normal_user"}

        # Get token response with lifetime information
        token_response = refresh_manager.create_initial_refresh_token(
            family_id=family_id, username="testuser", user_data=user_data
        )

        # CRITICAL BUG: refresh_token_expires_in should be INTEGER, not float
        refresh_expires_in = token_response["refresh_token_expires_in"]

        # This assertion should FAIL in RED phase - expires_in is fractional
        assert isinstance(refresh_expires_in, int), (
            f"refresh_token_expires_in must be integer, got {type(refresh_expires_in)} "
            f"with value {refresh_expires_in}"
        )

        # Additional verification: value should be non-zero positive integer
        assert refresh_expires_in > 0, "expires_in must be positive"
        assert refresh_expires_in == int(
            refresh_expires_in
        ), "expires_in must not have fractional part"

    @pytest.mark.parametrize(
        "lifetime_days",
        [
            0.00001,  # ~0.864 seconds
            0.0001,  # ~8.64 seconds
            0.001,  # ~86.4 seconds
            0.1,  # ~8640 seconds
            1.5,  # 1.5 days
            7.25,  # 7.25 days
        ],
    )
    def test_various_fractional_lifetimes_always_produce_integers(self, lifetime_days):
        """
        RED TEST: Test multiple fractional values to ensure consistency.

        All fractional lifetime values should produce integer expires_in,
        even when the mathematical result has decimal places.
        """
        # Create manager with fractional lifetime
        refresh_manager = RefreshTokenManager(
            jwt_manager=self.jwt_manager,
            db_path=str(self.temp_path / f"test_{lifetime_days}.db"),
            refresh_token_lifetime_days=lifetime_days,
        )

        # Create tokens
        family_id = refresh_manager.create_token_family("testuser")
        user_data = {"username": "testuser", "role": "normal_user"}

        token_response = refresh_manager.create_initial_refresh_token(
            family_id=family_id, username="testuser", user_data=user_data
        )

        # Verify expires_in is integer
        refresh_expires_in = token_response["refresh_token_expires_in"]
        assert isinstance(refresh_expires_in, int), (
            f"For lifetime {lifetime_days} days, expires_in must be integer, "
            f"got {type(refresh_expires_in)} with value {refresh_expires_in}"
        )

    def test_zero_lifetime_edge_case(self):
        """
        RED TEST: Test edge case of zero lifetime.

        Even zero lifetime should produce integer expires_in (0).
        """
        # Create manager with zero lifetime
        refresh_manager = RefreshTokenManager(
            jwt_manager=self.jwt_manager,
            db_path=str(self.temp_path / "zero_lifetime.db"),
            refresh_token_lifetime_days=0,  # Zero lifetime
        )

        # Create tokens
        family_id = refresh_manager.create_token_family("testuser")
        user_data = {"username": "testuser", "role": "normal_user"}

        token_response = refresh_manager.create_initial_refresh_token(
            family_id=family_id, username="testuser", user_data=user_data
        )

        # Verify zero lifetime produces integer 0
        refresh_expires_in = token_response["refresh_token_expires_in"]
        assert isinstance(refresh_expires_in, int), "Zero lifetime must produce integer"
        assert refresh_expires_in == 0, "Zero lifetime must produce expires_in = 0"

    def test_calculation_consistency_with_minimum_protection(self):
        """
        GREEN TEST: Verify expires_in uses minimum 1 second for non-zero lifetimes.

        Very small fractional lifetimes should not result in 0 seconds to prevent
        immediate token expiration. The system enforces a minimum of 1 second.
        """
        lifetime_days = 0.00001  # Fractional lifetime

        # Calculate raw seconds using timedelta
        raw_seconds = int(timedelta(days=lifetime_days).total_seconds())
        # For very small lifetimes, raw calculation yields 0, but we expect minimum 1
        expected_seconds = max(1, raw_seconds) if lifetime_days > 0 else 0

        # Create manager and get actual expires_in
        refresh_manager = RefreshTokenManager(
            jwt_manager=self.jwt_manager,
            db_path=str(self.temp_path / "consistency_test.db"),
            refresh_token_lifetime_days=lifetime_days,
        )

        family_id = refresh_manager.create_token_family("testuser")
        user_data = {"username": "testuser", "role": "normal_user"}

        token_response = refresh_manager.create_initial_refresh_token(
            family_id=family_id, username="testuser", user_data=user_data
        )

        # Verify consistency with minimum protection
        refresh_expires_in = token_response["refresh_token_expires_in"]
        assert refresh_expires_in == expected_seconds, (
            f"expires_in ({refresh_expires_in}) should match protected seconds ({expected_seconds}), "
            f"raw calculation was {raw_seconds}"
        )

        # Verify minimum protection is working
        assert (
            refresh_expires_in >= 1
        ), "Non-zero lifetime should result in at least 1 second"


# TDD VERDICT: 🔴 RED PHASE
# These tests should FAIL until the fractional lifetime calculation is fixed.
# The bug is in RefreshTokenManager.create_initial_refresh_token() method
# where expires_in calculation produces float instead of required integer.
