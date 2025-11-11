"""Unit tests for temporal path filter type bug.

Bug: --exclude-path and --path-filter with --time-range-all return ZERO results.

Root Cause:
1. CLI receives tuple: ("*.md",)
2. Daemon delegation incorrectly converts: list(exclude_path)[0] → string "*.md"
3. Daemon service has wrong type: Optional[str] instead of Optional[List[str]]
4. TemporalSearchService does list("*.md") → ['*', '.', 'm', 'd'] (character array!)
5. Creates filters for single characters → ZERO results

This test proves the bug exists by testing daemon service parameter signatures.
"""

import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock
from typing import Optional, List

# Mock rpyc before import if not available
try:
    import rpyc
except ImportError:
    sys.modules["rpyc"] = MagicMock()
    sys.modules["rpyc.utils.server"] = MagicMock()
    rpyc = sys.modules["rpyc"]

from src.code_indexer.daemon.service import CIDXDaemonService


class TestTemporalPathFilterBug(TestCase):
    """Test temporal path filter type bug."""

    def test_daemon_service_path_filter_signature_should_be_list(self):
        """Daemon service path_filter parameter should be Optional[List[str]], not Optional[str]."""

        service = CIDXDaemonService()

        # Get method signature
        import inspect

        sig = inspect.signature(service.exposed_query_temporal)

        # Check path_filter parameter type annotation
        path_filter_param = sig.parameters.get("path_filter")
        assert path_filter_param is not None, "path_filter parameter should exist"

        # Extract type annotation string representation
        annotation_str = str(path_filter_param.annotation)

        # Should be Optional[List[str]], NOT Optional[str]
        assert (
            "Optional[str]" != annotation_str or "[" in annotation_str
        ), "BUG: path_filter signature is Optional[str], should be Optional[List[str]]"
        assert (
            "List[str]" in annotation_str or "list[str]" in annotation_str
        ), f"path_filter signature should contain List[str], got {annotation_str}"

    def test_daemon_service_exclude_path_signature_should_be_list(self):
        """Daemon service exclude_path parameter should be Optional[List[str]], not Optional[str]."""

        service = CIDXDaemonService()

        # Get method signature
        import inspect

        sig = inspect.signature(service.exposed_query_temporal)

        # Check exclude_path parameter type annotation
        exclude_path_param = sig.parameters.get("exclude_path")
        assert exclude_path_param is not None, "exclude_path parameter should exist"

        # Extract type annotation string representation
        annotation_str = str(exclude_path_param.annotation)

        # Should be Optional[List[str]], NOT Optional[str]
        assert (
            "Optional[str]" != annotation_str or "[" in annotation_str
        ), "BUG: exclude_path signature is Optional[str], should be Optional[List[str]]"
        assert (
            "List[str]" in annotation_str or "list[str]" in annotation_str
        ), f"exclude_path signature should contain List[str], got {annotation_str}"

    def test_daemon_handles_multiple_path_filters_correctly(self):
        """Daemon should handle multiple path filter patterns correctly."""
        import json
        import tempfile

        service = CIDXDaemonService()

        # Create temporary project structure
        temp_dir = tempfile.mkdtemp()
        project_path = Path(temp_dir) / "test_project"
        project_path.mkdir(parents=True, exist_ok=True)

        # Create temporal collection
        temporal_collection_path = (
            project_path / ".code-indexer" / "index" / "code-indexer-temporal"
        )
        temporal_collection_path.mkdir(parents=True, exist_ok=True)

        metadata = {"hnsw_index": {"index_rebuild_uuid": "uuid-123"}}
        metadata_file = temporal_collection_path / "collection_meta.json"
        metadata_file.write_text(json.dumps(metadata))

        try:
            from unittest.mock import patch, MagicMock

            # Mock dependencies
            with patch(
                "code_indexer.config.ConfigManager.create_with_backtrack"
            ) as mock_config:
                with patch(
                    "code_indexer.backends.backend_factory.BackendFactory.create"
                ) as mock_backend_factory:
                    with patch(
                        "code_indexer.services.embedding_factory.EmbeddingProviderFactory.create"
                    ) as mock_embedding:
                        with patch(
                            "code_indexer.services.temporal.temporal_search_service.TemporalSearchService"
                        ) as mock_temporal_search:

                            # Setup mocks
                            mock_config.return_value = MagicMock()
                            mock_backend = MagicMock()
                            mock_backend.get_vector_store_client.return_value = (
                                MagicMock()
                            )
                            mock_backend_factory.return_value = mock_backend
                            mock_embedding.return_value = MagicMock()

                            # Mock TemporalSearchService
                            mock_search_service = MagicMock()
                            mock_search_result = MagicMock()
                            mock_search_result.results = []
                            mock_search_result.query = "test"
                            mock_search_result.filter_type = None
                            mock_search_result.filter_value = None
                            mock_search_result.total_found = 0
                            mock_search_result.performance = {}
                            mock_search_result.warning = None
                            mock_search_service.query_temporal.return_value = (
                                mock_search_result
                            )
                            mock_temporal_search.return_value = mock_search_service

                            # Patch cache to avoid threading issues
                            with patch.object(service, "cache_lock"):
                                with patch.object(service, "_ensure_cache_loaded"):
                                    with patch.object(
                                        service, "cache_entry"
                                    ) as mock_cache_entry:
                                        mock_cache_entry.temporal_hnsw_index = (
                                            MagicMock()
                                        )
                                        mock_cache_entry.is_temporal_stale_after_rebuild.return_value = (
                                            False
                                        )

                                        # Call with multiple path filters
                                        result = service.exposed_query_temporal(
                                            project_path=str(project_path),
                                            query="authentication",
                                            time_range="2024-01-01..2024-12-31",
                                            limit=10,
                                            path_filter=["*.py", "*.js"],
                                            exclude_path=["*/tests/*", "*/docs/*"],
                                        )

                                        # Verify TemporalSearchService was called
                                        mock_search_service.query_temporal.assert_called_once()
                                        call_kwargs = mock_search_service.query_temporal.call_args[
                                            1
                                        ]

                                        # Verify lists passed correctly
                                        path_filter_arg = call_kwargs.get("path_filter")
                                        exclude_path_arg = call_kwargs.get(
                                            "exclude_path"
                                        )

                                        assert isinstance(path_filter_arg, list)
                                        assert len(path_filter_arg) == 2
                                        assert "*.py" in path_filter_arg
                                        assert "*.js" in path_filter_arg

                                        assert isinstance(exclude_path_arg, list)
                                        assert len(exclude_path_arg) == 2
                                        assert "*/tests/*" in exclude_path_arg
                                        assert "*/docs/*" in exclude_path_arg
        finally:
            # Cleanup
            import shutil

            if Path(temp_dir).exists():
                shutil.rmtree(temp_dir)
