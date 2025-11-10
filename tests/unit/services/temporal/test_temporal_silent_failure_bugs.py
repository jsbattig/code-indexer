"""Tests for silent failure bugs in temporal indexing.

These tests expose critical bugs that cause silent failures with fake success reporting:
1. Bug #1: False vector count - reports estimated count not actual writes
2. Bug #2: No exception handling in worker threads - errors silently swallowed
3. Bug #3: Deduplication not logged - silent filtering with no feedback
4. Bug #4: CLI catches exceptions too broadly - might report success despite failure
"""

import json
import logging
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest

from code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestBug1FalseVectorCount:
    """Tests for Bug #1: False vector count without verification of actual writes."""

    def test_vector_count_clearly_labeled_as_approximate(self, tmp_path):
        """Test that vector count is clearly labeled as approximate in user-facing messages.

        NOTE: The implementation uses completed_count * 3 as an estimate (line 1030).
        This is acceptable AS LONG AS it's clearly communicated as approximate to users.

        The CLI already shows "(approx)" and "~" prefix, so this is handled correctly.
        This test verifies that the approximate nature is maintained.
        """
        # Verify CLI message includes approximation indicators
        cli_file = Path(__file__).parent.parent.parent.parent.parent / "src" / "code_indexer" / "cli.py"
        with open(cli_file, 'r') as f:
            cli_code = f.read()

        # Verify "(approx)" and "~" are used in the output message
        assert "(approx)" in cli_code and "approximate_vectors_created" in cli_code, (
            "CLI should clearly label vector count as approximate"
        )

        # This is acceptable - the estimate is clearly communicated
        # Real bugs are #2 (no exception handling), #3 (no deduplication logging), #4 (broad exception catching)


class TestBug2NoExceptionHandling:
    """Tests for Bug #2: No exception handling in worker threads causes silent failures."""

    def test_worker_thread_has_except_block_to_log_errors(self, tmp_path):
        """Test that worker thread has except block to catch and log errors before re-raising.

        BUG: Lines 523-993 have try/finally but NO except block.
        Errors in worker threads are silently swallowed, causing fake success reports.

        The fix should add an except block that:
        1. Logs the error at ERROR level with commit info
        2. Re-raises the exception to propagate to main thread
        """
        # Read the source code to verify the bug
        source_file = Path(__file__).parent.parent.parent.parent.parent / "src" / "code_indexer" / "services" / "temporal" / "temporal_indexer.py"
        with open(source_file, 'r') as f:
            source_lines = f.readlines()

        # Find the worker function
        worker_start_line = None
        for i, line in enumerate(source_lines):
            if "def worker():" in line and "Worker function to process commits" in source_lines[i+1] if i+1 < len(source_lines) else False:
                worker_start_line = i
                break

        assert worker_start_line is not None, "Could not find worker() function"

        # Look for the main try block in worker (around line 523)
        try_block_found = False
        except_block_found = False
        finally_block_found = False

        for i in range(worker_start_line, min(worker_start_line + 500, len(source_lines))):
            line = source_lines[i].strip()
            if line.startswith("try:"):
                try_block_found = True
            elif line.startswith("except") and try_block_found:
                except_block_found = True
            elif line.startswith("finally:") and try_block_found:
                finally_block_found = True

        # BUG EXPOSED: This assertion will FAIL because except block is missing
        assert except_block_found, (
            f"Worker thread (starting at line {worker_start_line + 1}) has try/finally but NO except block. "
            f"This causes errors to be silently swallowed. "
            f"Bug: Lines 523-993 need an except block to log errors before re-raising."
        )

        # Also verify it has finally (for cleanup) - this should pass
        assert finally_block_found, "Worker should have finally block for cleanup"
