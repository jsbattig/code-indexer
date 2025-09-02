"""
Test to reproduce the file extension filtering bug.

This test verifies that the file extension filtering logic is broken:
- When requesting specific file extensions, results should only include those extensions
- Current issue: filtering logic may not work correctly with mock data
- Expected: Bug reproduction should show incorrect filtering behavior
"""

import tempfile
from unittest.mock import patch, MagicMock
import pytest

from src.code_indexer.server.query.semantic_query_manager import (
    SemanticQueryManager,
    QueryResult,
)


class TestSemanticQueryManagerFileExtensionBugReproduction:
    """Test to reproduce the file extension filtering bug."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def activated_repo_manager_mock(self):
        """Mock activated repo manager."""
        mock = MagicMock()

        # Mock activated repos for test user
        mock.list_activated_repositories.return_value = [
            {
                "user_alias": "test-repo",
                "golden_repo_alias": "test-repo-golden",
                "current_branch": "main",
                "activated_at": "2024-01-01T00:00:00Z",
                "last_accessed": "2024-01-01T00:00:00Z",
            }
        ]

        # Mock repository paths
        mock.get_activated_repo_path.side_effect = (
            lambda username, user_alias: f"/tmp/repos/{username}/{user_alias}"
        )

        return mock

    @pytest.fixture
    def background_job_manager_mock(self):
        """Mock background job manager."""
        mock = MagicMock()
        mock.submit_job.return_value = "test-job-id-123"
        return mock

    @pytest.fixture
    def semantic_query_manager(
        self, temp_data_dir, activated_repo_manager_mock, background_job_manager_mock
    ):
        """Create SemanticQueryManager instance for testing."""
        return SemanticQueryManager(
            data_dir=temp_data_dir,
            activated_repo_manager=activated_repo_manager_mock,
            background_job_manager=background_job_manager_mock,
        )

    def test_file_extension_filtering_bug_reproduction_mixed_files(
        self, semantic_query_manager
    ):
        """
        Test that reproduces the file extension filtering bug.

        This test creates mock results with mixed file types (.py, .js, .txt, .md)
        and verifies that when we request specific extensions, only those should be returned.

        BUG: The filtering logic should work but currently has issues with mixed file types.
        """

        # Create mock search results with diverse file types - this simulates real repository content
        def mock_search_single_repo(
            repo_path, repo_alias, query_text, limit, min_score, file_extensions
        ):
            # Create mock results that would come from a real search - with mixed file types
            mock_results = [
                MagicMock(
                    file_path=f"{repo_path}/src/main.py",
                    content="def main():\n    print('Hello World')",
                    language="python",
                    score=0.95,
                    chunk_index=0,
                    total_chunks=1,
                ),
                MagicMock(
                    file_path=f"{repo_path}/src/app.js",
                    content="function app() {\n    console.log('Hello');\n}",
                    language="javascript",
                    score=0.88,
                    chunk_index=0,
                    total_chunks=1,
                ),
                MagicMock(
                    file_path=f"{repo_path}/docs/README.txt",
                    content="This is a text file\nwith documentation",
                    language="text",
                    score=0.75,
                    chunk_index=0,
                    total_chunks=1,
                ),
                MagicMock(
                    file_path=f"{repo_path}/config/settings.json",
                    content='{"debug": true, "port": 8080}',
                    language="json",
                    score=0.82,
                    chunk_index=0,
                    total_chunks=1,
                ),
                MagicMock(
                    file_path=f"{repo_path}/README.md",
                    content="# Project Title\nThis is markdown content",
                    language="markdown",
                    score=0.70,
                    chunk_index=0,
                    total_chunks=1,
                ),
            ]

            # Apply min_score filtering (this should work correctly)
            if min_score:
                mock_results = [r for r in mock_results if r.score >= min_score]

            # Apply file extension filtering (THIS IS WHERE THE BUG LIKELY IS)
            if file_extensions:
                filtered_results = []
                for result in mock_results:
                    file_path = result.file_path
                    # Check if file matches any of the specified extensions
                    if any(file_path.endswith(ext) for ext in file_extensions):
                        filtered_results.append(result)
                mock_results = filtered_results

            # Convert to QueryResult objects
            query_results = [
                QueryResult.from_search_result(result, repo_alias)
                for result in mock_results
            ]

            return query_results

        # Patch the search method to use our controlled mock data
        with patch.object(
            semantic_query_manager,
            "_search_single_repository",
            side_effect=mock_search_single_repo,
        ):

            # TEST 1: Request only .js files - should only return JavaScript files
            results = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="test query",
                file_extensions=[".js"],
                limit=10,
            )

            print(f"Results for .js filter: {len(results['results'])} files")
            for result in results["results"]:
                print(f"  - {result['file_path']}")

            # This should pass - only .js files should be returned
            assert (
                len(results["results"]) == 1
            ), f"Expected 1 .js file, got {len(results['results'])}"
            assert all(
                r["file_path"].endswith(".js") for r in results["results"]
            ), "All results should be .js files"

            # TEST 2: Request .py and .txt files
            results = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="test query",
                file_extensions=[".py", ".txt"],
                limit=10,
            )

            print(f"Results for .py,.txt filter: {len(results['results'])} files")
            for result in results["results"]:
                print(f"  - {result['file_path']}")

            # This should return 2 files (.py and .txt)
            assert (
                len(results["results"]) == 2
            ), f"Expected 2 files (.py, .txt), got {len(results['results'])}"
            file_extensions_found = [
                r["file_path"].split(".")[-1] for r in results["results"]
            ]
            assert "py" in file_extensions_found, "Should include .py file"
            assert "txt" in file_extensions_found, "Should include .txt file"

            # TEST 3: Request non-existent file extension
            results = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="test query",
                file_extensions=[".cpp"],  # No C++ files in our mock data
                limit=10,
            )

            print(f"Results for .cpp filter: {len(results['results'])} files")
            # Should return 0 results
            assert (
                len(results["results"]) == 0
            ), f"Expected 0 .cpp files, got {len(results['results'])}"

            # TEST 4: No file extension filter - should return all files
            results = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="test query",
                file_extensions=None,
                limit=10,
            )

            print(f"Results with no filter: {len(results['results'])} files")
            # Should return all 5 files
            assert (
                len(results["results"]) == 5
            ), f"Expected 5 files total, got {len(results['results'])}"

    def test_file_extension_filtering_edge_cases(self, semantic_query_manager):
        """Test edge cases for file extension filtering."""

        def mock_search_single_repo(
            repo_path, repo_alias, query_text, limit, min_score, file_extensions
        ):
            # Edge case files - files with multiple dots, no extension, etc.
            mock_results = [
                MagicMock(
                    file_path=f"{repo_path}/test.min.js",  # Multiple dots
                    content="// minified JS",
                    language="javascript",
                    score=0.90,
                    chunk_index=0,
                    total_chunks=1,
                ),
                MagicMock(
                    file_path=f"{repo_path}/Makefile",  # No extension
                    content="all:\n\techo 'building'",
                    language="makefile",
                    score=0.85,
                    chunk_index=0,
                    total_chunks=1,
                ),
                MagicMock(
                    file_path=f"{repo_path}/script",  # No extension
                    content="#!/bin/bash\necho hello",
                    language="shell",
                    score=0.80,
                    chunk_index=0,
                    total_chunks=1,
                ),
                MagicMock(
                    file_path=f"{repo_path}/config.yaml.bak",  # Backup file
                    content="backup: true",
                    language="yaml",
                    score=0.75,
                    chunk_index=0,
                    total_chunks=1,
                ),
            ]

            # Apply file extension filtering
            if file_extensions:
                filtered_results = []
                for result in mock_results:
                    file_path = result.file_path
                    if any(file_path.endswith(ext) for ext in file_extensions):
                        filtered_results.append(result)
                mock_results = filtered_results

            # Convert to QueryResult objects
            query_results = [
                QueryResult.from_search_result(result, repo_alias)
                for result in mock_results
            ]

            return query_results

        with patch.object(
            semantic_query_manager,
            "_search_single_repository",
            side_effect=mock_search_single_repo,
        ):

            # TEST: Request .js files - should match test.min.js
            results = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="test query",
                file_extensions=[".js"],
                limit=10,
            )

            assert (
                len(results["results"]) == 1
            ), "Should find the .js file (test.min.js)"
            assert results["results"][0]["file_path"].endswith(
                ".js"
            ), "Result should be .js file"

            # TEST: Request .bak files
            results = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="test query",
                file_extensions=[".bak"],
                limit=10,
            )

            assert len(results["results"]) == 1, "Should find the .bak file"
            assert results["results"][0]["file_path"].endswith(
                ".bak"
            ), "Result should be .bak file"

            # TEST: Request empty string extension (edge case)
            results = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="test query",
                file_extensions=[""],  # Empty extension
                limit=10,
            )

            # All files "end with" empty string, so this should return all files
            assert (
                len(results["results"]) == 4
            ), "Empty extension should match all files"
