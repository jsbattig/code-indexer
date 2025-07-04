"""
Test to reproduce stuck incremental indexing behavior on deleted files.

This test specifically targets the issue where incremental indexing gets stuck
when processing deleted files due to excessive verification retries.

Test Scenario:
1. Create git repo with initial files
2. Index the repository
3. Add new files and delete existing files
4. Run incremental indexing with timeout to detect stuck behavior
5. Verify indexing completes within reasonable time
"""

import time
import subprocess
from pathlib import Path
from typing import Optional
import pytest

from .test_infrastructure import (
    create_fast_e2e_setup,
    EmbeddingProvider,
)
from .test_suite_setup import register_test_collection


class TestStuckIncrementalIndexing:
    """Test class to reproduce stuck incremental indexing on deleted files."""

    def setup_method(self):
        """Setup test environment."""
        self.service_manager, self.cli_helper, self.dir_manager = create_fast_e2e_setup(
            EmbeddingProvider.OLLAMA
        )
        self.test_repo_dir: Optional[Path] = None
        self.collection_name = "stuck_indexing_test"

        # Register collection for cleanup
        register_test_collection(self.collection_name)

    def teardown_method(self):
        """Cleanup test environment."""
        if self.service_manager:
            self.service_manager.cleanup_project_data()

    def create_git_repo_with_files(self, base_dir: Path) -> Path:
        """Create a git repository with initial files."""
        repo_dir = base_dir / "test_repo"
        repo_dir.mkdir(exist_ok=True)

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_dir,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True
        )

        # Create initial files
        files_to_create = [
            (
                "src/main.py",
                "def main():\n    print('Hello World')\n\nif __name__ == '__main__':\n    main()",
            ),
            (
                "src/utils.py",
                "def helper_function():\n    return 'helper'\n\ndef another_helper():\n    return 'another'",
            ),
            (
                "src/config.py",
                "DATABASE_URL = 'sqlite:///app.db'\nDEBUG = True\nSECRET_KEY = 'dev-key'",
            ),
            (
                "docs/readme.md",
                "# Test Project\n\nThis is a test project for indexing.",
            ),
            (
                "docs/api.md",
                "# API Documentation\n\n## Endpoints\n\n- GET /health\n- POST /data",
            ),
            (
                "tests/test_main.py",
                "import unittest\n\nclass TestMain(unittest.TestCase):\n    def test_something(self):\n        self.assertTrue(True)",
            ),
        ]

        for file_path, content in files_to_create:
            full_path = repo_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)

        # Commit initial files
        subprocess.run(
            ["git", "add", "."], cwd=repo_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        return repo_dir

    def run_indexing_with_timeout(
        self, command: list, timeout_seconds: int = 30
    ) -> dict:
        """Run indexing command with timeout to detect stuck behavior."""
        start_time = time.time()

        try:
            result = self.cli_helper.run_cli_command(
                command, cwd=self.test_repo_dir, timeout=timeout_seconds
            )
            end_time = time.time()
            duration = end_time - start_time

            return {
                "success": True,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "duration": duration,
                "timed_out": False,
            }

        except subprocess.TimeoutExpired as e:
            end_time = time.time()
            duration = end_time - start_time

            return {
                "success": False,
                "returncode": -1,
                "stdout": e.stdout.decode() if e.stdout else "",
                "stderr": e.stderr.decode() if e.stderr else "",
                "duration": duration,
                "timed_out": True,
                "timeout_seconds": timeout_seconds,
            }

    def get_collection_stats(self) -> dict:
        """Get Qdrant collection statistics."""
        try:
            result = self.cli_helper.run_cli_command(
                ["status"], cwd=self.test_repo_dir, timeout=10
            )

            if result.returncode == 0:
                # Parse basic info from status output
                lines = result.stdout.strip().split("\n")
                stats = {}
                for line in lines:
                    if "points" in line.lower():
                        stats["info"] = line.strip()
                return stats
            else:
                return {"error": result.stderr}

        except Exception as e:
            return {"error": str(e)}

    @pytest.mark.slow
    def test_stuck_incremental_indexing_on_deleted_files(self, tmp_path):
        """
        Test that reproduces stuck incremental indexing when processing deleted files.

        This test should fail initially, demonstrating the stuck behavior,
        then pass after we fix the verification retry logic.
        """
        print("\n🚀 Starting stuck incremental indexing reproduction test")

        # Setup test repository
        self.test_repo_dir = self.create_git_repo_with_files(tmp_path)
        print(f"✅ Created test git repository at: {self.test_repo_dir}")

        # Initialize code-indexer
        print("🔧 Initializing code-indexer...")
        init_result = self.cli_helper.run_cli_command(
            ["init", "--embedding-provider", "ollama"],
            cwd=self.test_repo_dir,
            timeout=30,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Start services
        print("🚀 Starting services...")
        start_result = self.cli_helper.run_cli_command(
            ["start"], cwd=self.test_repo_dir, timeout=60
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

        # Perform initial indexing
        print("📋 Performing initial indexing...")
        initial_index_result = self.run_indexing_with_timeout(
            ["index"], timeout_seconds=60
        )
        assert initial_index_result[
            "success"
        ], f"Initial indexing failed: {initial_index_result}"
        assert (
            initial_index_result["returncode"] == 0
        ), f"Initial indexing error: {initial_index_result['stderr']}"

        print(
            f"✅ Initial indexing completed in {initial_index_result['duration']:.2f}s"
        )

        # Get initial stats
        initial_stats = self.get_collection_stats()
        print(f"📊 Initial collection stats: {initial_stats}")

        # Add new files
        print("📝 Adding new files...")
        new_files = [
            (
                "src/models.py",
                "class User:\n    def __init__(self, name):\n        self.name = name",
            ),
            (
                "src/views.py",
                "def render_template(template, context):\n    return f'{template}: {context}'",
            ),
            (
                "libs/helpers.py",
                "def format_date(date):\n    return date.strftime('%Y-%m-%d')",
            ),
        ]

        for file_path, content in new_files:
            full_path = self.test_repo_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)

        # Delete existing files (this should trigger the stuck behavior)
        print("🗑️  Deleting existing files...")
        files_to_delete = ["src/utils.py", "docs/api.md", "tests/test_main.py"]

        for file_path in files_to_delete:
            full_path = self.test_repo_dir / file_path
            if full_path.exists():
                full_path.unlink()
                print(f"   Deleted: {file_path}")

        # Commit changes to git
        subprocess.run(
            ["git", "add", "."], cwd=self.test_repo_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Add new files and delete old ones"],
            cwd=self.test_repo_dir,
            check=True,
            capture_output=True,
        )

        # Run incremental indexing with --detect-deletions (this is where it should get stuck)
        print("🔄 Running incremental indexing with deletion detection...")
        print("   This should reproduce the stuck behavior on deleted files...")

        incremental_result = self.run_indexing_with_timeout(
            ["index", "--detect-deletions"],
            timeout_seconds=30,  # 30 second timeout to catch stuck behavior
        )

        # Analyze results
        print("\n📊 Incremental indexing results:")
        print(f"   Success: {incremental_result['success']}")
        print(f"   Duration: {incremental_result['duration']:.2f}s")
        print(f"   Timed out: {incremental_result['timed_out']}")
        print(f"   Return code: {incremental_result['returncode']}")

        if incremental_result["stdout"]:
            print(f"   Stdout: {incremental_result['stdout'][-500:]}")  # Last 500 chars
        if incremental_result["stderr"]:
            print(f"   Stderr: {incremental_result['stderr'][-500:]}")  # Last 500 chars

        # Get final stats
        final_stats = self.get_collection_stats()
        print(f"📊 Final collection stats: {final_stats}")

        # Assertions to validate the test
        if incremental_result["timed_out"]:
            print(
                "❌ REPRODUCTION SUCCESSFUL: Indexing got stuck processing deleted files!"
            )
            print(
                f"   Indexing timed out after {incremental_result['timeout_seconds']}s"
            )
            print("   This confirms the reported issue exists.")

            # This assertion should initially fail, proving we reproduced the issue
            pytest.fail(
                f"Incremental indexing got stuck on deleted files. "
                f"Timed out after {incremental_result['timeout_seconds']}s. "
                f"Last output: {incremental_result['stdout'][-200:] if incremental_result['stdout'] else 'No output'}"
            )
        else:
            # If it doesn't timeout, it should complete successfully and quickly
            print("✅ Indexing completed without getting stuck")
            assert incremental_result[
                "success"
            ], f"Indexing failed: {incremental_result['stderr']}"
            assert (
                incremental_result["returncode"] == 0
            ), f"Indexing returned error code: {incremental_result['returncode']}"

            # Should complete reasonably quickly (less than 15 seconds for this small test)
            assert (
                incremental_result["duration"] < 15
            ), f"Indexing took too long: {incremental_result['duration']}s"

            print(
                f"✅ Test passed - indexing completed in {incremental_result['duration']:.2f}s"
            )

    @pytest.mark.slow
    def test_deletion_handling_performance_benchmark(self, tmp_path):
        """
        Benchmark test to measure deletion handling performance.

        This test creates many files, deletes many of them, and measures
        how long incremental indexing takes to process the deletions.
        """
        print("\n📊 Starting deletion handling performance benchmark")

        # Setup test repository
        self.test_repo_dir = self.create_git_repo_with_files(tmp_path)

        # Create many more files for performance testing
        print("📝 Creating additional files for performance testing...")
        for i in range(20):  # Create 20 additional files
            file_path = f"perf_test/file_{i:03d}.py"
            content = f"# Performance test file {i}\n\ndef function_{i}():\n    return {i}\n\nclass Class{i}:\n    def method(self):\n        return 'method_{i}'"
            full_path = self.test_repo_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)

        # Commit the additional files
        subprocess.run(
            ["git", "add", "."], cwd=self.test_repo_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Add performance test files"],
            cwd=self.test_repo_dir,
            check=True,
            capture_output=True,
        )

        # Initialize and index
        init_result = self.cli_helper.run_cli_command(
            ["init", "--embedding-provider", "ollama"],
            cwd=self.test_repo_dir,
            timeout=30,
        )
        assert init_result.returncode == 0

        start_result = self.cli_helper.run_cli_command(
            ["start"], cwd=self.test_repo_dir, timeout=60
        )
        assert start_result.returncode == 0

        initial_index_result = self.run_indexing_with_timeout(
            ["index"], timeout_seconds=90
        )
        assert initial_index_result["success"]

        # Delete many files (this should stress test the deletion handling)
        print("🗑️  Deleting multiple files...")
        files_to_delete = []
        for i in range(0, 20, 2):  # Delete every other file (10 files total)
            file_path = f"perf_test/file_{i:03d}.py"
            files_to_delete.append(file_path)
            full_path = self.test_repo_dir / file_path
            if full_path.exists():
                full_path.unlink()

        # Also delete some original files
        original_deletes = ["src/utils.py", "docs/api.md"]
        for file_path in original_deletes:
            full_path = self.test_repo_dir / file_path
            if full_path.exists():
                full_path.unlink()
                files_to_delete.append(file_path)

        subprocess.run(
            ["git", "add", "."], cwd=self.test_repo_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Delete multiple files for performance test"],
            cwd=self.test_repo_dir,
            check=True,
            capture_output=True,
        )

        print(f"📊 Deleted {len(files_to_delete)} files total")

        # Run incremental indexing and measure performance
        print("⏱️  Running performance benchmark...")
        benchmark_result = self.run_indexing_with_timeout(
            ["index", "--detect-deletions"],
            timeout_seconds=60,  # 60 second timeout for performance test
        )

        print("\n📊 Performance benchmark results:")
        print(f"   Files deleted: {len(files_to_delete)}")
        print(f"   Duration: {benchmark_result['duration']:.2f}s")
        print(
            f"   Avg time per deletion: {benchmark_result['duration']/len(files_to_delete):.2f}s"
        )
        print(f"   Timed out: {benchmark_result['timed_out']}")

        if benchmark_result["timed_out"]:
            pytest.fail(
                f"Performance benchmark failed: indexing timed out after 60s when processing {len(files_to_delete)} deletions. "
                f"Average time per deletion would be > {60/len(files_to_delete):.2f}s, which is too slow."
            )

        # Performance assertions
        assert benchmark_result[
            "success"
        ], f"Benchmark failed: {benchmark_result['stderr']}"

        # Should handle deletions reasonably quickly - less than 2 seconds per file on average
        max_time_per_deletion = 2.0
        actual_time_per_deletion = benchmark_result["duration"] / len(files_to_delete)

        assert actual_time_per_deletion < max_time_per_deletion, (
            f"Deletion handling too slow: {actual_time_per_deletion:.2f}s per file "
            f"(limit: {max_time_per_deletion}s per file)"
        )

        print(
            f"✅ Performance benchmark passed: {actual_time_per_deletion:.2f}s per deletion"
        )
