"""Remote mode functionality for CIDX.

This module provides functionality for remote CIDX server connections,
including initialization, authentication, and configuration management.
"""

from .factories import RemoteServiceFactory
from .services.repository_service import RemoteRepositoryService

__all__ = ["RemoteServiceFactory", "RemoteRepositoryService"]
