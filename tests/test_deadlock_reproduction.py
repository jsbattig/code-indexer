"""
Test to reproduce deadlock in incremental indexing on deleted files.

This test specifically targets deadlock conditions where the verification
retry logic gets stuck in an infinite wait, never completing.

Key deadlock scenarios to test:
1. Verification method gets stuck waiting for Qdrant response
2. Retry loop continues indefinitely because verification never succeeds
3. Race conditions between deletion and verification
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


class TestDeadlockReproduction:
    """Test class to reproduce deadlock in deletion handling."""

    @pytest.fixture(autouse=True)
    def setup_test_environment(self):
        """Setup test environment with aggressive setup strategy."""
        # AGGRESSIVE SETUP: Use test infrastructure for consistent setup
        self.service_manager, self.cli_helper, self.dir_manager = create_fast_e2e_setup(
            EmbeddingProvider.VOYAGE_AI
        )
        self.test_repo_dir: Optional[Path] = None

        # AGGRESSIVE SETUP: Ensure services and clean state
        print("🔧 Aggressive setup: Ensuring services and clean state...")
        services_ready = self.service_manager.ensure_services_ready()
        if not services_ready:
            pytest.skip("Could not ensure services are ready for E2E testing")

        # AGGRESSIVE SETUP: Clean all existing data first
        print("🧹 Aggressive setup: Cleaning all existing project data...")
        self._cleanup_all_data()

        # AGGRESSIVE SETUP: Verify services are actually working after cleanup
        print("🔍 Aggressive setup: Verifying services are functional...")
        try:
            # Test with a minimal project directory to verify services work
            test_setup_dir = Path(__file__).parent / "deadlock_setup_verification"
            test_setup_dir.mkdir(exist_ok=True)
            (test_setup_dir / "test.py").write_text("def test(): pass")

            # Initialize and verify basic functionality works
            init_result = self.cli_helper.run_cli_command(
                ["init", "--force", "--embedding-provider", "voyage-ai"],
                cwd=test_setup_dir,
                timeout=60,
            )
            if init_result.returncode != 0:
                print(f"Setup verification failed during init: {init_result.stderr}")
                pytest.skip("Services not functioning properly for E2E testing")

            # Start services
            start_result = self.cli_helper.run_cli_command(
                ["start", "--quiet"], cwd=test_setup_dir, timeout=120
            )
            if start_result.returncode != 0:
                print(f"Setup verification failed during start: {start_result.stderr}")
                pytest.skip("Could not start services for E2E testing")

            # Clean up verification directory
            try:
                import shutil

                shutil.rmtree(test_setup_dir, ignore_errors=True)
            except Exception:
                pass

            print("✅ Aggressive setup complete - services verified functional")

        except Exception as e:
            print(f"Setup verification failed: {e}")
            pytest.skip("Could not verify service functionality for E2E testing")

        yield

        # Cleanup after test - only clean project data, keep services running
        try:
            self._cleanup_all_data()
        except Exception as e:
            print(f"Warning: Cleanup failed: {e}")

    def _cleanup_all_data(self):
        """Clean all project data to ensure clean test state."""
        try:
            # Use clean-data command to clean all projects
            cleanup_result = self.cli_helper.run_cli_command(
                ["clean-data", "--all-projects"], timeout=60, expect_success=False
            )
            if cleanup_result.returncode != 0:
                print(f"Cleanup warning (non-fatal): {cleanup_result.stderr}")
        except Exception as e:
            print(f"Cleanup warning (non-fatal): {e}")

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

        # Create files that might cause issues during deletion
        files_to_create = [
            (
                "main.py",
                "def main():\n    print('Hello World')\n\nif __name__ == '__main__':\n    main()",
            ),
            (
                "utils.py",
                "def helper_function():\n    return 'helper'\n\ndef another_helper():\n    return 'another'",
            ),
            (
                "config.py",
                "DATABASE_URL = 'sqlite:///app.db'\nDEBUG = True\nSECRET_KEY = 'dev-key'",
            ),
            (
                "models.py",
                "class User:\n    def __init__(self, name):\n        self.name = name\n\nclass Product:\n    def __init__(self, name, price):\n        self.name = name\n        self.price = price",
            ),
            (
                "views.py",
                "def index():\n    return 'Index page'\n\ndef about():\n    return 'About page'",
            ),
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

    def run_with_aggressive_timeout(
        self, command: list, timeout_seconds: int = 10
    ) -> dict:
        """Run command with aggressive timeout to catch deadlocks quickly."""
        start_time = time.time()

        try:
            result = subprocess.run(
                ["code-indexer"] + command,
                cwd=self.test_repo_dir,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
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

    @pytest.mark.slow
    def test_deadlock_with_aggressive_timeout(self, tmp_path):
        """
        Test for deadlock with very aggressive timeout.

        This test uses a short timeout to quickly detect if the process
        gets stuck in an infinite wait condition.
        """
        print("\n💀 Testing for deadlock with aggressive 10-second timeout")

        # Setup test repository
        self.test_repo_dir = self.create_git_repo_with_files(tmp_path)
        print(f"✅ Created test git repository at: {self.test_repo_dir}")

        # Services are already verified as working in aggressive setup
        # Initialize this specific project
        init_result = self.cli_helper.run_cli_command(
            ["init", "--embedding-provider", "voyage-ai"],
            cwd=self.test_repo_dir,
            timeout=30,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Perform initial indexing
        initial_index_result = self.cli_helper.run_cli_command(
            ["index"], cwd=self.test_repo_dir, timeout=60
        )
        assert (
            initial_index_result.returncode == 0
        ), f"Initial indexing failed: {initial_index_result.stderr}"
        print("✅ Initial indexing completed")

        # Delete multiple files to trigger potential deadlock
        print("🗑️  Deleting multiple files...")
        files_to_delete = ["utils.py", "models.py", "views.py"]

        for file_path in files_to_delete:
            full_path = self.test_repo_dir / file_path
            if full_path.exists():
                full_path.unlink()
                print(f"   Deleted: {file_path}")

        # Commit deletions
        subprocess.run(
            ["git", "add", "."], cwd=self.test_repo_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Delete files to trigger deadlock"],
            cwd=self.test_repo_dir,
            check=True,
            capture_output=True,
        )

        # Run incremental indexing with aggressive timeout to catch deadlock
        print("⏱️  Running incremental indexing with 10-second timeout...")
        print("   If this times out, we've reproduced the deadlock!")

        deadlock_result = self.run_with_aggressive_timeout(
            ["index", "--detect-deletions"],
            timeout_seconds=10,  # Very aggressive timeout
        )

        # Analyze results
        print("\n📊 Deadlock test results:")
        print(f"   Success: {deadlock_result['success']}")
        print(f"   Duration: {deadlock_result['duration']:.2f}s")
        print(f"   Timed out: {deadlock_result['timed_out']}")
        print(f"   Return code: {deadlock_result['returncode']}")

        if deadlock_result["stdout"]:
            print(f"   Last stdout: {deadlock_result['stdout'][-300:]}")
        if deadlock_result["stderr"]:
            print(f"   Last stderr: {deadlock_result['stderr'][-300:]}")

        if deadlock_result["timed_out"]:
            print("🎯 DEADLOCK REPRODUCED!")
            print(f"   Process hung for {deadlock_result['timeout_seconds']}+ seconds")
            print("   This confirms the reported deadlock issue exists.")

            # This assertion should fail when deadlock is reproduced
            pytest.fail(
                f"DEADLOCK DETECTED: Incremental indexing hung for {deadlock_result['timeout_seconds']}+ seconds. "
                f"Last output: {deadlock_result['stdout'][-200:] if deadlock_result['stdout'] else 'No output'}"
            )
        else:
            print("✅ No deadlock detected - indexing completed normally")
            assert deadlock_result[
                "success"
            ], f"Indexing failed: {deadlock_result['stderr']}"
            assert (
                deadlock_result["returncode"] == 0
            ), f"Indexing returned error: {deadlock_result['returncode']}"

    @pytest.mark.slow
    def test_repeated_deletion_cycles_for_deadlock(self, tmp_path):
        """
        Test repeated deletion cycles to trigger race conditions.

        This test runs multiple deletion cycles rapidly to increase
        the chance of hitting race conditions that cause deadlock.
        """
        print("\n🔄 Testing repeated deletion cycles for deadlock")

        # Setup test repository
        self.test_repo_dir = self.create_git_repo_with_files(tmp_path)

        # Services are already verified as working in aggressive setup
        # Initialize this specific project
        init_result = self.cli_helper.run_cli_command(
            ["init", "--embedding-provider", "voyage-ai"],
            cwd=self.test_repo_dir,
            timeout=30,
        )
        assert init_result.returncode == 0

        # Perform initial indexing
        initial_index_result = self.cli_helper.run_cli_command(
            ["index"], cwd=self.test_repo_dir, timeout=60
        )
        assert initial_index_result.returncode == 0
        print("✅ Initial indexing completed")

        # Run multiple rapid deletion cycles
        for cycle in range(3):
            print(f"\n🔄 Deletion cycle {cycle + 1}/3")

            # Create and delete different files each cycle
            test_files = [
                f"temp_{cycle}_a.py",
                f"temp_{cycle}_b.py",
                f"temp_{cycle}_c.py",
            ]

            # Create files
            for file_name in test_files:
                full_path = self.test_repo_dir / file_name
                full_path.write_text(f"# Temporary file {file_name}\ndata = {cycle}")

            # Index the new files
            subprocess.run(
                ["git", "add", "."],
                cwd=self.test_repo_dir,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", f"Add cycle {cycle} files"],
                cwd=self.test_repo_dir,
                check=True,
                capture_output=True,
            )

            add_result = self.run_with_aggressive_timeout(["index"], timeout_seconds=15)
            if add_result["timed_out"]:
                pytest.fail(f"Deadlock during file addition in cycle {cycle + 1}")

            # Delete files
            for file_name in test_files:
                full_path = self.test_repo_dir / file_name
                if full_path.exists():
                    full_path.unlink()

            subprocess.run(
                ["git", "add", "."],
                cwd=self.test_repo_dir,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", f"Delete cycle {cycle} files"],
                cwd=self.test_repo_dir,
                check=True,
                capture_output=True,
            )

            # Test deletion with aggressive timeout
            delete_result = self.run_with_aggressive_timeout(
                ["index", "--detect-deletions"], timeout_seconds=15
            )

            print(f"   Cycle {cycle + 1} duration: {delete_result['duration']:.2f}s")

            if delete_result["timed_out"]:
                print(f"🎯 DEADLOCK REPRODUCED in cycle {cycle + 1}!")
                pytest.fail(
                    f"DEADLOCK in deletion cycle {cycle + 1}: "
                    f"Process hung for {delete_result['timeout_seconds']}+ seconds"
                )

        print("✅ All deletion cycles completed without deadlock")

    @pytest.mark.slow
    def test_concurrent_operations_deadlock(self, tmp_path):
        """
        Test concurrent operations that might trigger deadlock.

        This test simulates conditions where multiple operations
        might interfere with each other and cause deadlock.
        """
        print("\n⚡ Testing concurrent operations for deadlock")

        # Setup test repository
        self.test_repo_dir = self.create_git_repo_with_files(tmp_path)

        # Services are already verified as working in aggressive setup
        # Initialize this specific project
        init_result = self.cli_helper.run_cli_command(
            ["init", "--embedding-provider", "voyage-ai"],
            cwd=self.test_repo_dir,
            timeout=30,
        )
        assert init_result.returncode == 0

        # Perform initial indexing
        initial_index_result = self.cli_helper.run_cli_command(
            ["index"], cwd=self.test_repo_dir, timeout=60
        )
        assert initial_index_result.returncode == 0

        # Delete files
        files_to_delete = ["utils.py", "models.py"]
        for file_path in files_to_delete:
            full_path = self.test_repo_dir / file_path
            if full_path.exists():
                full_path.unlink()

        subprocess.run(
            ["git", "add", "."], cwd=self.test_repo_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Delete files for concurrent test"],
            cwd=self.test_repo_dir,
            check=True,
            capture_output=True,
        )

        # Run deletion detection multiple times rapidly to create race conditions
        print("🏃 Running rapid consecutive deletion detection...")

        for i in range(3):
            print(f"   Rapid run {i + 1}/3")
            rapid_result = self.run_with_aggressive_timeout(
                ["index", "--detect-deletions"],
                timeout_seconds=8,  # Even more aggressive timeout
            )

            if rapid_result["timed_out"]:
                print(f"🎯 DEADLOCK REPRODUCED in rapid run {i + 1}!")
                pytest.fail(
                    f"DEADLOCK in rapid deletion detection run {i + 1}: "
                    f"Process hung for {rapid_result['timeout_seconds']}+ seconds"
                )

            print(f"   Run {i + 1} completed in {rapid_result['duration']:.2f}s")

            # Small delay between runs
            time.sleep(0.5)

        print("✅ Concurrent operations test completed without deadlock")

    @pytest.mark.slow
    def test_specific_verification_deadlock(self, tmp_path):
        """
        Test specifically targeting the verification retry deadlock.

        This test tries to create conditions where the verification
        method gets stuck in an infinite retry loop.
        """
        print("\n🔍 Testing verification retry deadlock scenario")

        # Setup with a larger number of files to increase verification complexity
        self.test_repo_dir = self.create_git_repo_with_files(tmp_path)

        # Create additional files to make verification more complex
        for i in range(15):  # Create 15 additional files
            file_path = f"extra_{i:02d}.py"
            content = f"# Extra file {i}\ndef function_{i}():\n    return {i}\n\nclass Class{i}:\n    value = {i}"
            full_path = self.test_repo_dir / file_path
            full_path.write_text(content)

        subprocess.run(
            ["git", "add", "."], cwd=self.test_repo_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Add extra files"],
            cwd=self.test_repo_dir,
            check=True,
            capture_output=True,
        )

        # Services are already verified as working in aggressive setup
        # Initialize this specific project
        init_result = self.cli_helper.run_cli_command(
            ["init", "--embedding-provider", "voyage-ai"],
            cwd=self.test_repo_dir,
            timeout=30,
        )
        assert init_result.returncode == 0

        # Perform initial indexing
        initial_index_result = self.cli_helper.run_cli_command(
            ["index"], cwd=self.test_repo_dir, timeout=120
        )
        assert initial_index_result.returncode == 0
        print("✅ Initial indexing with extra files completed")

        # Delete many files at once to stress the verification system
        files_to_delete = ["utils.py", "models.py", "views.py"] + [
            f"extra_{i:02d}.py" for i in range(0, 15, 2)
        ]

        print(f"🗑️  Deleting {len(files_to_delete)} files to stress verification...")
        for file_path in files_to_delete:
            full_path = self.test_repo_dir / file_path
            if full_path.exists():
                full_path.unlink()

        subprocess.run(
            ["git", "add", "."], cwd=self.test_repo_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", f"Delete {len(files_to_delete)} files"],
            cwd=self.test_repo_dir,
            check=True,
            capture_output=True,
        )

        # Run deletion detection with very aggressive timeout
        print("⏱️  Running deletion detection with 12-second timeout...")
        verification_result = self.run_with_aggressive_timeout(
            ["index", "--detect-deletions"], timeout_seconds=12
        )

        print("\n📊 Verification deadlock test results:")
        print(f"   Files deleted: {len(files_to_delete)}")
        print(f"   Duration: {verification_result['duration']:.2f}s")
        print(f"   Timed out: {verification_result['timed_out']}")

        if verification_result["timed_out"]:
            print("🎯 VERIFICATION DEADLOCK REPRODUCED!")
            print(
                f"   Process hung during verification of {len(files_to_delete)} deletions"
            )

            pytest.fail(
                f"VERIFICATION DEADLOCK: Process hung for {verification_result['timeout_seconds']}+ seconds "
                f"while verifying {len(files_to_delete)} deletions. "
                f"This confirms the verification retry deadlock issue."
            )
        else:
            print("✅ Verification completed without deadlock")
            assert verification_result[
                "success"
            ], f"Verification failed: {verification_result['stderr']}"
