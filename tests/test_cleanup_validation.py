"""Tests for cleanup validation with HealthChecker integration."""

from unittest.mock import Mock, patch

from code_indexer.services.docker_manager import DockerManager
from code_indexer.services.health_checker import HealthChecker


class TestCleanupValidation:
    """Test cleanup validation functionality."""

    def setup_method(self):
        """Setup test environment."""
        self.mock_console = Mock()
        self.docker_manager = DockerManager(
            console=self.mock_console, project_name="test_shared", force_docker=False
        )

    def test_health_checker_initialization(self):
        """Test that DockerManager initializes HealthChecker."""
        assert isinstance(self.docker_manager.health_checker, HealthChecker)

    @patch.object(HealthChecker, "wait_for_cleanup_complete")
    def test_cleanup_validation_calls_health_checker(self, mock_wait_cleanup):
        """Test that cleanup validation calls HealthChecker correctly."""
        # Mock successful cleanup validation
        mock_wait_cleanup.return_value = True

        # Mock the compose command to avoid actual Docker calls
        with patch.object(self.docker_manager, "get_compose_command") as mock_compose:
            mock_compose.return_value = ["docker-compose"]

            # Mock compose file existence to trigger validation path
            with patch("pathlib.Path.exists") as mock_exists:
                mock_exists.return_value = True

                # Mock subprocess calls to avoid actual container operations
                with patch(
                    "code_indexer.services.docker_manager.subprocess.run"
                ) as mock_run:
                    mock_run.return_value.returncode = 0
                    mock_run.return_value.stdout = ""

                    # Call cleanup with validation
                    self.docker_manager.cleanup(validate=True, verbose=True)

                    # Verify HealthChecker was called
                    mock_wait_cleanup.assert_called_once()

                # Verify correct parameters were passed
                call_args = mock_wait_cleanup.call_args
                assert "container_names" in call_args.kwargs
                assert "ports" in call_args.kwargs
                assert "container_engine" in call_args.kwargs

                # Check container names include project prefix
                container_names = call_args.kwargs["container_names"]
                # The project name is auto-detected from current directory name
                assert any("ollama" in name for name in container_names)
                assert any("qdrant" in name for name in container_names)
                assert any("data-cleaner" in name for name in container_names)

                # Check required ports
                ports = call_args.kwargs["ports"]
                assert 6333 in ports  # Qdrant
                assert 11434 in ports  # Ollama
                assert 8091 in ports  # DataCleaner

    @patch.object(HealthChecker, "wait_for_cleanup_complete")
    def test_cleanup_validation_timeout(self, mock_wait_cleanup):
        """Test cleanup validation timeout handling."""
        # Mock cleanup validation timeout
        mock_wait_cleanup.return_value = False

        # Mock the compose command and subprocess to avoid actual Docker calls
        with patch.object(
            self.docker_manager, "get_compose_command"
        ) as mock_compose, patch(
            "code_indexer.services.docker_manager.subprocess.run"
        ) as mock_run:
            mock_compose.return_value = ["docker-compose"]
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""

            # Mock compose file existence to trigger validation path
            with patch("pathlib.Path.exists") as mock_exists:
                mock_exists.return_value = True

                self.docker_manager.cleanup(validate=True, verbose=True)

                # Cleanup should still succeed even if validation times out
                mock_wait_cleanup.assert_called_once()

                # Check that timeout warning was printed
                self.mock_console.print.assert_any_call(
                    "⚠️  Cleanup validation timed out, continuing anyway...",
                    style="yellow",
                )

    @patch.object(HealthChecker, "wait_for_cleanup_complete")
    def test_cleanup_validation_disabled(self, mock_wait_cleanup):
        """Test cleanup without validation."""
        # Mock the compose command and subprocess to avoid actual Docker calls
        with patch.object(
            self.docker_manager, "get_compose_command"
        ) as mock_compose, patch(
            "code_indexer.services.docker_manager.subprocess.run"
        ) as mock_run:
            mock_compose.return_value = ["docker-compose"]
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""

            self.docker_manager.cleanup(validate=False)

            # HealthChecker should not be called when validation is disabled
            mock_wait_cleanup.assert_not_called()

    @patch.object(HealthChecker, "wait_for_ports_available")
    @patch.object(HealthChecker, "is_port_available")
    def test_validate_cleanup_method_success(
        self, mock_is_port_available, mock_wait_ports
    ):
        """Test _validate_cleanup method with successful port validation."""
        mock_wait_ports.return_value = True

        # Mock container checking
        with patch(
            "code_indexer.services.docker_manager.subprocess.run"
        ) as mock_subprocess:
            mock_subprocess.return_value.stdout = ""  # No containers running

            result = self.docker_manager._validate_cleanup(verbose=True)

            assert result is True
            mock_wait_ports.assert_called_once_with([11434, 6333], timeout=10)

            # Check success message
            self.mock_console.print.assert_any_call(
                "✅ All critical ports [11434, 6333] are free"
            )

    @patch.object(HealthChecker, "wait_for_ports_available")
    @patch.object(HealthChecker, "is_port_available")
    def test_validate_cleanup_method_port_timeout(
        self, mock_is_port_available, mock_wait_ports
    ):
        """Test _validate_cleanup method with port validation timeout."""
        mock_wait_ports.return_value = False

        # Mock individual port checks for detailed reporting
        mock_is_port_available.side_effect = (
            lambda port: port != 11434
        )  # Port 11434 still in use

        # Mock container checking
        with patch(
            "code_indexer.services.docker_manager.subprocess.run"
        ) as mock_subprocess:
            mock_subprocess.return_value.stdout = ""  # No containers running

            result = self.docker_manager._validate_cleanup(verbose=True)

            # Should still return True (ports don't fail validation)
            assert result is True
            mock_wait_ports.assert_called_once_with([11434, 6333], timeout=10)

            # Check that individual port status was reported
            mock_is_port_available.assert_any_call(11434)
            mock_is_port_available.assert_any_call(6333)

            # Check warning messages
            self.mock_console.print.assert_any_call(
                "❌ Port 11434 still in use after cleanup", style="red"
            )
            self.mock_console.print.assert_any_call(
                "⚠️  Port cleanup delayed (common with podman rootless)", style="yellow"
            )

    def test_docker_manager_force_docker_flag(self):
        """Test that force_docker flag affects container engine detection."""
        docker_manager = DockerManager(
            console=self.mock_console, project_name="test_shared", force_docker=True
        )

        with patch.object(
            docker_manager.health_checker, "wait_for_cleanup_complete"
        ) as mock_wait_cleanup, patch.object(
            docker_manager, "get_compose_command"
        ) as mock_compose, patch(
            "code_indexer.services.docker_manager.subprocess.run"
        ) as mock_run:
            mock_compose.return_value = ["docker-compose"]
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_wait_cleanup.return_value = True

            # Mock compose file existence to trigger validation path
            with patch("pathlib.Path.exists") as mock_exists:
                mock_exists.return_value = True

                docker_manager.cleanup(validate=True)

                # Should use docker engine when force_docker=True
                call_args = mock_wait_cleanup.call_args
                assert call_args.kwargs["container_engine"] == "docker"

    @patch.object(HealthChecker, "wait_for_cleanup_complete")
    def test_cleanup_integration_with_health_checker_config(self, mock_wait_cleanup):
        """Test that HealthChecker uses engine-optimized timeouts."""
        mock_wait_cleanup.return_value = True

        # Mock the compose command and subprocess to avoid actual Docker calls
        with patch.object(
            self.docker_manager, "get_compose_command"
        ) as mock_compose, patch(
            "code_indexer.services.docker_manager.subprocess.run"
        ) as mock_run:
            mock_compose.return_value = ["docker-compose"]
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""

            # Mock compose file existence to trigger validation path
            with patch("pathlib.Path.exists") as mock_exists:
                mock_exists.return_value = True

                self.docker_manager.cleanup(validate=True)

                # Verify that timeout=None is passed (uses engine-optimized timeout)
                call_args = mock_wait_cleanup.call_args
                assert call_args.kwargs["timeout"] is None


class TestHealthCheckerPortValidation:
    """Test port validation functionality specifically."""

    def test_port_validation_integration(self):
        """Test that port validation works with real HealthChecker."""
        health_checker = HealthChecker()

        # Test with a high port that should be available
        high_port = 65500
        assert health_checker.is_port_available(high_port) is True

        # Test waiting for ports to be available
        result = health_checker.wait_for_ports_available(
            [high_port, high_port + 1], timeout=5
        )
        assert result is True

    def test_cleanup_complete_validation(self):
        """Test cleanup complete validation logic."""
        health_checker = HealthChecker()

        # Test with containers that shouldn't exist and ports that should be free
        result = health_checker.wait_for_cleanup_complete(
            container_names=["nonexistent-container"],
            ports=[65500, 65501],
            container_engine="podman",
            timeout=5,
        )

        assert (
            result is True
        )  # Should succeed with nonexistent containers and free ports

    @patch("code_indexer.services.health_checker.subprocess.run")
    def test_container_stopped_check(self, mock_subprocess):
        """Test container stopped checking."""
        health_checker = HealthChecker()

        # Mock container not running
        mock_subprocess.return_value.stdout = ""

        result = health_checker.is_container_stopped("test-container", "podman")
        assert result is True

        mock_subprocess.assert_called_once_with(
            [
                "podman",
                "ps",
                "--filter",
                "name=test-container",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
