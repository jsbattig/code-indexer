"""JWT fixtures for remote module tests.

Provides proper RSA key pairs and JWT token generation for testing
JWT token management functionality with real cryptographic operations.
"""

import pytest
from typing import Generator
from tests.infrastructure.real_jwt_manager import (
    RealJWTManager,
    create_real_jwt_manager,
)


@pytest.fixture
def real_jwt_manager() -> Generator[RealJWTManager, None, None]:
    """Fixture that provides a real JWT manager with RSA keys."""
    jwt_manager = create_real_jwt_manager()
    yield jwt_manager
    # Cleanup
    jwt_manager.clear_all_tokens()


@pytest.fixture
def rsa_key_pair(real_jwt_manager):
    """Fixture that provides RSA key pair for JWT operations."""
    return {
        "private_key": real_jwt_manager.private_key_pem,
        "public_key": real_jwt_manager.public_key_pem,
        "algorithm": real_jwt_manager.algorithm,
    }


@pytest.fixture
def valid_jwt_token(real_jwt_manager):
    """Fixture that provides a valid JWT token with proper RSA signature."""
    token_pair = real_jwt_manager.create_test_user_token("testuser")
    return token_pair.access_token


@pytest.fixture
def expired_jwt_token(real_jwt_manager):
    """Fixture that provides an expired JWT token."""
    return real_jwt_manager.create_expired_token("testuser")


@pytest.fixture
def near_expiry_jwt_token(real_jwt_manager):
    """Fixture that provides a JWT token near expiry."""
    return real_jwt_manager.create_near_expiry_token("testuser", expiry_seconds=30)
