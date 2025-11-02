"""
Test daemon FTS caching and performance.

This test suite validates:
1. FTS queries route to daemon when daemon.enabled: true
2. Tantivy index is cached in daemon memory after first load
3. Second FTS query uses cached index (faster than first)
4. Cache hit for FTS is <100ms (when warm)

ROOT CAUSE INVESTIGATION:
- Test whether Tantivy index is actually being cached
- Measure first vs second query times
- Prove that cache should speed up queries
"""

import pytest
import time
import json
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.fixture
def test_project_with_fts(tmp_path):
    """Create a test project with FTS index."""
    project_path = tmp_path / "test_project"
    project_path.mkdir()

    # Create config
    config_dir = project_path / ".code-indexer"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps({
        "daemon": {
            "enabled": True,
            "auto_start": True
        }
    }))

    # Create sample files
    (project_path / "test.py").write_text("def hello(): pass\ndef world(): pass")

    # Create real Tantivy index
    tantivy_dir = config_dir / "tantivy_index"
    tantivy_dir.mkdir()

    try:
        from code_indexer.services.tantivy_index_manager import TantivyIndexManager

        # Initialize and populate index
        manager = TantivyIndexManager(tantivy_dir)
        manager.initialize_index(create_new=True)

        # Add sample document
        manager.add_document({
            "path": "test.py",
            "content": "def hello(): pass\ndef world(): pass",
            "content_raw": "def hello(): pass\ndef world(): pass",
            "identifiers": "hello world",
            "line_start": 1,
            "line_end": 2,
            "language": "python",
            "language_facet": "/python",
        })

        manager.commit()
        manager.close()
    except ImportError:
        pytest.skip("Tantivy not installed")

    return project_path


def test_fts_index_caching_on_second_query(test_project_with_fts):
    """
    Test that second FTS query is faster due to caching.

    EXPECTED:
    - First query: Loads index from disk (~1000ms)
    - Second query: Uses cached index (<100ms)

    ACTUAL (before fix):
    - First query: ~1000ms
    - Second query: ~1000ms (NO cache benefit)
    """
    from code_indexer.services.rpyc_daemon import CIDXDaemonService

    daemon = CIDXDaemonService()
    project_str = str(test_project_with_fts)

    # First query - should load index
    start_time = time.perf_counter()
    result1 = daemon.exposed_query_fts(project_str, "hello", limit=10)
    first_query_time = time.perf_counter() - start_time

    # Verify index is now cached
    assert daemon.cache_entry is not None, "Cache entry should be created"
    assert daemon.cache_entry.tantivy_index is not None, "Tantivy index should be loaded"
    assert daemon.cache_entry.tantivy_searcher is not None, "Tantivy searcher should be cached"

    # Second query - should use cached index
    start_time = time.perf_counter()
    result2 = daemon.exposed_query_fts(project_str, "hello", limit=10)
    second_query_time = time.perf_counter() - start_time

    # CRITICAL: Second query MUST be faster than first
    print(f"\nFirst query time: {first_query_time*1000:.1f}ms")
    print(f"Second query time: {second_query_time*1000:.1f}ms")
    print(f"Speedup: {first_query_time/second_query_time:.1f}x")

    # This test will FAIL if caching is not working
    assert second_query_time < first_query_time, \
        f"Second query ({second_query_time*1000:.1f}ms) should be faster than first ({first_query_time*1000:.1f}ms)"

    # With proper caching, second query should be <100ms
    assert second_query_time < 0.100, \
        f"Cached query should be <100ms, got {second_query_time*1000:.1f}ms"


def test_fts_query_cache_hit(test_project_with_fts):
    """
    Test that identical queries return cached results.

    EXPECTED:
    - First query: Executes search (~100ms with cached index)
    - Second identical query: Returns cached result (<10ms)
    """
    from code_indexer.services.rpyc_daemon import CIDXDaemonService

    daemon = CIDXDaemonService()
    project_str = str(test_project_with_fts)

    # Warm up - load index
    daemon.exposed_query_fts(project_str, "warmup", limit=10)

    # First query
    start_time = time.perf_counter()
    result1 = daemon.exposed_query_fts(project_str, "hello", limit=10)
    first_time = time.perf_counter() - start_time

    # Second identical query - should hit query cache
    start_time = time.perf_counter()
    result2 = daemon.exposed_query_fts(project_str, "hello", limit=10)
    second_time = time.perf_counter() - start_time

    print(f"\nFirst query: {first_time*1000:.1f}ms")
    print(f"Cached query: {second_time*1000:.1f}ms")
    print(f"Speedup: {first_time/second_time:.1f}x")

    # Cached query should be MUCH faster
    assert second_time < first_time / 2, \
        "Query cache should provide at least 2x speedup"

    # Cached result should be <10ms
    assert second_time < 0.010, \
        f"Query cache hit should be <10ms, got {second_time*1000:.1f}ms"


def test_tantivy_index_persists_across_queries(test_project_with_fts):
    """
    Test that Tantivy index object is reused across queries.

    EXPECTED:
    - Index loaded once on first query
    - Same index object used for subsequent queries
    """
    from code_indexer.services.rpyc_daemon import CIDXDaemonService

    daemon = CIDXDaemonService()
    project_str = str(test_project_with_fts)

    # First query
    daemon.exposed_query_fts(project_str, "query1", limit=10)
    index_obj_1 = daemon.cache_entry.tantivy_index
    searcher_obj_1 = daemon.cache_entry.tantivy_searcher

    # Second query
    daemon.exposed_query_fts(project_str, "query2", limit=10)
    index_obj_2 = daemon.cache_entry.tantivy_index
    searcher_obj_2 = daemon.cache_entry.tantivy_searcher

    # CRITICAL: Same objects should be reused
    assert index_obj_1 is index_obj_2, \
        "Tantivy index object should be reused across queries"
    assert searcher_obj_1 is searcher_obj_2, \
        "Tantivy searcher object should be reused across queries"


def test_daemon_routing_fts_queries():
    """
    Test that FTS queries are routed to daemon when enabled.

    This validates that cli_daemon_delegation._query_via_daemon
    correctly calls exposed_query_fts for FTS queries.
    """
    from code_indexer.cli_daemon_delegation import _query_via_daemon

    daemon_config = {
        "enabled": True,
        "retry_delays_ms": [100]
    }

    # Mock the daemon connection and response
    mock_conn = MagicMock()
    mock_conn.root.exposed_query_fts.return_value = {
        "results": [{"path": "test.py", "line": 1, "score": 0.9}],
        "query": "hello",
        "total": 1
    }

    with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find, \
         patch("code_indexer.cli_daemon_delegation._connect_to_daemon") as mock_connect:

        mock_find.return_value = Path("/tmp/test/.code-indexer/config.json")
        mock_connect.return_value = mock_conn

        # Execute FTS query
        exit_code = _query_via_daemon(
            query_text="hello",
            daemon_config=daemon_config,
            fts=True,
            semantic=False,
            limit=10
        )

        # Verify exposed_query_fts was called
        mock_conn.root.exposed_query_fts.assert_called_once()
        call_args = mock_conn.root.exposed_query_fts.call_args

        # Verify correct parameters
        assert call_args[0][1] == "hello", "Query text should be passed"
        assert call_args[1]["limit"] == 10, "Limit should be passed"

        assert exit_code == 0, "FTS query should succeed"


def test_daemon_fts_cache_key_generation(test_project_with_fts):
    """
    Test that query cache keys are generated correctly for FTS.

    Different queries should have different cache keys.
    Same queries should have same cache keys.
    """
    from code_indexer.services.rpyc_daemon import CIDXDaemonService

    daemon = CIDXDaemonService()
    project_str = str(test_project_with_fts)

    # Query 1
    daemon.exposed_query_fts(project_str, "hello", limit=10)
    cache_keys_1 = set(daemon.cache_entry.query_cache.keys())

    # Query 2 (different)
    daemon.exposed_query_fts(project_str, "world", limit=10)
    cache_keys_2 = set(daemon.cache_entry.query_cache.keys())

    # Should have 2 different cache entries
    assert len(cache_keys_2) == 2, "Should have 2 cache entries"

    # Query 1 again - should reuse cache
    daemon.exposed_query_fts(project_str, "hello", limit=10)
    cache_keys_3 = set(daemon.cache_entry.query_cache.keys())

    # Should still have 2 entries (not 3)
    assert len(cache_keys_3) == 2, "Should reuse existing cache entry"


def test_daemon_fts_performance_benchmark(test_project_with_fts):
    """
    Benchmark FTS query performance with daemon caching.

    SUCCESS CRITERIA:
    - First query (cold cache): <2000ms acceptable
    - Second query (warm cache): <100ms required
    - Query cache hit: <10ms required
    """
    from code_indexer.services.rpyc_daemon import CIDXDaemonService

    daemon = CIDXDaemonService()
    project_str = str(test_project_with_fts)

    # Cold cache - first query
    start_time = time.perf_counter()
    result1 = daemon.exposed_query_fts(project_str, "hello", limit=10)
    cold_time = time.perf_counter() - start_time

    # Warm cache - different query
    start_time = time.perf_counter()
    result2 = daemon.exposed_query_fts(project_str, "world", limit=10)
    warm_time = time.perf_counter() - start_time

    # Query cache hit - same query
    start_time = time.perf_counter()
    result3 = daemon.exposed_query_fts(project_str, "hello", limit=10)
    cache_hit_time = time.perf_counter() - start_time

    print("\n=== FTS Performance Benchmark ===")
    print(f"Cold cache (first query):  {cold_time*1000:.1f}ms")
    print(f"Warm cache (index loaded): {warm_time*1000:.1f}ms")
    print(f"Query cache hit:           {cache_hit_time*1000:.1f}ms")

    # Validate performance targets
    assert cold_time < 2.0, \
        f"Cold cache query should be <2000ms, got {cold_time*1000:.1f}ms"

    assert warm_time < 0.100, \
        f"Warm cache query should be <100ms, got {warm_time*1000:.1f}ms"

    assert cache_hit_time < 0.010, \
        f"Query cache hit should be <10ms, got {cache_hit_time*1000:.1f}ms"
