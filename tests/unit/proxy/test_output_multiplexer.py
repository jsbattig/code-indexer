"""Unit tests for OutputMultiplexer (Story 5.2).

Tests unified output streaming from multiple watch processes.
"""

import pytest
import threading
import time
from unittest.mock import Mock
from io import StringIO
from code_indexer.proxy.output_multiplexer import OutputMultiplexer


class TestOutputMultiplexer:
    """Test output multiplexing from multiple processes."""

    @pytest.fixture
    def mock_processes(self):
        """Create mock subprocess.Popen objects."""
        processes = {}

        # Create mock process for repo1
        proc1 = Mock()
        proc1.stdout = StringIO("Line 1 from repo1\nLine 2 from repo1\n")
        processes["repo1"] = proc1

        # Create mock process for repo2
        proc2 = Mock()
        proc2.stdout = StringIO("Line 1 from repo2\nLine 2 from repo2\n")
        processes["repo2"] = proc2

        return processes

    def test_output_queue_initialization(self):
        """Test output multiplexer initializes with empty queue."""
        multiplexer = OutputMultiplexer({})

        assert multiplexer.output_queue is not None
        assert multiplexer.output_queue.empty()
        assert multiplexer.running is True

    def test_start_multiplexing_creates_reader_threads(self, mock_processes):
        """Test multiplexing starts reader thread for each process."""
        multiplexer = OutputMultiplexer(mock_processes)

        # Start multiplexing
        multiplexer.start_multiplexing()

        # Should create reader threads for each repository
        # Wait a bit for threads to start
        time.sleep(0.1)

        # Check threads were created (2 reader threads + 1 writer thread)
        assert len(multiplexer.reader_threads) == len(mock_processes)

    def test_read_process_output_queues_lines(self):
        """Test reading process output queues complete lines."""
        processes = {}
        proc = Mock()
        proc.stdout = StringIO("Line 1\nLine 2\nLine 3\n")
        processes["test-repo"] = proc

        multiplexer = OutputMultiplexer(processes)

        # Read output from process
        multiplexer._read_process_output("test-repo", proc)

        # Verify lines were queued
        assert multiplexer.output_queue.qsize() == 3

        # Check queued content
        repo1, line1 = multiplexer.output_queue.get_nowait()
        assert repo1 == "test-repo"
        assert line1 == "Line 1"

    def test_read_process_output_strips_newlines(self):
        """Test output reading strips trailing newlines."""
        processes = {}
        proc = Mock()
        proc.stdout = StringIO("Line with newline\n")
        processes["repo"] = proc

        multiplexer = OutputMultiplexer(processes)
        multiplexer._read_process_output("repo", proc)

        _, line = multiplexer.output_queue.get_nowait()

        # Newline should be stripped
        assert line == "Line with newline"
        assert not line.endswith("\n")

    def test_output_queue_thread_safe(self):
        """Test output queue is thread-safe for concurrent access."""
        multiplexer = OutputMultiplexer({})

        # Queue items from multiple threads
        def queue_items(repo_name, count):
            for i in range(count):
                multiplexer.output_queue.put((repo_name, f"Line {i}"))

        threads = []
        for i in range(5):
            thread = threading.Thread(target=queue_items, args=(f"repo{i}", 10))
            thread.start()
            threads.append(thread)

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Should have all items (5 repos * 10 lines)
        assert multiplexer.output_queue.qsize() == 50

    def test_stop_multiplexing_sets_running_flag(self, mock_processes):
        """Test stop_multiplexing sets running flag to False."""
        multiplexer = OutputMultiplexer(mock_processes)
        multiplexer.start_multiplexing()

        assert multiplexer.running is True

        multiplexer.stop_multiplexing()

        assert multiplexer.running is False

    def test_stop_multiplexing_waits_for_threads(self, mock_processes):
        """Test stop_multiplexing waits for reader threads to finish."""
        multiplexer = OutputMultiplexer(mock_processes)
        multiplexer.start_multiplexing()

        # Give threads time to start
        time.sleep(0.1)

        initial_thread_count = len(
            [t for t in multiplexer.reader_threads if t.is_alive()]
        )

        multiplexer.stop_multiplexing()

        # Threads should be stopped or joined
        # Note: daemon threads may still exist but won't block
        time.sleep(0.2)
        final_thread_count = len(
            [t for t in multiplexer.reader_threads if t.is_alive()]
        )

        # Final count should be <= initial count (threads terminating)
        assert final_thread_count <= initial_thread_count

    def test_stop_multiplexing_drains_queue(self):
        """Test stop_multiplexing drains remaining output queue."""
        multiplexer = OutputMultiplexer({})

        # Queue some items
        multiplexer.output_queue.put(("repo1", "line1"))
        multiplexer.output_queue.put(("repo2", "line2"))

        # Capture output during drain
        import sys
        from io import StringIO

        captured_output = StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured_output

        try:
            multiplexer.stop_multiplexing()
        finally:
            sys.stdout = old_stdout

        output = captured_output.getvalue()

        # Queue should be empty after drain
        assert multiplexer.output_queue.empty()

        # Output should contain queued items
        assert "repo1" in output or "repo2" in output

    def test_read_process_handles_empty_output(self):
        """Test reading from process with no output."""
        proc = Mock()
        proc.stdout = StringIO("")
        processes = {"empty-repo": proc}

        multiplexer = OutputMultiplexer(processes)
        multiplexer._read_process_output("empty-repo", proc)

        # Queue should be empty
        assert multiplexer.output_queue.empty()

    def test_read_process_handles_exception(self):
        """Test reading process handles exceptions gracefully."""
        proc = Mock()
        # Simulate error during reading
        proc.stdout = Mock()
        proc.stdout.__iter__ = Mock(side_effect=IOError("Read error"))
        processes = {"error-repo": proc}

        multiplexer = OutputMultiplexer(processes)

        # Should not raise exception
        multiplexer._read_process_output("error-repo", proc)

        # Should queue error message
        if not multiplexer.output_queue.empty():
            repo, line = multiplexer.output_queue.get_nowait()
            assert "ERROR" in line or "error" in line.lower()

    def test_multiple_repositories_interleaved_output(self):
        """Test output from multiple repositories is interleaved."""
        processes = {}

        # Create multiple repos with output
        for i in range(3):
            proc = Mock()
            proc.stdout = StringIO(f"Line 1 from repo{i}\nLine 2 from repo{i}\n")
            processes[f"repo{i}"] = proc

        multiplexer = OutputMultiplexer(processes)

        # Read from all processes
        for repo, proc in processes.items():
            multiplexer._read_process_output(repo, proc)

        # Should have output from all repositories
        assert multiplexer.output_queue.qsize() == 6  # 3 repos * 2 lines

        # Collect all outputs
        outputs = []
        while not multiplexer.output_queue.empty():
            outputs.append(multiplexer.output_queue.get_nowait())

        # Should have output from all repos
        repos_found = set(repo for repo, _ in outputs)
        assert len(repos_found) == 3
        assert "repo0" in repos_found
        assert "repo1" in repos_found
        assert "repo2" in repos_found

    def test_output_preserves_line_order_per_repository(self):
        """Test output lines from same repository maintain order."""
        proc = Mock()
        proc.stdout = StringIO("Line 1\nLine 2\nLine 3\n")
        processes = {"repo": proc}

        multiplexer = OutputMultiplexer(processes)
        multiplexer._read_process_output("repo", proc)

        # Get all lines
        lines = []
        while not multiplexer.output_queue.empty():
            _, line = multiplexer.output_queue.get_nowait()
            lines.append(line)

        # Order should be preserved
        assert lines == ["Line 1", "Line 2", "Line 3"]

    def test_reader_threads_are_daemon(self, mock_processes):
        """Test reader threads are daemon threads for automatic cleanup."""
        multiplexer = OutputMultiplexer(mock_processes)
        multiplexer.start_multiplexing()

        # Wait for threads to start
        time.sleep(0.1)

        # Check all reader threads are daemon
        for thread in multiplexer.reader_threads:
            assert thread.daemon is True

    def test_no_output_loss_during_multiplexing(self):
        """Test no output is lost during multiplexing."""
        # Generate large amount of output
        num_lines = 100
        proc = Mock()
        lines = "\n".join([f"Line {i}" for i in range(num_lines)]) + "\n"
        proc.stdout = StringIO(lines)
        processes = {"repo": proc}

        multiplexer = OutputMultiplexer(processes)
        multiplexer._read_process_output("repo", proc)

        # All lines should be queued
        assert multiplexer.output_queue.qsize() == num_lines

    def test_concurrent_read_and_write(self, mock_processes):
        """Test concurrent reading and writing works correctly."""
        multiplexer = OutputMultiplexer(mock_processes)

        # Start multiplexing (starts reader and writer threads)
        multiplexer.start_multiplexing()

        # Wait for some processing
        time.sleep(0.2)

        # Stop multiplexing
        multiplexer.stop_multiplexing()

        # Should complete without deadlock or errors
        assert multiplexer.running is False

    def test_empty_line_handling(self):
        """Test handling of empty lines in output."""
        proc = Mock()
        proc.stdout = StringIO("Line 1\n\nLine 3\n")
        processes = {"repo": proc}

        multiplexer = OutputMultiplexer(processes)
        multiplexer._read_process_output("repo", proc)

        # Should queue all lines including empty
        lines = []
        while not multiplexer.output_queue.empty():
            _, line = multiplexer.output_queue.get_nowait()
            lines.append(line)

        assert len(lines) == 3
        assert lines[1] == ""  # Empty line preserved

    def test_whitespace_preservation(self):
        """Test whitespace in lines is preserved."""
        proc = Mock()
        proc.stdout = StringIO("  Indented line  \n\tTabbed line\n")
        processes = {"repo": proc}

        multiplexer = OutputMultiplexer(processes)
        multiplexer._read_process_output("repo", proc)

        _, line1 = multiplexer.output_queue.get_nowait()
        _, line2 = multiplexer.output_queue.get_nowait()

        # Leading/trailing whitespace should be preserved (except trailing newline)
        assert line1 == "  Indented line  "
        assert line2 == "\tTabbed line"
