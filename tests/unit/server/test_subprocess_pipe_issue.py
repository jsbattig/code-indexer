"""
Test to confirm subprocess pipe buffer issue.
"""

import subprocess
import time
import json
import sys


import pytest


@pytest.mark.e2e
class TestSubprocessPipeIssue:
    """Test subprocess pipe buffer issues."""

    def test_server_with_pipes_vs_without_pipes(self, tmp_path):
        """Test server startup with and without subprocess pipes."""
        server_dir = tmp_path / "test-server"
        server_dir.mkdir()

        # Create valid configuration
        config = {"server_dir": str(server_dir), "host": "127.0.0.1", "port": 9002}

        config_file = server_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        cmd = [
            sys.executable,
            "-m",
            "code_indexer.server.main",
            "--host",
            "127.0.0.1",
            "--port",
            "9002",
        ]

        print("Testing server with PIPES (like ServerLifecycleManager)...")

        # Test 1: With pipes (problematic approach)
        process_with_pipes = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

        print(f"Process with pipes PID: {process_with_pipes.pid}")

        # Give it time to start
        time.sleep(3)

        # Check if it's still running
        poll_result = process_with_pipes.poll()
        print(f"Process with pipes poll result: {poll_result}")

        if poll_result is not None:
            stdout, stderr = process_with_pipes.communicate()
            print(f"Process with pipes died with code: {poll_result}")
            print(f"STDOUT: {stdout.decode()[:500]}...")
            print(f"STDERR: {stderr.decode()[:500]}...")

        # Clean up
        if process_with_pipes.poll() is None:
            process_with_pipes.terminate()
            process_with_pipes.wait(timeout=5)

        print("\nTesting server WITHOUT pipes (better approach)...")

        # Test 2: Without pipes (better approach)
        process_without_pipes = subprocess.Popen(
            cmd,
            stdout=None,  # Inherit parent's stdout
            stderr=None,  # Inherit parent's stderr
            start_new_session=True,
        )

        print(f"Process without pipes PID: {process_without_pipes.pid}")

        # Give it time to start
        time.sleep(3)

        # Check if it's still running
        poll_result = process_without_pipes.poll()
        print(f"Process without pipes poll result: {poll_result}")

        # This should still be running
        assert (
            poll_result is None
        ), f"Process without pipes died with code: {poll_result}"

        # Wait a bit longer to be sure
        time.sleep(5)
        poll_result = process_without_pipes.poll()
        print(f"Process without pipes poll result after 8 seconds: {poll_result}")

        assert (
            poll_result is None
        ), f"Process without pipes died after 8 seconds with code: {poll_result}"

        # Clean up
        process_without_pipes.terminate()
        process_without_pipes.wait(timeout=10)

        print("Test completed successfully!")

    def test_server_with_devnull_pipes(self, tmp_path):
        """Test server startup with pipes redirected to devnull."""
        server_dir = tmp_path / "test-server"
        server_dir.mkdir()

        # Create valid configuration
        config = {"server_dir": str(server_dir), "host": "127.0.0.1", "port": 9003}

        config_file = server_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        cmd = [
            sys.executable,
            "-m",
            "code_indexer.server.main",
            "--host",
            "127.0.0.1",
            "--port",
            "9003",
        ]

        print("Testing server with DEVNULL pipes...")

        # Test with pipes redirected to devnull
        with open("/dev/null", "w") as devnull:
            process_devnull = subprocess.Popen(
                cmd,
                stdout=devnull,
                stderr=devnull,
                start_new_session=True,
            )

        print(f"Process with devnull PID: {process_devnull.pid}")

        # Give it time to start
        time.sleep(3)

        # Check if it's still running
        poll_result = process_devnull.poll()
        print(f"Process with devnull poll result: {poll_result}")

        assert (
            poll_result is None
        ), f"Process with devnull died with code: {poll_result}"

        # Wait longer
        time.sleep(5)
        poll_result = process_devnull.poll()
        print(f"Process with devnull poll result after 8 seconds: {poll_result}")

        assert (
            poll_result is None
        ), f"Process with devnull died after 8 seconds with code: {poll_result}"

        # Clean up
        process_devnull.terminate()
        process_devnull.wait(timeout=10)

        print("Devnull test completed successfully!")
