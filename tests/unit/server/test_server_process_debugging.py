"""
Debug test to understand why server process dies.
"""

import pytest
import subprocess
import time
import json


class TestServerProcessDebugging:
    """Debug server process startup issues."""

    def test_server_process_startup_debug(self, tmp_path):
        """Debug why server process dies after startup."""
        server_dir = tmp_path / "test-server"
        server_dir.mkdir()

        # Create valid configuration
        config = {"server_dir": str(server_dir), "host": "127.0.0.1", "port": 9001}

        config_file = server_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        print(f"Starting server with config: {config}")

        # Start server process like the lifecycle manager does
        cmd = [
            "python",
            "-m",
            "code_indexer.server.main",
            "--host",
            "127.0.0.1",
            "--port",
            "9001",
        ]

        print(f"Command: {' '.join(cmd)}")

        # Start process in background exactly like lifecycle manager
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,  # Create new process group
        )

        print(f"Process started with PID: {process.pid}")

        # Give server time to start
        time.sleep(3)

        # Check if process is still running
        poll_result = process.poll()
        print(f"Process poll result: {poll_result}")

        if poll_result is not None:
            # Process has terminated
            stdout, stderr = process.communicate()
            print(f"Process terminated with code: {poll_result}")
            print(f"STDOUT:\n{stdout.decode()}")
            print(f"STDERR:\n{stderr.decode()}")

            # This should not happen - server should still be running
            pytest.fail(
                f"Server process terminated prematurely with code {poll_result}"
            )
        else:
            print("Process is still running!")

            # Let it run a bit longer
            time.sleep(5)

            # Check again
            poll_result = process.poll()
            print(f"Process poll result after 8 seconds: {poll_result}")

            if poll_result is not None:
                stdout, stderr = process.communicate()
                print(f"Process terminated after 8 seconds with code: {poll_result}")
                print(f"STDOUT:\n{stdout.decode()}")
                print(f"STDERR:\n{stderr.decode()}")

                pytest.fail(
                    f"Server process terminated after 8 seconds with code {poll_result}"
                )
            else:
                print("Server is still running after 8 seconds - this is good!")

                # Clean up
                process.terminate()
                process.wait(timeout=10)

    def test_direct_server_main_execution(self):
        """Test running server main directly to see if it works."""
        print("Testing direct server main execution...")

        # Run server main directly for a short time
        result = subprocess.run(
            [
                "python",
                "-c",
                """
import signal
import time
import sys
import os

def timeout_handler(signum, frame):
    print('Timeout reached, shutting down')
    sys.exit(0)

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(3)  # 3 seconds

try:
    from code_indexer.server.main import main
    main()
except KeyboardInterrupt:
    print('Interrupted by keyboard')
except SystemExit:
    print('Clean exit')
except Exception as e:
    print(f'Error: {e}')
    raise
""",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        print(f"Return code: {result.returncode}")
        print(f"STDOUT:\n{result.stdout}")
        print(f"STDERR:\n{result.stderr}")

        # Should exit cleanly due to timeout
        assert result.returncode == 0
