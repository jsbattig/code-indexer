"""TDD tests for repository info command implementation.

Tests the `cidx repos info` command with comprehensive information display,
branch listing, health monitoring, and activity tracking capabilities.
Following TDD methodology: Red -> Green -> Refactor
"""

from unittest.mock import Mock, patch, AsyncMock
from click.testing import CliRunner
from pathlib import Path

from code_indexer.cli import cli
from code_indexer.api_clients.base_client import APIClientError, AuthenticationError


class TestRepositoryInfoCommand:
    """TDD tests for cidx repos info command implementation."""

    def setup_method(self):
        """Set up test environment for each test."""
        self.runner = CliRunner()
        self.mock_project_root = Path("/test/project")
        self.mock_credentials = {"username": "test_user", "token": "test_token"}
        self.mock_remote_config = {"server_url": "https://cidx.example.com"}

    def test_repos_info_command_exists(self):
        """Test that repos info command exists and is accessible."""
        # RED: This test should fail initially since command doesn't exist
        result = self.runner.invoke(cli, ["repos", "info", "--help"])

        # Should show help for the info command
        assert result.exit_code == 0
        assert "Show detailed repository information" in result.output

    def test_repos_info_requires_user_alias_argument(self):
        """Test that repos info command requires user alias argument."""
        # RED: This test should fail initially
        result = self.runner.invoke(cli, ["repos", "info"])

        # Should require user alias argument
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage:" in result.output

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_remote_configuration")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("code_indexer.api_clients.repos_client.ReposAPIClient")
    def test_repos_info_basic_display(
        self,
        mock_client_class,
        mock_load_credentials,
        mock_load_config,
        mock_find_root,
    ):
        """Test basic repository information display."""
        # RED: This test should fail initially since functionality doesn't exist

        # Setup mocks
        mock_find_root.return_value = self.mock_project_root
        mock_load_config.return_value = self.mock_remote_config
        mock_load_credentials.return_value = self.mock_credentials

        # Mock repository info response
        mock_repo_info = {
            "alias": "my-project",
            "golden_repository": "web-application",
            "git_url": "https://github.com/company/web-app.git",
            "current_branch": "main",
            "activation_date": "2024-01-15T10:30:00Z",
            "sync_status": "up_to_date",
            "last_sync": "2024-01-15T14:22:00Z",
            "container_status": "running",
            "index_status": "complete",
            "query_ready": True,
            "storage_info": {
                "disk_usage_mb": 156,
                "shared_mb": 142,
                "unique_mb": 14,
                "index_size_mb": 23,
            },
        }

        mock_client = Mock()
        mock_client.get_repository_info = AsyncMock(return_value=mock_repo_info)
        mock_client_class.return_value = mock_client

        # Execute command
        result = self.runner.invoke(cli, ["repos", "info", "my-project"])

        # Should succeed and display repository information
        assert result.exit_code == 0
        assert "Repository Information: my-project" in result.output
        assert "Basic Information:" in result.output
        assert "Alias: my-project" in result.output
        assert "Git URL: https://github.com/company/web-app.git" in result.output
        assert "Current Branch: main" in result.output
        assert "Status:" in result.output
        assert "✓ Up to date with golden repository" in result.output

        # Verify API client was called correctly
        mock_client.get_repository_info.assert_called_once_with(
            user_alias="my-project", branches=False, health=False, activity=False
        )

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_remote_configuration")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("code_indexer.api_clients.repos_client.ReposAPIClient")
    def test_repos_info_with_branches_flag(
        self,
        mock_client_class,
        mock_load_credentials,
        mock_load_config,
        mock_find_root,
    ):
        """Test repository info with --branches flag for detailed branch information."""
        # RED: This test should fail initially

        # Setup mocks
        mock_find_root.return_value = self.mock_project_root
        mock_load_config.return_value = self.mock_remote_config
        mock_load_credentials.return_value = self.mock_credentials

        # Mock repository info with branches
        mock_repo_info = {
            "alias": "my-project",
            "current_branch": "feature/auth-improvements",
            "branches": [
                {
                    "name": "feature/auth-improvements",
                    "is_current": True,
                    "last_commit": {
                        "message": "feat: add OAuth integration",
                        "timestamp": "2024-01-15T12:00:00Z",
                        "author": "dev@example.com",
                    },
                },
                {
                    "name": "main",
                    "is_current": False,
                    "last_commit": {
                        "message": "fix: resolve login timeout issue",
                        "timestamp": "2024-01-14T10:00:00Z",
                        "author": "dev@example.com",
                    },
                },
                {
                    "name": "develop",
                    "is_current": False,
                    "last_commit": {
                        "message": "chore: update dependencies",
                        "timestamp": "2024-01-12T15:30:00Z",
                        "author": "dev@example.com",
                    },
                },
            ],
        }

        mock_client = Mock()
        mock_client.get_repository_info = AsyncMock(return_value=mock_repo_info)
        mock_client_class.return_value = mock_client

        # Execute command with --branches flag
        result = self.runner.invoke(cli, ["repos", "info", "my-project", "--branches"])

        # Should succeed and display branch information
        assert result.exit_code == 0
        assert "Branch Information:" in result.output
        assert "* feature/auth-improvements (current)" in result.output
        assert "feat: add OAuth integration" in result.output
        assert "main" in result.output
        assert "fix: resolve login timeout issue" in result.output
        assert "develop" in result.output
        assert "chore: update dependencies" in result.output

        # Verify API client was called with branches=True
        mock_client.get_repository_info.assert_called_once_with(
            user_alias="my-project", branches=True, health=False, activity=False
        )

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_remote_configuration")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("code_indexer.api_clients.repos_client.ReposAPIClient")
    def test_repos_info_with_health_flag(
        self,
        mock_client_class,
        mock_load_credentials,
        mock_load_config,
        mock_find_root,
    ):
        """Test repository info with --health flag for health monitoring."""
        # RED: This test should fail initially

        # Setup mocks
        mock_find_root.return_value = self.mock_project_root
        mock_load_config.return_value = self.mock_remote_config
        mock_load_credentials.return_value = self.mock_credentials

        # Mock repository health info
        mock_repo_info = {
            "alias": "my-project",
            "health": {
                "container_status": "running",
                "services": {
                    "qdrant": {"status": "healthy", "port": 6333},
                    "ollama": {"status": "healthy", "port": 11434},
                },
                "index_status": "complete",
                "query_ready": True,
                "storage": {
                    "disk_usage_mb": 156,
                    "available_space_gb": 45.2,
                    "index_size_mb": 23,
                },
                "issues": [],
                "recommendations": [
                    "Consider running 'cidx sync' to check for updates"
                ],
            },
        }

        mock_client = Mock()
        mock_client.get_repository_info = AsyncMock(return_value=mock_repo_info)
        mock_client_class.return_value = mock_client

        # Execute command with --health flag
        result = self.runner.invoke(cli, ["repos", "info", "my-project", "--health"])

        # Should succeed and display health information
        assert result.exit_code == 0
        assert "Health Information:" in result.output
        assert "Container Status: ✓ running" in result.output
        assert "Services:" in result.output
        assert "qdrant: ✓ Healthy (port 6333)" in result.output
        assert "ollama: ✓ Healthy (port 11434)" in result.output
        assert "Storage Information:" in result.output
        assert "Disk Usage: 156 MB" in result.output
        assert "Available Space: 45.2 GB" in result.output
        assert "Recommendations:" in result.output

        # Verify API client was called with health=True
        mock_client.get_repository_info.assert_called_once_with(
            user_alias="my-project", branches=False, health=True, activity=False
        )

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_remote_configuration")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("code_indexer.api_clients.repos_client.ReposAPIClient")
    def test_repos_info_with_activity_flag(
        self,
        mock_client_class,
        mock_load_credentials,
        mock_load_config,
        mock_find_root,
    ):
        """Test repository info with --activity flag for activity monitoring."""
        # RED: This test should fail initially

        # Setup mocks
        mock_find_root.return_value = self.mock_project_root
        mock_load_config.return_value = self.mock_remote_config
        mock_load_credentials.return_value = self.mock_credentials

        # Mock repository activity info
        mock_repo_info = {
            "alias": "my-project",
            "activity": {
                "recent_commits": [
                    {
                        "commit_hash": "abc123",
                        "message": "feat: add OAuth integration",
                        "author": "dev@example.com",
                        "timestamp": "2024-01-15T12:00:00Z",
                    },
                    {
                        "commit_hash": "def456",
                        "message": "fix: resolve login timeout",
                        "author": "dev@example.com",
                        "timestamp": "2024-01-14T10:00:00Z",
                    },
                ],
                "sync_history": [
                    {
                        "timestamp": "2024-01-15T14:22:00Z",
                        "status": "success",
                        "changes": "3 files updated",
                    }
                ],
                "query_activity": {
                    "recent_queries": 15,
                    "last_query": "2024-01-15T13:45:00Z",
                },
                "branch_operations": [
                    {
                        "operation": "switch",
                        "from_branch": "main",
                        "to_branch": "feature/auth-improvements",
                        "timestamp": "2024-01-15T09:30:00Z",
                    }
                ],
            },
        }

        mock_client = Mock()
        mock_client.get_repository_info = AsyncMock(return_value=mock_repo_info)
        mock_client_class.return_value = mock_client

        # Execute command with --activity flag
        result = self.runner.invoke(cli, ["repos", "info", "my-project", "--activity"])

        # Should succeed and display activity information
        assert result.exit_code == 0
        assert "Activity Information:" in result.output
        assert "Recent Commits:" in result.output
        assert "abc123: feat: add OAuth integration" in result.output
        assert "Sync History:" in result.output
        assert "3 files updated" in result.output
        assert "Query Activity:" in result.output
        assert "Recent queries: 15" in result.output
        assert "Branch Operations:" in result.output
        assert "switch: main → feature/auth-improvements" in result.output

        # Verify API client was called with activity=True
        mock_client.get_repository_info.assert_called_once_with(
            user_alias="my-project", branches=False, health=False, activity=True
        )

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_remote_configuration")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("code_indexer.api_clients.repos_client.ReposAPIClient")
    def test_repos_info_all_flags_combined(
        self,
        mock_client_class,
        mock_load_credentials,
        mock_load_config,
        mock_find_root,
    ):
        """Test repository info with all flags combined."""
        # RED: This test should fail initially

        # Setup mocks
        mock_find_root.return_value = self.mock_project_root
        mock_load_config.return_value = self.mock_remote_config
        mock_load_credentials.return_value = self.mock_credentials

        mock_client = Mock()
        mock_client.get_repository_info = AsyncMock(return_value={})
        mock_client_class.return_value = mock_client

        # Execute command with all flags
        result = self.runner.invoke(
            cli, ["repos", "info", "my-project", "--branches", "--health", "--activity"]
        )

        # Should succeed and call API with all options
        assert result.exit_code == 0

        # Verify API client was called with all options
        mock_client.get_repository_info.assert_called_once_with(
            user_alias="my-project", branches=True, health=True, activity=True
        )

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_remote_configuration")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("code_indexer.api_clients.repos_client.ReposAPIClient")
    def test_repos_info_handles_api_errors(
        self,
        mock_client_class,
        mock_load_credentials,
        mock_load_config,
        mock_find_root,
    ):
        """Test repository info handles API errors gracefully."""
        # Setup mocks
        mock_find_root.return_value = self.mock_project_root
        mock_load_config.return_value = self.mock_remote_config
        mock_load_credentials.return_value = self.mock_credentials

        # Mock API error
        mock_client = Mock()
        mock_client.get_repository_info = AsyncMock(
            side_effect=APIClientError("Repository not found", 404)
        )
        mock_client_class.return_value = mock_client

        # Execute command
        result = self.runner.invoke(cli, ["repos", "info", "nonexistent"])

        # Should handle error gracefully
        assert result.exit_code != 0
        assert (
            "Repository not found" in result.output
            or "Failed to get repository info" in result.output
        )

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_remote_configuration")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    @patch("code_indexer.api_clients.repos_client.ReposAPIClient")
    def test_repos_info_handles_authentication_errors(
        self,
        mock_client_class,
        mock_load_credentials,
        mock_load_config,
        mock_find_root,
    ):
        """Test repository info handles authentication errors."""
        # Setup mocks
        mock_find_root.return_value = self.mock_project_root
        mock_load_config.return_value = self.mock_remote_config
        mock_load_credentials.return_value = self.mock_credentials

        # Mock authentication error
        mock_client = Mock()
        mock_client.get_repository_info = AsyncMock(
            side_effect=AuthenticationError("Invalid credentials")
        )
        mock_client_class.return_value = mock_client

        # Execute command
        result = self.runner.invoke(cli, ["repos", "info", "my-project"])

        # Should handle authentication error
        assert result.exit_code != 0
        assert (
            "Authentication failed" in result.output
            or "Invalid credentials" in result.output
        )

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    def test_repos_info_requires_project_root(self, mock_find_root):
        """Test that repos info requires being in a CIDX project directory."""
        # Mock no project root found
        mock_find_root.return_value = None

        # Execute command
        result = self.runner.invoke(cli, ["repos", "info", "my-project"])

        # Should fail with project directory error
        assert result.exit_code != 0
        assert "Not in a CIDX project directory" in result.output

    @patch("code_indexer.mode_detection.command_mode_detector.find_project_root")
    @patch("code_indexer.remote.sync_execution._load_remote_configuration")
    def test_repos_info_requires_remote_configuration(
        self, mock_load_config, mock_find_root
    ):
        """Test that repos info requires remote configuration."""
        # Setup mocks
        mock_find_root.return_value = self.mock_project_root
        mock_load_config.side_effect = Exception("No remote configuration found")

        # Execute command
        result = self.runner.invoke(cli, ["repos", "info", "my-project"])

        # Should fail with configuration error
        assert result.exit_code != 0
        assert (
            "Failed to load credentials" in result.output
            or "No remote configuration" in result.output
        )
