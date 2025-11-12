"""Test that temporal search service works without GitBlobReader."""

import unittest
from pathlib import Path
from unittest.mock import Mock

from src.code_indexer.services.temporal.temporal_search_service import (
    TemporalSearchService,
)


class TestTemporalSearchServiceNoBlobReader(unittest.TestCase):
    """Test temporal search service without GitBlobReader."""

    def test_temporal_search_service_imports_without_blob_reader(self):
        """Test that TemporalSearchService can be imported without GitBlobReader."""
        # This test will fail if GitBlobReader import is still required
        # but the file has been deleted

        # Try to create a TemporalSearchService instance
        project_root = Path("/tmp/test-repo")
        config_manager = Mock()

        # This should work even though GitBlobReader.py is deleted
        service = TemporalSearchService(
            config_manager=config_manager,
            project_root=project_root,
            vector_store_client=Mock(),
            embedding_provider=Mock(),
        )

        self.assertIsNotNone(service)


if __name__ == "__main__":
    unittest.main()
