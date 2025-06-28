"""
Test to reproduce stuck behavior specifically in the verification retry logic.

This test targets the specific issue where verification retries cause stuck behavior
when processing deleted files, particularly in watch mode scenarios.
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


class TestStuckVerificationRetry:
    """Test class to reproduce stuck verification retry behavior."""

    def setup_method(self):
        """Setup test environment."""
        self.service_manager, self.cli_helper, self.dir_manager = create_fast_e2e_setup(
            EmbeddingProvider.OLLAMA
        )
        self.test_repo_dir: Optional[Path] = None
        self.watch_process: Optional[subprocess.Popen] = None

    def teardown_method(self):
        """Cleanup test environment."""
        if self.watch_process and self.watch_process.poll() is None:
            self.watch_process.terminate()
            try:
                self.watch_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.watch_process.kill()

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
            ("main.py", "print('Hello World')"),
            ("config.py", "DEBUG = True"),
            ("utils.py", "def helper(): return 'helper'"),
        ]

        for file_path, content in files_to_create:
            full_path = repo_dir / file_path
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

    def start_watch_mode(self) -> subprocess.Popen:
        """Start watch mode in background."""
        cmd = ["code-indexer", "watch"]
        process = subprocess.Popen(
            cmd,
            cwd=self.test_repo_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Give watch mode a moment to start
        time.sleep(2)
        return process

    def simulate_slow_qdrant_response(self):
        """
        Simulate slow Qdrant response by potentially overloading the system.
        This could trigger the verification retry timeouts.
        """
        # This is a placeholder - in real scenarios, the slow response might be
        # due to network latency, Qdrant being busy, or other factors
        pass

    @pytest.mark.slow
    def test_watch_mode_deletion_with_verification_retry(self, tmp_path):
        """
        Test watch mode deletion handling with verification retry logic.

        This test focuses on the specific scenario where watch mode processes
        deleted files and gets stuck in verification retry loops.
        """
        print("\n🎯 Testing watch mode deletion with verification retry")

        # Setup test repository
        self.test_repo_dir = self.create_git_repo_with_files(tmp_path)
        print(f"✅ Created test git repository at: {self.test_repo_dir}")

        # Initialize code-indexer
        init_result = self.cli_helper.run_cli_command(
            ["init", "--embedding-provider", "ollama"],
            cwd=self.test_repo_dir,
            timeout=30,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Start services
        start_result = self.cli_helper.run_cli_command(
            ["start"], cwd=self.test_repo_dir, timeout=60
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

        # Perform initial indexing
        initial_index_result = self.cli_helper.run_cli_command(
            ["index"], cwd=self.test_repo_dir, timeout=60
        )
        assert (
            initial_index_result.returncode == 0
        ), f"Initial indexing failed: {initial_index_result.stderr}"
        print("✅ Initial indexing completed")

        # Start watch mode
        print("🔍 Starting watch mode...")
        self.watch_process = self.start_watch_mode()

        # Verify watch mode started
        time.sleep(3)
        if self.watch_process.poll() is not None:
            stdout, stderr = self.watch_process.communicate()
            pytest.fail(f"Watch mode failed to start: {stderr}")

        print("✅ Watch mode started successfully")

        # Now delete files while watch mode is running
        print("🗑️  Deleting files while watch mode is active...")
        files_to_delete = ["utils.py", "config.py"]

        for file_path in files_to_delete:
            full_path = self.test_repo_dir / file_path
            if full_path.exists():
                full_path.unlink()
                print(f"   Deleted: {file_path}")

                # Give watch mode time to detect and process the deletion
                # This is where the verification retry logic should trigger
                time.sleep(2)

        # Commit deletions
        subprocess.run(
            ["git", "add", "."], cwd=self.test_repo_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Delete files in watch mode"],
            cwd=self.test_repo_dir,
            check=True,
            capture_output=True,
        )

        # Monitor watch mode output for a period to see if it gets stuck
        print("⏱️  Monitoring watch mode for stuck behavior...")
        monitor_duration = 15  # Monitor for 15 seconds
        start_time = time.time()

        while time.time() - start_time < monitor_duration:
            if self.watch_process.poll() is not None:
                # Watch mode exited
                stdout, stderr = self.watch_process.communicate()
                print(f"Watch mode exited unexpectedly: {stderr}")
                break

            # Check for output that might indicate stuck behavior
            # This is a simplified check - in real scenarios we'd need more sophisticated monitoring
            time.sleep(1)

        # Terminate watch mode
        print("🛑 Terminating watch mode...")
        self.watch_process.terminate()

        try:
            stdout, stderr = self.watch_process.communicate(timeout=5)
            print(f"Watch mode output: {stdout[-500:] if stdout else 'No stdout'}")
            if stderr:
                print(f"Watch mode errors: {stderr[-500:]}")
        except subprocess.TimeoutExpired:
            print("⚠️  Watch mode didn't terminate gracefully, killing...")
            self.watch_process.kill()
            stdout, stderr = self.watch_process.communicate()

        # Verify that deletions were processed correctly
        print("🔍 Verifying deletion processing...")
        query_result = self.cli_helper.run_cli_command(
            ["query", "helper function"], cwd=self.test_repo_dir, timeout=10
        )

        if query_result.returncode == 0:
            # Check if deleted files still appear in results
            for deleted_file in files_to_delete:
                if deleted_file in query_result.stdout:
                    print(
                        f"⚠️  Deleted file {deleted_file} still appears in query results"
                    )
                    print(f"Query output: {query_result.stdout}")
                else:
                    print(f"✅ Deleted file {deleted_file} properly removed from index")

        print("✅ Watch mode deletion test completed")

    @pytest.mark.slow
    def test_direct_verification_retry_behavior(self, tmp_path):
        """
        Test the verification retry behavior directly by calling internal methods.

        This test attempts to reproduce the stuck behavior by directly testing
        the verification retry logic that might be causing the issue.
        """
        print("\n🔬 Testing direct verification retry behavior")

        # Setup test repository
        self.test_repo_dir = self.create_git_repo_with_files(tmp_path)

        # Initialize and start services
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

        # Perform initial indexing
        initial_index_result = self.cli_helper.run_cli_command(
            ["index"], cwd=self.test_repo_dir, timeout=60
        )
        assert initial_index_result.returncode == 0

        # Delete a file
        file_to_delete = "utils.py"
        full_path = self.test_repo_dir / file_to_delete
        full_path.unlink()

        # Commit the deletion
        subprocess.run(
            ["git", "add", "."], cwd=self.test_repo_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Delete file for verification test"],
            cwd=self.test_repo_dir,
            check=True,
            capture_output=True,
        )

        # Now try to trigger the verification retry logic by using incremental indexing
        # with deletion detection multiple times in quick succession
        print("🔄 Running multiple deletion detection cycles...")

        for i in range(3):
            print(f"   Cycle {i+1}/3")
            start_time = time.time()

            result = self.cli_helper.run_cli_command(
                ["index", "--detect-deletions"], cwd=self.test_repo_dir, timeout=30
            )

            duration = time.time() - start_time
            print(f"   Duration: {duration:.2f}s")

            if result.returncode != 0:
                print(f"   Error: {result.stderr}")
            else:
                print(
                    f"   Success: {result.stdout[-200:] if result.stdout else 'No output'}"
                )

            # Check if any cycle takes significantly longer (indicating stuck behavior)
            if duration > 10:  # If any cycle takes more than 10 seconds
                pytest.fail(
                    f"Deletion detection cycle {i+1} took too long: {duration:.2f}s"
                )

        print("✅ Direct verification retry test completed")

    @pytest.mark.slow
    def test_performance_with_many_deletions(self, tmp_path):
        """
        Test performance impact of verification retry logic with many deletions.

        This test creates many files, deletes them, and measures if the verification
        retry logic causes performance degradation.
        """
        print("\n📊 Testing performance impact with many deletions")

        # Setup test repository
        self.test_repo_dir = self.create_git_repo_with_files(tmp_path)

        # Create many additional files
        print("📝 Creating many files...")
        for i in range(50):  # Create 50 files
            file_path = f"file_{i:03d}.py"
            content = f"# File {i}\ndef function_{i}(): return {i}"
            full_path = self.test_repo_dir / file_path
            full_path.write_text(content)

        # Commit all files
        subprocess.run(
            ["git", "add", "."], cwd=self.test_repo_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Add many files"],
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

        initial_index_result = self.cli_helper.run_cli_command(
            ["index"], cwd=self.test_repo_dir, timeout=120
        )
        assert initial_index_result.returncode == 0
        print("✅ Initial indexing of many files completed")

        # Delete many files
        print("🗑️  Deleting many files...")
        deleted_count = 0
        for i in range(0, 50, 2):  # Delete every other file
            file_path = f"file_{i:03d}.py"
            full_path = self.test_repo_dir / file_path
            if full_path.exists():
                full_path.unlink()
                deleted_count += 1

        # Also delete original files
        for file_path in ["utils.py", "config.py"]:
            full_path = self.test_repo_dir / file_path
            if full_path.exists():
                full_path.unlink()
                deleted_count += 1

        subprocess.run(
            ["git", "add", "."], cwd=self.test_repo_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", f"Delete {deleted_count} files"],
            cwd=self.test_repo_dir,
            check=True,
            capture_output=True,
        )

        print(f"📊 Deleted {deleted_count} files")

        # Measure deletion detection performance
        print("⏱️  Measuring deletion detection performance...")
        start_time = time.time()

        deletion_result = self.cli_helper.run_cli_command(
            ["index", "--detect-deletions"],
            cwd=self.test_repo_dir,
            timeout=120,  # 2 minute timeout
        )

        duration = time.time() - start_time

        print("📊 Deletion detection results:")
        print(f"   Files deleted: {deleted_count}")
        print(f"   Total duration: {duration:.2f}s")
        print(f"   Average per deletion: {duration/deleted_count:.2f}s")
        print(f"   Success: {deletion_result.returncode == 0}")

        if deletion_result.returncode != 0:
            print(f"   Error: {deletion_result.stderr}")

        # Performance assertion
        max_time_per_deletion = 3.0  # 3 seconds per deletion should be reasonable
        avg_time_per_deletion = duration / deleted_count

        if avg_time_per_deletion > max_time_per_deletion:
            print(
                f"❌ Performance issue detected: {avg_time_per_deletion:.2f}s per deletion"
            )
            print("   This suggests the verification retry logic may be causing delays")

            # This would be the failing assertion that proves the performance issue
            pytest.fail(
                f"Deletion processing too slow: {avg_time_per_deletion:.2f}s per file "
                f"(limit: {max_time_per_deletion}s per file). "
                f"This indicates the verification retry logic is causing performance issues."
            )
        else:
            print(
                f"✅ Performance acceptable: {avg_time_per_deletion:.2f}s per deletion"
            )

        print("✅ Performance test completed")
