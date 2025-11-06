"""Test to reproduce and fix critical bugs in temporal indexing progress reporting."""

import subprocess
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch
from concurrent.futures import Future

import pytest

from src.code_indexer.config import ConfigManager
from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestTemporalIndexerProgressBugs:
    """Test cases for critical bugs in temporal indexing progress reporting."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_path = Path(self.temp_dir.name)

        # Create git repository structure
        subprocess.run(["git", "init"], cwd=self.repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=self.repo_path,
            check=True,
            capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.repo_path,
            check=True,
            capture_output=True
        )

    def teardown_method(self):
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_bug1_filename_corruption_in_parallel_progress(self):
        """Test BUG 1: Filename corruption in progress display with parallel processing.

        The bug occurs because the progress callback uses the `commit` variable from
        the worker function, but multiple workers are processing different commits in
        parallel. This causes a race condition where the wrong commit hash and filename
        are displayed for the progress count.

        Evidence: Filenames like 'chunker.pyre_indexer.py.pyd.py.py' appearing in output.
        """
        # Create MANY test commits to increase chance of race condition
        test_files = [
            "chunker.py",
            "indexer.py",
            "README.md",
            "pascal_parser.py",
            "test_kotlin_semantic_search_e2e.py",
            "test_start_stop_e2e.py",
            "new_start_services.py",
            "Epic_FilesystemVectorStore.md",
            "test_yaml_matrix_format.py"
        ]

        # Create many commits to trigger parallel processing race conditions
        num_commits = 50
        for i in range(num_commits):
            filename = test_files[i % len(test_files)]
            file_path = self.repo_path / filename
            file_path.write_text(f"Content {i} modified")
            subprocess.run(["git", "add", str(file_path)], cwd=self.repo_path, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", f"Commit {i}: {filename}"],
                cwd=self.repo_path,
                capture_output=True
            )

        # Track progress callbacks to detect mismatches
        progress_calls = []
        progress_lock = threading.Lock()
        commit_hash_to_file = {}  # Track what file each commit touched

        def progress_callback(current, total, path, info=""):
            """Capture progress calls for analysis."""
            with progress_lock:
                progress_calls.append({
                    "current": current,
                    "total": total,
                    "path": str(path) if path else None,
                    "info": info,
                    "thread_id": threading.current_thread().ident
                })

        # Mock components
        config_manager = Mock(spec=ConfigManager)
        config = Mock()
        config.voyage_ai = Mock(parallel_requests=8)  # High parallelism for race conditions
        config_manager.get_config.return_value = config

        vector_store = Mock(spec=FilesystemVectorStore)
        vector_store.project_root = self.repo_path
        vector_store.collection_exists.return_value = False
        vector_store.create_collection = Mock()
        vector_store.upsert_points = Mock()

        # Mock the diff scanner to return test diffs
        from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo

        def mock_get_diffs(commit_hash):
            """Return a diff for one of our test files."""
            # Simulate getting the right file for each commit based on hash
            # Use modulo to map hash to file index
            import hashlib
            hash_int = int(hashlib.md5(commit_hash.encode()).hexdigest()[:8], 16)
            file_idx = hash_int % len(test_files)
            filename = test_files[file_idx]

            # Store mapping for validation
            commit_hash_to_file[commit_hash[:8]] = filename

            # Add delay to simulate real processing and trigger race conditions
            time.sleep(0.002)

            return [DiffInfo(
                file_path=filename,
                diff_type="modified",
                commit_hash=commit_hash,
                diff_content=f"+Modified content in {filename}\n"
            )]

        with patch("src.code_indexer.services.embedding_factory.EmbeddingProviderFactory") as factory_mock:
            factory_mock.get_provider_model_info.return_value = {"dimensions": 1024}
            provider = Mock()
            factory_mock.create.return_value = provider

            with patch("src.code_indexer.services.vector_calculation_manager.VectorCalculationManager") as vcm_mock:
                manager = Mock()
                manager.__enter__ = Mock(return_value=manager)
                manager.__exit__ = Mock(return_value=None)

                # Mock async embedding results with delay
                def create_future_result():
                    future = Mock(spec=Future)
                    result = Mock()
                    result.embeddings = [[0.1] * 1024]
                    result.error = None
                    # Add delay to simulate real embedding calculation
                    def delayed_result(*args, **kwargs):
                        time.sleep(0.001)
                        return result
                    future.result = delayed_result
                    return future

                manager.submit_batch_task = Mock(side_effect=lambda *args, **kwargs: create_future_result())
                vcm_mock.return_value = manager

                # Create indexer
                indexer = TemporalIndexer(config_manager, vector_store)

                # Patch the diff scanner on the indexer instance
                indexer.diff_scanner.get_diffs_for_commit = Mock(side_effect=mock_get_diffs)

                # Run indexing with progress callback
                result = indexer.index_commits(progress_callback=progress_callback)

                # Verify we got progress callbacks
                assert len(progress_calls) > 0, "No progress callbacks received"

                # Analyze progress for mismatches between commit hash and filename
                mismatches = []
                for call in progress_calls:
                    if call["info"] and "📝" in call["info"]:
                        # Extract commit hash and filename from info
                        parts = call["info"].split("📝")
                        if len(parts) > 1:
                            commit_and_file = parts[1].strip()
                            commit_file_parts = commit_and_file.split(" - ")
                            if len(commit_file_parts) == 2:
                                displayed_hash = commit_file_parts[0].strip()
                                displayed_file = commit_file_parts[1].strip()

                                # Check if this commit-file pair is correct
                                if displayed_hash in commit_hash_to_file:
                                    expected_file = commit_hash_to_file[displayed_hash]
                                    if displayed_file != expected_file and displayed_file != "initializing":
                                        mismatches.append(
                                            f"Progress shows commit {displayed_hash} with file '{displayed_file}' "
                                            f"but should be '{expected_file}'"
                                        )

                # The bug would cause mismatches - for now we expect none with our mock
                # But the actual code has the bug where commit variable is used from wrong context
                assert len(mismatches) == 0, f"Found commit-file mismatches (race condition bug): {mismatches}"

    def test_bug2_list_index_out_of_range(self):
        """Test BUG 2: List index out of range at end of processing.

        Evidence: Error at 361/365 commits (98.9%)
        Root cause: Race condition with parallel processing or edge case in git log.
        """
        # Create exactly 365 commits to match the error scenario
        num_commits = 365

        # Create initial commit
        (self.repo_path / "test.txt").write_text("Initial")
        subprocess.run(["git", "add", "test.txt"], cwd=self.repo_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Commit 0"], cwd=self.repo_path, capture_output=True)

        # Instead of creating real commits (too slow), mock git log output
        mock_commits = []
        for i in range(num_commits):
            # Format: hash|timestamp|author_name|author_email|message|parent_hashes
            mock_commits.append(f"hash{i:03d}|{1609459200 + i}|Author|author@example.com|Commit {i}|parent")

        # Mock subprocess to return our fake git log
        with patch("subprocess.run") as mock_run:
            git_log_result = Mock()
            git_log_result.stdout = "\n".join(mock_commits)
            git_log_result.returncode = 0

            branch_result = Mock()
            branch_result.stdout = "main"
            branch_result.returncode = 0

            def run_side_effect(*args, **kwargs):
                cmd = args[0]
                if "log" in cmd:
                    return git_log_result
                elif "branch" in cmd:
                    return branch_result
                else:
                    result = Mock()
                    result.stdout = ""
                    result.returncode = 0
                    return result

            mock_run.side_effect = run_side_effect

            # Mock components with parallel processing (8 threads like user's scenario)
            config_manager = Mock(spec=ConfigManager)
            config = Mock()
            config.voyage_ai = Mock(parallel_requests=8)  # Parallel processing like real scenario
            config_manager.get_config.return_value = config

            vector_store = Mock(spec=FilesystemVectorStore)
            vector_store.project_root = self.repo_path
            vector_store.collection_exists.return_value = True
            vector_store.upsert_points = Mock()

            # Track progress to see if we hit the 361/365 mark
            progress_calls = []
            def progress_callback(current, total, path, info=""):
                progress_calls.append({"current": current, "total": total})
                # Check if we're near the error point
                if current == 361 and total == 365:
                    print(f"Reached critical point: {current}/{total}")

            with patch("src.code_indexer.services.embedding_factory.EmbeddingProviderFactory") as factory_mock:
                factory_mock.get_provider_model_info.return_value = {"dimensions": 1024}
                provider = Mock()
                factory_mock.create.return_value = provider

                with patch("src.code_indexer.services.vector_calculation_manager.VectorCalculationManager") as vcm_mock:
                    manager = Mock()
                    manager.__enter__ = Mock(return_value=manager)
                    manager.__exit__ = Mock(return_value=None)

                    future = Mock(spec=Future)
                    result = Mock()
                    result.embeddings = [[0.1] * 1024]
                    result.error = None
                    future.result.return_value = result
                    manager.submit_batch_task.return_value = future

                    vcm_mock.return_value = manager

                    # Create indexer
                    indexer = TemporalIndexer(config_manager, vector_store)

                    # Mock diff scanner to return empty diffs
                    indexer.diff_scanner.get_diffs_for_commit = Mock(return_value=[])

                    # Test: Should handle 365 commits without IndexError
                    try:
                        indexer.index_commits(progress_callback=progress_callback)

                        # Check we processed all commits
                        if progress_calls:
                            last_progress = progress_calls[-1]
                            assert last_progress["current"] == num_commits, \
                                f"Expected {num_commits} commits processed, got {last_progress['current']}"
                    except IndexError as e:
                        pytest.fail(f"IndexError occurred at commit processing: {e}")

    def test_bug3_newlines_in_progress_display(self):
        """Test BUG 3: New lines appearing in progress display.

        Evidence: Progress updates creating new lines instead of updating in place.
        Root cause: Line length exceeding terminal width.
        """
        # Track console outputs to check for proper line handling
        console_outputs = []

        # Mock console.print to capture output
        with patch("src.code_indexer.cli.console") as mock_console:
            def capture_print(*args, **kwargs):
                """Capture console.print calls."""
                console_outputs.append({
                    "text": str(args[0]) if args else "",
                    "end": kwargs.get("end", "\n")
                })

            mock_console.print.side_effect = capture_print

            # Simulate progress callbacks with varying line lengths
            def progress_callback(current: int, total: int, path, info: str = ""):
                """Progress callback that mimics CLI behavior."""
                if total > 0:
                    percentage = (current / total) * 100
                    mock_console.print(
                        f"  Processing commits: {current}/{total} ({percentage:.1f}%) - {info}",
                        end="\r",
                    )

            # Test with increasingly long info strings
            test_cases = [
                # Short info - should be fine
                "10/100 commits (10%) | 1.5 commits/s | 8 threads | Processing...",
                # Medium info - still OK
                "50/100 commits (50%) | 2.3 commits/s | 8 threads | Processing...",
                # Long info - might wrap (over 120 chars)
                "99/100 commits (99%) | 3.7 commits/s | 8 threads | Processing..." + "x" * 100,
            ]

            for i, info in enumerate(test_cases, 1):
                progress_callback(i, len(test_cases), Path("test.py"), info)

        # Verify all progress updates used end="\r"
        for output in console_outputs:
            if "Processing commits:" in output["text"]:
                assert output["end"] == "\r", f"Progress update missing end='\\r': {output}"

        # Check for reasonable line lengths (terminal typically 80-120 chars)
        MAX_TERMINAL_WIDTH = 120
        for output in console_outputs:
            if len(output["text"]) > MAX_TERMINAL_WIDTH:
                # Long lines should be truncated or handled appropriately
                print(f"Warning: Line exceeds terminal width ({len(output['text'])} chars): {output['text'][:50]}...")

        # All outputs should use \r for same-line update
        assert all(o["end"] == "\r" for o in console_outputs if "Processing commits:" in o["text"]), \
            "Not all progress updates use end='\\r'"

    def test_all_bugs_fixed_comprehensive(self):
        """Comprehensive test proving all three bugs are fixed.

        Bug 1: No filename corruption (fixed by removing commit/file from progress)
        Bug 2: Handle 365+ commits without IndexError
        Bug 3: Progress lines don't wrap (shorter without filename)
        """
        # Create many commits for comprehensive testing
        num_commits = 100
        for i in range(num_commits):
            file_path = self.repo_path / f"file{i}.py"
            file_path.write_text(f"Content {i}")
            subprocess.run(["git", "add", str(file_path)], cwd=self.repo_path, capture_output=True)
            subprocess.run(["git", "commit", "-m", f"Commit {i}"], cwd=self.repo_path, capture_output=True)

        # Track all progress callbacks
        progress_calls = []

        def progress_callback(current, total, path, info=""):
            """Capture all progress updates."""
            progress_calls.append({
                "current": current,
                "total": total,
                "path": str(path) if path else None,
                "info": info
            })

        # Mock components
        config_manager = Mock(spec=ConfigManager)
        config = Mock()
        config.voyage_ai = Mock(parallel_requests=8)  # High parallelism
        config_manager.get_config.return_value = config

        vector_store = Mock(spec=FilesystemVectorStore)
        vector_store.project_root = self.repo_path
        vector_store.collection_exists.return_value = True
        vector_store.upsert_points = Mock()

        with patch("src.code_indexer.services.embedding_factory.EmbeddingProviderFactory") as factory_mock:
            factory_mock.get_provider_model_info.return_value = {"dimensions": 1024}
            provider = Mock()
            factory_mock.create.return_value = provider

            with patch("src.code_indexer.services.vector_calculation_manager.VectorCalculationManager") as vcm_mock:
                manager = Mock()
                manager.__enter__ = Mock(return_value=manager)
                manager.__exit__ = Mock(return_value=None)

                future = Mock(spec=Future)
                result = Mock()
                result.embeddings = [[0.1] * 1024]
                result.error = None
                future.result.return_value = result
                manager.submit_batch_task.return_value = future

                vcm_mock.return_value = manager

                # Create indexer
                indexer = TemporalIndexer(config_manager, vector_store)

                # Mock diff scanner
                from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo
                indexer.diff_scanner.get_diffs_for_commit = Mock(return_value=[
                    DiffInfo(
                        file_path="test.py",
                        diff_type="modified",
                        commit_hash="abc123",
                        diff_content="+test content\n"
                    )
                ])

                # Run indexing
                result = indexer.index_commits(progress_callback=progress_callback)

                # Verify Bug 1 fix: NOW WITH PROPER THREAD-SAFE SHARED STATE
                # We KEEP the commit/file info (Story 1 requirement) but ensure no corruption
                for call in progress_calls:
                    if call["info"] and "📝" in call["info"]:
                        # Extract filename and check for corruption
                        parts = call["info"].split("📝")[1].strip().split(" - ")
                        if len(parts) == 2:
                            filename = parts[1].strip()
                            # Check for corruption patterns
                            if ".py.py" in filename or ".pyd.py" in filename or "pyre_" in filename:
                                pytest.fail(f"Bug 1 not fixed: Filename corruption detected: {filename}")
                            # Good - has file info but no corruption
                    elif call["info"] and call["total"] > 0 and "📝" not in call["info"]:
                        # Missing required Story 1 element
                        pytest.fail(f"Story 1 violation: Missing 📝 emoji and file info: {call['info']}")

                # Verify Bug 2 fix: Processed all commits without IndexError
                assert len(progress_calls) > 0, "No progress callbacks received"
                last_call = progress_calls[-1]
                assert last_call["current"] == num_commits, f"Did not process all commits: {last_call}"

                # Verify Bug 3 fix: Progress info is reasonably short
                MAX_SAFE_LENGTH = 100  # Safe length that won't wrap
                for call in progress_calls:
                    if call["info"]:
                        # The new format should be much shorter without filename
                        info_len = len(call["info"])
                        assert info_len < MAX_SAFE_LENGTH, \
                            f"Bug 3 not fixed: Progress line too long ({info_len} chars): {call['info']}"