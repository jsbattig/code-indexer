"""Tests for golden repos temporal status display functionality."""

import pytest
from unittest.mock import MagicMock, patch, mock_open
import json


# Module-level constant for common test data
ALIAS_DATA = {
    "target_path": "/path/to/.versioned/v_1234567890",
    "last_refresh": "2024-01-01T12:00:00",
}


@pytest.fixture
def mock_golden_repo_manager():
    """Mock golden repo manager."""
    manager = MagicMock()
    manager.list_golden_repos.return_value = [
        {
            "alias": "test-repo",
            "clone_path": "/path/to/test-repo",
            "repo_url": "https://github.com/test/repo",
            "status": "ready",
            "created_at": "2024-01-01T00:00:00",
        },
        {
            "alias": "another-repo",
            "clone_path": "/path/to/another-repo",
            "repo_url": "https://github.com/test/another",
            "status": "ready",
            "created_at": "2024-01-02T00:00:00",
        },
    ]
    return manager


@pytest.fixture
def mock_global_registry():
    """Mock global registry."""
    registry = MagicMock()
    registry.list_global_repos.return_value = [
        {"repo_name": "test-repo", "alias_name": "test-global"},
    ]
    return registry


@patch("pathlib.Path.iterdir", return_value=[])
@patch("pathlib.Path.glob", return_value=[])
@patch("pathlib.Path.exists", return_value=False)
@patch("builtins.open", new_callable=lambda: mock_open(read_data=json.dumps(ALIAS_DATA)))
def test_golden_repos_list_includes_v2_temporal_status(
    mock_file, mock_exists, mock_glob, mock_iterdir, mock_golden_repo_manager, mock_global_registry
):
    """Test that _get_golden_repos_list includes v2 temporal status for global repos."""
    from code_indexer.server.web.routes import _get_golden_repos_list

    mock_dashboard = MagicMock()
    mock_dashboard.get_temporal_index_status.return_value = {
        "format": "v2",
        "file_count": 150,
        "indexed_files": 150,
    }

    with patch("code_indexer.server.web.routes._get_golden_repo_manager", return_value=mock_golden_repo_manager):
        with patch("code_indexer.global_repos.global_registry.GlobalRegistry", return_value=mock_global_registry):
            with patch("code_indexer.server.services.dashboard_service.DashboardService", return_value=mock_dashboard):
                repos = _get_golden_repos_list()

    # Verify temporal status was added to globally activated repo
    test_repo = next((r for r in repos if r["alias"] == "test-repo"), None)
    assert test_repo is not None
    assert "temporal_status" in test_repo
    assert test_repo["temporal_status"]["format"] == "v2"
    assert test_repo["temporal_status"]["file_count"] == 150


@patch("pathlib.Path.iterdir", return_value=[])
@patch("pathlib.Path.glob", return_value=[])
@patch("pathlib.Path.exists", return_value=False)
@patch("builtins.open", new_callable=lambda: mock_open(read_data=json.dumps(ALIAS_DATA)))
def test_golden_repos_list_handles_temporal_status_errors_gracefully(
    mock_file, mock_exists, mock_glob, mock_iterdir, mock_golden_repo_manager, mock_global_registry
):
    """Test that _get_golden_repos_list handles errors gracefully when fetching temporal status."""
    from code_indexer.server.web.routes import _get_golden_repos_list

    mock_dashboard = MagicMock()
    mock_dashboard.get_temporal_index_status.side_effect = Exception("Test error")

    with patch("code_indexer.server.web.routes._get_golden_repo_manager", return_value=mock_golden_repo_manager):
        with patch("code_indexer.global_repos.global_registry.GlobalRegistry", return_value=mock_global_registry):
            with patch("code_indexer.server.services.dashboard_service.DashboardService", return_value=mock_dashboard):
                repos = _get_golden_repos_list()

    # Verify error is captured in temporal_status
    test_repo = next((r for r in repos if r["alias"] == "test-repo"), None)
    assert test_repo is not None
    assert "temporal_status" in test_repo
    assert test_repo["temporal_status"]["format"] == "error"
    assert "Test error" in test_repo["temporal_status"]["message"]
