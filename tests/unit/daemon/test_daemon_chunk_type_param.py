"""
Unit tests for chunk_type parameter in daemon temporal queries.

Tests that chunk_type parameter is correctly propagated through:
1. CLI -> _query_temporal_via_daemon()
2. _query_temporal_via_daemon() -> exposed_query_temporal()
3. exposed_query_temporal() -> temporal_search_service.query_temporal()

BUG: chunk_type parameter is dropped in daemon mode, causing --chunk-type
flag to be ignored.
"""

import pytest
import inspect


def test_query_temporal_via_daemon_accepts_chunk_type():
    """Test that _query_temporal_via_daemon accepts chunk_type parameter.

    This test verifies the function signature accepts chunk_type.
    Currently FAILS because chunk_type is missing from signature.

    ROOT CAUSE: chunk_type parameter was never added to daemon delegation
    path when Story #476 was implemented.
    """
    from code_indexer.cli_daemon_delegation import _query_temporal_via_daemon

    sig = inspect.signature(_query_temporal_via_daemon)
    params = list(sig.parameters.keys())

    assert "chunk_type" in params, (
        "chunk_type parameter missing from _query_temporal_via_daemon signature. "
        f"Current params: {params}"
    )


def test_exposed_query_temporal_accepts_chunk_type():
    """Test that daemon's exposed_query_temporal accepts chunk_type.

    This test verifies the RPC method signature accepts chunk_type.
    Currently FAILS because chunk_type is missing from signature.
    """
    from code_indexer.daemon.service import CIDXDaemonService

    sig = inspect.signature(CIDXDaemonService.exposed_query_temporal)
    params = list(sig.parameters.keys())

    assert "chunk_type" in params, (
        "chunk_type parameter missing from exposed_query_temporal signature. "
        f"Current params: {params}"
    )


def test_daemon_passes_chunk_type_to_search_service():
    """Test that daemon passes chunk_type to temporal_search_service.

    This integration test verifies chunk_type flows through the entire
    daemon stack to the search service.

    Currently FAILS because chunk_type is not passed in the RPC call.
    """
    from code_indexer.cli_daemon_delegation import _query_temporal_via_daemon
    from unittest.mock import Mock, patch
    from pathlib import Path

    # Mock daemon connection
    mock_conn = Mock()
    mock_result = {
        "results": [],
        "query": "test",
        "filter_type": None,
        "filter_value": None,
        "total_found": 0,
        "performance": {},
        "warning": None,
    }
    mock_conn.root.exposed_query_temporal.return_value = mock_result
    mock_conn.close = Mock()

    daemon_config = {"enabled": True, "retry_delays_ms": [100]}

    with (
        patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find,
        patch("code_indexer.cli_daemon_delegation._get_socket_path") as mock_socket,
        patch("code_indexer.cli_daemon_delegation._connect_to_daemon") as mock_connect,
        patch("code_indexer.utils.temporal_display.display_temporal_results"),
    ):
        mock_find.return_value = Path("/fake/.code-indexer/config.json")
        mock_socket.return_value = Path("/fake/.code-indexer/daemon.sock")
        mock_connect.return_value = mock_conn

        # Call with chunk_type parameter
        result = _query_temporal_via_daemon(
            query_text="test query",
            time_range="all",
            daemon_config=daemon_config,
            project_root=Path("/fake/project"),
            limit=10,
            chunk_type="commit_diff",  # CRITICAL: This should be passed through
        )

        assert result == 0, "Function should return success"

        # Verify chunk_type was passed to RPC call
        assert (
            mock_conn.root.exposed_query_temporal.called
        ), "RPC method should be called"
        call_kwargs = mock_conn.root.exposed_query_temporal.call_args.kwargs

        assert "chunk_type" in call_kwargs, (
            f"chunk_type not passed to exposed_query_temporal. "
            f"Actual kwargs: {call_kwargs}"
        )
        assert (
            call_kwargs["chunk_type"] == "commit_diff"
        ), f"chunk_type value incorrect. Expected 'commit_diff', got {call_kwargs.get('chunk_type')}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
