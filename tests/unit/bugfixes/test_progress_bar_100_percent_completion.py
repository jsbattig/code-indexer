"""
Test to verify that the progress bar reaches 100% completion.

Story 1: Fix Progress Bar 100% Completion

The issue is that high_throughput_processor.py doesn't make a final
progress callback before returning, causing the Rich Progress bar to
stop at ~94% instead of reaching 100%.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock
import uuid

from code_indexer.services.high_throughput_processor import HighThroughputProcessor
from code_indexer.config import Config
from code_indexer.services import QdrantClient
from tests.unit.services.test_vector_calculation_manager import MockEmbeddingProvider
from tests.conftest import get_local_tmp_dir


class TestProgressBar100PercentCompletion:
    """Test that progress bar reaches 100% completion."""

    def setup_method(self):
        """Setup test environment."""
        # Create temporary directory
        self.temp_dir = str(get_local_tmp_dir() / f"test_{uuid.uuid4().hex[:8]}")
        self.temp_path = Path(self.temp_dir)
        self.temp_path.mkdir(parents=True, exist_ok=True)

        # Create test files
        self.test_files = []
        for i in range(3):  # Small number for controlled testing
            file_path = self.temp_path / f"test_file_{i}.py"
            content = f"""
def function_{i}():
    '''Function {i} with content for chunking.'''
    return "This is function {i} with content for testing."

class TestClass_{i}:
    '''Test class {i}'''
    
    def method_1(self):
        return "Method implementation"
    
    def method_2(self):
        return "Another method"
"""
            file_path.write_text(content)
            self.test_files.append(file_path)

        # Create mock config
        self.config = Mock(spec=Config)
        self.config.codebase_dir = self.temp_path
        self.config.exclude_dirs = []
        self.config.exclude_files = []
        self.config.file_extensions = ["py"]

        # Mock nested config attributes
        self.config.qdrant = Mock()
        self.config.qdrant.vector_size = 768

        self.config.indexing = Mock()
        self.config.indexing.chunk_size = 200
        self.config.indexing.overlap_size = 50
        self.config.indexing.max_file_size = 1000000
        self.config.indexing.min_file_size = 1

        self.config.chunking = Mock()
        self.config.chunking.chunk_size = 200
        self.config.chunking.overlap_size = 50

        # Mock Qdrant client
        self.mock_qdrant = Mock(spec=QdrantClient)
        self.mock_qdrant.upsert_points.return_value = True
        self.mock_qdrant.create_point.return_value = {"id": "test-point"}
        self.mock_qdrant.ensure_provider_aware_collection.return_value = (
            "test_collection"
        )
        self.mock_qdrant.clear_collection.return_value = True
        self.mock_qdrant.resolve_collection_name.return_value = "test_collection"
        self.mock_qdrant.collection_exists.return_value = True

        # Mock embedding provider
        self.mock_embedding_provider = MockEmbeddingProvider(delay=0.01)

    @pytest.mark.unit
    def test_progress_bar_missing_final_callback_demonstrates_problem(self):
        """Test that demonstrates the missing final callback problem (FAILING TEST)."""

        # Create processor
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
        )

        # Track all progress calls to analyze completion
        progress_calls = []
        final_call_received = False

        def track_progress_callback(current, total, file_path, error=None, info=None):
            nonlocal final_call_received

            progress_call = {
                "current": current,
                "total": total,
                "file_path": str(file_path),
                "info": info,
                "error": error,
            }
            progress_calls.append(progress_call)

            # Check if this is the final call (current == total)
            if total > 0 and current == total:
                final_call_received = True

            return None  # Don't cancel

        print(
            f"\n=== Testing progress bar completion with {len(self.test_files)} files ==="
        )

        # Process files and capture all progress calls
        stats = processor.process_files_high_throughput(
            files=self.test_files,
            vector_thread_count=2,
            batch_size=50,
            progress_callback=track_progress_callback,
        )

        # Verify processing succeeded
        assert stats.files_processed > 0, "Should have processed files successfully"
        assert stats.chunks_created > 0, "Should have created chunks"

        # Analyze progress calls
        file_progress_calls = [call for call in progress_calls if call["total"] > 0]

        print("\nProgress analysis:")
        print(f"  Total progress calls: {len(progress_calls)}")
        print(f"  File progress calls: {len(file_progress_calls)}")
        print(f"  Files processed: {stats.files_processed}")

        if file_progress_calls:
            last_call = file_progress_calls[-1]
            final_percentage = (
                (last_call["current"] / last_call["total"]) * 100
                if last_call["total"] > 0
                else 0
            )
            print(
                f"  Final progress call: {last_call['current']}/{last_call['total']} = {final_percentage:.1f}%"
            )
            print(f"  Final callback received: {final_call_received}")

            # This is the FAILING assertion that demonstrates the problem
            assert final_call_received, (
                f"Expected final progress callback with current==total, but last call was "
                f"{last_call['current']}/{last_call['total']} ({final_percentage:.1f}%). "
                f"Progress bar will stop at {final_percentage:.1f}% instead of 100%."
            )
        else:
            assert False, "No file progress calls were made!"

    @pytest.mark.unit
    def test_rich_progress_bar_simulation_shows_incomplete_percentage(self):
        """Test that simulates Rich Progress bar behavior and shows the incomplete percentage."""

        # Create processor
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
        )

        # Simulate Rich Progress bar behavior exactly like CLI
        mock_progress_bar = Mock()
        mock_task_id = "test-task"
        update_calls = []

        def track_update(task_id, **kwargs):
            update_calls.append(kwargs)

        mock_progress_bar.update.side_effect = track_update
        mock_progress_bar.add_task.return_value = mock_task_id

        total_files = len(self.test_files)

        def simulate_cli_progress_callback(
            current, total, file_path, error=None, info=None
        ):
            """Simulate the exact CLI progress callback behavior."""
            # This mirrors the CLI logic in cli.py:1595-1626

            # Handle setup messages (total=0) - just return, no progress update
            if info and total == 0:
                return

            # Handle file progress (total>0)
            if total > 0 and info:
                # This is the key line: CLI updates progress bar with current/total
                mock_progress_bar.update(
                    mock_task_id, completed=current, description=info
                )
                return

            return None

        print(f"\n=== Simulating CLI Rich Progress Bar with {total_files} files ===")

        # Process files using simulated CLI progress callback
        stats = processor.process_files_high_throughput(
            files=self.test_files,
            vector_thread_count=2,
            batch_size=50,
            progress_callback=simulate_cli_progress_callback,
        )

        # Verify processing succeeded
        assert stats.files_processed > 0, "Should have processed files successfully"
        assert len(update_calls) > 0, "Should have made progress bar update calls"

        # Analyze final Rich Progress bar state
        last_update = update_calls[-1]
        final_completed = last_update.get("completed", 0)
        final_percentage = (
            (final_completed / total_files) * 100 if total_files > 0 else 0
        )

        print("\nRich Progress Bar Analysis:")
        print(f"  Total files: {total_files}")
        print(f"  Files processed: {stats.files_processed}")
        print(f"  Progress bar updates: {len(update_calls)}")
        print(f"  Final progress bar 'completed': {final_completed}")
        print(f"  Final progress bar percentage: {final_percentage:.1f}%")

        # This test demonstrates the problem: progress bar stops before 100%
        if final_percentage < 100:
            print(
                f"  ❌ PROBLEM DEMONSTRATED: Progress bar stops at {final_percentage:.1f}% instead of 100%"
            )

        # This is the FAILING assertion that will pass after we implement the fix
        assert final_percentage == 100.0, (
            f"Expected Rich Progress bar to reach 100%, but it stopped at {final_percentage:.1f}%. "
            f"This demonstrates the missing final progress callback issue. "
            f"completed={final_completed}, total={total_files}"
        )

    @pytest.mark.unit
    def test_final_progress_callback_format_requirements(self):
        """Test requirements for the final progress callback format."""

        # Create processor
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
        )

        # Track progress calls to verify final callback format
        progress_calls = []

        def analyze_progress_callback(current, total, file_path, error=None, info=None):
            progress_calls.append(
                {
                    "current": current,
                    "total": total,
                    "file_path": str(file_path),
                    "info": info,
                    "timestamp": len(progress_calls) + 1,
                }
            )
            return None

        # Process files
        processor.process_files_high_throughput(
            files=self.test_files,
            vector_thread_count=2,
            batch_size=50,
            progress_callback=analyze_progress_callback,
        )

        # Find the final progress call (should be current == total)
        file_progress_calls = [call for call in progress_calls if call["total"] > 0]

        if file_progress_calls:
            final_call = file_progress_calls[-1]

            # Verify final call has proper format for CLI
            print("\nFinal progress call analysis:")
            print(f"  current: {final_call['current']}")
            print(f"  total: {final_call['total']}")
            print(f"  info: {final_call['info']}")

            # The final call should have current == total for 100% completion
            assert final_call["current"] == final_call["total"], (
                f"Final progress callback should have current==total for 100% completion, "
                f"but got {final_call['current']}/{final_call['total']}"
            )

            # The final call should include completion info
            assert (
                final_call["info"] is not None
            ), "Final progress callback should include info"
            assert "✅ Completed" in final_call["info"], (
                f"Final progress callback should include '✅ Completed' in info, "
                f"but got: {final_call['info']}"
            )
        else:
            assert False, "No file progress calls were made!"

    def teardown_method(self):
        """Cleanup test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-s"])  # -s to show print statements
