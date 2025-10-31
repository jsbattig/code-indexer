"""
Unit tests for daemon delegation fixes (TDD approach).

These tests verify the fixes for:
1. "stream has been closed" error in index delegation
2. "'Context' object is not iterable" error in fallback
3. Parameter mapping issues
4. Watch delegation implementation
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from click import Context, Command


class TestIndexDelegationFixes:
    """Tests for index delegation error fixes."""

    @pytest.fixture
    def mock_daemon_config(self):
        """Mock daemon configuration."""
        return {
            "enabled": True,
            "retry_delays_ms": [100, 200, 400]
        }

    @pytest.fixture
    def mock_config_file(self, tmp_path):
        """Create mock config file."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text("{}")
        return config_file

    def test_index_via_daemon_closes_connection_after_result_display(self, mock_config_file, mock_daemon_config):
        """Test that connection is closed AFTER results are displayed, not before."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        # Mock RPyC connection
        mock_conn = Mock()
        mock_result = {"status": "success", "stats": {"files_processed": 10}}
        mock_conn.root.exposed_index.return_value = mock_result

        # Mock progress handler
        mock_progress = Mock()
        mock_callback = Mock()
        mock_progress.create_progress_callback.return_value = mock_callback

        with patch('code_indexer.cli_daemon_delegation._find_config_file', return_value=mock_config_file):
            with patch('code_indexer.cli_daemon_delegation._connect_to_daemon', return_value=mock_conn):
                with patch('code_indexer.cli_progress_handler.ClientProgressHandler', return_value=mock_progress):
                    # Execute index delegation
                    exit_code = _index_via_daemon(
                        force_reindex=True,
                        daemon_config=mock_daemon_config,
                        enable_fts=False
                    )

        # Should succeed
        assert exit_code == 0

        # Connection should be closed LAST (after all operations)
        mock_conn.close.assert_called_once()

    def test_index_via_daemon_handles_connection_errors_gracefully(self, mock_config_file, mock_daemon_config):
        """Test that connection errors don't leave unclosed connections."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        # Mock connection that raises error
        mock_conn = Mock()
        mock_conn.root.exposed_index.side_effect = Exception("stream has been closed")

        with patch('code_indexer.cli_daemon_delegation._find_config_file', return_value=mock_config_file):
            with patch('code_indexer.cli_daemon_delegation._connect_to_daemon', return_value=mock_conn):
                with patch('code_indexer.cli_daemon_delegation._index_standalone', return_value=0) as mock_standalone:
                    # Execute index delegation (should fallback to standalone)
                    exit_code = _index_via_daemon(
                        force_reindex=True,
                        daemon_config=mock_daemon_config,
                        enable_fts=False
                    )

        # Should fallback to standalone
        mock_standalone.assert_called_once()

        # Connection should be closed even on error
        mock_conn.close.assert_called_once()

    def test_index_standalone_no_context_iteration_error(self):
        """Test that _index_standalone doesn't try to iterate over Context."""
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
                        # Execute standalone index
                        exit_code = _index_standalone(force_reindex=True)

        # Should succeed without iteration error
        assert exit_code == 0

        # Should call cli_index with correct parameters
        assert mock_index.called
        call_args = mock_index.call_args

        # Verify context was created properly
        assert isinstance(call_args[0][0], Context)

        # Verify force_reindex was mapped to clear parameter
        assert 'clear' in call_args[1]
        assert call_args[1]['clear'] is True

    def test_index_delegation_parameter_mapping(self, mock_config_file, mock_daemon_config):
        """Test that parameters are correctly mapped between CLI and daemon."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        mock_conn = Mock()
        mock_result = {"status": "success", "stats": {"files_processed": 5}}
        mock_conn.root.exposed_index.return_value = mock_result

        mock_progress = Mock()
        mock_callback = Mock()
        mock_progress.create_progress_callback.return_value = mock_callback

        with patch('code_indexer.cli_daemon_delegation._find_config_file', return_value=mock_config_file):
            with patch('code_indexer.cli_daemon_delegation._connect_to_daemon', return_value=mock_conn):
                with patch('code_indexer.cli_progress_handler.ClientProgressHandler', return_value=mock_progress):
                    # Test parameter mapping: force_reindex -> force_full, enable_fts -> enable_fts
                    _index_via_daemon(
                        force_reindex=True,
                        daemon_config=mock_daemon_config,
                        enable_fts=True
                    )

        # Verify exposed_index was called with correct mapped parameters
        call_kwargs = mock_conn.root.exposed_index.call_args[1]

        # force_reindex should map to force_full for daemon
        assert 'force_full' in call_kwargs or 'force_reindex' in call_kwargs

        # enable_fts should be passed through
        assert 'enable_fts' in call_kwargs


class TestWatchDelegationFixes:
    """Tests for watch delegation implementation."""

    @pytest.fixture
    def mock_daemon_config(self):
        """Mock daemon configuration."""
        return {
            "enabled": True,
            "retry_delays_ms": [100, 200, 400]
        }

    @pytest.fixture
    def mock_config_file(self, tmp_path):
        """Create mock config file."""
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text("{}")
        return config_file

    def test_watch_via_daemon_closes_connection_properly(self, mock_config_file, mock_daemon_config):
        """Test that watch delegation closes connection after starting watch."""
        from code_indexer.cli_daemon_delegation import _watch_via_daemon

        mock_conn = Mock()
        mock_result = {"status": "success", "message": "Watch started"}
        mock_conn.root.exposed_watch_start.return_value = mock_result

        with patch('code_indexer.cli_daemon_delegation._find_config_file', return_value=mock_config_file):
            with patch('code_indexer.cli_daemon_delegation._connect_to_daemon', return_value=mock_conn):
                # Execute watch delegation
                exit_code = _watch_via_daemon(
                    debounce=1.0,
                    batch_size=50,
                    initial_sync=True,
                    enable_fts=False,
                    daemon_config=mock_daemon_config
                )

        # Should succeed
        assert exit_code == 0

        # exposed_watch_start should be called
        mock_conn.root.exposed_watch_start.assert_called_once()

        # Connection should be closed
        mock_conn.close.assert_called_once()

    def test_watch_via_daemon_parameter_mapping(self, mock_config_file, mock_daemon_config):
        """Test that watch parameters are correctly mapped to daemon call."""
        from code_indexer.cli_daemon_delegation import _watch_via_daemon

        mock_conn = Mock()
        mock_result = {"status": "success"}
        mock_conn.root.exposed_watch_start.return_value = mock_result

        with patch('code_indexer.cli_daemon_delegation._find_config_file', return_value=mock_config_file):
            with patch('code_indexer.cli_daemon_delegation._connect_to_daemon', return_value=mock_conn):
                # Test parameter passing
                _watch_via_daemon(
                    debounce=2.5,
                    batch_size=100,
                    initial_sync=True,
                    enable_fts=True,
                    daemon_config=mock_daemon_config
                )

        # Verify exposed_watch_start was called with correct parameters
        call_args = mock_conn.root.exposed_watch_start.call_args
        assert call_args[1]['project_path'] == str(Path.cwd())
        assert call_args[1]['debounce_seconds'] == 2.5
        assert call_args[1]['batch_size'] == 100
        assert call_args[1]['initial_sync'] is True
        assert call_args[1]['enable_fts'] is True

    def test_watch_standalone_fallback_works(self):
        """Test that watch standalone fallback works without errors."""
        from code_indexer.cli_daemon_delegation import _watch_standalone

        mock_watch = Mock()
        mock_config_manager = Mock()
        mock_mode_detector = Mock()
        mock_mode_detector.detect_mode.return_value = "local"

        with patch('code_indexer.mode_detection.command_mode_detector.find_project_root', return_value=Path.cwd()):
            with patch('code_indexer.mode_detection.command_mode_detector.CommandModeDetector', return_value=mock_mode_detector):
                with patch('code_indexer.config.ConfigManager.create_with_backtrack', return_value=mock_config_manager):
                    with patch('code_indexer.cli.watch', mock_watch):
                        # Execute standalone watch
                        exit_code = _watch_standalone(
                            debounce=1.0,
                            batch_size=50,
                            initial_sync=True,
                            enable_fts=False
                        )

        # Should succeed
        assert exit_code == 0

        # Should call cli_watch with correct parameters
        assert mock_watch.called
        call_args = mock_watch.call_args

        # Verify context was created
        assert isinstance(call_args[0][0], Context)

        # Verify parameters
        assert call_args[1]['debounce'] == 1.0
        assert call_args[1]['batch_size'] == 50
        assert call_args[1]['initial_sync'] is True
        assert call_args[1]['fts'] is False  # enable_fts maps to fts parameter


class TestConnectionLifecycleManagement:
    """Tests for proper connection lifecycle management."""

    def test_connection_closed_in_finally_block(self):
        """Test that connections are closed in finally block to prevent leaks."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        mock_conn = Mock()
        # Simulate error during indexing
        mock_conn.root.exposed_index.side_effect = Exception("Indexing error")

        with patch('code_indexer.cli_daemon_delegation._find_config_file', return_value=Path("test/.code-indexer/config.json")):
            with patch('code_indexer.cli_daemon_delegation._connect_to_daemon', return_value=mock_conn):
                with patch('code_indexer.cli_daemon_delegation._index_standalone', return_value=0):
                    # Execute - should handle error and close connection
                    _index_via_daemon(
                        force_reindex=False,
                        daemon_config={"enabled": True, "retry_delays_ms": [100]}
                    )

        # Connection should be closed even when error occurs
        mock_conn.close.assert_called()

    def test_progress_handler_error_doesnt_prevent_cleanup(self):
        """Test that progress handler errors don't prevent connection cleanup."""
        from code_indexer.cli_daemon_delegation import _index_via_daemon

        mock_conn = Mock()
        mock_result = {"status": "success", "stats": {"files_processed": 10}}
        mock_conn.root.exposed_index.return_value = mock_result

        # Mock progress handler that raises error
        mock_progress = Mock()
        mock_progress.error.side_effect = Exception("Progress error")

        with patch('code_indexer.cli_daemon_delegation._find_config_file', return_value=Path("test/.code-indexer/config.json")):
            with patch('code_indexer.cli_daemon_delegation._connect_to_daemon', return_value=mock_conn):
                with patch('code_indexer.cli_progress_handler.ClientProgressHandler', return_value=mock_progress):
                    with patch('code_indexer.cli_daemon_delegation._index_standalone', return_value=0):
                        # Execute - should handle error
                        _index_via_daemon(
                            force_reindex=False,
                            daemon_config={"enabled": True, "retry_delays_ms": [100]}
                        )

        # Connection should still be closed
        mock_conn.close.assert_called()
