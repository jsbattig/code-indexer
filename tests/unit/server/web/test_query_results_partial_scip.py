"""Unit tests for SCIP query execution in query_results_partial_post() endpoint."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_session():
    """Mock session data."""
    session = MagicMock()
    session.username = "testuser"
    return session


class TestSCIPQueryExecutionInPartialEndpoint:
    """Tests for SCIP query execution in query_results_partial_post() htmx endpoint."""

    async def test_partial_endpoint_executes_scip_definition_query(
        self, mock_session, tmp_path
    ):
        """query_results_partial_post() should execute SCIP definition search when search_mode='scip'."""
        from code_indexer.server.web.routes import query_results_partial_post
        from fastapi import Request
        from code_indexer.scip.query.primitives import QueryResult

        # Create mock request
        request = MagicMock(spec=Request)
        request.cookies = {}

        # Create test SCIP index
        scip_dir = tmp_path / ".code-indexer" / "scip"
        scip_dir.mkdir(parents=True)
        scip_file = scip_dir / "index.scip"
        scip_file.touch()

        # Mock SCIP query results
        mock_query_result = QueryResult(
            symbol="CacheEntry#",
            project=str(tmp_path),
            file_path="src/cache.py",
            line=10,
            column=0,
            kind="definition",
        )

        with (
            patch(
                "code_indexer.server.web.routes._require_admin_session",
                return_value=mock_session,
            ),
            patch(
                "code_indexer.server.web.routes._get_all_activated_repos_for_query",
                return_value=[
                    {
                        "user_alias": "test-repo",
                        "username": "testuser",
                        "is_global": False,
                        "path": str(tmp_path),
                    }
                ],
            ),
            patch(
                "code_indexer.scip.query.primitives.SCIPQueryEngine"
            ) as mock_engine_class,
            patch("code_indexer.server.web.routes.templates") as mock_templates,
            patch("code_indexer.server.web.routes._add_to_query_history"),
        ):
            # Setup mock engine
            mock_engine = MagicMock()
            mock_engine.find_definition.return_value = [mock_query_result]
            mock_engine_class.return_value = mock_engine

            # Execute partial endpoint
            await query_results_partial_post(
                request=request,
                query_text="CacheEntry",
                repository="test-repo",
                search_mode="scip",
                limit=10,
                language="",
                path_pattern="",
                min_score="",
                csrf_token=None,
                time_range_all=False,
                time_range="",
                at_commit="",
                include_removed=False,
                case_sensitive=False,
                fuzzy=False,
                regex=False,
                scip_query_type="definition",
                scip_exact=False,
            )

            # Verify SCIPQueryEngine was called
            mock_engine_class.assert_called_once()
            mock_engine.find_definition.assert_called_once_with(
                "CacheEntry", exact=False
            )

            # Verify template was rendered with SCIP results
            call_args = mock_templates.TemplateResponse.call_args
            assert call_args is not None
            template_context = call_args[0][1]
            results = template_context.get("results")
            assert results is not None
            assert len(results) == 1
            assert results[0]["file_path"] == "src/cache.py"
            assert results[0]["line_numbers"] == "10"
            assert results[0]["score"] == 1.0  # SCIP results have score=1.0
            assert "definition" in results[0]["content"]

    async def test_partial_endpoint_handles_missing_scip_index(
        self, mock_session, tmp_path
    ):
        """query_results_partial_post() should handle missing SCIP index gracefully."""
        from code_indexer.server.web.routes import query_results_partial_post
        from fastapi import Request

        request = MagicMock(spec=Request)
        request.cookies = {}

        # No SCIP index exists

        with (
            patch(
                "code_indexer.server.web.routes._require_admin_session",
                return_value=mock_session,
            ),
            patch(
                "code_indexer.server.web.routes._get_all_activated_repos_for_query",
                return_value=[
                    {
                        "user_alias": "test-repo",
                        "username": "testuser",
                        "is_global": False,
                        "path": str(tmp_path),
                    }
                ],
            ),
            patch("code_indexer.server.web.routes.templates") as mock_templates,
            patch("code_indexer.server.web.routes._add_to_query_history"),
        ):
            await query_results_partial_post(
                request=request,
                query_text="CacheEntry",
                repository="test-repo",
                search_mode="scip",
                limit=10,
                language="",
                path_pattern="",
                min_score="",
                csrf_token=None,
                time_range_all=False,
                time_range="",
                at_commit="",
                include_removed=False,
                case_sensitive=False,
                fuzzy=False,
                regex=False,
                scip_query_type="definition",
                scip_exact=False,
            )

            # Should return error message
            call_args = mock_templates.TemplateResponse.call_args
            template_context = call_args[0][1]
            error_message = template_context.get("error_message")
            assert error_message is not None
            assert "SCIP index" in error_message or "not found" in error_message.lower()

    async def test_partial_endpoint_handles_scip_engine_exceptions(
        self, mock_session, tmp_path
    ):
        """query_results_partial_post() should handle SCIPQueryEngine exceptions gracefully."""
        from code_indexer.server.web.routes import query_results_partial_post
        from fastapi import Request

        request = MagicMock(spec=Request)
        request.cookies = {}
        scip_dir = tmp_path / ".code-indexer" / "scip"
        scip_dir.mkdir(parents=True)
        (scip_dir / "index.scip").touch()

        with (
            patch(
                "code_indexer.server.web.routes._require_admin_session",
                return_value=mock_session,
            ),
            patch(
                "code_indexer.server.web.routes._get_all_activated_repos_for_query",
                return_value=[
                    {
                        "user_alias": "test-repo",
                        "username": "testuser",
                        "is_global": False,
                        "path": str(tmp_path),
                    }
                ],
            ),
            patch(
                "code_indexer.scip.query.primitives.SCIPQueryEngine"
            ) as mock_engine_class,
            patch("code_indexer.server.web.routes.templates") as mock_templates,
            patch("code_indexer.server.web.routes._add_to_query_history"),
        ):
            # Setup mock engine to raise exception
            mock_engine = MagicMock()
            mock_engine.find_definition.side_effect = FileNotFoundError(
                "SCIP index file corrupted"
            )
            mock_engine_class.return_value = mock_engine

            await query_results_partial_post(
                request=request,
                query_text="CacheEntry",
                repository="test-repo",
                search_mode="scip",
                limit=10,
                language="",
                path_pattern="",
                min_score="",
                csrf_token=None,
                time_range_all=False,
                time_range="",
                at_commit="",
                include_removed=False,
                case_sensitive=False,
                fuzzy=False,
                regex=False,
                scip_query_type="definition",
                scip_exact=False,
            )

            # Should return error message, not raise exception
            call_args = mock_templates.TemplateResponse.call_args
            template_context = call_args[0][1]
            error_message = template_context.get("error_message")
            assert error_message is not None
            assert "SCIP" in error_message
            assert (
                "corrupted" in error_message.lower()
                or "not found" in error_message.lower()
            )
            assert "cidx scip generate" in error_message
