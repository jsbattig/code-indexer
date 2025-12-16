"""Unit tests for SCIP MCP tool handlers."""

import pytest
from unittest.mock import Mock, patch
import json
from datetime import datetime, timezone

from code_indexer.scip.query.primitives import QueryResult
from code_indexer.server.auth.user_manager import User, UserRole


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    return User(
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        role=UserRole.NORMAL_USER,
        password_hash="hashed_password",
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_scip_files(tmp_path):
    """Create mock SCIP file paths for testing."""
    scip_dir = tmp_path / ".code-indexer" / "scip"
    scip_dir.mkdir(parents=True)
    scip_file = scip_dir / "project1.scip"
    scip_file.touch()
    return [scip_file]


class TestSCIPDefinitionTool:
    """Tests for scip_definition MCP tool."""

    @pytest.mark.asyncio
    async def test_scip_definition_returns_mcp_response(
        self, mock_user, mock_scip_files
    ):
        """Should return MCP-compliant response with definition results."""
        from code_indexer.server.mcp.handlers import scip_definition

        mock_result = QueryResult(
            symbol="com.example.UserService",
            project="/path/to/project1",
            file_path="src/services/user_service.py",
            line=10,
            column=5,
            kind="definition",
            relationship=None,
            context=None,
        )

        params = {"symbol": "UserService", "exact": False}

        with patch("code_indexer.scip.query.primitives.SCIPQueryEngine") as MockEngine:
            mock_engine = Mock()
            mock_engine.find_definition.return_value = [mock_result]
            MockEngine.return_value = mock_engine

            with patch(
                "code_indexer.server.mcp.handlers._find_scip_files"
            ) as mock_find:
                mock_find.return_value = mock_scip_files

                response = await scip_definition(params, mock_user)

                # Verify MCP-compliant response structure
                assert "content" in response
                assert len(response["content"]) == 1
                assert response["content"][0]["type"] == "text"

                # Parse JSON response
                data = json.loads(response["content"][0]["text"])
                assert data["success"] is True
                assert data["symbol"] == "UserService"
                assert data["total_results"] >= 1
                assert len(data["results"]) >= 1
                assert data["results"][0]["kind"] == "definition"


class TestSCIPReferencesTool:
    """Tests for scip_references MCP tool."""

    @pytest.mark.asyncio
    async def test_scip_references_returns_mcp_response(
        self, mock_user, mock_scip_files
    ):
        """Should return MCP-compliant response with reference results."""
        from code_indexer.server.mcp.handlers import scip_references

        mock_ref = QueryResult(
            symbol="com.example.UserService",
            project="/path/to/project1",
            file_path="src/auth/handler.py",
            line=15,
            column=10,
            kind="reference",
            relationship="call",
            context=None,
        )

        params = {"symbol": "UserService", "limit": 100, "exact": False}

        with patch("code_indexer.scip.query.primitives.SCIPQueryEngine") as MockEngine:
            mock_engine = Mock()
            mock_engine.find_references.return_value = [mock_ref]
            MockEngine.return_value = mock_engine

            with patch(
                "code_indexer.server.mcp.handlers._find_scip_files"
            ) as mock_find:
                mock_find.return_value = mock_scip_files

                response = await scip_references(params, mock_user)

                assert "content" in response
                data = json.loads(response["content"][0]["text"])
                assert data["success"] is True
                assert data["results"][0]["kind"] == "reference"


class TestSCIPDependenciesTool:
    """Tests for scip_dependencies MCP tool."""

    @pytest.mark.asyncio
    async def test_scip_dependencies_returns_mcp_response(
        self, mock_user, mock_scip_files
    ):
        """Should return MCP-compliant response with dependency results."""
        from code_indexer.server.mcp.handlers import scip_dependencies

        mock_dep = QueryResult(
            symbol="com.example.Database",
            project="/path/to/project1",
            file_path="src/services/user_service.py",
            line=5,
            column=0,
            kind="dependency",
            relationship="import",
            context=None,
        )

        params = {"symbol": "UserService", "exact": False}

        with patch("code_indexer.scip.query.primitives.SCIPQueryEngine") as MockEngine:
            mock_engine = Mock()
            mock_engine.get_dependencies.return_value = [mock_dep]
            MockEngine.return_value = mock_engine

            with patch(
                "code_indexer.server.mcp.handlers._find_scip_files"
            ) as mock_find:
                mock_find.return_value = mock_scip_files

                response = await scip_dependencies(params, mock_user)

                # Verify MCP-compliant response structure
                assert "content" in response
                assert len(response["content"]) == 1
                assert response["content"][0]["type"] == "text"

                # Parse JSON response
                data = json.loads(response["content"][0]["text"])
                assert data["success"] is True
                assert data["symbol"] == "UserService"
                assert data["total_results"] >= 1
                assert len(data["results"]) >= 1
                assert data["results"][0]["kind"] == "dependency"


class TestSCIPDependentsTool:
    """Tests for scip_dependents MCP tool."""

    @pytest.mark.asyncio
    async def test_scip_dependents_returns_mcp_response(
        self, mock_user, mock_scip_files
    ):
        """Should return MCP-compliant response with dependent results."""
        from code_indexer.server.mcp.handlers import scip_dependents

        mock_dependent = QueryResult(
            symbol="com.example.AuthHandler",
            project="/path/to/project1",
            file_path="src/auth/handler.py",
            line=20,
            column=5,
            kind="dependent",
            relationship="uses",
            context=None,
        )

        params = {"symbol": "UserService", "exact": False}

        with patch("code_indexer.scip.query.primitives.SCIPQueryEngine") as MockEngine:
            mock_engine = Mock()
            mock_engine.get_dependents.return_value = [mock_dependent]
            MockEngine.return_value = mock_engine

            with patch(
                "code_indexer.server.mcp.handlers._find_scip_files"
            ) as mock_find:
                mock_find.return_value = mock_scip_files

                response = await scip_dependents(params, mock_user)

                # Verify MCP-compliant response structure
                assert "content" in response
                assert len(response["content"]) == 1
                assert response["content"][0]["type"] == "text"

                # Parse JSON response
                data = json.loads(response["content"][0]["text"])
                assert data["success"] is True
                assert data["symbol"] == "UserService"
                assert data["total_results"] >= 1
                assert len(data["results"]) >= 1
                assert data["results"][0]["kind"] == "dependent"


class TestSCIPImpactTool:
    """Tests for scip_impact MCP tool."""

    @pytest.mark.asyncio
    async def test_scip_impact_returns_mcp_response(self, mock_user, tmp_path):
        """Should return MCP-compliant response with impact analysis results."""
        from code_indexer.server.mcp.handlers import scip_impact
        from code_indexer.scip.query.composites import (
            ImpactAnalysisResult,
            AffectedSymbol,
            AffectedFile,
        )
        from pathlib import Path

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

        params = {"symbol": "UserService", "depth": 3}

        with (
            patch("code_indexer.scip.query.composites.analyze_impact") as mock_analyze,
            patch("code_indexer.server.mcp.handlers._find_scip_files") as mock_find,
        ):
            mock_analyze.return_value = mock_impact_result
            mock_find.return_value = [Path("/fake/path/index.scip")]

            response = await scip_impact(params, mock_user)

            # Verify MCP-compliant response structure
            assert "content" in response
            assert len(response["content"]) == 1
            assert response["content"][0]["type"] == "text"

            # Parse JSON response
            data = json.loads(response["content"][0]["text"])
            assert data["success"] is True
            assert data["target_symbol"] == "com.example.UserService"
            assert data["depth_analyzed"] == 3
            assert data["total_affected"] == 1
            assert "affected_symbols" in data
            assert len(data["affected_symbols"]) == 1


class TestSCIPCallChainTool:
    """Tests for scip_callchain MCP tool."""

    @pytest.mark.asyncio
    async def test_scip_callchain_returns_mcp_response(self, mock_user):
        """Should return MCP-compliant response with call chain results."""
        from code_indexer.server.mcp.handlers import scip_callchain
        from code_indexer.scip.query.composites import (
            CallChainResult,
            CallChain,
            CallStep,
        )
        from pathlib import Path

        mock_result = CallChainResult(
            from_symbol="Controller",
            to_symbol="Database",
            chains=[
                CallChain(
                    path=[
                        CallStep(
                            symbol="Service",
                            file_path=Path("src/service.py"),
                            line=10,
                            column=5,
                            call_type="call",
                        )
                    ],
                    length=1,
                )
            ],
            total_chains_found=1,
            truncated=False,
            max_depth_reached=False,
        )

        params = {"from_symbol": "Controller", "to_symbol": "Database"}

        with (
            patch("code_indexer.scip.query.composites.trace_call_chain") as mock_trace,
            patch("code_indexer.server.mcp.handlers._find_scip_files") as mock_find,
        ):
            mock_trace.return_value = mock_result
            mock_find.return_value = [Path("/fake/path/index.scip")]

            response = await scip_callchain(params, mock_user)

            assert "content" in response
            data = json.loads(response["content"][0]["text"])
            assert data["success"] is True
            assert data["from_symbol"] == "Controller"
            assert data["to_symbol"] == "Database"
            assert data["total_chains_found"] == 1


class TestSCIPContextTool:
    """Tests for scip_context MCP tool."""

    @pytest.mark.asyncio
    async def test_scip_context_returns_mcp_response(self, mock_user):
        """Should return MCP-compliant response with smart context results."""
        from code_indexer.server.mcp.handlers import scip_context
        from code_indexer.scip.query.composites import (
            SmartContextResult,
            ContextFile,
            ContextSymbol,
        )
        from pathlib import Path

        mock_result = SmartContextResult(
            target_symbol="UserService",
            summary="Read these 1 file(s)",
            files=[
                ContextFile(
                    path=Path("src/service.py"),
                    project="backend",
                    relevance_score=0.9,
                    symbols=[
                        ContextSymbol(
                            name="UserService",
                            kind="class",
                            relationship="definition",
                            line=10,
                            column=0,
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

        params = {"symbol": "UserService"}

        with (
            patch(
                "code_indexer.scip.query.composites.get_smart_context"
            ) as mock_context,
            patch("code_indexer.server.mcp.handlers._find_scip_files") as mock_find,
        ):
            mock_context.return_value = mock_result
            mock_find.return_value = [Path("/fake/path/index.scip")]

            response = await scip_context(params, mock_user)

            assert "content" in response
            data = json.loads(response["content"][0]["text"])
            assert data["success"] is True
            assert data["target_symbol"] == "UserService"
            assert data["total_files"] == 1
