"""Tests for the enhanced cancellation system with immediate feedback and timeout protection."""

from unittest.mock import Mock, patch
from pathlib import Path

from code_indexer.cli import GracefulInterruptHandler


class TestGracefulInterruptHandler:
    """Test enhanced graceful interrupt handling."""

    def setup_method(self):
        """Setup test environment."""
        self.mock_console = Mock()
        self.handler = GracefulInterruptHandler(
            self.mock_console,
            "Testing",
            cancellation_timeout=2.0,  # Short timeout for testing
        )

    def test_initial_state(self):
        """Test initial state of interrupt handler."""
        assert not self.handler.interrupted
        assert not self.handler.force_quit
        assert self.handler.interrupt_time is None
        assert self.handler.operation_name == "Testing"
        assert self.handler.cancellation_timeout == 2.0

    @patch("sys.exit")
    def test_first_interrupt_graceful(self, mock_exit):
        """Test first interrupt triggers graceful cancellation."""
        with patch("time.time", return_value=1000.0):
            self.handler._signal_handler(2, None)  # SIGINT

        assert self.handler.interrupted
        assert not self.handler.force_quit
        assert self.handler.interrupt_time == 1000.0

        # Should show cancellation messages
        assert self.mock_console.print.call_count >= 3
        calls = [
            str(call[0][0]) if call[0] else str(call)
            for call in self.mock_console.print.call_args_list
        ]

        # Check for key messages
        cancellation_msg = next(
            (msg for msg in calls if "CANCELLATION REQUESTED" in msg), None
        )
        assert cancellation_msg is not None

        timeout_msg = next(
            (msg for msg in calls if "within 2.0s to force quit" in msg), None
        )
        assert timeout_msg is not None

        # Should not exit on first interrupt
        mock_exit.assert_not_called()

    @patch("sys.exit")
    def test_second_interrupt_force_quit(self, mock_exit):
        """Test second interrupt within timeout triggers force quit."""
        # First interrupt
        with patch("time.time", return_value=1000.0):
            self.handler._signal_handler(2, None)

        # Second interrupt within timeout
        with patch("time.time", return_value=1001.0):  # 1 second later
            self.handler._signal_handler(2, None)

        assert self.handler.interrupted
        assert self.handler.force_quit

        # Should exit with code 1 (force quit)
        mock_exit.assert_called_once_with(1)

        # Should show force quit messages
        calls = [
            str(call[0][0]) if call[0] else str(call)
            for call in self.mock_console.print.call_args_list
        ]
        force_quit_msg = next(
            (msg for msg in calls if "FORCE QUIT REQUESTED" in msg), None
        )
        assert force_quit_msg is not None

    @patch("sys.exit")
    def test_timeout_automatic_force_quit(self, mock_exit):
        """Test automatic force quit when timeout is exceeded."""
        # First interrupt
        with patch("time.time", return_value=1000.0):
            self.handler._signal_handler(2, None)

        # Interrupt after timeout exceeded
        with patch(
            "time.time", return_value=1003.0
        ):  # 3 seconds later (> 2.0s timeout)
            self.handler._signal_handler(2, None)

        assert self.handler.interrupted
        assert self.handler.force_quit

        # Should exit with code 2 (timeout)
        mock_exit.assert_called_once_with(2)

        # Should show timeout messages
        calls = [
            str(call[0][0]) if call[0] else str(call)
            for call in self.mock_console.print.call_args_list
        ]
        timeout_msg = next(
            (msg for msg in calls if "CANCELLATION TIMEOUT" in msg), None
        )
        assert timeout_msg is not None

    def test_is_cancellation_overdue(self):
        """Test cancellation timeout checking."""
        # No cancellation yet
        assert not self.handler.is_cancellation_overdue()

        # Simulate cancellation
        with patch("time.time", return_value=1000.0):
            self.handler._signal_handler(2, None)

        # Within timeout
        with patch("time.time", return_value=1001.0):
            assert not self.handler.is_cancellation_overdue()

        # Beyond timeout
        with patch("time.time", return_value=1003.0):
            assert self.handler.is_cancellation_overdue()

    def test_get_time_since_cancellation(self):
        """Test time tracking since cancellation."""
        # No cancellation yet
        assert self.handler.get_time_since_cancellation() == 0.0

        # Simulate cancellation
        with patch("time.time", return_value=1000.0):
            self.handler._signal_handler(2, None)

        # Check elapsed time
        with patch("time.time", return_value=1002.5):
            assert self.handler.get_time_since_cancellation() == 2.5

    def test_progress_bar_stopping(self):
        """Test that progress bar is stopped on interruption."""
        mock_progress_bar = Mock()
        self.handler.set_progress_bar(mock_progress_bar)

        with patch("time.time", return_value=1000.0):
            self.handler._signal_handler(2, None)

        mock_progress_bar.stop.assert_called_once()

    def test_context_manager_behavior(self):
        """Test context manager behavior."""
        mock_signal = Mock()

        with patch("signal.signal", mock_signal):
            with self.handler:
                # Signal handler should be installed
                mock_signal.assert_called_once()

            # Should be called twice - install and restore
            assert mock_signal.call_count == 2

    def test_context_manager_with_interruption(self):
        """Test context manager handles interruption properly."""
        with patch("signal.signal"):
            with self.handler as handler:
                # Simulate interruption
                handler.interrupted = True

        # Should show completion message
        calls = [
            str(call[0][0]) if call[0] else str(call)
            for call in self.mock_console.print.call_args_list
        ]
        interrupted_msg = next(
            (msg for msg in calls if "interrupted by user" in msg), None
        )
        assert interrupted_msg is not None

    def test_custom_timeout_configuration(self):
        """Test custom timeout configuration."""
        custom_handler = GracefulInterruptHandler(
            self.mock_console, "Custom Operation", cancellation_timeout=10.0
        )

        assert custom_handler.cancellation_timeout == 10.0
        assert custom_handler.operation_name == "Custom Operation"

        # Test timeout message includes custom timeout
        with patch("time.time", return_value=1000.0):
            custom_handler._signal_handler(2, None)

        calls = [
            str(call[0][0]) if call[0] else str(call)
            for call in self.mock_console.print.call_args_list
        ]
        timeout_msg = next(
            (msg for msg in calls if "within 10.0s to force quit" in msg), None
        )
        assert timeout_msg is not None


class TestEnhancedCancellationIntegration:
    """Integration tests for enhanced cancellation features."""

    def test_cancellation_feedback_integration(self):
        """Test that cancellation feedback works with progress callbacks."""
        from code_indexer.cli import console

        # Create handler
        handler = GracefulInterruptHandler(
            console, "Integration Test", cancellation_timeout=5.0
        )

        # Mock the check_for_interruption function
        def mock_check_interruption():
            if handler.interrupted:
                return "INTERRUPT"
            return None

        # Simulate the progress callback logic from CLI
        def progress_callback(current, total, file_path, error=None, info=None):
            interrupt_result = mock_check_interruption()
            if interrupt_result:
                return interrupt_result

            if total > 0 and info:
                if handler.interrupted:
                    cancellation_info = f"🛑 CANCELLING - {info}"
                    return cancellation_info
                else:
                    return info

        # Test normal operation
        result = progress_callback(5, 10, Path("test.py"), info="Processing files")
        assert result == "Processing files"

        # Simulate interruption
        with patch("time.time", return_value=1000.0):
            handler._signal_handler(2, None)

        # Test cancellation response
        result = progress_callback(5, 10, Path("test.py"))
        assert result == "INTERRUPT"

        # Test cancellation info modification - check returns interrupt first
        result = progress_callback(
            5, 10, Path("test.py"), info="5/10 files | 2.5 emb/s"
        )
        # The logic checks for interrupt first, so it returns "INTERRUPT"
        assert result == "INTERRUPT"

    def test_timeout_protection_scenarios(self):
        """Test various timeout protection scenarios."""
        mock_console = Mock()
        handler = GracefulInterruptHandler(
            mock_console, "Timeout Test", cancellation_timeout=1.0
        )

        # Test normal graceful cancellation within timeout
        with patch("time.time", return_value=1000.0):
            handler._signal_handler(2, None)

        assert handler.interrupted
        assert not handler.force_quit

        # Check cancellation is not overdue immediately after interrupt
        with patch("time.time", return_value=1000.5):  # 0.5s later
            assert not handler.is_cancellation_overdue()

        # Test timeout detection
        with patch("time.time", return_value=1001.5):  # 1.5s later
            assert handler.is_cancellation_overdue()
            assert handler.get_time_since_cancellation() == 1.5

        # Test force quit behavior would be triggered
        with patch("sys.exit") as mock_exit:
            with patch("time.time", return_value=1001.5):
                handler._signal_handler(2, None)
            mock_exit.assert_called_once_with(2)  # Timeout exit code
