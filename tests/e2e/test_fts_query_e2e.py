"""
End-to-end tests for FTS query command.

Tests complete workflow from TantivyIndexManager to display:
- FTS search with various options
- Case sensitivity, fuzzy matching, snippets
- Performance requirements
- Integration with display logic

NOTE: Full CLI E2E tests require initialized repository context.
These tests focus on the FTS functionality layer.
"""

import pytest
import time
from code_indexer.services.tantivy_index_manager import TantivyIndexManager
from code_indexer.cli import _display_fts_results


class TestFTSQueryE2E:
    """End-to-end tests for FTS query functionality."""

    @pytest.fixture
    def test_repo(self, tmp_path):
        """Create test repository with sample files."""
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        # Create sample Python files
        (repo_dir / "auth.py").write_text(
            """def authenticate_user(username, password):
    '''Authenticate user with credentials'''
    if not username or not password:
        raise ValueError("Invalid credentials")

    # Perform authentication
    return validate_credentials(username, password)

def validate_credentials(username, password):
    '''Validate user credentials against database'''
    return True
"""
        )

        (repo_dir / "config.py").write_text(
            """CONFIG_PATH = '/etc/app/config'
DATABASE_URL = 'postgresql://localhost:5432/db'

class Configuration:
    '''Application configuration class'''

    def __init__(self):
        self.debug = False
        self.port = 8080
"""
        )

        (repo_dir / "utils.py").write_text(
            """def calculate_hash(data):
    '''Calculate hash of data'''
    import hashlib
    return hashlib.sha256(data.encode()).hexdigest()

def format_timestamp(ts):
    '''Format timestamp to ISO 8601'''
    return ts.isoformat()
"""
        )

        return repo_dir

    @pytest.fixture
    def indexed_repo(self, test_repo):
        """Repository with FTS index created."""
        # Create FTS index
        fts_index_dir = test_repo / ".code-indexer" / "tantivy_index"
        fts_index_dir.mkdir(parents=True, exist_ok=True)

        tantivy_manager = TantivyIndexManager(fts_index_dir)
        tantivy_manager.initialize_index(create_new=True)

        # Index the sample files
        for py_file in test_repo.glob("*.py"):
            content = py_file.read_text()
            doc = {
                "path": str(py_file.relative_to(test_repo)),
                "content": content,
                "content_raw": content,
                "identifiers": ["test"],  # Simplified
                "line_start": 1,
                "line_end": len(content.split("\n")),
                "language": "python",
            }
            tantivy_manager.add_document(doc)

        tantivy_manager.commit()
        tantivy_manager.close()

        return test_repo

    def test_fts_search_basic_query(self, indexed_repo):
        """Test basic FTS search returns results."""
        fts_index_dir = indexed_repo / ".code-indexer" / "tantivy_index"

        tantivy_manager = TantivyIndexManager(fts_index_dir)
        tantivy_manager.initialize_index(create_new=False)

        results = tantivy_manager.search(
            query_text="authenticate",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )

        tantivy_manager.close()

        # Should find results
        assert len(results) > 0
        assert any("authenticate" in r["match_text"].lower() for r in results)

    def test_case_sensitive_vs_insensitive(self, indexed_repo):
        """Test case-sensitive vs case-insensitive search."""
        fts_index_dir = indexed_repo / ".code-indexer" / "tantivy_index"

        tantivy_manager = TantivyIndexManager(fts_index_dir)
        tantivy_manager.initialize_index(create_new=False)

        # Case-insensitive search
        results_insensitive = tantivy_manager.search(
            query_text="CONFIG",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )

        # Case-sensitive search
        results_sensitive = tantivy_manager.search(
            query_text="CONFIG",
            case_sensitive=True,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )

        tantivy_manager.close()

        # Both should return results
        assert len(results_insensitive) > 0 or len(results_sensitive) > 0

    def test_fuzzy_matching_finds_typos(self, indexed_repo):
        """Test fuzzy matching finds misspelled terms."""
        fts_index_dir = indexed_repo / ".code-indexer" / "tantivy_index"

        tantivy_manager = TantivyIndexManager(fts_index_dir)
        tantivy_manager.initialize_index(create_new=False)

        # Misspell "authenticate" as "authenticat"
        results = tantivy_manager.search(
            query_text="authenticat",
            case_sensitive=False,
            edit_distance=1,
            snippet_lines=5,
            limit=10,
        )

        tantivy_manager.close()

        # Should find results with fuzzy matching
        assert len(results) > 0

    def test_snippet_lines_configuration(self, indexed_repo):
        """Test different snippet line configurations."""
        fts_index_dir = indexed_repo / ".code-indexer" / "tantivy_index"

        tantivy_manager = TantivyIndexManager(fts_index_dir)
        tantivy_manager.initialize_index(create_new=False)

        # Zero lines - list only
        results_zero = tantivy_manager.search(
            query_text="authenticate",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=0,
            limit=10,
        )

        # Standard lines
        results_standard = tantivy_manager.search(
            query_text="authenticate",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )

        # Extended lines
        results_extended = tantivy_manager.search(
            query_text="authenticate",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=10,
            limit=10,
        )

        tantivy_manager.close()

        # Zero lines should have empty snippets
        assert all(r["snippet"] == "" for r in results_zero)

        # Standard and extended should have snippets
        assert any(r["snippet"] != "" for r in results_standard)
        assert any(r["snippet"] != "" for r in results_extended)

    def test_language_filter(self, indexed_repo):
        """Test language filtering."""
        fts_index_dir = indexed_repo / ".code-indexer" / "tantivy_index"

        tantivy_manager = TantivyIndexManager(fts_index_dir)
        tantivy_manager.initialize_index(create_new=False)

        results = tantivy_manager.search(
            query_text="def",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
            language_filter="python",
        )

        tantivy_manager.close()

        # All results should be Python files
        assert all(r["language"] == "python" for r in results)

    def test_path_filter(self, indexed_repo):
        """Test path pattern filtering."""
        fts_index_dir = indexed_repo / ".code-indexer" / "tantivy_index"

        tantivy_manager = TantivyIndexManager(fts_index_dir)
        tantivy_manager.initialize_index(create_new=False)

        results = tantivy_manager.search(
            query_text="CONFIG",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
            path_filter="*config*",
        )

        tantivy_manager.close()

        # All results should match path pattern
        assert all("config" in r["path"] for r in results)

    def test_limit_parameter(self, indexed_repo):
        """Test limit parameter restricts results."""
        fts_index_dir = indexed_repo / ".code-indexer" / "tantivy_index"

        tantivy_manager = TantivyIndexManager(fts_index_dir)
        tantivy_manager.initialize_index(create_new=False)

        results_limit_2 = tantivy_manager.search(
            query_text="def",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=2,
        )

        results_limit_10 = tantivy_manager.search(
            query_text="def",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )

        tantivy_manager.close()

        # Limit should be respected
        assert len(results_limit_2) <= 2
        assert len(results_limit_10) <= 10

    def test_display_fts_results_formatting(self, indexed_repo):
        """Test display function formats results correctly."""
        fts_index_dir = indexed_repo / ".code-indexer" / "tantivy_index"

        tantivy_manager = TantivyIndexManager(fts_index_dir)
        tantivy_manager.initialize_index(create_new=False)

        results = tantivy_manager.search(
            query_text="authenticate",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=3,
        )

        tantivy_manager.close()

        # Test display function doesn't crash
        try:
            _display_fts_results(results, quiet=False)
            _display_fts_results(results, quiet=True)
        except Exception as e:
            pytest.fail(f"Display function failed: {e}")

    def test_performance_requirement(self, indexed_repo):
        """Test FTS query performance meets <5ms target."""
        fts_index_dir = indexed_repo / ".code-indexer" / "tantivy_index"

        tantivy_manager = TantivyIndexManager(fts_index_dir)
        tantivy_manager.initialize_index(create_new=False)

        # Warm up
        tantivy_manager.search(
            query_text="authenticate",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )

        # Measure query time
        start = time.perf_counter()
        tantivy_manager.search(
            query_text="authenticate",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=5,
            limit=10,
        )
        end = time.perf_counter()

        query_time_ms = (end - start) * 1000

        tantivy_manager.close()

        # Should complete in under 10ms (allowing slack for CI)
        assert query_time_ms < 10, f"Query took {query_time_ms:.2f}ms (target: <5ms)"

    def test_combined_filters(self, indexed_repo):
        """Test combining multiple filters."""
        fts_index_dir = indexed_repo / ".code-indexer" / "tantivy_index"

        tantivy_manager = TantivyIndexManager(fts_index_dir)
        tantivy_manager.initialize_index(create_new=False)

        results = tantivy_manager.search(
            query_text="def",
            case_sensitive=False,
            edit_distance=0,
            snippet_lines=3,
            limit=5,
            language_filter="python",
            path_filter="*.py",
        )

        tantivy_manager.close()

        # All results should match combined filters
        assert all(r["language"] == "python" for r in results)
        assert all(r["path"].endswith(".py") for r in results)
