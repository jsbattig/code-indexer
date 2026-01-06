"""
Integration tests for SCIP glob pattern fix (Bug #621).

CRITICAL: .scip protobuf files are DELETED after database conversion.
Only .scip.db (SQLite) files persist after 'cidx scip generate'.

These tests verify that SCIP query functions use the correct glob pattern
to find .scip.db files instead of searching for non-existent .scip files.

Test Coverage:
1. Server REST API: _find_scip_files() in scip_queries.py:39
2. Composite queries: _find_target_definition() in composites.py:229
3. Composite queries: _bfs_traverse_dependents() in composites.py:261
4. Composite queries: get_smart_context() in composites.py:636
"""

import pytest
from pathlib import Path
from unittest.mock import patch, Mock

from code_indexer.scip.query.composites import (
    analyze_impact,
    get_smart_context,
    _find_target_definition,
)
from code_indexer.scip.query.primitives import QueryResult


@pytest.fixture
def scip_db_only_dir(tmp_path):
    """
    Create test directory with ONLY .scip.db files (realistic scenario).

    This simulates the real state after 'cidx scip generate':
    - .scip protobuf files are DELETED
    - Only .scip.db SQLite files remain
    """
    scip_dir = tmp_path / ".code-indexer" / "scip"
    scip_dir.mkdir(parents=True)

    # Create ONLY .scip.db files (protobuf .scip files deleted)
    (scip_dir / "project1.scip.db").touch()
    (scip_dir / "project2.scip.db").touch()
    (scip_dir / "subdir").mkdir()
    (scip_dir / "subdir" / "project3.scip.db").touch()

    return scip_dir


@pytest.fixture
def scip_fixture_db_path():
    """Path to real .scip.db test fixture."""
    fixture_path = (
        Path(__file__).parent.parent / "scip" / "fixtures" / "test_index.scip.db"
    )
    if not fixture_path.exists():
        pytest.skip(f"SCIP fixture not found: {fixture_path}")
    return fixture_path


class TestServerRestAPIGlobPattern:
    """Test _find_scip_files() in server/routers/scip_queries.py:39"""

    def test_find_scip_files_finds_db_files_not_scip_files(
        self, scip_db_only_dir, monkeypatch
    ):
        """
        _find_scip_files() should find .scip.db files, not .scip files.

        Bug: Line 39 uses glob("**/*.scip") which finds DELETED protobuf files.
        Fix: Should use glob("**/*.scip.db") to find persisted SQLite files.
        """
        from code_indexer.server.routers.scip_queries import _find_scip_files

        # Mock Path.cwd() to return our test directory
        monkeypatch.setattr(Path, "cwd", lambda: scip_db_only_dir.parent.parent)

        # Call the function
        scip_files = _find_scip_files()

        # Should find ALL .scip.db files (3 total)
        assert len(scip_files) == 3, (
            f"Expected 3 .scip.db files, found {len(scip_files)}. "
            f"This indicates wrong glob pattern (searching for .scip instead of .scip.db)"
        )

        # All found files should have .scip.db extension
        for scip_file in scip_files:
            assert scip_file.suffix == ".db", (
                f"Found file with wrong extension: {scip_file.name}. "
                f"Should only find .scip.db files, not .scip files."
            )
            assert scip_file.name.endswith(
                ".scip.db"
            ), f"File {scip_file.name} doesn't end with .scip.db"

    def test_find_scip_files_works_with_nested_directories(
        self, scip_db_only_dir, monkeypatch
    ):
        """_find_scip_files() should recursively find .scip.db files."""
        from code_indexer.server.routers.scip_queries import _find_scip_files

        monkeypatch.setattr(Path, "cwd", lambda: scip_db_only_dir.parent.parent)

        scip_files = _find_scip_files()
        file_names = {f.name for f in scip_files}

        # Should find files in root and subdirectories
        assert "project1.scip.db" in file_names
        assert "project2.scip.db" in file_names
        assert "project3.scip.db" in file_names


class TestCompositeQueriesFindTargetDefinition:
    """Test _find_target_definition() in scip/query/composites.py:229"""

    def test_find_target_definition_uses_db_glob_pattern(self, scip_db_only_dir):
        """
        _find_target_definition() should glob for .scip.db files.

        Bug: Line 229 uses glob("**/*.scip") which won't find .scip.db files.
        Fix: Should use glob("**/*.scip.db").
        """
        # Mock SCIPQueryEngine to avoid loading real database
        with patch("code_indexer.scip.query.composites.SCIPQueryEngine") as MockEngine:
            mock_instance = Mock()
            mock_instance.find_definition.return_value = [
                QueryResult(
                    symbol="test_symbol",
                    project="test_project",
                    file_path="test.py",
                    line=1,
                    column=1,
                    kind="definition",
                    relationship=None,
                    context=None,
                )
            ]
            MockEngine.return_value = mock_instance

            # Call _find_target_definition with directory containing ONLY .scip.db files
            result = _find_target_definition("test_symbol", scip_db_only_dir)

            # Should successfully query .scip.db files and return result
            assert result is not None, (
                "Expected to find definition, but got None. "
                "This indicates _find_target_definition() couldn't find .scip.db files "
                "because it's using wrong glob pattern (.scip instead of .scip.db)"
            )

            # Verify SCIPQueryEngine was called with .scip.db files
            assert (
                MockEngine.call_count >= 1
            ), "Should have created SCIPQueryEngine instances"

            # Check that files passed to engine have .scip.db extension
            for call_args in MockEngine.call_args_list:
                scip_file = call_args[0][0]  # First positional argument
                assert str(scip_file).endswith(".scip.db"), (
                    f"Engine created with wrong file type: {scip_file}. "
                    f"Should use .scip.db files, not .scip files."
                )


class TestCompositeQueriesBFSTraverse:
    """Test _bfs_traverse_dependents() in scip/query/composites.py:261"""

    def test_bfs_traverse_uses_db_glob_pattern(self, scip_db_only_dir):
        """
        analyze_impact() -> _bfs_traverse_dependents() should glob for .scip.db files.

        Bug: Line 261 uses glob("**/*.scip") which won't find .scip.db files.
        Fix: Should use glob("**/*.scip.db").
        """
        # Mock SCIPQueryEngine to avoid loading real database
        with patch("code_indexer.scip.query.composites.SCIPQueryEngine") as MockEngine:
            mock_instance = Mock()
            # Return empty dependents (we just want to test glob pattern)
            mock_instance.get_dependents.return_value = []
            MockEngine.return_value = mock_instance

            # Call analyze_impact which uses _bfs_traverse_dependents internally
            analyze_impact(
                symbol="test_symbol", scip_dir=scip_db_only_dir, depth=1
            )

            # Should have attempted to query .scip.db files
            # With 3 .scip.db files in directory, should create 3+ engine instances
            # (one for _find_target_definition, one for _bfs_traverse_dependents)
            assert MockEngine.call_count >= 3, (
                f"Expected at least 3 SCIPQueryEngine calls for 3 .scip.db files, "
                f"got {MockEngine.call_count}. This indicates wrong glob pattern."
            )

            # Verify all engine calls used .scip.db files
            for call_args in MockEngine.call_args_list:
                scip_file = call_args[0][0]
                assert str(scip_file).endswith(
                    ".scip.db"
                ), f"Engine created with wrong file: {scip_file}"


class TestCompositeQueriesSmartContext:
    """Test get_smart_context() in scip/query/composites.py:636"""

    def test_smart_context_uses_db_glob_pattern(self, scip_db_only_dir):
        """
        get_smart_context() should glob for .scip.db files.

        Bug: Line 636 uses glob("**/*.scip") which won't find .scip.db files.
        Fix: Should use glob("**/*.scip.db").
        """
        # Mock SCIPQueryEngine to avoid loading real database
        with patch("code_indexer.scip.query.composites.SCIPQueryEngine") as MockEngine:
            mock_instance = Mock()
            # Return mock results for definition query
            mock_instance.find_definition.return_value = [
                QueryResult(
                    symbol="test_symbol",
                    project="test_project",
                    file_path="test.py",
                    line=1,
                    column=1,
                    kind="definition",
                    relationship=None,
                    context=None,
                )
            ]
            mock_instance.find_references.return_value = []
            MockEngine.return_value = mock_instance

            # Call get_smart_context with directory containing ONLY .scip.db files
            result = get_smart_context(
                symbol="test_symbol", scip_dir=scip_db_only_dir, limit=20
            )

            # Should have queried .scip.db files
            assert MockEngine.call_count >= 3, (
                f"Expected engine calls for 3 .scip.db files, got {MockEngine.call_count}. "
                f"This indicates wrong glob pattern."
            )

            # Verify all engine calls used .scip.db files
            for call_args in MockEngine.call_args_list:
                scip_file = call_args[0][0]
                assert str(scip_file).endswith(
                    ".scip.db"
                ), f"Smart context used wrong file: {scip_file}"

            # Should return valid result with at least the definition
            assert (
                result.total_files >= 1
            ), "Expected at least 1 file in smart context (the definition file)"


class TestRealSCIPFixture:
    """Test with real .scip.db fixture to ensure end-to-end functionality."""

    def test_analyze_impact_with_real_scip_db(self, scip_fixture_db_path):
        """
        Verify analyze_impact() works with real .scip.db file.

        This ensures the fix doesn't just pass mocked tests but actually
        works with real SCIP database files.
        """
        from code_indexer.scip.query.composites import analyze_impact

        scip_dir = scip_fixture_db_path.parent

        # Should be able to analyze impact using .scip.db file
        # Pick a symbol we know exists in test fixture
        result = analyze_impact(
            symbol="test", scip_dir=scip_dir, depth=1  # Generic symbol likely to exist
        )

        # Should complete without error and return valid result
        assert isinstance(result.target_symbol, str)
        assert result.depth_analyzed >= 1
        # May or may not find affected symbols, but should return valid structure
        assert isinstance(result.affected_symbols, list)
        assert isinstance(result.affected_files, list)

    def test_smart_context_with_real_scip_db(self, scip_fixture_db_path):
        """
        Verify get_smart_context() works with real .scip.db file.
        """
        from code_indexer.scip.query.composites import get_smart_context

        scip_dir = scip_fixture_db_path.parent

        # Should be able to get smart context using .scip.db file
        result = get_smart_context(symbol="test", scip_dir=scip_dir, limit=10)

        # Should complete without error
        assert isinstance(result.target_symbol, str)
        assert isinstance(result.files, list)
        assert result.total_files >= 0
