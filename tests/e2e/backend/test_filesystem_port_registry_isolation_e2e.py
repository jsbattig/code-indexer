"""E2E tests for filesystem backend port registry isolation.

Uses environment variable injection to detect GlobalPortRegistry access in subprocess.
This approach works because subprocess runs real CLI code, and we can detect
if that code tries to instantiate GlobalPortRegistry.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestFilesystemPortRegistryIsolationE2E(unittest.TestCase):
    """E2E tests proving filesystem backend never accesses port registry."""

    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp(prefix="cidx_test_")
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        """Clean up test environment."""
        os.chdir(self.original_dir)
        import shutil

        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_filesystem_init_no_port_registry_access(self):
        """Test that cidx init with filesystem backend doesn't access port registry."""
        # Set environment variable that will be detected if GlobalPortRegistry is instantiated
        env = {**os.environ, "CIDX_FAIL_ON_PORT_REGISTRY": "1"}

        # Patch GlobalPortRegistry.__init__ to check for the environment variable
        # We need to create a wrapper script that patches and then runs cidx
        wrapper_script = Path(self.test_dir) / "test_wrapper.py"
        wrapper_script.write_text(
            """
import os
import sys
import importlib.util

# Check if we should fail on port registry access
if os.getenv("CIDX_FAIL_ON_PORT_REGISTRY") == "1":
    # Patch GlobalPortRegistry before it's imported
    import code_indexer.services.global_port_registry as gpr_module

    original_init = gpr_module.GlobalPortRegistry.__init__

    def patched_init(self):
        raise RuntimeError("FORBIDDEN: GlobalPortRegistry accessed with filesystem backend!")

    gpr_module.GlobalPortRegistry.__init__ = patched_init

# Now run the actual CLI
from code_indexer.cli import cli
cli()
"""
        )

        # Run cidx init with filesystem backend through wrapper
        result = subprocess.run(
            [
                "python3",
                str(wrapper_script),
                "init",
                "--vector-store",
                "filesystem",
                "--embedding-provider",
                "voyage-ai",
                "--voyage-model",
                "voyage-code-3",
            ],
            env=env,
            capture_output=True,
            text=True,
        )

        # Should succeed without accessing port registry
        self.assertEqual(result.returncode, 0, f"Init failed: {result.stderr}")
        self.assertNotIn("FORBIDDEN", result.stderr)
        self.assertNotIn("GlobalPortRegistry", result.stderr)

        # Verify config was created correctly
        config_file = Path(".code-indexer/config.json")
        self.assertTrue(config_file.exists())

        import json

        with open(config_file) as f:
            config = json.load(f)
        self.assertEqual(config["vector_store"]["provider"], "filesystem")

    def test_filesystem_index_no_port_registry_access(self):
        """Test that cidx index with filesystem backend doesn't access port registry."""
        # First create a filesystem config
        subprocess.run(
            [
                "python3",
                "-m",
                "code_indexer.cli",
                "init",
                "--vector-store",
                "filesystem",
                "--embedding-provider",
                "voyage-ai",
                "--voyage-model",
                "voyage-code-3",
            ],
            capture_output=True,
            check=True,
        )

        # Create a test file to index
        test_file = Path("test.py")
        test_file.write_text("def hello(): return 'world'")

        # Now test indexing with port registry detection
        env = {**os.environ, "CIDX_FAIL_ON_PORT_REGISTRY": "1"}

        wrapper_script = Path(self.test_dir) / "test_index_wrapper.py"
        wrapper_script.write_text(
            """
import os
import sys

# Check if we should fail on port registry access
if os.getenv("CIDX_FAIL_ON_PORT_REGISTRY") == "1":
    # Patch GlobalPortRegistry before it's imported
    import code_indexer.services.global_port_registry as gpr_module

    def patched_init(self):
        raise RuntimeError("FORBIDDEN: GlobalPortRegistry accessed during index!")

    gpr_module.GlobalPortRegistry.__init__ = patched_init

# Now run the actual CLI
from code_indexer.cli import cli
cli()
"""
        )

        # Run cidx index through wrapper
        result = subprocess.run(
            ["python3", str(wrapper_script), "index"],
            env=env,
            capture_output=True,
            text=True,
        )

        # Should succeed without accessing port registry
        self.assertEqual(result.returncode, 0, f"Index failed: {result.stderr}")
        self.assertNotIn("FORBIDDEN", result.stderr)
        self.assertNotIn("GlobalPortRegistry", result.stderr)

    def test_filesystem_query_no_port_registry_access(self):
        """Test that cidx query with filesystem backend doesn't access port registry."""
        # First create a filesystem config and index
        subprocess.run(
            [
                "python3",
                "-m",
                "code_indexer.cli",
                "init",
                "--vector-store",
                "filesystem",
                "--embedding-provider",
                "voyage-ai",
                "--voyage-model",
                "voyage-code-3",
            ],
            capture_output=True,
            check=True,
        )

        # Create and index a test file
        test_file = Path("test.py")
        test_file.write_text("def hello(): return 'world'")

        subprocess.run(
            ["python3", "-m", "code_indexer.cli", "index"],
            capture_output=True,
            check=True,
        )

        # Now test querying with port registry detection
        env = {**os.environ, "CIDX_FAIL_ON_PORT_REGISTRY": "1"}

        wrapper_script = Path(self.test_dir) / "test_query_wrapper.py"
        wrapper_script.write_text(
            """
import os
import sys

# Check if we should fail on port registry access
if os.getenv("CIDX_FAIL_ON_PORT_REGISTRY") == "1":
    # Patch GlobalPortRegistry before it's imported
    import code_indexer.services.global_port_registry as gpr_module

    def patched_init(self):
        raise RuntimeError("FORBIDDEN: GlobalPortRegistry accessed during query!")

    gpr_module.GlobalPortRegistry.__init__ = patched_init

# Now run the actual CLI
from code_indexer.cli import cli
cli()
"""
        )

        # Run cidx query through wrapper
        result = subprocess.run(
            ["python3", str(wrapper_script), "query", "hello", "--quiet"],
            env=env,
            capture_output=True,
            text=True,
        )

        # Should succeed without accessing port registry
        self.assertEqual(result.returncode, 0, f"Query failed: {result.stderr}")
        self.assertNotIn("FORBIDDEN", result.stderr)
        self.assertNotIn("GlobalPortRegistry", result.stderr)


if __name__ == "__main__":
    unittest.main()
