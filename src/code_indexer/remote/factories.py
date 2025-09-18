"""Factory classes for remote service dependency injection."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..api_clients.base_client import CIDXRemoteAPIClient
    from .staleness_detector import StalenessDetector
    from .services.repository_service import RemoteRepositoryService
    from ..remote_status import RemoteStatusDisplayer


class RemoteServiceFactory:
    """Factory for creating remote service instances with proper dependency injection."""

    @staticmethod
    def create_repository_service(
        api_client: "CIDXRemoteAPIClient", staleness_detector: "StalenessDetector"
    ) -> "RemoteRepositoryService":
        """Create RemoteRepositoryService with injected dependencies.

        Args:
            api_client: CIDX Remote API client for server communication
            staleness_detector: Detector for staleness analysis

        Returns:
            Configured RemoteRepositoryService instance
        """
        from .services.repository_service import RemoteRepositoryService

        return RemoteRepositoryService(api_client, staleness_detector)

    @staticmethod
    def create_remote_status_displayer(
        repository_service: "RemoteRepositoryService",
    ) -> "RemoteStatusDisplayer":
        """Create RemoteStatusDisplayer with injected repository service.

        Args:
            repository_service: Repository service for business logic

        Returns:
            Configured RemoteStatusDisplayer instance
        """
        from ..remote_status import RemoteStatusDisplayer

        return RemoteStatusDisplayer(repository_service)
