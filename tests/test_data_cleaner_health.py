"""Tests for data cleaner health check integration."""

from unittest.mock import Mock, patch, MagicMock

from code_indexer.services.docker_manager import DockerManager
from code_indexer.services.health_checker import HealthChecker


class TestDataCleanerHealth:
    """Test data cleaner health check functionality."""

    def setup_method(self):
        """Setup test environment."""
        self.mock_console = Mock()
        self.docker_manager = DockerManager(
            console=self.mock_console, project_name="test_shared", force_docker=False
        )

    @patch.object(HealthChecker, "get_timeouts")
    @patch.object(HealthChecker, "wait_for_service_ready")
    def test_data_cleaner_health_check_success(
        self, mock_wait_service, mock_get_timeouts
    ):
        """Test successful data cleaner health check."""
        # Mock health check success
        mock_wait_service.return_value = True
        mock_get_timeouts.return_value = {"data_cleaner_startup": 120}

        # Mock data cleaner running check and start
        with patch.object(
            self.docker_manager, "start_data_cleaner"
        ) as mock_start, patch(
            "code_indexer.services.docker_manager.subprocess.run"
        ) as mock_run:
            mock_start.return_value = True
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""  # Data cleaner not running initially

            result = self.docker_manager.clean_with_data_cleaner(["/data/test"])

            # Should succeed with health check
            assert result is True
            mock_wait_service.assert_called_once_with(
                "http://localhost:8091",
                timeout=120,  # Default data_cleaner_startup timeout
            )

    @patch.object(HealthChecker, "get_timeouts")
    @patch.object(HealthChecker, "wait_for_service_ready")
    def test_data_cleaner_health_check_timeout(
        self, mock_wait_service, mock_get_timeouts
    ):
        """Test data cleaner health check timeout."""
        # Mock health check timeout
        mock_wait_service.return_value = False
        mock_get_timeouts.return_value = {"data_cleaner_startup": 120}

        # Mock data cleaner start
        with patch.object(
            self.docker_manager, "start_data_cleaner"
        ) as mock_start, patch(
            "code_indexer.services.docker_manager.subprocess.run"
        ) as mock_run:
            mock_start.return_value = True
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""  # Data cleaner not running initially

            result = self.docker_manager.clean_with_data_cleaner(["/data/test"])

            # Should fail when health check times out
            assert result is False
            mock_wait_service.assert_called_once()

            # Check error message was printed
            self.mock_console.print.assert_any_call(
                "❌ Data cleaner failed to become ready", style="red"
            )

    @patch.object(HealthChecker, "get_timeouts")
    @patch.object(HealthChecker, "wait_for_service_ready")
    def test_data_cleaner_already_running_with_health_check(
        self, mock_wait_service, mock_get_timeouts
    ):
        """Test that health check is performed when data cleaner is already running (for reliability)."""
        # Mock health check to return success
        mock_wait_service.return_value = True
        mock_get_timeouts.return_value = {"data_cleaner_startup": 120}

        # Mock multiple subprocess calls that clean_with_data_cleaner makes
        def mock_subprocess_calls(*args, **kwargs):
            mock_result = Mock()
            mock_result.returncode = 0

            # Handle different subprocess calls
            if args[0][0] == "which":
                mock_result.stdout = ""  # No podman, use docker
            elif "ps" in args[0]:
                mock_result.stdout = (
                    "test-project-data-cleaner"  # Container already running
                )
            else:
                mock_result.stdout = ""  # Other calls succeed
                mock_result.stderr = ""

            return mock_result

        with patch(
            "code_indexer.services.docker_manager.subprocess.run",
            side_effect=mock_subprocess_calls,
        ):
            result = self.docker_manager.clean_with_data_cleaner(["/data/test"])

            # Should succeed and perform health check even when already running (for reliability)
            assert result is True
            mock_wait_service.assert_called_once_with(
                "http://localhost:8091",
                timeout=120,  # Default data_cleaner_startup timeout
            )

    @patch.object(HealthChecker, "get_timeouts")
    @patch.object(HealthChecker, "wait_for_service_ready")
    def test_data_cleaner_uses_configured_timeout(
        self, mock_wait_service, mock_get_timeouts
    ):
        """Test that data cleaner uses configured timeout."""
        # Mock custom timeout configuration
        mock_get_timeouts.return_value = {
            "data_cleaner_startup": 120  # Custom 2-minute timeout
        }
        mock_wait_service.return_value = True

        # Mock data cleaner start
        with patch.object(
            self.docker_manager, "start_data_cleaner"
        ) as mock_start, patch(
            "code_indexer.services.docker_manager.subprocess.run"
        ) as mock_run:
            mock_start.return_value = True
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""  # Data cleaner not running initially

            result = self.docker_manager.clean_with_data_cleaner(["/data/test"])

            assert result is True
            mock_wait_service.assert_called_once_with(
                "http://localhost:8091",
                timeout=120,  # Custom timeout should be used
            )

    @patch.object(HealthChecker, "get_timeouts")
    @patch.object(HealthChecker, "wait_for_service_ready")
    def test_data_cleaner_start_failure(self, mock_wait_service, mock_get_timeouts):
        """Test handling when data cleaner fails to start."""
        # Mock timeouts but won't be used since start fails
        mock_get_timeouts.return_value = {"data_cleaner_startup": 120}

        # Mock data cleaner start failure
        with patch.object(
            self.docker_manager, "start_data_cleaner"
        ) as mock_start, patch(
            "code_indexer.services.docker_manager.subprocess.run"
        ) as mock_run:
            mock_start.return_value = False  # Start failed
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""  # Data cleaner not running initially

            result = self.docker_manager.clean_with_data_cleaner(["/data/test"])

            # Should fail without calling health check
            assert result is False
            mock_wait_service.assert_not_called()

    def test_health_checker_service_ready_real_integration(self):
        """Test HealthChecker.wait_for_service_ready with real HTTP simulation."""
        health_checker = HealthChecker()

        # Test with a URL that should not be reachable (timeout quickly)
        result = health_checker.wait_for_service_ready(
            "http://localhost:65432",
            timeout=1,  # High port unlikely to be in use
        )

        assert result is False  # Should timeout quickly

    @patch("code_indexer.services.health_checker.httpx.Client")
    def test_health_checker_service_ready_success(self, mock_client_class):
        """Test HealthChecker.wait_for_service_ready success scenario."""
        health_checker = HealthChecker()

        # Mock successful HTTP response
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.get.return_value = mock_response

        result = health_checker.wait_for_service_ready(
            "http://localhost:8091", timeout=5
        )

        assert result is True
        mock_client.get.assert_called_with("http://localhost:8091")

    @patch("code_indexer.services.health_checker.httpx.Client")
    def test_health_checker_service_ready_failure(self, mock_client_class):
        """Test HealthChecker.wait_for_service_ready failure scenario."""
        health_checker = HealthChecker()

        # Mock HTTP error response
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 500
        mock_client.get.return_value = mock_response

        result = health_checker.wait_for_service_ready(
            "http://localhost:8091", timeout=1
        )

        assert result is False


class TestDataCleanerIntegration:
    """Integration tests for data cleaner functionality."""

    def setup_method(self):
        """Setup test environment."""
        self.mock_console = Mock()
        self.docker_manager = DockerManager(
            console=self.mock_console, project_name="test_shared", force_docker=False
        )

    def test_clean_with_data_cleaner_workflow(self):
        """Test the complete data cleaner workflow."""
        # Mock all external dependencies
        with patch.object(
            self.docker_manager, "start_data_cleaner"
        ) as mock_start, patch.object(
            self.docker_manager.health_checker, "wait_for_service_ready"
        ) as mock_health, patch(
            "code_indexer.services.docker_manager.subprocess.run"
        ) as mock_run:
            # Setup mocks for successful workflow
            mock_start.return_value = True
            mock_health.return_value = True

            # Mock subprocess calls
            run_responses = [
                Mock(returncode=0, stdout=""),  # Data cleaner not running check
                Mock(returncode=0, stdout="docker"),  # Container engine detection
                Mock(returncode=0, stdout=""),  # Cleanup command execution
            ]
            mock_run.side_effect = run_responses

            result = self.docker_manager.clean_with_data_cleaner(["/data/qdrant/test"])

            assert result is True
            mock_start.assert_called_once()
            mock_health.assert_called_once_with("http://localhost:8091", timeout=120)

    def test_data_cleaner_error_propagation(self):
        """Test that data cleaner errors are properly propagated."""
        # Mock health check failure
        with patch.object(
            self.docker_manager, "start_data_cleaner"
        ) as mock_start, patch.object(
            self.docker_manager.health_checker, "wait_for_service_ready"
        ) as mock_health, patch(
            "code_indexer.services.docker_manager.subprocess.run"
        ) as mock_run:
            mock_start.return_value = True
            mock_health.return_value = False  # Health check fails
            mock_run.return_value = Mock(returncode=0, stdout="")

            result = self.docker_manager.clean_with_data_cleaner(["/data/test"])

            assert result is False

            # Verify error handling
            self.mock_console.print.assert_any_call(
                "❌ Data cleaner failed to become ready", style="red"
            )
