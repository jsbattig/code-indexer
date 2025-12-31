"""Unit tests for SCIP REST API router."""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from code_indexer.scip.query.primitives import QueryResult


@pytest.fixture
def mock_scip_dir(tmp_path):
    """Create a temporary SCIP directory with test .scip files."""
    scip_dir = tmp_path / ".code-indexer" / "scip"
    scip_dir.mkdir(parents=True)

    # Create test .scip files
    (scip_dir / "project1.scip").touch()
    (scip_dir / "project2.scip").touch()

    return scip_dir


@pytest.fixture
def mock_query_results():
    """Mock QueryResult objects for testing."""
    return [
        QueryResult(
            symbol="com.example.UserService",
            project="/path/to/project1",
            file_path="src/services/user_service.py",
            line=10,
            column=5,
            kind="definition",
            relationship=None,
            context=None,
        ),
        QueryResult(
            symbol="com.example.UserService",
            project="/path/to/project2",
            file_path="src/auth/handler.py",
            line=25,
            column=8,
            kind="definition",
            relationship=None,
            context=None,
        ),
    ]


class TestDefinitionEndpoint:
    """Tests for /scip/definition endpoint."""

    def test_definition_endpoint_returns_results(
        self, mock_scip_dir, mock_query_results
    ):
        """Should query all .scip files and return aggregated definition results."""
        # Import here to avoid circular imports during test collection
        from code_indexer.server.app import app
        from code_indexer.server.routers.scip_queries import router

        # Include router in app
        app.include_router(router)
        client = TestClient(app)

        # Mock SCIPQueryEngine to return test results
        with patch(
            "code_indexer.server.routers.scip_queries.SCIPQueryEngine"
        ) as MockEngine:
            mock_engine_instance = Mock()
            mock_engine_instance.find_definition.return_value = mock_query_results[:1]
            MockEngine.return_value = mock_engine_instance

            # Mock _find_scip_files to return our test .scip files
            mock_scip_files = [
                mock_scip_dir / "project1.scip",
                mock_scip_dir / "project2.scip",
            ]
            with patch(
                "code_indexer.server.routers.scip_queries._find_scip_files"
            ) as mock_find:
                mock_find.return_value = mock_scip_files

                # Make request
                response = client.get("/scip/definition?symbol=UserService")

                # Assertions
                assert response.status_code == 200
                data = response.json()

                assert data["success"] is True
                assert data["symbol"] == "UserService"
                assert data["total_results"] >= 1
                assert "results" in data
                assert len(data["results"]) >= 1

                # Verify result structure
                result = data["results"][0]
                assert "symbol" in result
                assert "project" in result
                assert "file_path" in result
                assert "line" in result
                assert "column" in result
                assert result["kind"] == "definition"


class TestReferencesEndpoint:
    """Tests for /scip/references endpoint."""

    def test_references_endpoint_returns_results(self, mock_scip_dir):
        """Should query all .scip files and return aggregated reference results."""
        from code_indexer.server.app import app
        from code_indexer.server.routers.scip_queries import router

        app.include_router(router)
        client = TestClient(app)

        # Create mock reference results
        mock_refs = [
            QueryResult(
                symbol="com.example.UserService",
                project="/path/to/project1",
                file_path="src/auth/handler.py",
                line=15,
                column=10,
                kind="reference",
                relationship="call",
                context=None,
            )
        ]

        with patch(
            "code_indexer.server.routers.scip_queries.SCIPQueryEngine"
        ) as MockEngine:
            mock_engine_instance = Mock()
            mock_engine_instance.find_references.return_value = mock_refs
            MockEngine.return_value = mock_engine_instance

            mock_scip_files = [mock_scip_dir / "project1.scip"]
            with patch(
                "code_indexer.server.routers.scip_queries._find_scip_files"
            ) as mock_find:
                mock_find.return_value = mock_scip_files

                response = client.get("/scip/references?symbol=UserService&limit=100")

                assert response.status_code == 200
                data = response.json()

                assert data["success"] is True
                assert data["symbol"] == "UserService"
                assert data["total_results"] >= 1
                assert len(data["results"]) >= 1
                assert data["results"][0]["kind"] == "reference"


class TestDependenciesEndpoint:
    """Tests for /scip/dependencies endpoint."""

    def test_dependencies_endpoint_returns_results(self, mock_scip_dir):
        """Should query all .scip files and return aggregated dependency results."""
        from code_indexer.server.app import app
        from code_indexer.server.routers.scip_queries import router

        app.include_router(router)
        client = TestClient(app)

        mock_deps = [
            QueryResult(
                symbol="com.example.Database",
                project="/path/to/project1",
                file_path="src/services/user_service.py",
                line=5,
                column=0,
                kind="dependency",
                relationship="import",
                context=None,
            )
        ]

        with patch(
            "code_indexer.server.routers.scip_queries.SCIPQueryEngine"
        ) as MockEngine:
            mock_engine_instance = Mock()
            mock_engine_instance.get_dependencies.return_value = mock_deps
            MockEngine.return_value = mock_engine_instance

            mock_scip_files = [mock_scip_dir / "project1.scip"]
            with patch(
                "code_indexer.server.routers.scip_queries._find_scip_files"
            ) as mock_find:
                mock_find.return_value = mock_scip_files

                response = client.get("/scip/dependencies?symbol=UserService&depth=1")

                assert response.status_code == 200
                data = response.json()

                assert data["success"] is True
                assert data["symbol"] == "UserService"
                assert data["total_results"] >= 1
                assert len(data["results"]) >= 1
                assert data["results"][0]["kind"] == "dependency"


class TestDependentsEndpoint:
    """Tests for /scip/dependents endpoint."""

    def test_dependents_endpoint_returns_results(self, mock_scip_dir):
        """Should query all .scip files and return aggregated dependent results."""
        from code_indexer.server.app import app
        from code_indexer.server.routers.scip_queries import router

        app.include_router(router)
        client = TestClient(app)

        mock_dependents = [
            QueryResult(
                symbol="com.example.AuthHandler",
                project="/path/to/project1",
                file_path="src/auth/handler.py",
                line=20,
                column=5,
                kind="dependent",
                relationship="call",
                context=None,
            )
        ]

        with patch(
            "code_indexer.server.routers.scip_queries.SCIPQueryEngine"
        ) as MockEngine:
            mock_engine_instance = Mock()
            mock_engine_instance.get_dependents.return_value = mock_dependents
            MockEngine.return_value = mock_engine_instance

            mock_scip_files = [mock_scip_dir / "project1.scip"]
            with patch(
                "code_indexer.server.routers.scip_queries._find_scip_files"
            ) as mock_find:
                mock_find.return_value = mock_scip_files

                response = client.get("/scip/dependents?symbol=UserService&depth=1")

                assert response.status_code == 200
                data = response.json()

                assert data["success"] is True
                assert data["symbol"] == "UserService"
                assert data["total_results"] >= 1
                assert len(data["results"]) >= 1
                assert data["results"][0]["kind"] == "dependent"


class TestImpactEndpoint:
    """Tests for /scip/impact endpoint."""

    def test_impact_endpoint_returns_results(self, mock_scip_dir):
        """Should return impact analysis results for a symbol."""
        from code_indexer.server.app import app
        from code_indexer.server.routers.scip_queries import router
        from code_indexer.scip.query.composites import (
            ImpactAnalysisResult,
            AffectedSymbol,
            AffectedFile,
        )

        app.include_router(router)
        client = TestClient(app)

        mock_impact_result = ImpactAnalysisResult(
            target_symbol="com.example.UserService",
            target_location=None,
            depth_analyzed=3,
            affected_symbols=[
                AffectedSymbol(
                    symbol="com.example.AuthHandler",
                    file_path=Path("src/auth/handler.py"),
                    line=20,
                    column=5,
                    depth=1,
                    relationship="call",
                    chain=["com.example.UserService", "com.example.AuthHandler"],
                )
            ],
            affected_files=[
                AffectedFile(
                    path=Path("src/auth/handler.py"),
                    project="project1",
                    affected_symbol_count=1,
                    min_depth=1,
                    max_depth=1,
                )
            ],
            truncated=False,
            total_affected=1,
        )

        with patch("code_indexer.scip.query.composites.analyze_impact") as mock_analyze:
            mock_analyze.return_value = mock_impact_result

            response = client.get("/scip/impact?symbol=UserService&depth=3")

            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            assert data["target_symbol"] == "com.example.UserService"
            assert data["depth_analyzed"] == 3
            assert data["total_affected"] == 1
            assert "affected_symbols" in data
            assert "affected_files" in data
            assert len(data["affected_symbols"]) == 1
            assert data["affected_symbols"][0]["symbol"] == "com.example.AuthHandler"


class TestCallChainEndpoint:
    """Tests for /scip/callchain endpoint."""

    def test_callchain_endpoint_returns_results(self, mock_scip_dir):
        """Should return call chain tracing results between two symbols."""
        from code_indexer.server.app import app
        from code_indexer.server.routers.scip_queries import router
        from code_indexer.scip.query.composites import (
            CallChainResult,
            CallChain,
            CallStep,
        )

        app.include_router(router)
        client = TestClient(app)

        mock_callchain_result = CallChainResult(
            from_symbol="com.example.Controller",
            to_symbol="com.example.Database",
            chains=[
                CallChain(
                    path=[
                        CallStep(
                            symbol="com.example.Service",
                            file_path=Path("src/services/service.py"),
                            line=15,
                            column=10,
                            call_type="call",
                        ),
                        CallStep(
                            symbol="com.example.Database",
                            file_path=Path("src/db/database.py"),
                            line=50,
                            column=5,
                            call_type="call",
                        ),
                    ],
                    length=2,
                )
            ],
            total_chains_found=1,
            truncated=False,
            max_depth_reached=False,
        )

        with patch("code_indexer.scip.query.composites.trace_call_chain") as mock_trace:
            mock_trace.return_value = mock_callchain_result

            response = client.get(
                "/scip/callchain?from_symbol=Controller&to_symbol=Database&max_depth=10"
            )

            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            assert data["from_symbol"] == "com.example.Controller"
            assert data["to_symbol"] == "com.example.Database"
            assert data["total_chains_found"] == 1
            assert "chains" in data
            assert len(data["chains"]) == 1
            assert len(data["chains"][0]["path"]) == 2
            assert data["chains"][0]["path"][0]["symbol"] == "com.example.Service"


class TestContextEndpoint:
    """Tests for /scip/context endpoint."""

    def test_context_endpoint_returns_results(self, mock_scip_dir):
        """Should return smart context results for a symbol."""
        from code_indexer.server.app import app
        from code_indexer.server.routers.scip_queries import router
        from code_indexer.scip.query.composites import (
            SmartContextResult,
            ContextFile,
            ContextSymbol,
        )

        app.include_router(router)
        client = TestClient(app)

        mock_context_result = SmartContextResult(
            target_symbol="com.example.UserService",
            summary="Read these 1 file(s) to understand com.example.UserService (avg relevance: 0.90)",
            files=[
                ContextFile(
                    path=Path("src/services/user_service.py"),
                    project="backend",
                    relevance_score=0.9,
                    symbols=[
                        ContextSymbol(
                            name="com.example.UserService",
                            kind="class",
                            relationship="definition",
                            line=10,
                            column=5,
                            relevance=1.0,
                        )
                    ],
                    read_priority=1,
                )
            ],
            total_files=1,
            total_symbols=1,
            avg_relevance=0.9,
        )

        with patch(
            "code_indexer.scip.query.composites.get_smart_context"
        ) as mock_context:
            mock_context.return_value = mock_context_result

            response = client.get("/scip/context?symbol=UserService&limit=20")

            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            assert data["target_symbol"] == "com.example.UserService"
            assert data["total_files"] == 1
            assert data["total_symbols"] == 1
            assert "files" in data
            assert len(data["files"]) == 1
            assert data["files"][0]["relevance_score"] == 0.9
            assert data["files"][0]["read_priority"] == 1
