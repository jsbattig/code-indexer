"""
Shared test infrastructure for unit and integration tests.

Provides common components for testing including embedding provider enums.

NOTE: This file previously contained Docker/Podman container management code
that has been removed as CIDX moved to a container-free architecture.
Only the EmbeddingProvider enum remains for test compatibility.
"""

from enum import Enum


class EmbeddingProvider(Enum):
    """Enumeration of embedding providers for testing."""

    VOYAGE_AI = "voyage_ai"
    VOYAGE = "voyage"
    MOCK = "mock"
