"""
Unit tests for index command delegation with progress callbacks.

Tests cover:
- Index delegation creates ClientProgressHandler
- Index delegation passes callback to daemon
- Progress handler is used during indexing
- Error handling updates progress handler
- Completion updates progress handler
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


class TestIndexDelegationProgress:
    """Test index command delegation with progress callbacks."""

    def test_index_via_daemon_function_exists(self):
        """Test _index_via_daemon function exists in cli_daemon_delegation."""
        from code_indexer import cli_daemon_delegation

        assert hasattr(cli_daemon_delegation, "_index_via_daemon")
        assert callable(cli_daemon_delegation._index_via_daemon)

    def test_index_via_daemon_creates_progress_handler(self):
        """Test _index_via_daemon creates ClientProgressHandler."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        # Mock all dependencies
        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/test/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = MagicMock()
                mock_conn.root.exposed_index.return_value = {
                    "status": "completed",
                    "project": "/test",
                }
                mock_connect.return_value = mock_conn

                with patch(
                    "code_indexer.cli_progress_handler.ClientProgressHandler"
                ) as mock_handler_class:
                    mock_handler = MagicMock()
                    mock_handler_class.return_value = mock_handler
                    mock_handler.create_progress_callback.return_value = Mock()

                    # Call _index_via_daemon
                    daemon_config = {"retry_delays_ms": [100, 500]}
                    _index_via_daemon(force_reindex=False, daemon_config=daemon_config)

                    # Verify ClientProgressHandler was created
                    assert mock_handler_class.called

    def test_index_via_daemon_passes_callback_to_daemon(self):
        """Test _index_via_daemon passes callback to daemon's exposed_index."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        # Mock all dependencies
        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/test/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = MagicMock()
                mock_conn.root.exposed_index.return_value = {
                    "status": "completed",
                    "project": "/test",
                }
                mock_connect.return_value = mock_conn

                with patch(
                    "code_indexer.cli_progress_handler.ClientProgressHandler"
                ) as mock_handler_class:
                    mock_handler = MagicMock()
                    mock_callback = Mock()
                    mock_handler.create_progress_callback.return_value = mock_callback
                    mock_handler_class.return_value = mock_handler

                    # Call _index_via_daemon
                    daemon_config = {"retry_delays_ms": [100, 500]}
                    _index_via_daemon(force_reindex=False, daemon_config=daemon_config)

                    # Verify exposed_index was called with callback
                    assert mock_conn.root.exposed_index.called
                    call_args = mock_conn.root.exposed_index.call_args
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
                mock_conn.root.exposed_index.return_value = {
                    "status": "completed",
                    "project": "/test",
                }
                mock_connect.return_value = mock_conn

                with patch("code_indexer.cli_progress_handler.ClientProgressHandler"):
                    daemon_config = {"retry_delays_ms": [100, 500]}
                    result = _index_via_daemon(
                        force_reindex=False, daemon_config=daemon_config
                    )

                    assert result == 0

    def test_index_via_daemon_handles_error_with_progress_handler(self):
        """Test _index_via_daemon calls progress.error() on indexing error."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/test/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = MagicMock()
                # Simulate error
                mock_conn.root.exposed_index.side_effect = Exception("Indexing failed")
                mock_connect.return_value = mock_conn

                with patch(
                    "code_indexer.cli_progress_handler.ClientProgressHandler"
                ) as mock_handler_class:
                    mock_handler = MagicMock()
                    mock_handler_class.return_value = mock_handler

                    daemon_config = {"retry_delays_ms": [100, 500]}

                    # Call should raise exception
                    with pytest.raises(Exception, match="Indexing failed"):
                        _index_via_daemon(
                            force_reindex=False, daemon_config=daemon_config
                        )

                    # Verify error() was called on progress handler
                    assert mock_handler.error.called

    def test_index_via_daemon_closes_connection(self):
        """Test _index_via_daemon closes connection after indexing."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/test/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = MagicMock()
                mock_conn.root.exposed_index.return_value = {
                    "status": "completed",
                    "project": "/test",
                }
                mock_connect.return_value = mock_conn

                with patch("code_indexer.cli_progress_handler.ClientProgressHandler"):
                    daemon_config = {"retry_delays_ms": [100, 500]}
                    _index_via_daemon(force_reindex=False, daemon_config=daemon_config)

                    # Verify connection was closed
                    assert mock_conn.close.called

    def test_index_via_daemon_passes_force_reindex_parameter(self):
        """Test _index_via_daemon passes force_reindex to daemon."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/test/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = MagicMock()
                mock_conn.root.exposed_index.return_value = {
                    "status": "completed",
                    "project": "/test",
                }
                mock_connect.return_value = mock_conn

                with patch("code_indexer.cli_progress_handler.ClientProgressHandler"):
                    daemon_config = {"retry_delays_ms": [100, 500]}
                    _index_via_daemon(force_reindex=True, daemon_config=daemon_config)

                    # Verify force_reindex was passed
                    call_args = mock_conn.root.exposed_index.call_args
                    assert call_args.kwargs.get("force_reindex")

    def test_index_via_daemon_displays_success_message(self):
        """Test _index_via_daemon displays success message with file count."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        with patch("code_indexer.cli_daemon_delegation._find_config_file") as mock_find:
            mock_find.return_value = Path("/test/.code-indexer/config.json")

            with patch(
                "code_indexer.cli_daemon_delegation._connect_to_daemon"
            ) as mock_connect:
                mock_conn = MagicMock()
                mock_conn.root.exposed_index.return_value = {
                    "status": "completed",
                    "project": "/test",
                    "stats": {"files_processed": 42},
                }
                mock_connect.return_value = mock_conn

                with patch("code_indexer.cli_progress_handler.ClientProgressHandler"):
                    with patch(
                        "code_indexer.cli_daemon_delegation.console"
                    ) as mock_console:
                        daemon_config = {"retry_delays_ms": [100, 500]}
                        _index_via_daemon(
                            force_reindex=False, daemon_config=daemon_config
                        )

                        # Verify success message was printed
                        assert mock_console.print.called
                        # Check for files_processed in message
                        call_args = str(mock_console.print.call_args)
                        assert "42" in call_args or "files" in call_args.lower()

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
                mock_conn.root.exposed_index.return_value = {
                    "status": "completed",
                    "project": "/test",
                }
                mock_connect.return_value = mock_conn

                with patch("code_indexer.cli_progress_handler.ClientProgressHandler"):
                    daemon_config = {"retry_delays_ms": [100, 500]}
                    _index_via_daemon(
                        force_reindex=False,
                        daemon_config=daemon_config,
                        enable_fts=True,
                        custom_param="test",
                    )

                    # Verify kwargs were passed
                    call_args = mock_conn.root.exposed_index.call_args
                    assert call_args.kwargs.get("enable_fts")
                    assert call_args.kwargs.get("custom_param") == "test"
