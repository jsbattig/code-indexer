"""TDD tests for Repository CLI commands implementation.

This test file implements comprehensive TDD tests for the repository discovery
and browsing CLI commands as defined in Story 4.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from click.testing import CliRunner

from src.code_indexer.cli import cli
from src.code_indexer.api_clients.repos_client import (
    ActivatedRepository,
    GoldenRepository,
    RepositoryDiscoveryResult,
    RepositoryStatusSummary,
    DiscoveredRepository,
    ActivatedRepositorySummary,
    AvailableRepositorySummary,
    RecentActivity,
)
from src.code_indexer.api_clients.base_client import APIClientError, AuthenticationError


class TestReposCommandGroup:
    """Test the repos command group structure."""

    def test_repos_command_group_exists(self):
        """Test that repos command group is properly registered."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "repos" in result.output

    def test_repos_command_group_help(self):
        """Test repos command group help information."""
        runner = CliRunner()
        result = runner.invoke(cli, ["repos", "--help"])

        assert result.exit_code == 0
        assert "Repository management commands" in result.output
        assert "list" in result.output
        assert "available" in result.output
        assert "discover" in result.output
        assert "status" in result.output

    def test_repos_command_requires_remote_mode(self):
        """Test that repos commands require remote mode."""
        runner = CliRunner()

        # Mock mode detection to return local mode
        with patch(
            "src.code_indexer.disabled_commands.detect_current_mode"
        ) as mock_detect_mode:
            mock_detect_mode.return_value = "local"

            result = runner.invoke(cli, ["repos", "list"])

            assert result.exit_code != 0
            # Check for disabled command error message pattern
            assert (
                "not available" in result.output.lower()
                or "requires:" in result.output.lower()
                or "remote" in result.output.lower()
            )


class TestReposListCommand:
    """Test the 'cidx repos list' command functionality."""

    @pytest.fixture
    def mock_repos_client(self):
        """Create a mock ReposAPIClient for testing."""
        with patch(
            "src.code_indexer.api_clients.repos_client.ReposAPIClient"
        ) as mock_class:
            mock_client = Mock()
            # Make the async methods async mocks
            mock_client.list_activated_repositories = AsyncMock()
            mock_client.list_available_repositories = AsyncMock()
            mock_client.discover_repositories = AsyncMock()
            mock_client.get_repository_status_summary = AsyncMock()
            mock_class.return_value = mock_client
            return mock_client

    def test_repos_list_command_exists(self):
        """Test that repos list command is properly registered."""
        runner = CliRunner()
        result = runner.invoke(cli, ["repos", "--help"])

        assert result.exit_code == 0
        assert "list" in result.output

    @patch("src.code_indexer.cli.CommandModeDetector")
    def test_repos_list_command_success_with_repositories(
        self, mock_detector, mock_repos_client
    ):
        """Test successful execution of repos list command with repositories."""
        # Setup mode detection
        mock_detector.return_value.determine_command_mode.return_value = "remote"

        # Mock repository data
        mock_repositories = [
            ActivatedRepository(
                alias="web-app",
                current_branch="main",
                sync_status="synced",
                last_sync="2024-01-15T10:30:00Z",
                activation_date="2024-01-10T14:20:00Z",
                conflict_details=None,
            ),
            ActivatedRepository(
                alias="api-service",
                current_branch="feature/v2",
                sync_status="needs_sync",
                last_sync="2024-01-14T08:15:00Z",
                activation_date="2024-01-12T09:45:00Z",
                conflict_details=None,
            ),
            ActivatedRepository(
                alias="mobile-app",
                current_branch="develop",
                sync_status="conflict",
                last_sync="2024-01-13T16:00:00Z",
                activation_date="2024-01-11T11:30:00Z",
                conflict_details="Merge conflict in main.py",
            ),
        ]

        mock_repos_client.list_activated_repositories.return_value = mock_repositories

        with patch(
            "src.code_indexer.api_clients.repos_client.ReposAPIClient",
            return_value=mock_repos_client,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["repos", "list"])

        assert result.exit_code == 0
        # Check that repository information is displayed
        assert "web-app" in result.output
        assert "api-service" in result.output
        assert "mobile-app" in result.output
        assert "main" in result.output
        assert "feature/v2" in result.output
        assert "develop" in result.output
        # Check status indicators
        assert "✓" in result.output or "synced" in result.output
        assert (
            "⚠" in result.output
            or "needs_sync" in result.output
            or "needs sync" in result.output
        )
        assert "✗" in result.output or "conflict" in result.output

    @patch("src.code_indexer.cli.CommandModeDetector")
    def test_repos_list_command_empty_repositories(
        self, mock_detector, mock_repos_client
    ):
        """Test repos list command with no repositories."""
        # Setup mode detection
        mock_detector.return_value.determine_command_mode.return_value = "remote"

        mock_repos_client.list_activated_repositories.return_value = []

        with patch(
            "src.code_indexer.api_clients.repos_client.ReposAPIClient",
            return_value=mock_repos_client,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["repos", "list"])

        assert result.exit_code == 0
        assert "No repositories activated" in result.output
        assert "activate" in result.output.lower()  # Should provide guidance

    @patch("src.code_indexer.cli.CommandModeDetector")
    def test_repos_list_command_with_filter(self, mock_detector, mock_repos_client):
        """Test repos list command with filter option."""
        # Setup mode detection
        mock_detector.return_value.determine_command_mode.return_value = "remote"

        mock_repositories = [
            ActivatedRepository(
                alias="web-app",
                current_branch="main",
                sync_status="synced",
                last_sync="2024-01-15T10:30:00Z",
                activation_date="2024-01-10T14:20:00Z",
                conflict_details=None,
            )
        ]

        mock_repos_client.list_activated_repositories.return_value = mock_repositories

        with patch(
            "src.code_indexer.api_clients.repos_client.ReposAPIClient",
            return_value=mock_repos_client,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["repos", "list", "--filter", "web"])

        assert result.exit_code == 0
        # Verify that filter was passed to the client
        mock_repos_client.list_activated_repositories.assert_called_once_with(
            filter_pattern="web"
        )
        assert "web-app" in result.output

    @patch("src.code_indexer.cli.CommandModeDetector")
    def test_repos_list_command_authentication_error(
        self, mock_detector, mock_repos_client
    ):
        """Test repos list command handling authentication errors."""
        # Setup mode detection
        mock_detector.return_value.determine_command_mode.return_value = "remote"

        mock_repos_client.list_activated_repositories.side_effect = AuthenticationError(
            "Token expired"
        )

        with patch(
            "src.code_indexer.api_clients.repos_client.ReposAPIClient",
            return_value=mock_repos_client,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["repos", "list"])

        assert result.exit_code != 0
        assert (
            "authentication" in result.output.lower()
            or "token" in result.output.lower()
        )

    @patch("src.code_indexer.cli.CommandModeDetector")
    def test_repos_list_command_network_error(self, mock_detector, mock_repos_client):
        """Test repos list command handling network errors."""
        # Setup mode detection
        mock_detector.return_value.determine_command_mode.return_value = "remote"

        mock_repos_client.list_activated_repositories.side_effect = APIClientError(
            "Connection failed"
        )

        with patch(
            "src.code_indexer.api_clients.repos_client.ReposAPIClient",
            return_value=mock_repos_client,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["repos", "list"])

        assert result.exit_code != 0
        assert "connection" in result.output.lower() or "error" in result.output.lower()


class TestReposAvailableCommand:
    """Test the 'cidx repos available' command functionality."""

    @pytest.fixture
    def mock_repos_client(self):
        """Create a mock ReposAPIClient for testing."""
        with patch(
            "src.code_indexer.api_clients.repos_client.ReposAPIClient"
        ) as mock_class:
            mock_client = Mock()
            # Make the async methods async mocks
            mock_client.list_activated_repositories = AsyncMock()
            mock_client.list_available_repositories = AsyncMock()
            mock_client.discover_repositories = AsyncMock()
            mock_client.get_repository_status_summary = AsyncMock()
            mock_class.return_value = mock_client
            return mock_client

    @patch("src.code_indexer.cli.CommandModeDetector")
    def test_repos_available_command_success(self, mock_detector, mock_repos_client):
        """Test successful execution of repos available command."""
        # Setup mode detection
        mock_detector.return_value.determine_command_mode.return_value = "remote"

        # Mock repository data
        mock_repositories = [
            GoldenRepository(
                alias="web-framework",
                description="Modern web application framework",
                default_branch="main",
                indexed_branches=["main", "develop", "feature/auth"],
                is_activated=False,
                last_updated="2024-01-15T12:00:00Z",
            ),
            GoldenRepository(
                alias="data-pipeline",
                description="ETL data processing pipeline",
                default_branch="master",
                indexed_branches=["master", "staging"],
                is_activated=True,
                last_updated="2024-01-14T16:30:00Z",
            ),
        ]

        mock_repos_client.list_available_repositories.return_value = mock_repositories

        with patch(
            "src.code_indexer.api_clients.repos_client.ReposAPIClient",
            return_value=mock_repos_client,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["repos", "available"])

        assert result.exit_code == 0
        assert "web-framework" in result.output
        assert "data-pipeline" in result.output
        # Description text may be wrapped in table, check for key parts
        assert "Modern web" in result.output
        assert "framework" in result.output
        assert "ETL data" in result.output
        assert "pipeline" in result.output
        # Check activation status indicators
        assert "Already activated" in result.output or "activated" in result.output

    @patch("src.code_indexer.cli.CommandModeDetector")
    def test_repos_available_command_with_search(
        self, mock_detector, mock_repos_client
    ):
        """Test repos available command with search option."""
        # Setup mode detection
        mock_detector.return_value.determine_command_mode.return_value = "remote"

        mock_repositories = [
            GoldenRepository(
                alias="web-framework",
                description="Modern web application framework",
                default_branch="main",
                indexed_branches=["main"],
                is_activated=False,
                last_updated="2024-01-15T12:00:00Z",
            )
        ]

        mock_repos_client.list_available_repositories.return_value = mock_repositories

        with patch(
            "src.code_indexer.api_clients.repos_client.ReposAPIClient",
            return_value=mock_repos_client,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["repos", "available", "--search", "web"])

        assert result.exit_code == 0
        # Verify that search was passed to the client
        mock_repos_client.list_available_repositories.assert_called_once_with(
            search_term="web"
        )
        assert "web-framework" in result.output

    @patch("src.code_indexer.cli.CommandModeDetector")
    def test_repos_available_command_empty_repositories(
        self, mock_detector, mock_repos_client
    ):
        """Test repos available command with no repositories."""
        # Setup mode detection
        mock_detector.return_value.determine_command_mode.return_value = "remote"

        mock_repos_client.list_available_repositories.return_value = []

        with patch(
            "src.code_indexer.api_clients.repos_client.ReposAPIClient",
            return_value=mock_repos_client,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["repos", "available"])

        assert result.exit_code == 0
        assert "No repositories available" in result.output


class TestReposDiscoverCommand:
    """Test the 'cidx repos discover' command functionality."""

    @pytest.fixture
    def mock_repos_client(self):
        """Create a mock ReposAPIClient for testing."""
        with patch(
            "src.code_indexer.api_clients.repos_client.ReposAPIClient"
        ) as mock_class:
            mock_client = Mock()
            # Make the async methods async mocks
            mock_client.list_activated_repositories = AsyncMock()
            mock_client.list_available_repositories = AsyncMock()
            mock_client.discover_repositories = AsyncMock()
            mock_client.get_repository_status_summary = AsyncMock()
            mock_class.return_value = mock_client
            return mock_client

    @patch("src.code_indexer.cli.CommandModeDetector")
    def test_repos_discover_command_success(self, mock_detector, mock_repos_client):
        """Test successful execution of repos discover command."""
        # Setup mode detection
        mock_detector.return_value.determine_command_mode.return_value = "remote"

        # Mock discovery result
        mock_result = RepositoryDiscoveryResult(
            discovered_repositories=[
                DiscoveredRepository(
                    name="awesome-project",
                    url="https://github.com/myorg/awesome-project",
                    description="An awesome open source project",
                    is_available=False,
                    is_accessible=True,
                    default_branch="main",
                    last_updated="2024-01-15T10:00:00Z",
                ),
                DiscoveredRepository(
                    name="internal-tool",
                    url="https://github.com/myorg/internal-tool",
                    description="Internal development tool",
                    is_available=True,
                    is_accessible=True,
                    default_branch="master",
                    last_updated="2024-01-14T14:30:00Z",
                ),
            ],
            source="github.com/myorg",
            total_discovered=2,
            access_errors=[],
        )

        mock_repos_client.discover_repositories.return_value = mock_result

        with patch(
            "src.code_indexer.api_clients.repos_client.ReposAPIClient",
            return_value=mock_repos_client,
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli, ["repos", "discover", "--source", "github.com/myorg"]
            )

        assert result.exit_code == 0
        # Names may be truncated in table, check for partial matches
        assert "awesome-proj" in result.output  # May be truncated
        assert "internal-tool" in result.output
        assert "github.com/myorg" in result.output
        # Verify the source was passed to the client
        mock_repos_client.discover_repositories.assert_called_once_with(
            "github.com/myorg"
        )

    @patch("src.code_indexer.cli.CommandModeDetector")
    def test_repos_discover_command_with_access_errors(
        self, mock_detector, mock_repos_client
    ):
        """Test repos discover command with access errors."""
        # Setup mode detection
        mock_detector.return_value.determine_command_mode.return_value = "remote"

        # Mock discovery result with access errors
        mock_result = RepositoryDiscoveryResult(
            discovered_repositories=[
                DiscoveredRepository(
                    name="public-repo",
                    url="https://github.com/org/public-repo",
                    description="Public repository",
                    is_available=False,
                    is_accessible=True,
                    default_branch="main",
                    last_updated="2024-01-15T10:00:00Z",
                )
            ],
            source="github.com/org",
            total_discovered=1,
            access_errors=[
                "Repository 'private-repo' requires authentication",
                "Repository 'archived-repo' is archived and cannot be accessed",
            ],
        )

        mock_repos_client.discover_repositories.return_value = mock_result

        with patch(
            "src.code_indexer.api_clients.repos_client.ReposAPIClient",
            return_value=mock_repos_client,
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli, ["repos", "discover", "--source", "github.com/org"]
            )

        assert result.exit_code == 0
        assert "public-repo" in result.output
        assert "requires authentication" in result.output
        assert "archived" in result.output

    @patch("src.code_indexer.cli.CommandModeDetector")
    def test_repos_discover_command_missing_source(self, mock_detector):
        """Test repos discover command without required source parameter."""
        # Setup mode detection
        mock_detector.return_value.determine_command_mode.return_value = "remote"

        runner = CliRunner()
        result = runner.invoke(cli, ["repos", "discover"])

        assert result.exit_code != 0
        assert "source" in result.output.lower()

    @patch("src.code_indexer.cli.CommandModeDetector")
    def test_repos_discover_command_invalid_source(
        self, mock_detector, mock_repos_client
    ):
        """Test repos discover command with invalid source."""
        # Setup mode detection
        mock_detector.return_value.determine_command_mode.return_value = "remote"

        mock_repos_client.discover_repositories.side_effect = APIClientError(
            "Invalid source format"
        )

        with patch(
            "src.code_indexer.api_clients.repos_client.ReposAPIClient",
            return_value=mock_repos_client,
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli, ["repos", "discover", "--source", "invalid-source"]
            )

        assert result.exit_code != 0
        assert "invalid" in result.output.lower() or "error" in result.output.lower()


class TestReposStatusCommand:
    """Test the 'cidx repos status' command functionality."""

    @pytest.fixture
    def mock_repos_client(self):
        """Create a mock ReposAPIClient for testing."""
        with patch(
            "src.code_indexer.api_clients.repos_client.ReposAPIClient"
        ) as mock_class:
            mock_client = Mock()
            # Make the async methods async mocks
            mock_client.list_activated_repositories = AsyncMock()
            mock_client.list_available_repositories = AsyncMock()
            mock_client.discover_repositories = AsyncMock()
            mock_client.get_repository_status_summary = AsyncMock()
            mock_class.return_value = mock_client
            return mock_client

    @patch("src.code_indexer.cli.CommandModeDetector")
    def test_repos_status_command_success(self, mock_detector, mock_repos_client):
        """Test successful execution of repos status command."""
        # Setup mode detection
        mock_detector.return_value.determine_command_mode.return_value = "remote"

        # Mock status summary
        mock_summary = RepositoryStatusSummary(
            activated_repositories=ActivatedRepositorySummary(
                total_count=3,
                synced_count=1,
                needs_sync_count=1,
                conflict_count=1,
                recent_activations=[
                    {"alias": "new-project", "activation_date": "2024-01-15T10:00:00Z"}
                ],
            ),
            available_repositories=AvailableRepositorySummary(
                total_count=10, not_activated_count=7
            ),
            recent_activity=RecentActivity(
                recent_syncs=[
                    {
                        "alias": "web-app",
                        "sync_date": "2024-01-15T09:30:00Z",
                        "status": "success",
                    }
                ]
            ),
            recommendations=[
                "Consider syncing 'api-service' (last sync 3 days ago)",
                "Resolve conflicts in 'mobile-app' repository",
            ],
        )

        mock_repos_client.get_repository_status_summary.return_value = mock_summary

        with patch(
            "src.code_indexer.api_clients.repos_client.ReposAPIClient",
            return_value=mock_repos_client,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["repos", "status"])

        assert result.exit_code == 0
        # Check that summary information is displayed
        assert "3" in result.output  # total activated repositories
        assert "10" in result.output  # total available repositories
        assert "1" in result.output  # synced/needs_sync/conflict counts
        assert "new-project" in result.output  # recent activations
        assert "web-app" in result.output  # recent syncs
        assert "api-service" in result.output  # recommendations
        assert "mobile-app" in result.output

    @patch("src.code_indexer.cli.CommandModeDetector")
    def test_repos_status_command_empty_state(self, mock_detector, mock_repos_client):
        """Test repos status command with no repositories."""
        # Setup mode detection
        mock_detector.return_value.determine_command_mode.return_value = "remote"

        # Mock empty status summary
        mock_summary = RepositoryStatusSummary(
            activated_repositories=ActivatedRepositorySummary(
                total_count=0,
                synced_count=0,
                needs_sync_count=0,
                conflict_count=0,
                recent_activations=[],
            ),
            available_repositories=AvailableRepositorySummary(
                total_count=5, not_activated_count=5
            ),
            recent_activity=RecentActivity(recent_syncs=[]),
            recommendations=[
                "No repositories activated yet. Use 'cidx repos available' to browse and activate repositories."
            ],
        )

        mock_repos_client.get_repository_status_summary.return_value = mock_summary

        with patch(
            "src.code_indexer.api_clients.repos_client.ReposAPIClient",
            return_value=mock_repos_client,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["repos", "status"])

        assert result.exit_code == 0
        assert "No repositories activated" in result.output
        assert "repos available" in result.output


class TestTableFormatting:
    """Test rich table formatting for repository displays."""

    def test_repository_list_table_formatting(self):
        """Test that repository list displays as a properly formatted table."""
        repositories = [
            ActivatedRepository(
                alias="web-app",
                current_branch="main",
                sync_status="synced",
                last_sync="2024-01-15T10:30:00Z",
                activation_date="2024-01-10T14:20:00Z",
                conflict_details=None,
            ),
            ActivatedRepository(
                alias="api-service",
                current_branch="feature/v2",
                sync_status="needs_sync",
                last_sync="2024-01-14T08:15:00Z",
                activation_date="2024-01-12T09:45:00Z",
                conflict_details=None,
            ),
        ]

        # Import and test the formatting function
        from src.code_indexer.cli import format_repository_list

        formatted_output = format_repository_list(repositories)

        # Check table structure
        assert "┌" in formatted_output or "│" in formatted_output  # Table borders
        assert "Alias" in formatted_output
        assert "Branch" in formatted_output
        assert "Sync Status" in formatted_output
        assert "web-app" in formatted_output
        assert "api-service" in formatted_output

    def test_available_repositories_table_formatting(self):
        """Test that available repositories display as a properly formatted table."""
        repositories = [
            GoldenRepository(
                alias="web-framework",
                description="Modern web application framework",
                default_branch="main",
                indexed_branches=["main", "develop"],
                is_activated=False,
                last_updated="2024-01-15T12:00:00Z",
            )
        ]

        # Import and test the formatting function
        from src.code_indexer.cli import format_available_repositories

        formatted_output = format_available_repositories(repositories)

        # Check table structure and content
        assert "web-framework" in formatted_output
        assert "Modern web application framework" in formatted_output
        assert "main" in formatted_output

    def test_discovery_results_formatting(self):
        """Test that discovery results display with actionable information."""
        discovery_result = RepositoryDiscoveryResult(
            discovered_repositories=[
                DiscoveredRepository(
                    name="awesome-project",
                    url="https://github.com/myorg/awesome-project",
                    description="An awesome open source project",
                    is_available=False,
                    is_accessible=True,
                    default_branch="main",
                    last_updated="2024-01-15T10:00:00Z",
                )
            ],
            source="github.com/myorg",
            total_discovered=1,
            access_errors=[],
        )

        # Import and test the formatting function
        from src.code_indexer.cli import format_discovery_results

        formatted_output = format_discovery_results(discovery_result)

        # Check content and actionable information
        assert "awesome-project" in formatted_output
        assert "github.com/myorg" in formatted_output
        assert "1" in formatted_output  # total discovered

    def test_status_summary_dashboard_formatting(self):
        """Test that status summary displays in dashboard-style layout."""
        summary = RepositoryStatusSummary(
            activated_repositories=ActivatedRepositorySummary(
                total_count=3,
                synced_count=1,
                needs_sync_count=1,
                conflict_count=1,
                recent_activations=[],
            ),
            available_repositories=AvailableRepositorySummary(
                total_count=10, not_activated_count=7
            ),
            recent_activity=RecentActivity(recent_syncs=[]),
            recommendations=["Test recommendation"],
        )

        # Import and test the formatting function
        from src.code_indexer.cli import format_status_summary

        formatted_output = format_status_summary(summary)

        # Check dashboard-style information
        assert "3" in formatted_output  # total activated
        assert "10" in formatted_output  # total available
        assert "Test recommendation" in formatted_output
