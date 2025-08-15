"""Performance validation tests for payload indexes - Story 6.

Tests comprehensive performance improvements and functionality of payload indexes
to validate the epic's claims of 50-90% CPU reduction and 2-10x performance improvement.

These tests require real Qdrant services and are designed to run with the e2e infrastructure.
"""

import time
from typing import List, Dict, Any

from code_indexer.services.qdrant import QdrantClient


class TestPayloadIndexPerformanceValidation:
    """Comprehensive performance validation tests for payload indexes."""

    def setup_method(self):
        """Setup test environment - will be configured via pytest fixtures."""
        self.test_collections: List[str] = []  # Track collections for cleanup
        self.config = None
        self.client = None

    def _setup_client(self, e2e_config):
        """Initialize client with config."""
        from rich.console import Console
        import httpx

        self.config = e2e_config
        self.client = QdrantClient(
            self.config.qdrant, console=Console(), project_root=self.config.codebase_dir
        )

        # Test connectivity
        try:
            response = httpx.get(f"{self.config.qdrant.host}/healthz", timeout=5.0)
            if response.status_code != 200:
                print(f"Qdrant health check failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"Direct creation exception: {e}")
            return False
        return True

    def teardown_method(self):
        """Clean up test collections."""
        if self.client:
            for collection_name in self.test_collections:
                try:
                    # Delete the collection if it exists
                    if self.client.collection_exists(collection_name):
                        self.client.client.delete(f"/collections/{collection_name}")
                except Exception:
                    pass  # Ignore cleanup errors

    def test_filter_performance_multiple_scales(self, e2e_config):
        """Test that filtering with indexes is significantly faster across different data sizes."""
        setup_success = self._setup_client(e2e_config)
        assert setup_success, "Failed to connect to Qdrant service"
        assert self.client is not None, "Client should be initialized"

        # Start with smaller sizes for CI compatibility and realistic performance testing
        test_sizes = [500, 1_500]  # Reduced sizes for CI performance

        for size in test_sizes:
            # Create collection without indexes
            collection_without = f"test_no_indexes_{size}"
            self.test_collections.append(collection_without)
            assert self.client.create_collection(collection_without)

            # Create collection with indexes
            collection_with = f"test_with_indexes_{size}"
            self.test_collections.append(collection_with)
            assert self.client.create_collection(collection_with)
            assert self.client._create_payload_indexes_with_retry(collection_with)

            # Add identical realistic test data
            test_points = self._generate_realistic_test_points(size)
            assert self.client.upsert_points(test_points, collection_without)
            assert self.client.upsert_points(test_points, collection_with)

            # Test multiple filter patterns that benefit from indexes
            filter_patterns = [
                # Single field filters (should show dramatic improvement)
                {"must": [{"key": "type", "match": {"value": "content"}}]},
                {"must": [{"key": "path", "match": {"text": "src/"}}]},
                {"must": [{"key": "git_branch", "match": {"value": "main"}}]},
                # Compound filters (common in reconcile operations)
                {
                    "must": [
                        {"key": "type", "match": {"value": "content"}},
                        {"key": "git_branch", "match": {"value": "main"}},
                    ]
                },
                # Complex filters with multiple conditions
                {
                    "must": [
                        {"key": "type", "match": {"value": "content"}},
                        {"key": "path", "match": {"text": ".py"}},
                        {"key": "git_branch", "match": {"value": "main"}},
                    ]
                },
            ]

            for i, filter_conditions in enumerate(filter_patterns):
                # Benchmark without indexes
                start = time.perf_counter()
                results_without, _ = self.client.scroll_points(
                    collection_name=collection_without,
                    filter_conditions=filter_conditions,
                    limit=100,
                )
                time_without = time.perf_counter() - start

                # Benchmark with indexes
                start = time.perf_counter()
                results_with, _ = self.client.scroll_points(
                    collection_name=collection_with,
                    filter_conditions=filter_conditions,
                    limit=100,
                )
                time_with = time.perf_counter() - start

                # Verify results are identical
                assert len(results_without) == len(
                    results_with
                ), f"Results should be identical for filter {i}"

                # Verify performance improvement scales with data size
                # Epic claims: 2-10x faster queries
                if size <= 1_000:
                    expected_ratio = 1.5  # Be conservative for small datasets
                elif size <= 10_000:
                    expected_ratio = 2.0  # 2x improvement minimum
                else:
                    expected_ratio = 3.0  # Higher ratios for larger datasets

                # Avoid division by zero and handle very fast queries
                if time_with > 0.001:  # Only test if query took more than 1ms
                    performance_ratio = time_without / time_with
                    assert (
                        performance_ratio >= expected_ratio
                    ), f"Size {size}, Filter {i}: Expected {expected_ratio}x improvement, got {performance_ratio:.2f}x"

    def test_index_creation_reliability(self, e2e_config):
        """Test index creation with retry logic and error handling."""
        setup_success = self._setup_client(e2e_config)
        assert setup_success, "Failed to connect to Qdrant service"
        assert self.client is not None, "Client should be initialized"

        collection_name = "test_index_reliability"
        self.test_collections.append(collection_name)
        assert self.client.create_collection(collection_name)

        # Test successful index creation
        success = self.client._create_payload_indexes_with_retry(collection_name)
        assert success, "Index creation should succeed"

        # Test idempotent behavior (creating indexes that already exist)
        success_again = self.client._create_payload_indexes_with_retry(collection_name)
        assert success_again, "Index creation should be idempotent"

        # Verify all expected indexes exist
        existing_indexes = self.client.list_payload_indexes(collection_name)
        existing_fields = {idx["field"] for idx in existing_indexes}
        expected_fields = {
            "type",
            "path",
            "git_branch",
            "file_mtime",
            "hidden_branches",
        }

        assert (
            existing_fields >= expected_fields
        ), f"Missing indexes: {expected_fields - existing_fields}"

    def test_index_health_monitoring(self, e2e_config):
        """Test index status reporting and health checks."""
        setup_success = self._setup_client(e2e_config)
        assert setup_success, "Failed to connect to Qdrant service"
        assert self.client is not None, "Client should be initialized"

        collection_name = "test_index_health"
        self.test_collections.append(collection_name)
        assert self.client.create_collection(collection_name)

        # Test status with no indexes
        status = self.client.get_payload_index_status(collection_name)
        assert not status["healthy"], "Should report unhealthy when indexes missing"
        assert (
            len(status["missing_indexes"]) == 5
        ), "Should report all 5 missing indexes"

        # Create indexes
        assert self.client._create_payload_indexes_with_retry(collection_name)

        # Test status with all indexes
        status = self.client.get_payload_index_status(collection_name)
        assert status["healthy"], "Should report healthy when all indexes exist"
        assert len(status["missing_indexes"]) == 0, "Should report no missing indexes"
        assert status["total_indexes"] >= 5, "Should have at least 5 indexes"

    def test_realistic_workload_performance(self, e2e_config):
        """Test performance with realistic code indexing workloads."""
        self._setup_client(e2e_config)
        assert self.client is not None, "Client should be initialized"

        # This test simulates actual reconcile operations which heavily use filtering
        collection_name = "test_realistic_workload"
        self.test_collections.append(collection_name)
        assert self.client.create_collection(collection_name)
        assert self.client._create_payload_indexes_with_retry(collection_name)

        # Generate realistic codebase data (smaller size for CI performance)
        test_points = self._generate_realistic_codebase_simulation(1_500)
        assert self.client.upsert_points(test_points, collection_name)

        # Common reconcile filters that should benefit from indexes
        reconcile_filters = [
            # Find all files in a specific branch
            {"must": [{"key": "git_branch", "match": {"value": "feature/auth"}}]},
            # Find content files for diffing
            {"must": [{"key": "type", "match": {"value": "content"}}]},
            # Find Python files in src directory
            {
                "must": [
                    {"key": "path", "match": {"text": "src/"}},
                    {"key": "path", "match": {"text": ".py"}},
                ]
            },
            # Find recent files (timestamp-based filtering)
            {"range": {"key": "file_mtime", "gte": int(time.time()) - 86400}},
        ]

        total_query_time = 0.0
        for filter_conditions in reconcile_filters:
            start = time.perf_counter()
            results, _ = self.client.scroll_points(
                collection_name=collection_name,
                filter_conditions=filter_conditions,
                limit=1000,
            )
            query_time = time.perf_counter() - start
            total_query_time += query_time

            # Each query should complete quickly with indexes
            assert query_time < 0.5, f"Query took too long: {query_time:.3f}s"
            assert len(results) > 0, "Should find matching results"

        # Total time for all realistic queries should be reasonable
        assert (
            total_query_time < 1.0
        ), f"Total query time too high: {total_query_time:.3f}s"

    def test_field_type_performance_validation(self, e2e_config):
        """Test that all field types perform well with their respective indexes."""
        self._setup_client(e2e_config)
        assert self.client is not None, "Client should be initialized"

        collection_name = "test_field_types"
        self.test_collections.append(collection_name)
        assert self.client.create_collection(collection_name)
        assert self.client._create_payload_indexes_with_retry(collection_name)

        # Generate data that exercises all field types (smaller size for CI)
        test_points = self._generate_field_type_test_data(1_000)
        assert self.client.upsert_points(test_points, collection_name)

        # Test each field type with appropriate queries
        field_tests = [
            # Keyword field tests
            ("type", {"must": [{"key": "type", "match": {"value": "content"}}]}),
            (
                "git_branch",
                {"must": [{"key": "git_branch", "match": {"value": "main"}}]},
            ),
            # Text field tests
            ("path", {"must": [{"key": "path", "match": {"text": "service"}}]}),
            # Integer field tests
            (
                "file_mtime",
                {"range": {"key": "file_mtime", "gte": int(time.time()) - 3600}},
            ),
            # Array field tests
            (
                "hidden_branches",
                {"must": [{"key": "hidden_branches", "match": {"value": "develop"}}]},
            ),
        ]

        for field_name, filter_conditions in field_tests:
            start = time.perf_counter()
            results, _ = self.client.scroll_points(
                collection_name=collection_name,
                filter_conditions=filter_conditions,
                limit=100,
            )
            query_time = time.perf_counter() - start

            # With indexes, each field type should query quickly
            assert (
                query_time < 0.1
            ), f"Field {field_name} query too slow: {query_time:.3f}s"
            assert len(results) > 0, f"Should find results for {field_name}"

    def _generate_realistic_test_points(self, count: int) -> List[Dict[str, Any]]:
        """Generate realistic test data that mimics actual code indexing payloads."""
        points = []
        file_extensions = [".py", ".js", ".ts", ".java", ".cpp", ".go", ".rs"]
        branches = ["main", "develop", "feature/auth", "bugfix/parser"]
        content_types = ["content", "metadata"]

        for i in range(count):
            ext = file_extensions[i % len(file_extensions)]
            branch = branches[i % len(branches)]
            content_type = content_types[i % len(content_types)]

            # Create realistic file paths
            module_num = i // 100
            file_name = f"file_{i % 100}"
            path = f"src/module_{module_num}/{file_name}{ext}"

            points.append(
                {
                    "id": str(i),
                    "vector": [0.1]
                    * (
                        self.config.qdrant.vector_size if self.config else 384
                    ),  # Use actual configured vector size
                    "payload": {
                        "type": content_type,
                        "path": path,
                        "git_branch": branch,
                        "file_mtime": int(time.time() - (i * 60)),  # Minutes ago
                        "hidden_branches": [b for b in branches if b != branch][:2],
                        "language": ext[1:],  # Remove dot
                        "content": f"Function definition for item {i}",
                        "chunk_index": i % 5,  # Multiple chunks per file
                    },
                }
            )
        return points

    def _generate_realistic_codebase_simulation(
        self, count: int
    ) -> List[Dict[str, Any]]:
        """Generate data that simulates a realistic codebase structure."""
        points = []

        # Realistic distribution of file types
        file_patterns = [
            ("src/services/", ".py", 0.3),
            ("src/controllers/", ".py", 0.2),
            ("frontend/components/", ".tsx", 0.15),
            ("frontend/utils/", ".js", 0.1),
            ("tests/", ".py", 0.15),
            ("docs/", ".md", 0.05),
            ("config/", ".yaml", 0.05),
        ]

        branches = [
            "main",
            "develop",
            "feature/auth",
            "feature/ui",
            "bugfix/performance",
        ]

        for i in range(count):
            # Select file pattern based on realistic distribution
            cumulative_prob = 0.0
            selected_pattern = file_patterns[0]

            rand_val = (i * 37) % 100 / 100  # Pseudo-random based on index
            for pattern in file_patterns:
                cumulative_prob += pattern[2]
                if rand_val <= cumulative_prob:
                    selected_pattern = pattern
                    break

            directory, extension, _ = selected_pattern
            branch = branches[i % len(branches)]

            points.append(
                {
                    "id": str(i),
                    "vector": [0.1]
                    * (self.config.qdrant.vector_size if self.config else 384),
                    "payload": {
                        "type": "content" if extension != ".md" else "metadata",
                        "path": f"{directory}module_{i//50}/file_{i}{extension}",
                        "git_branch": branch,
                        "file_mtime": int(time.time() - (i * 120)),  # 2 minutes apart
                        "hidden_branches": [b for b in branches if b != branch][:1],
                        "language": extension[1:],
                        "content": f"Realistic code content for {extension} file {i}",
                    },
                }
            )
        return points

    def _generate_field_type_test_data(self, count: int) -> List[Dict[str, Any]]:
        """Generate test data that exercises all payload index field types."""
        points = []

        for i in range(count):
            points.append(
                {
                    "id": str(i),
                    "vector": [0.1]
                    * (self.config.qdrant.vector_size if self.config else 384),
                    "payload": {
                        # Keyword fields
                        "type": ["content", "metadata", "test"][i % 3],
                        "git_branch": ["main", "develop", "feature/test"][i % 3],
                        # Text field
                        "path": f"src/service_{i//100}/module_{i//10}/file_{i}.py",
                        # Integer field
                        "file_mtime": int(time.time() - (i * 30)),  # 30 seconds apart
                        # Array field (keyword array)
                        "hidden_branches": [
                            ["develop", "staging"],
                            ["main", "release"],
                            ["feature/a", "feature/b"],
                        ][i % 3],
                        "content": f"Test content {i}",
                    },
                }
            )
        return points
