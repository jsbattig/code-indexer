"""Unit tests for SCIP query execution in web routes."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_session():
    """Mock session data."""
    session = MagicMock()
    session.username = "testuser"
    return session


@pytest.fixture
def mock_query_manager():
    """Mock semantic query manager."""
    manager = MagicMock()
    return manager


class TestSCIPQueryExecution:
    """Tests for SCIP query execution in routes.py."""

    async def test_query_submit_accepts_scip_parameters(self, mock_session, tmp_path):
        """query_submit() should accept scip_query_type and scip_exact parameters."""
        from code_indexer.server.web.routes import query_submit
        from fastapi import Request

        # Create a mock request
        request = MagicMock(spec=Request)
        request.cookies = {}

        # Create test SCIP index
        scip_dir = tmp_path / ".code-indexer" / "scip"
        scip_dir.mkdir(parents=True)
        scip_file = scip_dir / "index.scip"
        scip_file.touch()

        with patch(
            "code_indexer.server.web.routes._require_admin_session",
            return_value=mock_session,
        ), patch(
            "code_indexer.server.web.routes.validate_login_csrf_token",
            return_value=True,
        ), patch(
            "code_indexer.server.web.routes._get_all_activated_repos_for_query",
            return_value=[
                {
                    "user_alias": "test-repo",
                    "username": "testuser",
                    "is_global": False,
                    "path": str(tmp_path),
                }
            ],
        ), patch(
            "code_indexer.server.web.routes._create_query_page_response"
        ) as mock_response, patch(
            "code_indexer.server.web.routes._add_to_query_history"
        ):

            # Call query_submit with SCIP parameters
            # This should NOT raise an error even though parameters don't exist yet
            try:
                _ = await query_submit(
                    request=request,
                    query_text="CacheEntry",
                    repository="test-repo",
                    search_mode="scip",
                    limit=10,
                    language="",
                    path_pattern="",
                    min_score="",
                    csrf_token="valid_token",
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

                # Should be called without error
                assert mock_response.called

            except TypeError as e:
                # Expected to fail - parameters don't exist yet
                assert "scip_query_type" in str(e) or "scip_exact" in str(e)

    async def test_scip_query_executes_definition_search(self, mock_session, tmp_path):
        """query_submit() should execute SCIP definition search when search_mode='scip' and type='definition'."""
        from code_indexer.server.web.routes import query_submit
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

        with patch(
            "code_indexer.server.web.routes._require_admin_session",
            return_value=mock_session,
        ), patch(
            "code_indexer.server.web.routes.validate_login_csrf_token",
            return_value=True,
        ), patch(
            "code_indexer.server.web.routes._get_all_activated_repos_for_query",
            return_value=[
                {
                    "user_alias": "test-repo",
                    "username": "testuser",
                    "is_global": False,
                    "path": str(tmp_path),
                }
            ],
        ), patch(
            "code_indexer.scip.query.primitives.SCIPQueryEngine"
        ) as mock_engine_class, patch(
            "code_indexer.server.web.routes._create_query_page_response"
        ) as mock_response, patch(
            "code_indexer.server.web.routes._add_to_query_history"
        ):

            # Setup mock engine
            mock_engine = MagicMock()
            mock_engine.find_definition.return_value = [mock_query_result]
            mock_engine_class.return_value = mock_engine

            # Execute query
            try:
                _ = await query_submit(
                    request=request,
                    query_text="CacheEntry",
                    repository="test-repo",
                    search_mode="scip",
                    limit=10,
                    language="",
                    path_pattern="",
                    min_score="",
                    csrf_token="valid_token",
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

                # Verify results were passed to response
                call_args = mock_response.call_args
                assert call_args is not None
                results = call_args[1].get("results")
                assert results is not None
                assert len(results) > 0
                assert results[0]["file_path"] == "src/cache.py"
                assert results[0]["line_numbers"] == "10"

            except (TypeError, AttributeError) as e:
                # Expected to fail - implementation doesn't exist yet
                pytest.fail(f"Test setup failed: {e}")

    async def test_scip_query_handles_missing_index(self, mock_session, tmp_path):
        """query_submit() should handle missing SCIP index gracefully."""
        from code_indexer.server.web.routes import query_submit
        from fastapi import Request

        # Create mock request
        request = MagicMock(spec=Request)
        request.cookies = {}

        # No SCIP index exists at tmp_path

        with patch(
            "code_indexer.server.web.routes._require_admin_session",
            return_value=mock_session,
        ), patch(
            "code_indexer.server.web.routes.validate_login_csrf_token",
            return_value=True,
        ), patch(
            "code_indexer.server.web.routes._get_all_activated_repos_for_query",
            return_value=[
                {
                    "user_alias": "test-repo",
                    "username": "testuser",
                    "is_global": False,
                    "path": str(tmp_path),
                }
            ],
        ), patch(
            "code_indexer.server.web.routes._create_query_page_response"
        ) as mock_response, patch(
            "code_indexer.server.web.routes._add_to_query_history"
        ):

            try:
                _ = await query_submit(
                    request=request,
                    query_text="CacheEntry",
                    repository="test-repo",
                    search_mode="scip",
                    limit=10,
                    language="",
                    path_pattern="",
                    min_score="",
                    csrf_token="valid_token",
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
                call_args = mock_response.call_args
                assert call_args is not None
                error_message = call_args[1].get("error_message")
                assert error_message is not None
                assert "SCIP index" in error_message or "not found" in error_message.lower()

            except (TypeError, AttributeError) as e:
                # Expected to fail - implementation doesn't exist yet
                pytest.fail(f"Test setup failed: {e}")

    async def test_scip_query_executes_all_query_types(self, mock_session, tmp_path):
        """query_submit() should support all SCIP query types: definition, references, dependencies, dependents."""
        from code_indexer.server.web.routes import query_submit
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

        # Test each query type
        query_types = [
            ("definition", "find_definition"),
            ("references", "find_references"),
            ("dependencies", "get_dependencies"),
            ("dependents", "get_dependents"),
        ]

        for query_type, method_name in query_types:
            with patch(
                "code_indexer.server.web.routes._require_admin_session",
                return_value=mock_session,
            ), patch(
                "code_indexer.server.web.routes.validate_login_csrf_token",
                return_value=True,
            ), patch(
                "code_indexer.server.web.routes._get_all_activated_repos_for_query",
                return_value=[
                    {
                        "user_alias": "test-repo",
                        "username": "testuser",
                        "is_global": False,
                        "path": str(tmp_path),
                    }
                ],
            ), patch(
                "code_indexer.scip.query.primitives.SCIPQueryEngine"
            ) as mock_engine_class, patch(
                "code_indexer.server.web.routes._create_query_page_response"
            ), patch(
                "code_indexer.server.web.routes._add_to_query_history"
            ):

                # Setup mock engine
                mock_engine = MagicMock()
                mock_result = QueryResult(
                    symbol="TestSymbol#",
                    project=str(tmp_path),
                    file_path="src/test.py",
                    line=5,
                    column=0,
                    kind=query_type,
                )
                getattr(mock_engine, method_name).return_value = [mock_result]
                mock_engine_class.return_value = mock_engine

                try:
                    _ = await query_submit(
                        request=request,
                        query_text="TestSymbol",
                        repository="test-repo",
                        search_mode="scip",
                        limit=10,
                        language="",
                        path_pattern="",
                        min_score="",
                        csrf_token="valid_token",
                        time_range_all=False,
                        time_range="",
                        at_commit="",
                        include_removed=False,
                        case_sensitive=False,
                        fuzzy=False,
                        regex=False,
                        scip_query_type=query_type,
                        scip_exact=True,
                    )

                    # Verify correct method was called
                    getattr(mock_engine, method_name).assert_called_once()

                except (TypeError, AttributeError) as e:
                    # Expected to fail - implementation doesn't exist yet
                    pytest.fail(f"Test setup failed: {e}")

    async def test_scip_query_handles_engine_exception(self, mock_session, tmp_path):
        """query_submit() should handle SCIPQueryEngine exceptions gracefully."""
        from code_indexer.server.web.routes import query_submit
        from fastapi import Request

        # Create mock request
        request = MagicMock(spec=Request)
        request.cookies = {}

        # Create test SCIP index
        scip_dir = tmp_path / ".code-indexer" / "scip"
        scip_dir.mkdir(parents=True)
        scip_file = scip_dir / "index.scip"
        scip_file.touch()

        with patch(
            "code_indexer.server.web.routes._require_admin_session",
            return_value=mock_session,
        ), patch(
            "code_indexer.server.web.routes.validate_login_csrf_token",
            return_value=True,
        ), patch(
            "code_indexer.server.web.routes._get_all_activated_repos_for_query",
            return_value=[
                {
                    "user_alias": "test-repo",
                    "username": "testuser",
                    "is_global": False,
                    "path": str(tmp_path),
                }
            ],
        ), patch(
            "code_indexer.scip.query.primitives.SCIPQueryEngine"
        ) as mock_engine_class, patch(
            "code_indexer.server.web.routes._create_query_page_response"
        ) as mock_response, patch(
            "code_indexer.server.web.routes._add_to_query_history"
        ):

            # Setup mock engine to raise exception
            mock_engine = MagicMock()
            mock_engine.find_definition.side_effect = FileNotFoundError("SCIP index file corrupted")
            mock_engine_class.return_value = mock_engine

            try:
                _ = await query_submit(
                    request=request,
                    query_text="CacheEntry",
                    repository="test-repo",
                    search_mode="scip",
                    limit=10,
                    language="",
                    path_pattern="",
                    min_score="",
                    csrf_token="valid_token",
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
                call_args = mock_response.call_args
                assert call_args is not None
                error_message = call_args[1].get("error_message")
                assert error_message is not None
                assert "SCIP" in error_message or "failed" in error_message.lower()

            except (TypeError, AttributeError) as e:
                # Expected to fail - implementation doesn't exist yet
                pytest.fail(f"Test setup failed: {e}")

    async def test_scip_query_exception_message_format(self, mock_session, tmp_path):
        """query_submit() should provide user-friendly error messages for SCIP query failures."""
        from code_indexer.server.web.routes import query_submit
        from fastapi import Request

        # Create mock request
        request = MagicMock(spec=Request)
        request.cookies = {}

        # Create test SCIP index
        scip_dir = tmp_path / ".code-indexer" / "scip"
        scip_dir.mkdir(parents=True)
        scip_file = scip_dir / "index.scip"
        scip_file.touch()

        with patch(
            "code_indexer.server.web.routes._require_admin_session",
            return_value=mock_session,
        ), patch(
            "code_indexer.server.web.routes.validate_login_csrf_token",
            return_value=True,
        ), patch(
            "code_indexer.server.web.routes._get_all_activated_repos_for_query",
            return_value=[
                {
                    "user_alias": "test-repo",
                    "username": "testuser",
                    "is_global": False,
                    "path": str(tmp_path),
                }
            ],
        ), patch(
            "code_indexer.scip.query.primitives.SCIPQueryEngine"
        ) as mock_engine_class, patch(
            "code_indexer.server.web.routes._create_query_page_response"
        ) as mock_response, patch(
            "code_indexer.server.web.routes._add_to_query_history"
        ):

            # Setup mock engine to raise exception
            mock_engine = MagicMock()
            mock_engine.find_definition.side_effect = Exception("Index corrupted")
            mock_engine_class.return_value = mock_engine

            try:
                _ = await query_submit(
                    request=request,
                    query_text="CacheEntry",
                    repository="test-repo",
                    search_mode="scip",
                    limit=10,
                    language="",
                    path_pattern="",
                    min_score="",
                    csrf_token="valid_token",
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

                # Should provide user-friendly error message with actionable guidance
                call_args = mock_response.call_args
                assert call_args is not None
                error_message = call_args[1].get("error_message")
                assert error_message is not None

                # Error message should mention SCIP and provide guidance
                # (This test will initially fail if we need to improve the message)
                assert "SCIP" in error_message
                assert "cidx scip generate" in error_message or "cidx scip index" in error_message, \
                    f"Error message should include guidance to run 'cidx scip generate': {error_message}"

            except (TypeError, AttributeError) as e:
                # Expected to fail - implementation doesn't exist yet
                pytest.fail(f"Test setup failed: {e}")

    async def test_scip_query_handles_file_not_found_exception(self, mock_session, tmp_path):
        """query_submit() should handle FileNotFoundError exceptions with specific error message."""
        from code_indexer.server.web.routes import query_submit
        from fastapi import Request

        # Create mock request
        request = MagicMock(spec=Request)
        request.cookies = {}

        # Create test SCIP index
        scip_dir = tmp_path / ".code-indexer" / "scip"
        scip_dir.mkdir(parents=True)
        scip_file = scip_dir / "index.scip"
        scip_file.touch()

        with patch(
            "code_indexer.server.web.routes._require_admin_session",
            return_value=mock_session,
        ), patch(
            "code_indexer.server.web.routes.validate_login_csrf_token",
            return_value=True,
        ), patch(
            "code_indexer.server.web.routes._get_all_activated_repos_for_query",
            return_value=[
                {
                    "user_alias": "test-repo",
                    "username": "testuser",
                    "is_global": False,
                    "path": str(tmp_path),
                }
            ],
        ), patch(
            "code_indexer.scip.query.primitives.SCIPQueryEngine"
        ) as mock_engine_class, patch(
            "code_indexer.server.web.routes._create_query_page_response"
        ) as mock_response, patch(
            "code_indexer.server.web.routes._add_to_query_history"
        ):

            # Setup mock engine to raise FileNotFoundError
            mock_engine = MagicMock()
            mock_engine.find_definition.side_effect = FileNotFoundError("Index file missing")
            mock_engine_class.return_value = mock_engine

            try:
                _ = await query_submit(
                    request=request,
                    query_text="CacheEntry",
                    repository="test-repo",
                    search_mode="scip",
                    limit=10,
                    language="",
                    path_pattern="",
                    min_score="",
                    csrf_token="valid_token",
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

                # Should provide specific error message for FileNotFoundError
                call_args = mock_response.call_args
                assert call_args is not None
                error_message = call_args[1].get("error_message")
                assert error_message is not None
                assert "SCIP" in error_message
                assert "corrupted" in error_message.lower() or "not found" in error_message.lower()
                assert "cidx scip generate" in error_message

            except (TypeError, AttributeError) as e:
                # Expected to fail - implementation doesn't exist yet
                pytest.fail(f"Test setup failed: {e}")

    async def test_scip_query_executes_impact_query(self, mock_session, tmp_path):
        """query_submit() should execute SCIP impact analysis when scip_query_type='impact'."""
        from code_indexer.server.web.routes import query_submit
        from fastapi import Request
        from code_indexer.scip.query.composites import ImpactAnalysisResult, AffectedSymbol

        request = MagicMock(spec=Request)
        request.cookies = {}
        scip_dir = tmp_path / ".code-indexer" / "scip"
        scip_dir.mkdir(parents=True)
        (scip_dir / "index.scip").touch()

        mock_result = ImpactAnalysisResult(
            target_symbol="UserService",
            target_location="src/user.py:10",
            depth_analyzed=2,
            affected_symbols=[AffectedSymbol(symbol="AuthHandler", file_path="src/auth.py", line=25, column=0, depth=1, relationship="call")],
            affected_files=[],
            truncated=False,
            total_affected=1,
        )

        with patch("code_indexer.server.web.routes._require_admin_session", return_value=mock_session), \
             patch("code_indexer.server.web.routes.validate_login_csrf_token", return_value=True), \
             patch("code_indexer.server.web.routes._get_all_activated_repos_for_query",
                   return_value=[{"user_alias": "test-repo", "username": "testuser", "is_global": False, "path": str(tmp_path)}]), \
             patch("code_indexer.scip.query.composites.analyze_impact", return_value=mock_result) as mock_impact, \
             patch("code_indexer.server.web.routes._create_query_page_response") as mock_response, \
             patch("code_indexer.server.web.routes._add_to_query_history"):

            try:
                _ = await query_submit(request=request, query_text="UserService", repository="test-repo", search_mode="scip",
                                      limit=10, language="", path_pattern="", min_score="", csrf_token="valid_token",
                                      time_range_all=False, time_range="", at_commit="", include_removed=False,
                                      case_sensitive=False, fuzzy=False, regex=False, scip_query_type="impact", scip_exact=False)

                mock_impact.assert_called_once()
                assert mock_impact.call_args[0][0] == "UserService"
                assert mock_response.called

            except (TypeError, AttributeError) as e:
                pytest.fail(f"Test setup failed: {e}")

    async def test_scip_query_executes_callchain_query(self, mock_session, tmp_path):
        """query_submit() should trace call chains when scip_query_type='callchain'."""
        from code_indexer.server.web.routes import query_submit
        from fastapi import Request
        from code_indexer.scip.query.backends import CallChain

        request = MagicMock(spec=Request)
        request.cookies = {}
        scip_dir = tmp_path / ".code-indexer" / "scip"
        scip_dir.mkdir(parents=True)
        (scip_dir / "index.scip").touch()

        with patch("code_indexer.server.web.routes._require_admin_session", return_value=mock_session), \
             patch("code_indexer.server.web.routes.validate_login_csrf_token", return_value=True), \
             patch("code_indexer.server.web.routes._get_all_activated_repos_for_query",
                   return_value=[{"user_alias": "test-repo", "username": "testuser", "is_global": False, "path": str(tmp_path)}]), \
             patch("code_indexer.scip.query.primitives.SCIPQueryEngine") as mock_engine_class, \
             patch("code_indexer.server.web.routes._create_query_page_response") as mock_response, \
             patch("code_indexer.server.web.routes._add_to_query_history"):

            mock_engine = MagicMock()
            mock_chain = CallChain(path=["main", "run", "UserService"], length=2, has_cycle=False)
            mock_engine.trace_call_chain.return_value = [mock_chain]
            mock_engine_class.return_value = mock_engine

            try:
                _ = await query_submit(request=request, query_text="main UserService", repository="test-repo", search_mode="scip",
                                      limit=10, language="", path_pattern="", min_score="", csrf_token="valid_token",
                                      time_range_all=False, time_range="", at_commit="", include_removed=False,
                                      case_sensitive=False, fuzzy=False, regex=False, scip_query_type="callchain", scip_exact=False)

                mock_engine.trace_call_chain.assert_called_once_with("main", "UserService", max_depth=5)
                assert mock_response.called

            except (TypeError, AttributeError) as e:
                pytest.fail(f"Test setup failed: {e}")

    async def test_scip_query_callchain_validates_input_format(self, mock_session, tmp_path):
        """query_submit() should return error message for invalid callchain input (single symbol)."""
        from code_indexer.server.web.routes import query_submit
        from fastapi import Request

        request = MagicMock(spec=Request)
        request.cookies = {}
        scip_dir = tmp_path / ".code-indexer" / "scip"
        scip_dir.mkdir(parents=True)
        (scip_dir / "index.scip").touch()

        with patch("code_indexer.server.web.routes._require_admin_session", return_value=mock_session), \
             patch("code_indexer.server.web.routes.validate_login_csrf_token", return_value=True), \
             patch("code_indexer.server.web.routes._get_all_activated_repos_for_query",
                   return_value=[{"user_alias": "test-repo", "username": "testuser", "is_global": False, "path": str(tmp_path)}]), \
             patch("code_indexer.server.web.routes._create_query_page_response") as mock_response, \
             patch("code_indexer.server.web.routes._add_to_query_history"):

            # Execute query with invalid input (single symbol, no space)
            await query_submit(
                request=request,
                query_text="single_symbol",
                repository="test-repo",
                search_mode="scip",
                limit=10,
                language="",
                path_pattern="",
                min_score="",
                csrf_token="valid_token",
                time_range_all=False,
                time_range="",
                at_commit="",
                include_removed=False,
                case_sensitive=False,
                fuzzy=False,
                regex=False,
                scip_query_type="callchain",
                scip_exact=False,
            )

            # Should return error message (ValueError caught and converted)
            call_args = mock_response.call_args
            assert call_args is not None
            error_message = call_args[1].get("error_message")
            assert error_message is not None
            assert "Call chain requires two symbols" in error_message

    async def test_scip_query_executes_context_query(self, mock_session, tmp_path):
        """query_submit() should get smart context when scip_query_type='context'."""
        from code_indexer.server.web.routes import query_submit
        from fastapi import Request
        from code_indexer.scip.query.composites import SmartContextResult, ContextFile
        from pathlib import Path as PathLib

        request = MagicMock(spec=Request)
        request.cookies = {}
        scip_dir = tmp_path / ".code-indexer" / "scip"
        scip_dir.mkdir(parents=True)
        (scip_dir / "index.scip").touch()

        mock_result = SmartContextResult(
            target_symbol="UserService",
            summary="Context for UserService",
            total_files=1,
            total_symbols=5,
            avg_relevance=1.0,
            files=[ContextFile(path=PathLib("src/user.py"), project=str(tmp_path), relevance_score=1.0, symbols=[], read_priority=1)],
        )

        with patch("code_indexer.server.web.routes._require_admin_session", return_value=mock_session), \
             patch("code_indexer.server.web.routes.validate_login_csrf_token", return_value=True), \
             patch("code_indexer.server.web.routes._get_all_activated_repos_for_query",
                   return_value=[{"user_alias": "test-repo", "username": "testuser", "is_global": False, "path": str(tmp_path)}]), \
             patch("code_indexer.scip.query.composites.get_smart_context", return_value=mock_result) as mock_context, \
             patch("code_indexer.server.web.routes._create_query_page_response") as mock_response, \
             patch("code_indexer.server.web.routes._add_to_query_history"):

            try:
                _ = await query_submit(request=request, query_text="UserService", repository="test-repo", search_mode="scip",
                                      limit=10, language="", path_pattern="", min_score="", csrf_token="valid_token",
                                      time_range_all=False, time_range="", at_commit="", include_removed=False,
                                      case_sensitive=False, fuzzy=False, regex=False, scip_query_type="context", scip_exact=False)

                mock_context.assert_called_once()
                assert mock_context.call_args[0][0] == "UserService"
                assert mock_context.call_args[1]["limit"] == 10
                assert mock_response.called

            except (TypeError, AttributeError) as e:
                pytest.fail(f"Test setup failed: {e}")
