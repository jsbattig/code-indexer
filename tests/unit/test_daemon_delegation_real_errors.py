"""
Tests that reproduce the ACTUAL errors reported in the issue.

These tests verify:
1. "stream has been closed" error when accessing result after conn.close()
2. "'Context' object is not iterable" error in fallback
3. Parameter mapping issues (force_reindex vs force_full)
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from click import Context, Command


class TestActualStreamClosedError:
    """Reproduce the actual 'stream has been closed' error."""

    def test_result_access_after_connection_closed_fails(self):
        """Test that result data is extracted BEFORE closing connection."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        # Create mock connection with RPyC-like behavior
        mock_conn = Mock()

        # Mock result that becomes invalid after connection closes
        mock_result = MagicMock()
        get_call_count = []
        def get_raises_error(*args, **kwargs):
            get_call_count.append(1)
            if not mock_conn._is_open:
                raise EOFError("stream has been closed")
            # Return different values for different get() calls
            key = args[0] if args else None
            if key == "status":
                return "success"
            elif key == "message":
                return "Indexing completed"
            elif key == "stats":
                return {"files_processed": 10}
            return {}

        mock_result.get.side_effect = get_raises_error
        mock_conn._is_open = True
        mock_conn.root.exposed_index.return_value = mock_result

        # Make close() mark connection as closed
        def close_conn():
            mock_conn._is_open = False
        mock_conn.close.side_effect = close_conn

        # Mock other dependencies
        config_file = Path("test/.code-indexer/config.json")
        mock_progress = Mock()
        mock_callback = Mock()
        mock_progress.create_progress_callback.return_value = mock_callback

        with patch('code_indexer.cli_daemon_delegation._find_config_file', return_value=config_file):
            with patch('code_indexer.cli_daemon_delegation._connect_to_daemon', return_value=mock_conn):
                with patch('code_indexer.cli_progress_handler.ClientProgressHandler', return_value=mock_progress):
                    # This should NOT trigger error because we extract data before closing
                    exit_code = _index_via_daemon(
                        force_reindex=True,
                        daemon_config={"enabled": True, "retry_delays_ms": [100]},
                        enable_fts=False
                    )

        # Should succeed without fallback
        assert exit_code == 0
        # result.get() should have been called multiple times while connection was open
        assert len(get_call_count) >= 3, "Should extract multiple fields from result"


class TestActualParameterMappingError:
    """Reproduce parameter mapping issues."""

    def test_force_reindex_not_mapped_to_force_full(self):
        """Test that force_reindex parameter needs to be mapped to force_full."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        mock_conn = Mock()
        mock_result = {"status": "success", "message": "Indexing completed"}
        mock_conn.root.exposed_index.return_value = mock_result

        config_file = Path("test/.code-indexer/config.json")
        mock_progress = Mock()
        mock_callback = Mock()
        mock_progress.create_progress_callback.return_value = mock_callback

        with patch('code_indexer.cli_daemon_delegation._find_config_file', return_value=config_file):
            with patch('code_indexer.cli_daemon_delegation._connect_to_daemon', return_value=mock_conn):
                with patch('code_indexer.cli_progress_handler.ClientProgressHandler', return_value=mock_progress):
                    _index_via_daemon(
                        force_reindex=True,
                        daemon_config={"enabled": True, "retry_delays_ms": [100]},
                        enable_fts=False
                    )

        # Check what parameters were passed to daemon
        call_kwargs = mock_conn.root.exposed_index.call_args[1]

        # daemon.service.exposed_index expects force_full, not force_reindex
        assert 'force_full' in call_kwargs, "force_reindex should be mapped to force_full"
        assert call_kwargs['force_full'] is True

    def test_result_dict_missing_stats_key(self):
        """Test that daemon returns simple dict without 'stats' key."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        mock_conn = Mock()
        # Daemon returns {"status": "success", "message": "..."} NOT {"stats": {...}}
        mock_result = {"status": "success", "message": "Indexing completed"}
        mock_conn.root.exposed_index.return_value = mock_result

        config_file = Path("test/.code-indexer/config.json")
        mock_progress = Mock()
        mock_callback = Mock()
        mock_progress.create_progress_callback.return_value = mock_callback

        with patch('code_indexer.cli_daemon_delegation._find_config_file', return_value=config_file):
            with patch('code_indexer.cli_daemon_delegation._connect_to_daemon', return_value=mock_conn):
                with patch('code_indexer.cli_progress_handler.ClientProgressHandler', return_value=mock_progress):
                    # Should not crash when result doesn't have 'stats' key
                    exit_code = _index_via_daemon(
                        force_reindex=True,
                        daemon_config={"enabled": True, "retry_delays_ms": [100]},
                        enable_fts=False
                    )

        # Should succeed even without 'stats' key
        assert exit_code == 0


class TestActualContextIterationError:
    """Verify that daemon-specific kwargs are properly filtered."""

    def test_kwargs_with_daemon_params_are_filtered(self):
        """Test that daemon-specific kwargs are filtered out before calling CLI."""
        from code_indexer.cli_daemon_delegation import _index_standalone

        # Mock CLI components
        mock_index = Mock()
        mock_config_manager = Mock()
        mock_mode_detector = Mock()
        mock_mode_detector.detect_mode.return_value = "local"

        with patch('code_indexer.mode_detection.command_mode_detector.find_project_root', return_value=Path.cwd()):
            with patch('code_indexer.mode_detection.command_mode_detector.CommandModeDetector', return_value=mock_mode_detector):
                with patch('code_indexer.config.ConfigManager.create_with_backtrack', return_value=mock_config_manager):
                    with patch('code_indexer.cli.index', mock_index):
                        # Pass daemon-specific param that should be filtered out
                        exit_code = _index_standalone(
                            force_reindex=True,
                            enable_fts=False,
                            daemon_config={"enabled": True}  # Should be filtered
                        )

        # Should succeed - daemon_config should be filtered out
        assert exit_code == 0

        # Verify daemon_config was NOT passed to CLI
        call_kwargs = mock_index.call_args[1]
        assert 'daemon_config' not in call_kwargs, "daemon_config should be filtered out"


class TestCorrectFixes:
    """Tests that verify the correct fixes."""

    def test_extract_result_data_before_closing_connection(self):
        """Verify that result data is extracted BEFORE closing connection."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        mock_conn = Mock()

        # Create a mock result object with tracking
        operations = []
        mock_result = MagicMock()
        def track_get(key, default=None):
            operations.append(f'get:{key}')
            if key == "status":
                return "success"
            elif key == "message":
                return "Done"
            elif key == "stats":
                return {}
            return default

        mock_result.get.side_effect = track_get
        mock_conn.root.exposed_index.return_value = mock_result
        mock_conn.close = Mock(side_effect=lambda: operations.append('close'))

        config_file = Path("test/.code-indexer/config.json")
        mock_progress = Mock()
        mock_callback = Mock()
        mock_progress.create_progress_callback.return_value = mock_callback

        with patch('code_indexer.cli_daemon_delegation._find_config_file', return_value=config_file):
            with patch('code_indexer.cli_daemon_delegation._connect_to_daemon', return_value=mock_conn):
                with patch('code_indexer.cli_progress_handler.ClientProgressHandler', return_value=mock_progress):
                    exit_code = _index_via_daemon(
                        force_reindex=True,
                        daemon_config={"enabled": True, "retry_delays_ms": [100]},
                        enable_fts=False
                    )

        # Verify result.get() calls happened BEFORE conn.close()
        assert exit_code == 0
        assert 'close' in operations, "Connection should be closed"

        # Find first get and close positions
        get_positions = [i for i, op in enumerate(operations) if op.startswith('get:')]
        close_position = operations.index('close')

        assert len(get_positions) > 0, "Should have called get() at least once"
        assert all(pos < close_position for pos in get_positions), \
            "All get() calls must happen BEFORE close()"

    def test_clean_kwargs_before_passing_to_cli(self):
        """Verify that daemon-specific kwargs are removed before calling CLI."""
        from code_indexer.cli_daemon_delegation import _index_standalone

        mock_index = Mock()
        mock_config_manager = Mock()
        mock_mode_detector = Mock()
        mock_mode_detector.detect_mode.return_value = "local"

        with patch('code_indexer.mode_detection.command_mode_detector.find_project_root', return_value=Path.cwd()):
            with patch('code_indexer.mode_detection.command_mode_detector.CommandModeDetector', return_value=mock_mode_detector):
                with patch('code_indexer.config.ConfigManager.create_with_backtrack', return_value=mock_config_manager):
                    with patch('code_indexer.cli.index', mock_index):
                        # Pass daemon-specific param
                        exit_code = _index_standalone(
                            force_reindex=True,
                            enable_fts=False,
                            daemon_config={"enabled": True}
                        )

        # Should succeed - daemon_config should be filtered out
        assert exit_code == 0

        # Verify daemon_config was NOT passed to CLI
        call_kwargs = mock_index.call_args[1]
        assert 'daemon_config' not in call_kwargs, "daemon_config should be filtered out"
