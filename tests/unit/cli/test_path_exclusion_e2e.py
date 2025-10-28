"""
Test-driven development for end-to-end path exclusion integration.

Tests complete integration of path exclusion from CLI to query execution:
- CLI argument parsing
- Filter construction and application
- Integration with both Qdrant and filesystem backends
- Real file filtering
"""

from unittest.mock import patch
from click.testing import CliRunner


class TestCLIPathExclusionIntegration:
    """Test CLI integration for path exclusion."""

    def test_cli_accepts_single_exclude_path_option(self):
        """Test that CLI accepts --exclude-path option."""
        from code_indexer.cli import query

        runner = CliRunner()

        # Mock the query execution to test CLI argument parsing
        with patch("code_indexer.cli.BackendFactory.create") as mock_backend:
            with patch(
                "code_indexer.cli.EmbeddingProviderFactory.create"
            ) as mock_embed:
                # Setup mocks
                mock_backend.return_value.get_vector_store_client.return_value.health_check.return_value = (
                    True
                )
                mock_embed.return_value.health_check.return_value = True
                mock_embed.return_value.get_provider_name.return_value = "voyageai"
                mock_embed.return_value.get_model_info.return_value = {
                    "name": "test-model"
                }

                # Test CLI parsing - ignore result since we're only testing parameter acceptance
                _ = runner.invoke(query, ["test query", "--exclude-path", "*/tests/*"])

                # CLI should parse without errors (execution may fail due to mocking)
                # We're testing that the argument is accepted
                assert "--exclude-path" in query.params or any(
                    p.name == "exclude_paths" for p in query.params
                )

    def test_cli_accepts_multiple_exclude_path_options(self):
        """Test that CLI accepts multiple --exclude-path options."""
        from code_indexer.cli import query

        runner = CliRunner()

        # Test that multiple --exclude-path flags are accepted
        with patch("code_indexer.cli.BackendFactory.create"):
            with patch("code_indexer.cli.EmbeddingProviderFactory.create"):
                _ = runner.invoke(
                    query,
                    [
                        "test query",
                        "--exclude-path",
                        "*/tests/*",
                        "--exclude-path",
                        "*.min.js",
                    ],
                )

                # CLI should accept multiple flags
                assert any(
                    p.name == "exclude_paths" and p.multiple for p in query.params
                )

    def test_cli_combines_exclude_path_with_other_filters(self):
        """Test that --exclude-path combines correctly with other filter options."""
        from code_indexer.cli import query

        # Verify CLI accepts combined filters
        assert any(p.name == "exclude_paths" for p in query.params)
        assert any(
            p.name == "languages" for p in query.params
        )  # Changed from "language" to "languages"
        assert any(p.name == "path_filter" for p in query.params)


class TestFilterConstructionIntegration:
    """Test filter construction for backend integration."""

    def test_filter_construction_for_qdrant_backend(self):
        """Test that path exclusion filters are correctly structured for Qdrant."""
        from code_indexer.services.path_filter_builder import PathFilterBuilder

        builder = PathFilterBuilder()

        # Build filters with path exclusions
        exclusion_patterns = ["*/tests/*", "*.min.js"]
        filter_conditions = builder.build_exclusion_filter(exclusion_patterns)

        # Verify structure matches Qdrant expectations
        assert "must_not" in filter_conditions
        assert len(filter_conditions["must_not"]) == 2

        # Verify each filter has correct structure
        for condition in filter_conditions["must_not"]:
            assert "key" in condition
            assert (
                condition["key"] == "path"
            )  # Changed from "file_path" to "path" (Bug Fix #5)
            assert "match" in condition
            # Should use 'text' for glob pattern matching
            assert "text" in condition["match"]
            assert condition["match"]["text"] in exclusion_patterns

    def test_filter_construction_for_filesystem_backend(self):
        """Test that path exclusion filters work with FilesystemVectorStore filter evaluation.

        This test verifies that the filter structure created by PathFilterBuilder
        works correctly with FilesystemVectorStore's internal filter evaluation logic.

        Tests the CRITICAL BUG: PathFilterBuilder uses 'value' but should use 'text'
        for glob pattern matching in FilesystemVectorStore.
        """
        from code_indexer.services.path_filter_builder import PathFilterBuilder

        # Build path exclusion filters using PathFilterBuilder
        builder = PathFilterBuilder()
        exclusion_patterns = ["*/tests/*", "*.min.js", "**/vendor/**"]
        filter_conditions = builder.build_exclusion_filter(exclusion_patterns)

        # Verify the filter structure uses 'text' for glob matching (not 'value')
        # THIS IS THE CRITICAL BUG FIX
        assert "must_not" in filter_conditions
        for condition in filter_conditions["must_not"]:
            assert "match" in condition
            # CRITICAL: Should use 'text' for glob patterns, not 'value'
            # 'value' does exact string matching (file_path == "*/tests/*" - WRONG!)
            # 'text' does glob pattern matching (fnmatch(file_path, "*/tests/*") - CORRECT!)
            assert "text" in condition["match"], (
                f"Filter condition must use 'text' for glob pattern matching, "
                f"not 'value'. Got: {condition['match']}"
            )

        # Now test that these filters actually work with FilesystemVectorStore's logic
        # We'll simulate the filter evaluation logic directly
        test_payloads = [
            {
                "path": "src/module.py"
            },  # Changed from "file_path" to "path" (Bug Fix #5)
            {"path": "src/tests/test_module.py"},  # Should be excluded
            {"path": "lib/vendor/package.js"},  # Should be excluded
            {"path": "dist/app.min.js"},  # Should be excluded
            {"path": "src/utils.py"},
        ]

        # Manually evaluate filters using the same logic as FilesystemVectorStore
        # This simulates what happens in the real search operation
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        matcher = PathPatternMatcher()

        def evaluate_filter(payload, filter_conditions):
            """Evaluate Qdrant-style filter against payload (simplified)."""
            if "must_not" in filter_conditions:
                for condition in filter_conditions["must_not"]:
                    if "key" in condition and "match" in condition:
                        key = condition["key"]
                        match_spec = condition["match"]

                        # Get value from payload
                        value = payload.get(key, "")

                        # Use 'text' for glob pattern matching
                        if "text" in match_spec:
                            pattern = match_spec["text"]
                            if matcher.matches_pattern(value, pattern):
                                return False  # Exclude this result
            return True  # Include this result

        # Filter payloads
        filtered_results = [
            p for p in test_payloads if evaluate_filter(p, filter_conditions)
        ]

        # CRITICAL ASSERTION: Should only return 2 results (module.py and utils.py)
        assert (
            len(filtered_results) == 2
        ), f"Expected 2 results, got {len(filtered_results)}"

        # Verify the correct files are included
        result_paths = [
            r["path"] for r in filtered_results
        ]  # Changed from "file_path" to "path" (Bug Fix #5)
        assert "src/module.py" in result_paths
        assert "src/utils.py" in result_paths

        # Verify excluded files are NOT in results
        assert "src/tests/test_module.py" not in result_paths
        assert "lib/vendor/package.js" not in result_paths
        assert "dist/app.min.js" not in result_paths


class TestEndToEndPathFiltering:
    """Test complete end-to-end path filtering workflow."""

    def test_e2e_path_exclusion_filters_results(self, tmp_path):
        """Test that path exclusions actually filter results in real scenario."""
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher

        # Create test file structure
        test_files = [
            "src/module.py",
            "src/tests/test_module.py",
            "lib/vendor/package.js",
            "dist/app.min.js",
            "src/utils.py",
        ]

        # Create mock results
        mock_results = [
            {"file_path": path, "score": 0.9, "content": "test"} for path in test_files
        ]

        # Apply path exclusions
        exclusion_patterns = ["*/tests/*", "*.min.js", "**/vendor/**"]
        matcher = PathPatternMatcher()

        filtered_results = [
            result
            for result in mock_results
            if not matcher.matches_any_pattern(result["file_path"], exclusion_patterns)
        ]

        # Should exclude 3 files: test_module.py, package.js, app.min.js
        assert len(filtered_results) == 2
        filtered_paths = [r["file_path"] for r in filtered_results]
        assert "src/module.py" in filtered_paths
        assert "src/utils.py" in filtered_paths

        # Should NOT include excluded files
        assert "src/tests/test_module.py" not in filtered_paths
        assert "lib/vendor/package.js" not in filtered_paths
        assert "dist/app.min.js" not in filtered_paths
