"""
Integration tests for advanced query filtering (Story #490).

Tests the complete flow of advanced filtering through the POST /api/query endpoint.
Following strict TDD: One test at a time, verify failure, implement, verify pass.
"""

import json
import pytest
from pathlib import Path
from typing import cast
from fastapi import FastAPI
from fastapi.testclient import TestClient
from datetime import datetime
from unittest.mock import patch

from code_indexer.server.app import create_app
from code_indexer.server.models.activated_repository import ActivatedRepository
from code_indexer.server.auth import dependencies


@pytest.fixture
def app_with_indexed_repo(tmp_path: Path):
    """Create FastAPI app with test repository containing indexed files."""
    # Create test directory structure
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    activated_repos_dir = data_dir / "activated-repos"
    activated_repos_dir.mkdir()

    # Create user directory
    user_dir = activated_repos_dir / "testuser"
    user_dir.mkdir()

    # Create single repository
    repo_dir = user_dir / "test-repo"
    repo_dir.mkdir()
    config_dir = repo_dir / ".code-indexer"
    config_dir.mkdir()

    # Create sample code files
    (repo_dir / "auth.py").write_text(
        """
def authenticate(user, password):
    '''Authentication function in Python.'''
    return user and password
"""
    )

    (repo_dir / "user.go").write_text(
        """
package main

func GetUser(id int) User {
    // User retrieval in Go
    return User{ID: id}
}
"""
    )

    # Create config
    config = {"proxy_mode": False, "embedding_provider": "voyage-ai"}
    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps(config, indent=2))

    # Create metadata
    metadata = ActivatedRepository(
        user_alias="test-repo",
        username="testuser",
        path=repo_dir,
        activated_at=datetime.now(),
        last_accessed=datetime.now(),
        golden_repo_alias="test-golden-repo",
        current_branch="main",
    )

    metadata_file = repo_dir / ".cidx-metadata.json"
    metadata_file.write_text(json.dumps(metadata.to_dict(), indent=2))

    # Create app with test configuration
    app = create_app()

    # Override activated repo manager data directory
    from code_indexer.server import app as app_module

    app_module.activated_repo_manager.activated_repos_dir = activated_repos_dir

    yield app


@pytest.fixture
def test_client(app_with_indexed_repo):
    """Create test client."""
    return TestClient(app_with_indexed_repo)


# Mock user for authentication bypass
class MockUser:
    def __init__(self):
        self.username = "testuser"
        self.role = "user"


def override_get_current_user():
    """Override authentication dependency for testing."""
    return MockUser()


class TestMultipleLanguageFilters:
    """Test multiple language filters with OR logic."""

    def test_multiple_languages_filters_results(self, test_client: TestClient):
        """Test that multiple language filters work with OR logic."""
        # Mock authentication and query execution
        app = cast(FastAPI, test_client.app)
        app.dependency_overrides[dependencies.get_current_user] = (
            override_get_current_user
        )

        try:
            # Mock the query_user_repositories method to return test results
            with patch(
                "code_indexer.server.app.semantic_query_manager.query_user_repositories"
            ) as mock_query:
                mock_query.return_value = {
                    "results": [
                        {
                            "file_path": "auth.py",
                            "line_number": 2,
                            "code_snippet": "def authenticate",
                            "similarity_score": 0.95,
                            "repository_alias": "test-repo",
                        },
                        {
                            "file_path": "user.go",
                            "line_number": 4,
                            "code_snippet": "func GetUser",
                            "similarity_score": 0.90,
                            "repository_alias": "test-repo",
                        },
                    ],
                    "total_results": 2,
                    "query_metadata": {
                        "query_text": "user authentication",
                        "execution_time_ms": 100,
                        "repositories_searched": 1,
                        "timeout_occurred": False,
                    },
                }

                # Test with multiple languages
                response = test_client.post(
                    "/api/query",
                    json={
                        "query_text": "user authentication",
                        "language": ["python", "go"],
                        "repository_alias": "test-repo",
                    },
                )

                # Verify response
                assert response.status_code == 200
                data = response.json()
                assert "results" in data

                # Verify mock was called with proper parameters
                mock_query.assert_called_once()
                call_kwargs = mock_query.call_args[1]
                assert call_kwargs["username"] == "testuser"
                assert call_kwargs["query_text"] == "user authentication"
                assert call_kwargs["repository_alias"] == "test-repo"

        finally:
            app.dependency_overrides.clear()

    def test_regex_with_semantic_mode_returns_400(self, test_client: TestClient):
        """Test that regex=True with search_mode=semantic returns 400 error."""
        app = cast(FastAPI, test_client.app)
        app.dependency_overrides[dependencies.get_current_user] = (
            override_get_current_user
        )

        try:
            response = test_client.post(
                "/api/query",
                json={
                    "query_text": "def.*",
                    "search_mode": "semantic",
                    "regex": True,
                    "repository_alias": "test-repo",
                },
            )

            # Should return 400 error
            assert response.status_code == 400
            data = response.json()
            assert (
                "regex" in data["detail"].lower()
                or "semantic" in data["detail"].lower()
            )

        finally:
            app.dependency_overrides.clear()


class TestMultiplePathFilters:
    """Test multiple path filters with OR logic."""

    def test_multiple_path_filters_passed_to_fts_search(
        self, app_with_indexed_repo, tmp_path: Path
    ):
        """Test that multiple path filters are normalized and passed to FTS search."""
        from starlette.testclient import TestClient

        test_client = TestClient(app_with_indexed_repo)
        app = cast(FastAPI, test_client.app)
        app.dependency_overrides[dependencies.get_current_user] = (
            override_get_current_user
        )

        try:
            # Create a fake FTS index directory in the test repo to pass the availability check
            from code_indexer.server import app as app_module

            activated_repos_dir = app_module.activated_repo_manager.activated_repos_dir

            fts_index_dir = (
                Path(activated_repos_dir)
                / "testuser"
                / "test-repo"
                / ".code-indexer"
                / "tantivy_index"
            )
            fts_index_dir.mkdir(parents=True, exist_ok=True)

            # Create a dummy file so the directory exists check passes
            (fts_index_dir / "dummy.txt").write_text("dummy")

            # Mock activated repository listing to return our test repo
            with patch(
                "code_indexer.server.app.activated_repo_manager.list_activated_repositories"
            ) as mock_list_repos:
                mock_list_repos.return_value = [
                    {
                        "user_alias": "test-repo",
                        "path": str(
                            Path(activated_repos_dir) / "testuser" / "test-repo"
                        ),
                    }
                ]

                # Mock the TantivyIndexManager where it's imported
                with patch(
                    "code_indexer.services.tantivy_index_manager.TantivyIndexManager"
                ) as MockTantivyClass:
                    mock_tantivy_instance = MockTantivyClass.return_value
                    mock_tantivy_instance.initialize_index.return_value = None
                    mock_tantivy_instance.search.return_value = []

                    response = test_client.post(
                        "/api/query",
                        json={
                            "query_text": "test query",
                            "search_mode": "fts",
                            "path_filter": ["*/src/*", "*/lib/*"],
                            "repository_alias": "test-repo",
                        },
                    )

                    # Should return 200 (FTS available and mocked)
                    if response.status_code != 200:
                        print(f"Response: {response.status_code} - {response.json()}")
                    assert response.status_code == 200

                    # Verify search was called
                    assert (
                        mock_tantivy_instance.search.called
                    ), "Tantivy search should have been called"

                    call_kwargs = mock_tantivy_instance.search.call_args[1]
                    # This will FAIL until we wire the normalization
                    assert (
                        "path_filters" in call_kwargs
                    ), f"path_filters not in kwargs: {call_kwargs.keys()}"
                    assert call_kwargs["path_filters"] == ["*/src/*", "*/lib/*"]

        finally:
            app.dependency_overrides.clear()
