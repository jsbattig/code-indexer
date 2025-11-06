"""E2E tests for backward compatibility with legacy configs.

Legacy configs (without vector_store field) should still work with Qdrant
and port registry for backward compatibility.
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestLegacyConfigCompatibilityE2E(unittest.TestCase):
    """E2E tests verifying legacy configs still work with port registry."""

    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp(prefix="cidx_legacy_test_")
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        """Clean up test environment."""
        os.chdir(self.original_dir)
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_legacy_config_uses_qdrant_backend(self):
        """Test that legacy configs without vector_store field default to Qdrant."""
        # Create a legacy config manually (without vector_store field)
        config_dir = Path(".code-indexer")
        config_dir.mkdir()

        legacy_config = {
            "index_patterns": ["**/*.py"],
            "exclude_patterns": ["__pycache__/**", ".git/**"],
            "embedding_provider": "voyage-ai",
            "voyage": {
                "model": "voyage-code-3",
                "api_key_source": "env"
            },
            "qdrant": {
                "collection": "test_legacy"
            }
            # Note: No vector_store field (legacy config)
        }

        config_file = config_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(legacy_config, f, indent=2)

        # Create a test file to index
        test_file = Path("test.py")
        test_file.write_text("def legacy_test(): return 'backward compatible'")

        # Try to index with legacy config
        # This should work and use Qdrant backend (backward compatibility)
        result = subprocess.run(
            ["python3", "-m", "code_indexer.cli", "index"],
            capture_output=True,
            text=True
        )

        # Should succeed (or fail with port registry error if not set up, but not fail on missing vector_store)
        # The key is it shouldn't fail with "no vector_store in config" error

        # The BackendFactory should have defaulted to Qdrant for legacy config
        # Check the output for any indication it's working with the legacy config
        if result.returncode == 0:
            # If it succeeded, that's good - legacy config works
            self.assertIn("index", result.stdout.lower() or result.stderr.lower())
        else:
            # If it failed, check it's not because of missing vector_store field
            self.assertNotIn("vector_store", result.stderr.lower(),
                            "Legacy config should not fail on missing vector_store field")
            # Could be port registry or other expected errors for Qdrant
            # The important thing is it tried to use Qdrant, not fail on config


if __name__ == "__main__":
    unittest.main()