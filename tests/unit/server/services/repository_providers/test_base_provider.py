"""
Tests for RepositoryProviderBase ABC.

Following TDD methodology - these tests are written FIRST before implementation.
Tests define the expected behavior for the abstract base class that all
repository providers (GitLab, GitHub) must implement.
"""

import pytest
from abc import ABC
from unittest.mock import AsyncMock


class TestRepositoryProviderBase:
    """Tests for RepositoryProviderBase abstract base class."""

    def test_provider_base_is_abstract(self):
        """Test that RepositoryProviderBase is an abstract class."""
        from code_indexer.server.services.repository_providers.base import (
            RepositoryProviderBase,
        )

        assert issubclass(RepositoryProviderBase, ABC)

    def test_provider_base_cannot_be_instantiated(self):
        """Test that RepositoryProviderBase cannot be instantiated directly."""
        from code_indexer.server.services.repository_providers.base import (
            RepositoryProviderBase,
        )

        with pytest.raises(TypeError):
            RepositoryProviderBase()

    def test_provider_base_has_discover_repositories_method(self):
        """Test that RepositoryProviderBase defines discover_repositories method."""
        from code_indexer.server.services.repository_providers.base import (
            RepositoryProviderBase,
        )

        # Verify the method exists as an abstract method
        assert hasattr(RepositoryProviderBase, "discover_repositories")
        assert getattr(
            RepositoryProviderBase.discover_repositories, "__isabstractmethod__", False
        )

    def test_provider_base_has_platform_property(self):
        """Test that RepositoryProviderBase defines platform property."""
        from code_indexer.server.services.repository_providers.base import (
            RepositoryProviderBase,
        )

        # Verify the property exists as an abstract property
        assert hasattr(RepositoryProviderBase, "platform")

    def test_provider_base_has_is_configured_method(self):
        """Test that RepositoryProviderBase defines is_configured method."""
        from code_indexer.server.services.repository_providers.base import (
            RepositoryProviderBase,
        )

        assert hasattr(RepositoryProviderBase, "is_configured")
        assert getattr(
            RepositoryProviderBase.is_configured, "__isabstractmethod__", False
        )

    def test_concrete_implementation_can_be_created(self):
        """Test that a concrete implementation can be created."""
        from code_indexer.server.services.repository_providers.base import (
            RepositoryProviderBase,
        )
        from code_indexer.server.models.auto_discovery import (
            RepositoryDiscoveryResult,
            DiscoveredRepository,
        )

        class ConcreteProvider(RepositoryProviderBase):
            @property
            def platform(self) -> str:
                return "test"

            async def is_configured(self) -> bool:
                return True

            async def discover_repositories(
                self, page: int = 1, page_size: int = 50
            ) -> RepositoryDiscoveryResult:
                return RepositoryDiscoveryResult(
                    repositories=[],
                    total_count=0,
                    page=page,
                    page_size=page_size,
                    total_pages=0,
                    platform="gitlab",
                )

        provider = ConcreteProvider()
        assert provider.platform == "test"

    @pytest.mark.asyncio
    async def test_concrete_implementation_methods_can_be_called(self):
        """Test that concrete implementation methods can be called."""
        from code_indexer.server.services.repository_providers.base import (
            RepositoryProviderBase,
        )
        from code_indexer.server.models.auto_discovery import (
            RepositoryDiscoveryResult,
        )

        class ConcreteProvider(RepositoryProviderBase):
            @property
            def platform(self) -> str:
                return "test"

            async def is_configured(self) -> bool:
                return True

            async def discover_repositories(
                self, page: int = 1, page_size: int = 50
            ) -> RepositoryDiscoveryResult:
                return RepositoryDiscoveryResult(
                    repositories=[],
                    total_count=0,
                    page=page,
                    page_size=page_size,
                    total_pages=0,
                    platform="gitlab",
                )

        provider = ConcreteProvider()
        assert await provider.is_configured() is True
        result = await provider.discover_repositories(page=1, page_size=50)
        assert isinstance(result, RepositoryDiscoveryResult)
