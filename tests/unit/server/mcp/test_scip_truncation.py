"""Unit tests for SCIP payload truncation.

Story #685: S7 - SCIP with Payload Control

Tests for _apply_scip_payload_truncation() function that truncates
large context fields in SCIP results (definition, references, dependencies, dependents).

TDD: Tests written BEFORE implementation.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from code_indexer.server.auth.user_manager import User, UserRole


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    user = Mock(spec=User)
    user.username = "testuser"
    user.role = UserRole.NORMAL_USER
    user.has_permission = Mock(return_value=True)
    return user


@pytest.fixture
def mock_payload_cache():
    """Create a mock PayloadCache for testing."""
    mock_cache = AsyncMock()
    mock_cache.config = Mock()
    mock_cache.config.preview_size_chars = 2000
    return mock_cache


class TestApplyScipPayloadTruncation:
    """Tests for _apply_scip_payload_truncation function (Story #685)."""

    @pytest.mark.asyncio
    async def test_small_context_unchanged(self, mock_payload_cache):
        """Test that small context (<= 2000 chars) is not truncated."""
        from code_indexer.server.mcp.handlers import _apply_scip_payload_truncation

        small_context = "x" * 100  # Small context (< preview_size_chars)

        # store() should not be called for small content
        mock_payload_cache.store = AsyncMock(return_value="uuid-should-not-be-used")

        results = [
            {
                "symbol": "MyClass.method",
                "project": "/src",
                "file_path": "/src/main.py",
                "line": 42,
                "column": 0,
                "kind": "method",
                "relationship": None,
                "context": small_context,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = mock_payload_cache

            result = await _apply_scip_payload_truncation(results)

        # Context should remain unchanged
        assert result[0]["context"] == small_context
        assert result[0].get("context_cache_handle") is None
        assert result[0].get("context_has_more") is False
        # store() should not have been called
        mock_payload_cache.store.assert_not_called()

    @pytest.mark.asyncio
    async def test_large_context_truncated_with_cache_handle(self, mock_payload_cache):
        """Test that large context (> 2000 chars) is truncated and cached."""
        from code_indexer.server.mcp.handlers import _apply_scip_payload_truncation

        large_context = "x" * 5000  # Large context
        preview = large_context[:2000]  # First 2000 chars

        # Mock store() to return cache handle
        mock_payload_cache.store = AsyncMock(return_value="uuid-123")

        results = [
            {
                "symbol": "MyClass.method",
                "project": "/src",
                "file_path": "/src/main.py",
                "line": 42,
                "column": 0,
                "kind": "method",
                "relationship": None,
                "context": large_context,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = mock_payload_cache

            result = await _apply_scip_payload_truncation(results)

        # Context should be replaced with context_preview
        assert "context" not in result[0]
        assert result[0]["context_preview"] == preview
        assert result[0]["context_cache_handle"] == "uuid-123"
        assert result[0]["context_has_more"] is True
        assert result[0]["context_total_size"] == 5000
        # Verify store was called with the full context
        mock_payload_cache.store.assert_called_once_with(large_context)

    @pytest.mark.asyncio
    async def test_multiple_results_mixed_sizes(self, mock_payload_cache):
        """Test truncation with mixed result sizes."""
        from code_indexer.server.mcp.handlers import _apply_scip_payload_truncation

        small_context = "small" * 10  # 50 chars
        large_context = "x" * 4000  # 4000 chars

        # Mock store() to return cache handle with content length in it
        mock_payload_cache.store = AsyncMock(return_value=f"uuid-{len(large_context)}")

        results = [
            {
                "symbol": "Small.method",
                "project": "/src",
                "file_path": "/src/small.py",
                "line": 10,
                "column": 0,
                "kind": "method",
                "relationship": None,
                "context": small_context,
            },
            {
                "symbol": "Large.method",
                "project": "/src",
                "file_path": "/src/large.py",
                "line": 20,
                "column": 0,
                "kind": "method",
                "relationship": None,
                "context": large_context,
            },
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = mock_payload_cache

            result = await _apply_scip_payload_truncation(results)

        # First result: small context unchanged
        assert result[0]["context"] == small_context
        assert result[0].get("context_cache_handle") is None
        assert result[0].get("context_has_more") is False

        # Second result: large context truncated
        assert "context" not in result[1]
        assert result[1]["context_preview"] == large_context[:2000]
        assert result[1]["context_cache_handle"] == f"uuid-{len(large_context)}"
        assert result[1]["context_has_more"] is True
        assert result[1]["context_total_size"] == len(large_context)
        # Verify store was only called once (for the large context)
        mock_payload_cache.store.assert_called_once_with(large_context)

    @pytest.mark.asyncio
    async def test_null_context_handled_gracefully(self, mock_payload_cache):
        """Test that null/None context is handled gracefully."""
        from code_indexer.server.mcp.handlers import _apply_scip_payload_truncation

        results = [
            {
                "symbol": "NoContext.method",
                "project": "/src",
                "file_path": "/src/main.py",
                "line": 42,
                "column": 0,
                "kind": "method",
                "relationship": None,
                "context": None,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = mock_payload_cache

            result = await _apply_scip_payload_truncation(results)

        # Should have default metadata
        assert result[0]["context"] is None
        assert result[0].get("context_cache_handle") is None
        assert result[0].get("context_has_more") is False

    @pytest.mark.asyncio
    async def test_missing_context_handled_gracefully(self, mock_payload_cache):
        """Test that missing context field is handled gracefully."""
        from code_indexer.server.mcp.handlers import _apply_scip_payload_truncation

        results = [
            {
                "symbol": "NoContext.method",
                "project": "/src",
                "file_path": "/src/main.py",
                "line": 42,
                "column": 0,
                "kind": "method",
                "relationship": None,
                # No context field
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = mock_payload_cache

            result = await _apply_scip_payload_truncation(results)

        # Should have default metadata, no crash
        assert result[0].get("context_cache_handle") is None
        assert result[0].get("context_has_more") is False

    @pytest.mark.asyncio
    async def test_cache_unavailable_returns_unchanged(self):
        """Test that results are unchanged when cache is unavailable."""
        from code_indexer.server.mcp.handlers import _apply_scip_payload_truncation

        context = "x" * 5000  # Large context

        results = [
            {
                "symbol": "MyClass.method",
                "project": "/src",
                "file_path": "/src/main.py",
                "line": 42,
                "column": 0,
                "kind": "method",
                "relationship": None,
                "context": context,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = None  # Cache unavailable

            result = await _apply_scip_payload_truncation(results)

        # Results should be unchanged
        assert result[0]["context"] == context
        # No truncation metadata added
        assert "context_cache_handle" not in result[0]
        assert "context_has_more" not in result[0]

    @pytest.mark.asyncio
    async def test_cache_error_returns_unchanged_with_metadata(
        self, mock_payload_cache
    ):
        """Test that cache errors leave context unchanged but add metadata."""
        from code_indexer.server.mcp.handlers import _apply_scip_payload_truncation

        context = "x" * 5000  # Large context

        # Mock store() to raise an exception
        mock_payload_cache.store = AsyncMock(side_effect=Exception("Cache error"))

        results = [
            {
                "symbol": "MyClass.method",
                "project": "/src",
                "file_path": "/src/main.py",
                "line": 42,
                "column": 0,
                "kind": "method",
                "relationship": None,
                "context": context,
            }
        ]

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = mock_payload_cache

            result = await _apply_scip_payload_truncation(results)

        # Context should remain (error in store doesn't delete it), metadata indicates no truncation
        assert result[0]["context"] == context
        assert result[0].get("context_cache_handle") is None
        assert result[0].get("context_has_more") is False

    @pytest.mark.asyncio
    async def test_empty_results_list(self, mock_payload_cache):
        """Test that empty results list is handled correctly."""
        from code_indexer.server.mcp.handlers import _apply_scip_payload_truncation

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = mock_payload_cache

            result = await _apply_scip_payload_truncation([])

        assert result == []


class TestScipDefinitionPayloadTruncation:
    """Tests for SCIP definition handler with payload truncation."""

    @pytest.mark.asyncio
    async def test_scip_definition_applies_truncation(
        self, mock_user, mock_payload_cache
    ):
        """Test that scip_definition applies payload truncation to results."""
        from code_indexer.server.mcp.handlers import scip_definition

        large_context = "x" * 5000

        # Mock the SCIP engine and files
        mock_result = Mock()
        mock_result.symbol = "MyClass"
        mock_result.project = "/src"
        mock_result.file_path = "/src/main.py"
        mock_result.line = 42
        mock_result.column = 0
        mock_result.kind = "class"
        mock_result.relationship = "definition"
        mock_result.context = large_context

        mock_engine = Mock()
        mock_engine.find_definition = Mock(return_value=[mock_result])

        # Set up store() mock for truncation (AsyncMock imported at line 12)
        mock_payload_cache.store = AsyncMock(return_value="uuid-def-123")

        with (
            patch(
                "code_indexer.server.mcp.handlers.app_module.app.state"
            ) as mock_state,
            patch(
                "code_indexer.server.mcp.handlers._find_scip_files"
            ) as mock_find_files,
            patch(
                "code_indexer.scip.query.primitives.SCIPQueryEngine",
                return_value=mock_engine,
            ),
        ):
            mock_state.payload_cache = mock_payload_cache
            mock_find_files.return_value = [Mock()]  # One mock SCIP file

            result = await scip_definition({"symbol": "MyClass"}, mock_user)

        import json

        data = json.loads(result["content"][0]["text"])
        assert data["success"] is True
        assert len(data["results"]) == 1
        # Verify truncation was applied
        result_item = data["results"][0]
        assert "context" not in result_item
        assert result_item["context_preview"] == large_context[:2000]
        assert result_item["context_cache_handle"] == "uuid-def-123"
        assert result_item["context_has_more"] is True


class TestScipReferencesPayloadTruncation:
    """Tests for SCIP references handler with payload truncation."""

    @pytest.mark.asyncio
    async def test_scip_references_applies_truncation(
        self, mock_user, mock_payload_cache
    ):
        """Test that scip_references applies payload truncation to results."""
        from code_indexer.server.mcp.handlers import scip_references

        large_context = "x" * 5000

        # Mock the SCIP engine and files
        mock_result = Mock()
        mock_result.symbol = "MyClass"
        mock_result.project = "/src"
        mock_result.file_path = "/src/caller.py"
        mock_result.line = 100
        mock_result.column = 5
        mock_result.kind = "reference"
        mock_result.relationship = "call"
        mock_result.context = large_context

        mock_engine = Mock()
        mock_engine.find_references = Mock(return_value=[mock_result])

        # Set up store() mock for truncation (AsyncMock imported at line 12)
        mock_payload_cache.store = AsyncMock(return_value="uuid-ref-123")

        with (
            patch(
                "code_indexer.server.mcp.handlers.app_module.app.state"
            ) as mock_state,
            patch(
                "code_indexer.server.mcp.handlers._find_scip_files"
            ) as mock_find_files,
            patch(
                "code_indexer.scip.query.primitives.SCIPQueryEngine",
                return_value=mock_engine,
            ),
        ):
            mock_state.payload_cache = mock_payload_cache
            mock_find_files.return_value = [Mock()]

            result = await scip_references({"symbol": "MyClass"}, mock_user)

        import json

        data = json.loads(result["content"][0]["text"])
        assert data["success"] is True
        assert len(data["results"]) == 1
        result_item = data["results"][0]
        assert "context" not in result_item
        assert result_item["context_preview"] == large_context[:2000]
        assert result_item["context_cache_handle"] == "uuid-ref-123"


class TestScipDependenciesPayloadTruncation:
    """Tests for SCIP dependencies handler with payload truncation."""

    @pytest.mark.asyncio
    async def test_scip_dependencies_applies_truncation(
        self, mock_user, mock_payload_cache
    ):
        """Test that scip_dependencies applies payload truncation to results."""
        from code_indexer.server.mcp.handlers import scip_dependencies

        large_context = "x" * 5000

        mock_result = Mock()
        mock_result.symbol = "Dependency"
        mock_result.project = "/src"
        mock_result.file_path = "/src/dep.py"
        mock_result.line = 50
        mock_result.column = 0
        mock_result.kind = "class"
        mock_result.relationship = "import"
        mock_result.context = large_context

        mock_engine = Mock()
        mock_engine.get_dependencies = Mock(return_value=[mock_result])

        # Set up store() mock for truncation (AsyncMock imported at line 12)
        mock_payload_cache.store = AsyncMock(return_value="uuid-dep-123")

        with (
            patch(
                "code_indexer.server.mcp.handlers.app_module.app.state"
            ) as mock_state,
            patch(
                "code_indexer.server.mcp.handlers._find_scip_files"
            ) as mock_find_files,
            patch(
                "code_indexer.scip.query.primitives.SCIPQueryEngine",
                return_value=mock_engine,
            ),
        ):
            mock_state.payload_cache = mock_payload_cache
            mock_find_files.return_value = [Mock()]

            result = await scip_dependencies({"symbol": "MyClass"}, mock_user)

        import json

        data = json.loads(result["content"][0]["text"])
        assert data["success"] is True
        result_item = data["results"][0]
        assert "context" not in result_item
        assert result_item["context_cache_handle"] == "uuid-dep-123"


class TestScipDependentsPayloadTruncation:
    """Tests for SCIP dependents handler with payload truncation."""

    @pytest.mark.asyncio
    async def test_scip_dependents_applies_truncation(
        self, mock_user, mock_payload_cache
    ):
        """Test that scip_dependents applies payload truncation to results."""
        from code_indexer.server.mcp.handlers import scip_dependents

        large_context = "x" * 5000

        mock_result = Mock()
        mock_result.symbol = "Dependent"
        mock_result.project = "/src"
        mock_result.file_path = "/src/user.py"
        mock_result.line = 75
        mock_result.column = 0
        mock_result.kind = "class"
        mock_result.relationship = "uses"
        mock_result.context = large_context

        mock_engine = Mock()
        mock_engine.get_dependents = Mock(return_value=[mock_result])

        # Set up store() mock for truncation (AsyncMock imported at line 12)
        mock_payload_cache.store = AsyncMock(return_value="uuid-dpt-123")

        with (
            patch(
                "code_indexer.server.mcp.handlers.app_module.app.state"
            ) as mock_state,
            patch(
                "code_indexer.server.mcp.handlers._find_scip_files"
            ) as mock_find_files,
            patch(
                "code_indexer.scip.query.primitives.SCIPQueryEngine",
                return_value=mock_engine,
            ),
        ):
            mock_state.payload_cache = mock_payload_cache
            mock_find_files.return_value = [Mock()]

            result = await scip_dependents({"symbol": "MyClass"}, mock_user)

        import json

        data = json.loads(result["content"][0]["text"])
        assert data["success"] is True
        result_item = data["results"][0]
        assert "context" not in result_item
        assert result_item["context_cache_handle"] == "uuid-dpt-123"
