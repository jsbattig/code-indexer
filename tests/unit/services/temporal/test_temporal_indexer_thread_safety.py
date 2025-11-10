"""Test thread safety in temporal indexer progress reporting."""

import time
import threading
from unittest.mock import MagicMock, patch, Mock
from datetime import datetime


from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo
from src.code_indexer.services.temporal.models import CommitInfo
from src.code_indexer.config import ConfigManager
from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestTemporalIndexerThreadSafety:
    """Test thread safety of progress reporting in temporal indexer."""

    def test_progress_filenames_thread_safe(self, tmp_path):
        """Test that progress reporting shows correct filenames without race conditions.

        This test verifies that when multiple threads process different commits,
        each thread's progress report shows the correct filename from its own commit,
        not filenames from other threads due to shared state.
        """
        # Create test repository
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        (repo_path / ".git").mkdir()

        # Create config and vector store mocks
        config_manager = Mock(spec=ConfigManager)
        config = Mock()
        config.voyage_ai = Mock()
        config.voyage_ai.parallel_requests = 2
        config.voyage_ai.max_concurrent_batches_per_commit = 10  # Use 2 threads for the test
        config_manager.get_config.return_value = config

        vector_store = Mock(spec=FilesystemVectorStore)
        vector_store.project_root = repo_path
        vector_store.load_id_index.return_value = set()  # Return empty set for len() call

        # Create indexer with mocked dependencies
        with patch("src.code_indexer.services.temporal.temporal_indexer.TemporalDiffScanner") as mock_scanner, \
             patch("src.code_indexer.services.temporal.temporal_indexer.FileIdentifier") as mock_file_id, \
             patch("src.code_indexer.services.temporal.temporal_indexer.FixedSizeChunker") as mock_chunker, \
             patch("src.code_indexer.services.embedding_factory.EmbeddingProviderFactory") as mock_embed_factory, \
             patch("src.code_indexer.services.temporal.temporal_indexer.VectorCalculationManager") as mock_vector_mgr, \
             patch("subprocess.run") as mock_subprocess:

            # Setup mock scanner to return different files for different commits
            mock_scanner_instance = MagicMock()
            mock_scanner.return_value = mock_scanner_instance

            # Create distinct commits with unique files
            commits = []
            for i in range(10):  # More commits for better race detection
                # Use longer unique hashes that remain unique when truncated to 8 chars
                commits.append(CommitInfo(
                    hash=f"{i:08x}{'a' * 32}",  # e.g., "00000000aaaa...", "00000001aaaa..."
                    author_name=f"author{i}",
                    author_email=f"author{i}@test.com",
                    timestamp=int(datetime(2024, 1, 1, 10+i, 0, 0).timestamp()),
                    message=f"Commit {i}",
                    parent_hashes=""
                ))

            # Map commits to their unique files
            commit_files = {}
            for i, commit in enumerate(commits):
                # Each commit gets unique files to detect cross-contamination
                commit_files[commit.hash] = [
                    DiffInfo(
                        file_path=f"file_{i}_a.py",
                        diff_type="added",
                        commit_hash=commit.hash,
                        diff_content=f"+code for file {i} a",
                        old_path=""
                    ),
                    DiffInfo(
                        file_path=f"file_{i}_b.py",
                        diff_type="added",
                        commit_hash=commit.hash,
                        diff_content=f"+code for file {i} b",
                        old_path=""
                    )
                ]

            def get_diffs_side_effect(commit_hash):
                # Introduce delay to increase chance of race condition
                time.sleep(0.05)  # Increase delay for better chance of race
                return commit_files.get(commit_hash, [])

            mock_scanner_instance.get_commits.return_value = commits
            mock_scanner_instance.get_diffs_for_commit.side_effect = get_diffs_side_effect

            # Mock subprocess for git commands
            def subprocess_side_effect(*args, **kwargs):
                cmd = args[0] if args else kwargs.get('args', [])
                if cmd and cmd[0] == 'git':
                    if 'log' in cmd:
                        # Return commit info for git log
                        result = Mock()
                        lines = []
                        for commit in commits:
                            lines.append(f"{commit.hash}|{commit.timestamp}|{commit.author_name}|{commit.author_email}|{commit.message}|")
                        result.stdout = "\n".join(lines)
                        result.returncode = 0
                        return result
                    elif 'rev-parse' in cmd:
                        # Return branch name
                        result = Mock()
                        result.stdout = "main\n"
                        result.returncode = 0
                        return result
                # Default mock response
                result = Mock()
                result.stdout = ""
                result.returncode = 0
                return result

            mock_subprocess.side_effect = subprocess_side_effect

            # Setup mock file identifier
            mock_file_id_instance = MagicMock()
            mock_file_id.return_value = mock_file_id_instance
            mock_file_id_instance._get_project_id.return_value = "test-project-id"

            # Setup mock chunker
            mock_chunker_instance = MagicMock()
            mock_chunker.return_value = mock_chunker_instance
            # Return some chunks to trigger progress reporting
            mock_chunker_instance.chunk_text.return_value = [
                {"text": "chunk1", "char_start": 0, "char_end": 10}
            ]

            # Setup mock embedding factory
            mock_embed_provider = MagicMock()
            mock_embed_factory.create.return_value = mock_embed_provider

            # Setup mock vector manager
            mock_vector_mgr_instance = MagicMock()
            mock_vector_mgr.return_value = mock_vector_mgr_instance
            # Mock the submit_batch_task to return embeddings
            mock_future = MagicMock()
            mock_result = MagicMock()
            mock_result.embeddings = [[0.1] * 1536]  # Mock embedding vector
            mock_result.error = None  # No error
            mock_future.result.return_value = mock_result
            mock_vector_mgr_instance.submit_batch_task.return_value = mock_future

            # Mock vector store methods that will be called
            vector_store.list_collections.return_value = ["code-indexer-temporal"]
            vector_store.create_collection.return_value = None

            # Create indexer
            indexer = TemporalIndexer(
                config_manager=config_manager,
                vector_store=vector_store
            )

            # Track progress reports
            progress_reports = []
            progress_lock = threading.Lock()

            def progress_callback(current, total, file_path, info="", **kwargs):
                """Capture progress reports thread-safely.

                Accepts new kwargs for slot-based tracking (concurrent_files, slot_tracker, item_type)
                to maintain backward compatibility while supporting the deadlock fix.
                """
                with progress_lock:
                    # Extract commit hash and filename from info string
                    # Format: "X/Y commits (Z%) | A commits/s | B threads | 📝 HASH - filename"
                    if "📝" in info and " - " in info:
                        parts = info.split("📝")[1].strip()
                        if " - " in parts:
                            commit_hash = parts.split(" - ")[0].strip()
                            filename = parts.split(" - ")[1].strip()
                            progress_reports.append({
                                'commit_hash': commit_hash,
                                'filename': filename,
                                'file_path': str(file_path)
                            })

            # Index with multiple threads
            indexer.index_commits(
                all_branches=False,
                progress_callback=progress_callback
            )

            # Verify no cross-contamination between threads
            # Each commit should only show its own files in progress
            for i, commit in enumerate(commits):
                commit_reports = [r for r in progress_reports if r['commit_hash'] == commit.hash[:8]]
                expected_files = [f"file_{i}_a.py", f"file_{i}_b.py", "initializing"]

                # Check this commit only shows its own files
                for report in commit_reports:
                    assert report['filename'] in expected_files, \
                        f"Commit {commit.hash} showed wrong file: {report['filename']}, expected one of {expected_files}"

                    # Should never show other commits' files
                    for j, other_commit in enumerate(commits):
                        if i != j:
                            forbidden_files = [f"file_{j}_a.py", f"file_{j}_b.py"]
                            assert report['filename'] not in forbidden_files, \
                                f"Race condition detected: Commit {i} ({commit.hash}) showed file from commit {j}: {report['filename']}"