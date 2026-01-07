"""
E2E Tests for Temporal Search Payload Control (Story #681).

CRITICAL REQUIREMENT: This test uses ZERO mocks for core functionality:
- Real PayloadCache with real SQLite database
- Real temporal truncation and cache retrieval
- Real MCP tool invocation

Tests verify the complete temporal user workflow:
1. Large temporal content is truncated with cache handle for later retrieval
2. Evolution content and diff fields can be cached independently
3. Cached temporal content can be retrieved via MCP get_cached_content tool
4. Pagination works for temporal cached content
"""

import pytest
from unittest.mock import patch, Mock

from code_indexer.server.cache.payload_cache import (
    PayloadCache,
    PayloadCacheConfig,
)
from code_indexer.server.auth.user_manager import User, UserRole


PREVIEW_SIZE = 2000


class TestTemporalPayloadCacheE2E:
    """E2E tests for Temporal PayloadCache truncation functionality."""

    @pytest.fixture
    async def cache_with_standard_config(self, tmp_path):
        """Create PayloadCache with standard settings."""
        config = PayloadCacheConfig(
            preview_size_chars=PREVIEW_SIZE,
            max_fetch_size_chars=5000,
            cache_ttl_seconds=900,
        )
        cache = PayloadCache(db_path=tmp_path / "test_cache.db", config=config)
        await cache.initialize()
        yield cache
        await cache.close()

    @pytest.mark.asyncio
    async def test_temporal_large_content_truncation_workflow(
        self, cache_with_standard_config
    ):
        """E2E: Large temporal content is truncated with cache handle for retrieval."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        large_content = "def temporal_function():\n" + "    # Temporal code\n" * 200
        results = [
            {
                "file_path": "/src/temporal.py",
                "content": large_content,
                "similarity_score": 0.95,
                "temporal_context": {
                    "commit_hash": "abc123",
                    "commit_date": "2024-01-15T10:30:00Z",
                },
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache_with_standard_config

            truncated = await _apply_temporal_payload_truncation(results)

        result = truncated[0]

        # Verify truncation happened
        assert result["content_has_more"] is True
        assert len(result["content_preview"]) == PREVIEW_SIZE
        assert result["content_cache_handle"] is not None

        # Verify full content can be retrieved from cache
        retrieved = await cache_with_standard_config.retrieve(
            result["content_cache_handle"], page=0
        )
        assert retrieved.content == large_content
        assert retrieved.page == 0
        assert retrieved.has_more is False

    @pytest.mark.asyncio
    async def test_temporal_evolution_content_truncation_workflow(
        self, cache_with_standard_config
    ):
        """E2E: Large evolution content is truncated with cache handle."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        large_evo_content = "EVOLUTION_CONTENT_" * 200  # ~3400 chars
        results = [
            {
                "file_path": "/src/example.py",
                "content": "small main content",
                "temporal_context": {
                    "evolution": [
                        {
                            "commit_hash": "def456",
                            "content": large_evo_content,
                            "diff": "small diff",
                            "timestamp": "2024-02-01T00:00:00Z",
                        }
                    ]
                },
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache_with_standard_config

            truncated = await _apply_temporal_payload_truncation(results)

        evo_entry = truncated[0]["temporal_context"]["evolution"][0]

        # Verify evolution content truncation
        assert evo_entry["content_has_more"] is True
        assert len(evo_entry["content_preview"]) == PREVIEW_SIZE
        assert evo_entry["content_cache_handle"] is not None

        # Verify full evolution content can be retrieved
        retrieved = await cache_with_standard_config.retrieve(
            evo_entry["content_cache_handle"], page=0
        )
        assert retrieved.content == large_evo_content

    @pytest.mark.asyncio
    async def test_temporal_evolution_diff_truncation_workflow(
        self, cache_with_standard_config
    ):
        """E2E: Large evolution diff is truncated with cache handle."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        large_diff = "DIFF_LINE_" * 300  # 3000 chars
        results = [
            {
                "content": "main content",
                "temporal_context": {
                    "evolution": [
                        {
                            "commit_hash": "ghi789",
                            "content": "small content",
                            "diff": large_diff,
                        }
                    ]
                },
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache_with_standard_config

            truncated = await _apply_temporal_payload_truncation(results)

        evo_entry = truncated[0]["temporal_context"]["evolution"][0]

        # Verify diff truncation
        assert evo_entry["diff_has_more"] is True
        assert len(evo_entry["diff_preview"]) == PREVIEW_SIZE
        assert evo_entry["diff_cache_handle"] is not None

        # Verify full diff can be retrieved
        retrieved = await cache_with_standard_config.retrieve(
            evo_entry["diff_cache_handle"], page=0
        )
        assert retrieved.content == large_diff

    @pytest.mark.asyncio
    async def test_temporal_all_fields_independent_caching(
        self, cache_with_standard_config
    ):
        """E2E: Main content, evolution content, and diff are cached independently."""
        from code_indexer.server.mcp.handlers import _apply_temporal_payload_truncation

        main_content = "MAIN_" * 500  # 2500 chars
        evo_content = "EVO_" * 600  # 2400 chars
        evo_diff = "DIFF_" * 700  # 3500 chars

        results = [
            {
                "content": main_content,
                "temporal_context": {
                    "evolution": [
                        {
                            "commit_hash": "xyz123",
                            "content": evo_content,
                            "diff": evo_diff,
                        }
                    ]
                },
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache_with_standard_config

            truncated = await _apply_temporal_payload_truncation(results)

        result = truncated[0]
        evo_entry = result["temporal_context"]["evolution"][0]

        # All three should be truncated with different handles
        assert result["content_has_more"] is True
        assert evo_entry["content_has_more"] is True
        assert evo_entry["diff_has_more"] is True

        handles = [
            result["content_cache_handle"],
            evo_entry["content_cache_handle"],
            evo_entry["diff_cache_handle"],
        ]
        assert len(set(handles)) == 3  # All unique

        # Retrieve each and verify correct content
        main_retrieved = await cache_with_standard_config.retrieve(handles[0], page=0)
        evo_retrieved = await cache_with_standard_config.retrieve(handles[1], page=0)
        diff_retrieved = await cache_with_standard_config.retrieve(handles[2], page=0)

        assert main_retrieved.content == main_content
        assert evo_retrieved.content == evo_content
        assert diff_retrieved.content == evo_diff


class TestTemporalMcpCacheRetrievalE2E:
    """E2E tests for MCP get_cached_content tool with temporal handles (AC5)."""

    @pytest.fixture
    async def cache(self, tmp_path):
        """Create PayloadCache for testing."""
        config = PayloadCacheConfig(
            preview_size_chars=PREVIEW_SIZE,
            max_fetch_size_chars=5000,
            cache_ttl_seconds=900,
        )
        cache = PayloadCache(db_path=tmp_path / "test_cache.db", config=config)
        await cache.initialize()
        yield cache
        await cache.close()

    @pytest.fixture
    def mock_user(self):
        """Create a mock user for MCP handler testing."""
        user = Mock(spec=User)
        user.username = "testuser"
        user.role = UserRole.NORMAL_USER
        user.has_permission = Mock(return_value=True)
        return user

    @pytest.mark.asyncio
    async def test_mcp_get_cached_content_for_temporal_content(self, cache, mock_user):
        """E2E: MCP get_cached_content works with temporal content handles."""
        from code_indexer.server.mcp.handlers import (
            _apply_temporal_payload_truncation,
            handle_get_cached_content,
        )
        import json

        # Create and truncate temporal result
        large_content = "TEMPORAL_CONTENT_" * 200  # 3400 chars
        results = [
            {
                "content": large_content,
                "temporal_context": {"commit_hash": "abc123"},
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache
            truncated = await _apply_temporal_payload_truncation(results)

        content_handle = truncated[0]["content_cache_handle"]

        # Retrieve via MCP tool
        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            mcp_result = await handle_get_cached_content(
                {"handle": content_handle, "page": 0}, mock_user
            )

        # Parse MCP response
        data = json.loads(mcp_result["content"][0]["text"])

        assert data["success"] is True
        assert data["content"] == large_content
        assert data["page"] == 0
        assert data["has_more"] is False

    @pytest.mark.asyncio
    async def test_mcp_get_cached_content_for_evolution_content(self, cache, mock_user):
        """E2E: MCP get_cached_content works with evolution content handles."""
        from code_indexer.server.mcp.handlers import (
            _apply_temporal_payload_truncation,
            handle_get_cached_content,
        )
        import json

        large_evo_content = "EVO_CONTENT_" * 250  # 3000 chars
        results = [
            {
                "content": "small",
                "temporal_context": {
                    "evolution": [
                        {"content": large_evo_content, "diff": "small diff"}
                    ]
                },
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache
            truncated = await _apply_temporal_payload_truncation(results)

        evo_handle = truncated[0]["temporal_context"]["evolution"][0][
            "content_cache_handle"
        ]

        # Retrieve via MCP tool
        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            mcp_result = await handle_get_cached_content(
                {"handle": evo_handle, "page": 0}, mock_user
            )

        data = json.loads(mcp_result["content"][0]["text"])
        assert data["success"] is True
        assert data["content"] == large_evo_content

    @pytest.mark.asyncio
    async def test_mcp_get_cached_content_for_evolution_diff(self, cache, mock_user):
        """E2E: MCP get_cached_content works with evolution diff handles."""
        from code_indexer.server.mcp.handlers import (
            _apply_temporal_payload_truncation,
            handle_get_cached_content,
        )
        import json

        large_diff = "DIFF_" * 600  # 3000 chars
        results = [
            {
                "content": "small",
                "temporal_context": {
                    "evolution": [{"content": "small", "diff": large_diff}]
                },
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache
            truncated = await _apply_temporal_payload_truncation(results)

        diff_handle = truncated[0]["temporal_context"]["evolution"][0][
            "diff_cache_handle"
        ]

        # Retrieve via MCP tool
        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            mcp_result = await handle_get_cached_content(
                {"handle": diff_handle, "page": 0}, mock_user
            )

        data = json.loads(mcp_result["content"][0]["text"])
        assert data["success"] is True
        assert data["content"] == large_diff

    @pytest.mark.asyncio
    async def test_mcp_pagination_for_temporal_content(self, cache, mock_user):
        """E2E: MCP pagination works for large temporal cached content."""
        from code_indexer.server.mcp.handlers import (
            _apply_temporal_payload_truncation,
            handle_get_cached_content,
        )
        import json

        # Create content that spans multiple pages
        page1_content = "A" * 5000
        page2_content = "B" * 5000
        large_content = page1_content + page2_content

        results = [{"content": large_content, "temporal_context": {}}]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache
            truncated = await _apply_temporal_payload_truncation(results)

        content_handle = truncated[0]["content_cache_handle"]

        # Retrieve page 0 and page 1 via MCP
        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            page0_result = await handle_get_cached_content(
                {"handle": content_handle, "page": 0}, mock_user
            )
            page1_result = await handle_get_cached_content(
                {"handle": content_handle, "page": 1}, mock_user
            )

        # Verify page 0
        page0_data = json.loads(page0_result["content"][0]["text"])
        assert page0_data["success"] is True
        assert page0_data["content"] == page1_content
        assert page0_data["page"] == 0
        assert page0_data["total_pages"] == 2
        assert page0_data["has_more"] is True

        # Verify page 1
        page1_data = json.loads(page1_result["content"][0]["text"])
        assert page1_data["success"] is True
        assert page1_data["content"] == page2_content
        assert page1_data["page"] == 1
        assert page1_data["has_more"] is False

    @pytest.mark.asyncio
    async def test_mcp_expired_temporal_handle_returns_error(self, cache, mock_user):
        """E2E: MCP returns error for expired/invalid temporal cache handle."""
        from code_indexer.server.mcp.handlers import handle_get_cached_content
        import json

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = cache

            mcp_result = await handle_get_cached_content(
                {"handle": "non-existent-temporal-handle", "page": 0}, mock_user
            )

        data = json.loads(mcp_result["content"][0]["text"])
        assert data["success"] is False
        assert "error" in data
