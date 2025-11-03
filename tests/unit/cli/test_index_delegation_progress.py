"""
Unit tests for index command delegation with progress callbacks.

Tests cover:
- Index delegation creates progress display components
- Index delegation uses RichLiveProgressManager + MultiThreadedProgressManager
- Progress callback is passed to daemon's exposed_index_blocking
- RPC timeout is disabled (sync_request_timeout=None)
- Error handling and cleanup
- Completion handling
"""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


class TestIndexDelegationProgress:
    """Test index command delegation with standalone display components."""

    def test_index_via_daemon_function_exists(self):
        """Test _index_via_daemon function exists in cli_daemon_delegation."""
        from code_indexer import cli_daemon_delegation

        assert hasattr(cli_daemon_delegation, "_index_via_daemon")
        assert callable(cli_daemon_delegation._index_via_daemon)

    def test_index_via_daemon_creates_progress_display_components(self):
        """Test _index_via_daemon creates RichLiveProgressManager + MultiThreadedProgressManager."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        # Mock all dependencies
        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/test/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = MagicMock()
                mock_conn.root.exposed_index_blocking.return_value = {
                    "status": "completed",
                    "stats": {
                        "files_processed": 0,
                        "chunks_created": 0,
                        "failed_files": 0,
                        "duration_seconds": 0,
                    },
                }
                mock_connect.return_value = mock_conn

                # Patch at import location (inside _index_via_daemon function)
                with patch(
                    "code_indexer.progress.progress_display.RichLiveProgressManager"
                ) as mock_rich_live:
                    with patch(
                        "code_indexer.progress.MultiThreadedProgressManager"
                    ) as mock_progress_mgr:
                        # Call _index_via_daemon
                        daemon_config = {"retry_delays_ms": [100, 500]}
                        _index_via_daemon(
                            force_reindex=False, daemon_config=daemon_config
                        )

                        # Verify display components were created
                        assert mock_rich_live.called
                        assert mock_progress_mgr.called

    def test_index_via_daemon_calls_exposed_index_blocking(self):
        """Test _index_via_daemon calls exposed_index_blocking (not exposed_index)."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        # Mock all dependencies
        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/test/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = MagicMock()
                mock_conn.root.exposed_index_blocking.return_value = {
                    "status": "completed",
                    "stats": {
                        "files_processed": 0,
                        "chunks_created": 0,
                        "failed_files": 0,
                        "duration_seconds": 0,
                    },
                }
                mock_connect.return_value = mock_conn

                # Call _index_via_daemon
                daemon_config = {"retry_delays_ms": [100, 500]}
                _index_via_daemon(force_reindex=False, daemon_config=daemon_config)

                # Verify exposed_index_blocking was called (not exposed_index)
                assert mock_conn.root.exposed_index_blocking.called
                assert not mock_conn.root.exposed_index.called

    def test_index_via_daemon_passes_callback_to_daemon(self):
        """Test _index_via_daemon passes progress callback to daemon."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        # Mock all dependencies
        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/test/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = MagicMock()
                mock_conn.root.exposed_index_blocking.return_value = {
                    "status": "completed",
                    "stats": {
                        "files_processed": 0,
                        "chunks_created": 0,
                        "failed_files": 0,
                        "duration_seconds": 0,
                    },
                }
                mock_connect.return_value = mock_conn

                # Call _index_via_daemon
                daemon_config = {"retry_delays_ms": [100, 500]}
                _index_via_daemon(force_reindex=False, daemon_config=daemon_config)

                # Verify exposed_index_blocking was called with callback
                assert mock_conn.root.exposed_index_blocking.called
                call_args = mock_conn.root.exposed_index_blocking.call_args
                # Check that callback was passed
                assert "callback" in call_args.kwargs

    def test_index_via_daemon_returns_success_code(self):
        """Test _index_via_daemon returns 0 on success."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/test/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = MagicMock()
                mock_conn.root.exposed_index_blocking.return_value = {
                    "status": "completed",
                    "stats": {
                        "files_processed": 0,
                        "chunks_created": 0,
                        "failed_files": 0,
                        "duration_seconds": 0,
                    },
                }
                mock_connect.return_value = mock_conn

                daemon_config = {"retry_delays_ms": [100, 500]}
                result = _index_via_daemon(
                    force_reindex=False, daemon_config=daemon_config
                )

                assert result == 0

    def test_index_via_daemon_handles_error_gracefully(self):
        """Test _index_via_daemon handles errors and falls back to standalone."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/test/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = MagicMock()
                # Simulate error
                mock_conn.root.exposed_index_blocking.side_effect = Exception(
                    "Indexing failed"
                )
                mock_connect.return_value = mock_conn

                with patch(
                    "code_indexer.cli_daemon_delegation._index_standalone"
                ) as mock_standalone:
                    mock_standalone.return_value = 0

                    daemon_config = {"retry_delays_ms": [100, 500]}
                    result = _index_via_daemon(
                        force_reindex=False, daemon_config=daemon_config
                    )

                    # Should fall back to standalone
                    assert mock_standalone.called
                    assert result == 0

    def test_index_via_daemon_closes_connection(self):
        """Test _index_via_daemon closes connection after indexing."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/test/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = MagicMock()
                mock_conn.root.exposed_index_blocking.return_value = {
                    "status": "completed",
                    "stats": {
                        "files_processed": 0,
                        "chunks_created": 0,
                        "failed_files": 0,
                        "duration_seconds": 0,
                    },
                }
                mock_connect.return_value = mock_conn

                daemon_config = {"retry_delays_ms": [100, 500]}
                _index_via_daemon(force_reindex=False, daemon_config=daemon_config)

                # Verify connection was closed
                assert mock_conn.close.called

    def test_index_via_daemon_passes_force_reindex_parameter(self):
        """Test _index_via_daemon passes force_full to daemon."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/test/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = MagicMock()
                mock_conn.root.exposed_index_blocking.return_value = {
                    "status": "completed",
                    "stats": {
                        "files_processed": 0,
                        "chunks_created": 0,
                        "failed_files": 0,
                        "duration_seconds": 0,
                    },
                }
                mock_connect.return_value = mock_conn

                daemon_config = {"retry_delays_ms": [100, 500]}
                _index_via_daemon(force_reindex=True, daemon_config=daemon_config)

                # Verify force_full was passed
                call_args = mock_conn.root.exposed_index_blocking.call_args
                assert call_args.kwargs.get("force_full")

    def test_index_via_daemon_displays_success_message(self):
        """Test _index_via_daemon displays success message with file count."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/test/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = MagicMock()
                mock_conn.root.exposed_index_blocking.return_value = {
                    "status": "completed",
                    "stats": {
                        "files_processed": 42,
                        "chunks_created": 100,
                        "failed_files": 0,
                        "duration_seconds": 10.5,
                    },
                }
                mock_connect.return_value = mock_conn

                with patch(
                    "code_indexer.cli_daemon_delegation.console"
                ) as mock_console:
                    daemon_config = {"retry_delays_ms": [100, 500]}
                    _index_via_daemon(force_reindex=False, daemon_config=daemon_config)

                    # Verify success message was printed
                    assert mock_console.print.called
                    # Check for files_processed in message
                    call_args_list = [
                        str(call) for call in mock_console.print.call_args_list
                    ]
                    assert any("42" in call for call in call_args_list)

    def test_index_via_daemon_handles_no_config_file(self):
        """Test _index_via_daemon handles missing config file."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = None

            with patch(
                "code_indexer.cli_daemon_delegation._index_standalone"
            ) as mock_standalone:
                mock_standalone.return_value = 0

                daemon_config = {"retry_delays_ms": [100, 500]}
                _index_via_daemon(force_reindex=False, daemon_config=daemon_config)

                # Should fall back to standalone
                assert mock_standalone.called

    def test_index_via_daemon_passes_additional_kwargs(self):
        """Test _index_via_daemon passes additional kwargs to daemon."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/test/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = MagicMock()
                mock_conn.root.exposed_index_blocking.return_value = {
                    "status": "completed",
                    "stats": {
                        "files_processed": 0,
                        "chunks_created": 0,
                        "failed_files": 0,
                        "duration_seconds": 0,
                    },
                }
                mock_connect.return_value = mock_conn

                daemon_config = {"retry_delays_ms": [100, 500]}
                _index_via_daemon(
                    force_reindex=False,
                    daemon_config=daemon_config,
                    enable_fts=True,
                    batch_size=100,
                )

                # Verify kwargs were passed
                call_args = mock_conn.root.exposed_index_blocking.call_args
                assert call_args.kwargs.get("enable_fts")
                assert call_args.kwargs.get("batch_size") == 100

    def test_connect_to_daemon_disables_rpc_timeout(self):
        """Test _connect_to_daemon configures sync_request_timeout=None and uses timeout."""
        from code_indexer.cli_daemon_delegation import _connect_to_daemon
        import socket as socket_module

        # Patch socket, SocketStream and connect_stream
        with patch("socket.socket") as mock_socket:
            with patch("rpyc.core.stream.SocketStream") as mock_stream_class:
                with patch("rpyc.utils.factory.connect_stream") as mock_connect_stream:
                    mock_sock_instance = Mock()
                    mock_socket.return_value = mock_sock_instance
                    mock_stream_instance = Mock()
                    mock_stream_class.return_value = mock_stream_instance
                    mock_conn = Mock()
                    mock_connect_stream.return_value = mock_conn

                    socket_path = Path("/test/daemon.sock")
                    daemon_config = {"retry_delays_ms": [100]}

                    result = _connect_to_daemon(
                        socket_path, daemon_config, connection_timeout=2.0
                    )

                    # Verify socket was created with AF_UNIX and SOCK_STREAM
                    mock_socket.assert_called_with(
                        socket_module.AF_UNIX, socket_module.SOCK_STREAM
                    )

                    # Verify timeout was set (should be called twice: once for connection, once to disable after)
                    assert mock_sock_instance.settimeout.call_count >= 1
                    # First call should set timeout to 2.0
                    first_timeout_call = mock_sock_instance.settimeout.call_args_list[0]
                    assert first_timeout_call[0][0] == 2.0

                    # Verify SocketStream was created with the socket
                    mock_stream_class.assert_called_once_with(mock_sock_instance)

                    # Verify connect_stream was called with config
                    assert mock_connect_stream.called
                    call_args = mock_connect_stream.call_args
                    config = call_args.kwargs.get("config")
                    assert config is not None
                    assert config.get("sync_request_timeout") is None
                    assert config.get("allow_public_attrs") is True
                    assert result == mock_conn
