"""Unit tests for _omni_search_code explicit truncation after aggregation.

Bug Fix for Story #683: MCP _omni_search_code Missing Payload Truncation

TDD methodology: Tests written BEFORE the fix is implemented.
"""

import json
import pytest
from unittest.mock import patch


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    from datetime import datetime
    from code_indexer.server.auth.user_manager import User, UserRole

    return User(
        username="test_user",
        password_hash="dummy_hash",
        role=UserRole.NORMAL_USER,
        created_at=datetime.now(),
    )


@pytest.fixture
def setup_payload_cache(cache_100_chars):
    """Set up and tear down payload cache on app state."""
    from code_indexer.server import app as app_module

    original = getattr(app_module.app.state, "payload_cache", None)
    app_module.app.state.payload_cache = cache_100_chars
    yield cache_100_chars
    if original is None:
        if hasattr(app_module.app.state, "payload_cache"):
            delattr(app_module.app.state, "payload_cache")
    else:
        app_module.app.state.payload_cache = original


def _make_mock_result(file_path: str, content: str, score: float) -> dict:
    """Create a mock MCP search result."""
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "success": True,
                        "results": {
                            "results": [
                                {
                                    "file_path": file_path,
                                    "content": content,
                                    "similarity_score": score,
                                }
                            ]
                        },
                    }
                ),
            }
        ]
    }


class TestOmniSearchAppliesTruncation:
    """Tests verifying _omni_search_code applies truncation after aggregation."""

    @pytest.mark.asyncio
    async def test_semantic_truncation_applied_to_aggregated_results(
        self, setup_payload_cache, mock_user
    ):
        """_omni_search_code applies _apply_payload_truncation for semantic mode."""
        from code_indexer.server.mcp import handlers

        truncation_calls = []
        original_fn = handlers._apply_payload_truncation

        async def tracking_fn(results):
            truncation_calls.append(len(results))
            return await original_fn(results)

        async def mock_search(params, user):
            repo = params.get("repository_alias")
            if repo == "repo-alpha-global":
                return _make_mock_result("/src/a.py", "A" * 200, 0.92)
            return _make_mock_result("/src/b.py", "B" * 200, 0.88)

        with (
            patch.object(handlers, "search_code", side_effect=mock_search),
            patch.object(
                handlers, "_apply_payload_truncation", side_effect=tracking_fn
            ),
            patch.object(
                handlers, "_expand_wildcard_patterns", side_effect=lambda x: x
            ),
        ):
            params = {
                "repository_alias": ["repo-alpha-global", "repo-beta-global"],
                "query": "test",
                "search_mode": "semantic",
                "limit": 10,
            }
            await handlers._omni_search_code(params, mock_user)

        assert len(truncation_calls) > 0, "Semantic truncation should be called"
        assert truncation_calls[-1] == 2, "Should truncate 2 aggregated results"

    @pytest.mark.asyncio
    async def test_fts_truncation_applied_for_fts_mode(
        self, setup_payload_cache, mock_user
    ):
        """_omni_search_code applies _apply_fts_payload_truncation for FTS mode."""
        from code_indexer.server.mcp import handlers

        truncation_calls = []
        original_fn = handlers._apply_fts_payload_truncation

        async def tracking_fn(results):
            truncation_calls.append(len(results))
            return await original_fn(results)

        async def mock_search(params, user):
            return _make_mock_result("/src/a.py", "S" * 200, 0.92)

        with (
            patch.object(handlers, "search_code", side_effect=mock_search),
            patch.object(
                handlers, "_apply_fts_payload_truncation", side_effect=tracking_fn
            ),
            patch.object(
                handlers, "_expand_wildcard_patterns", side_effect=lambda x: x
            ),
        ):
            params = {
                "repository_alias": ["repo-alpha-global"],
                "query": "test",
                "search_mode": "fts",
                "limit": 10,
            }
            await handlers._omni_search_code(params, mock_user)

        assert len(truncation_calls) > 0, "FTS truncation should be called for FTS mode"
