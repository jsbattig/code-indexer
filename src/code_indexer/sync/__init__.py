"""Enhanced Sync Integration for CIDX Repository Management.

Provides repository-aware sync functionality with backward compatibility.
"""

from .repository_context_detector import (
    RepositoryContextDetector,
    RepositoryContext,
    RepositoryContextError,
)
from .conflict_resolution import (
    ConflictDetector,
    ConflictResolver,
    SyncConflict,
    ConflictType,
    ResolutionAction,
    ResolutionResult,
    ConflictResolutionError,
)

__all__ = [
    "RepositoryContextDetector",
    "RepositoryContext",
    "RepositoryContextError",
    "ConflictDetector",
    "ConflictResolver",
    "SyncConflict",
    "ConflictType",
    "ResolutionAction",
    "ResolutionResult",
    "ConflictResolutionError",
]
