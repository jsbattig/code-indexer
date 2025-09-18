"""API Client Abstractions for CIDX Remote Operations.

Provides clean HTTP client abstractions with no raw HTTP calls in business logic.
All HTTP functionality is contained within dedicated API client classes.
"""

from .base_client import (
    CIDXRemoteAPIClient,
    APIClientError,
    AuthenticationError,
    NetworkError,
    TokenExpiredError,
)
from .jwt_token_manager import JWTTokenManager, TokenValidationError
from .repository_linking_client import (
    RepositoryLinkingClient,
    RepositoryDiscoveryResponse,
    BranchInfo,
    ActivatedRepository,
    RepositoryNotFoundError,
    BranchNotFoundError,
    ActivationError,
)
from .remote_query_client import (
    RemoteQueryClient,
    QueryResultItem,
    RepositoryInfo,
    QueryExecutionError,
    RepositoryAccessError,
    QueryLimitExceededError,
)

__all__ = [
    # Base client
    "CIDXRemoteAPIClient",
    "APIClientError",
    "AuthenticationError",
    "NetworkError",
    "TokenExpiredError",
    # JWT token manager
    "JWTTokenManager",
    "TokenValidationError",
    # Repository linking client
    "RepositoryLinkingClient",
    "RepositoryDiscoveryResponse",
    "BranchInfo",
    "ActivatedRepository",
    "RepositoryNotFoundError",
    "BranchNotFoundError",
    "ActivationError",
    # Remote query client
    "RemoteQueryClient",
    "QueryResultItem",
    "RepositoryInfo",
    "QueryExecutionError",
    "RepositoryAccessError",
    "QueryLimitExceededError",
]
