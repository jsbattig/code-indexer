"""Test ensuring Story 1 Acceptance Criteria are maintained for temporal indexing progress.

CRITICAL: Story 1 requires ALL 7 elements in progress display:
1. current/total commits
2. percentage
3. commits/s rate
4. thread count
5. 📝 emoji
6. commit hash (8 chars)
7. filename being processed

This test ensures we NEVER violate these requirements while fixing bugs.
"""

import subprocess
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch
from concurrent.futures import Future


from src.code_indexer.config import ConfigManager
from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestTemporalIndexerStory1AcceptanceCriteria:
    """Test that Story 1 acceptance criteria are maintained."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_path = Path(self.temp_dir.name)

        # Create git repository structure
        subprocess.run(
            ["git", "init"], cwd=self.repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
        )

    def teardown_method(self):
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_progress_display_has_all_required_elements(self):
        """Test that progress display includes ALL 7 required elements from Story 1 AC.

        Required format:
        "{current}/{total} commits ({pct}%) | {rate} commits/s | {threads} threads | 📝 {commit_hash} - {file}"

        ALL elements are mandatory per Story 1 acceptance criteria.
        """
        # Create test commits
        test_files = ["file1.py", "file2.js", "file3.md"]
        for i, filename in enumerate(test_files):
            file_path = self.repo_path / filename
            file_path.write_text(f"Content {i}")
            subprocess.run(
                ["git", "add", str(file_path)], cwd=self.repo_path, capture_output=True
            )
            subprocess.run(
                ["git", "commit", "-m", f"Commit {i}: {filename}"],
                cwd=self.repo_path,
                capture_output=True,
            )

        # Track progress callbacks
        progress_calls = []

        def progress_callback(current, total, path, info=""):
            """Capture progress calls for validation."""
            progress_calls.append(
                {
                    "current": current,
                    "total": total,
                    "path": str(path) if path else None,
                    "info": info,
                }
            )

        # Mock components
        config_manager = Mock(spec=ConfigManager)
        config = Mock()
        config.voyage_ai = Mock(
            parallel_requests=4, max_concurrent_batches_per_commit=10
        )
        config_manager.get_config.return_value = config

        vector_store = Mock(spec=FilesystemVectorStore)
        vector_store.project_root = self.repo_path
        vector_store.collection_exists.return_value = True
        vector_store.upsert_points = Mock()
        vector_store.load_id_index.return_value = (
            set()
        )  # Return empty set for len() call

        # Mock diff scanner to return test diffs
        from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo

        def mock_get_diffs(commit_hash):
            """Return a diff with proper file."""
            # Use hash to determine which file
            file_idx = int(commit_hash[:1], 16) % len(test_files)
            return [
                DiffInfo(
                    file_path=test_files[file_idx],
                    diff_type="modified",
                    commit_hash=commit_hash,
                    diff_content=f"+Modified {test_files[file_idx]}\n",
                )
            ]

        with patch(
            "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory"
        ) as factory_mock:
            factory_mock.get_provider_model_info.return_value = {"dimensions": 1024}
            provider = Mock()
            factory_mock.create.return_value = provider

            with patch(
                "src.code_indexer.services.vector_calculation_manager.VectorCalculationManager"
            ) as vcm_mock:
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
                indexer.diff_scanner.get_diffs_for_commit = Mock(
                    side_effect=mock_get_diffs
                )

                # Run indexing
                result = indexer.index_commits(progress_callback=progress_callback)

                # Validate ALL progress callbacks have required elements
                assert len(progress_calls) > 0, "No progress callbacks received"

                for call in progress_calls:
                    if call["info"] and call["total"] > 0:  # Skip setup messages
                        info = call["info"]

                        # Check for ALL 7 required elements
                        # 1. Current/total commits
                        assert "/" in info, f"Missing current/total separator: {info}"
                        assert "commits" in info, f"Missing 'commits' word: {info}"

                        # 2. Percentage
                        assert "%" in info, f"Missing percentage: {info}"

                        # 3. Commits/s rate
                        assert "commits/s" in info, f"Missing commits/s rate: {info}"

                        # 4. Thread count
                        assert "threads" in info, f"Missing thread count: {info}"

                        # 5. 📝 emoji (CRITICAL - Story 1 requirement)
                        assert (
                            "📝" in info
                        ), f"Missing 📝 emoji (Story 1 AC violation): {info}"

                        # 6 & 7. Commit hash and filename
                        if "📝" in info:
                            parts = info.split("📝")
                            if len(parts) > 1:
                                commit_file_part = parts[1].strip()
                                # Should have format: "hash - filename"
                                assert (
                                    " - " in commit_file_part
                                ), f"Missing 'hash - file' format after 📝: {info}"

                                hash_file = commit_file_part.split(" - ")
                                if len(hash_file) == 2:
                                    commit_hash = hash_file[0].strip()
                                    filename = hash_file[1].strip()

                                    # Hash should be 8 chars (or placeholder)
                                    assert (
                                        len(commit_hash) >= 8
                                    ), f"Commit hash too short: {commit_hash} in {info}"

                                    # Filename should be present (not "Processing...")
                                    assert filename not in [
                                        "Processing...",
                                        "",
                                    ], f"Missing actual filename (Story 1 violation): {info}"

    def test_thread_safe_progress_no_corruption(self):
        """Test that shared state approach fixes race conditions and filename corruption."""

        # Create many commits to trigger parallel processing
        num_commits = 50
        test_files = [
            "chunker.py",
            "indexer.py",
            "test_start_stop_e2e.py",
            "pascal_parser.py",
            "README.md",
        ]

        for i in range(num_commits):
            filename = test_files[i % len(test_files)]
            file_path = self.repo_path / filename
            file_path.write_text(f"Content iteration {i}")
            subprocess.run(
                ["git", "add", str(file_path)], cwd=self.repo_path, capture_output=True
            )
            subprocess.run(
                ["git", "commit", "-m", f"Commit {i}"],
                cwd=self.repo_path,
                capture_output=True,
            )

        # Track progress to verify thread safety
        progress_calls = []
        seen_hashes = set()
        seen_files = set()
        corruption_detected = []

        def progress_callback(current, total, path, info=""):
            """Track progress and detect corruption."""
            progress_calls.append(
                {
                    "current": current,
                    "total": total,
                    "info": info,
                    "thread_id": threading.current_thread().ident,
                }
            )

            # Extract hash and file from info
            if "📝" in info:
                parts = info.split("📝")[1].strip().split(" - ")
                if len(parts) == 2:
                    hash_val = parts[0].strip()
                    file_val = parts[1].strip()
                    seen_hashes.add(hash_val)
                    seen_files.add(file_val)

                    # Check for corruption patterns
                    corruption_patterns = [
                        ".py.py",
                        ".pyd.py",
                        "pyre_",
                        "walking",
                        ".pyalking",
                        ".pyypy",
                    ]
                    for pattern in corruption_patterns:
                        if pattern in file_val:
                            corruption_detected.append(f"Corrupted: {file_val}")

        # Mock components with parallel processing
        config_manager = Mock(spec=ConfigManager)
        config = Mock()
        config.voyage_ai = Mock(
            parallel_requests=8, max_concurrent_batches_per_commit=10
        )  # High parallelism to trigger races
        config_manager.get_config.return_value = config

        vector_store = Mock(spec=FilesystemVectorStore)
        vector_store.project_root = self.repo_path
        vector_store.collection_exists.return_value = True
        vector_store.upsert_points = Mock()
        vector_store.load_id_index.return_value = (
            set()
        )  # Return empty set for len() call

        # Mock diff scanner with delays to simulate real processing
        from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo

        def mock_get_diffs(commit_hash):
            """Return diff with delay to simulate processing."""
            time.sleep(0.002)  # Small delay to trigger race conditions
            file_idx = abs(hash(commit_hash)) % len(test_files)
            return [
                DiffInfo(
                    file_path=test_files[file_idx],
                    diff_type="modified",
                    commit_hash=commit_hash,
                    diff_content="+Modified line\n",
                )
            ]

        with patch(
            "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory"
        ) as factory_mock:
            factory_mock.get_provider_model_info.return_value = {"dimensions": 1024}
            provider = Mock()
            factory_mock.create.return_value = provider

            with patch(
                "src.code_indexer.services.vector_calculation_manager.VectorCalculationManager"
            ) as vcm_mock:
                manager = Mock()
                manager.__enter__ = Mock(return_value=manager)
                manager.__exit__ = Mock(return_value=None)

                # Mock async results with delay
                def create_future():
                    future = Mock(spec=Future)
                    result = Mock()
                    result.embeddings = [[0.1] * 1024]
                    result.error = None

                    def delayed_result(*args, **kwargs):
                        time.sleep(0.001)
                        return result

                    future.result = delayed_result
                    return future

                manager.submit_batch_task = Mock(
                    side_effect=lambda *args, **kwargs: create_future()
                )
                vcm_mock.return_value = manager

                # Create indexer
                indexer = TemporalIndexer(config_manager, vector_store)
                indexer.diff_scanner.get_diffs_for_commit = Mock(
                    side_effect=mock_get_diffs
                )

                # Run indexing
                indexer.index_commits(progress_callback=progress_callback)

                # Verify no corruption
                assert (
                    len(corruption_detected) == 0
                ), f"Filename corruption detected: {corruption_detected}"

                # Verify thread safety - saw multiple different values
                assert len(seen_hashes) > 1, f"Only saw hash: {seen_hashes}"
                assert len(seen_files) > 1, f"Only saw files: {seen_files}"

                # Verify valid filenames seen
                for filename in seen_files:
                    if filename != "initializing":
                        # Should be one of our test files
                        assert filename in test_files, f"Unexpected file: {filename}"

    def test_no_index_error_at_365_commits(self):
        """Test that we handle 365+ commits without IndexError (Bug 2 fix)."""

        # Mock git log to return exactly 365 commits (the problematic count)
        num_commits = 365
        mock_commits = []
        for i in range(num_commits):
            mock_commits.append(
                f"hash{i:03d}|{1609459200 + i}|Author|test@example.com|Commit {i}|parent"
            )

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

            # Track progress
            progress_calls = []
            error_occurred = False
            critical_point_info = None

            def progress_callback(current, total, path, info=""):
                """Track progress and catch errors."""
                try:
                    progress_calls.append(
                        {"current": current, "total": total, "info": info}
                    )

                    # Capture info at the critical 361/365 point where bug occurred
                    if current == 361 and total == 365:
                        nonlocal critical_point_info
                        critical_point_info = info

                except IndexError:
                    nonlocal error_occurred
                    error_occurred = True
                    raise

            # Mock components
            config_manager = Mock(spec=ConfigManager)
            config = Mock()
            config.voyage_ai = Mock(
                parallel_requests=8, max_concurrent_batches_per_commit=10
            )
            config_manager.get_config.return_value = config

            vector_store = Mock(spec=FilesystemVectorStore)
            vector_store.project_root = self.repo_path
            vector_store.collection_exists.return_value = True
            vector_store.upsert_points = Mock()
            vector_store.load_id_index.return_value = (
                set()
            )  # Return empty set for len() call

            with patch(
                "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory"
            ) as factory_mock:
                factory_mock.get_provider_model_info.return_value = {"dimensions": 1024}
                provider = Mock()
                factory_mock.create.return_value = provider

                with patch(
                    "src.code_indexer.services.vector_calculation_manager.VectorCalculationManager"
                ) as vcm_mock:
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
                    from src.code_indexer.services.temporal.temporal_diff_scanner import (
                        DiffInfo,
                    )

                    indexer.diff_scanner.get_diffs_for_commit = Mock(
                        return_value=[
                            DiffInfo(
                                file_path="test.py",
                                diff_type="modified",
                                commit_hash="abc123",
                                diff_content="+test\n",
                            )
                        ]
                    )

                    # Run indexing - should NOT raise IndexError
                    result = indexer.index_commits(progress_callback=progress_callback)

                    # Verify no errors
                    assert not error_occurred, "IndexError occurred during processing"
                    assert len(progress_calls) > 0, "No progress received"

                    # Check we processed all commits
                    last_call = progress_calls[-1]
                    assert (
                        last_call["current"] == num_commits
                    ), f"Did not process all {num_commits} commits: {last_call}"

                    # Verify Story 1 elements present even at critical 361/365 point
                    if critical_point_info:
                        assert (
                            "📝" in critical_point_info
                        ), f"Missing emoji at critical point 361/365: {critical_point_info}"
                        assert (
                            "361/365" in critical_point_info
                        ), f"Wrong count at critical point: {critical_point_info}"

                    # Verify final progress has all elements
                    if last_call["info"]:
                        assert (
                            "📝" in last_call["info"]
                        ), "Final progress missing required emoji"
                        assert (
                            f"{num_commits}/{num_commits}" in last_call["info"]
                        ), f"Final count wrong: {last_call['info']}"
