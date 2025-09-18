"""Business Logic for CIDX Remote Operations.

Clean business logic that uses API client abstractions with no raw HTTP calls.
All HTTP functionality is delegated to dedicated API client classes.
"""

from .remote_operations import (
    execute_remote_query,
    discover_and_link_repository,
    get_remote_repository_status,
    RemoteOperationError,
    RepositoryLinkingError,
)

__all__ = [
    "execute_remote_query",
    "discover_and_link_repository",
    "get_remote_repository_status",
    "RemoteOperationError",
    "RepositoryLinkingError",
]
