"""Unit tests for DeploymentExecutor maintenance mode drain flow.

Story #734: Job-Aware Auto-Update with Graceful Drain Mode

Tests AC3 (Auto-Update Uses Maintenance Mode) and AC4 (Graceful Timeout).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile


class TestDeploymentExecutorInit:
    """Test DeploymentExecutor constructor with new parameters."""

    def test_accepts_server_url_parameter(self):
        """DeploymentExecutor should accept server_url parameter."""
        from code_indexer.server.auto_update.deployment_executor import (
            DeploymentExecutor,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            executor = DeploymentExecutor(
                repo_path=Path(tmpdir),
                server_url="http://localhost:8000",
            )
            assert executor.server_url == "http://localhost:8000"

    def test_default_server_url(self):
        """DeploymentExecutor should default server_url to localhost:8000."""
        from code_indexer.server.auto_update.deployment_executor import (
            DeploymentExecutor,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            executor = DeploymentExecutor(repo_path=Path(tmpdir))
            assert executor.server_url == "http://localhost:8000"

    def test_accepts_drain_timeout_parameter(self):
        """DeploymentExecutor should accept drain_timeout parameter."""
        from code_indexer.server.auto_update.deployment_executor import (
            DeploymentExecutor,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            executor = DeploymentExecutor(
                repo_path=Path(tmpdir),
                drain_timeout=600,
            )
            assert executor.drain_timeout == 600

    def test_default_drain_timeout(self):
        """DeploymentExecutor should default drain_timeout to 300 seconds."""
        from code_indexer.server.auto_update.deployment_executor import (
            DeploymentExecutor,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            executor = DeploymentExecutor(repo_path=Path(tmpdir))
            assert executor.drain_timeout == 300

    def test_accepts_drain_poll_interval_parameter(self):
        """DeploymentExecutor should accept drain_poll_interval parameter."""
        from code_indexer.server.auto_update.deployment_executor import (
            DeploymentExecutor,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            executor = DeploymentExecutor(
                repo_path=Path(tmpdir),
                drain_poll_interval=5,
            )
            assert executor.drain_poll_interval == 5

    def test_default_drain_poll_interval(self):
        """DeploymentExecutor should default drain_poll_interval to 10 seconds."""
        from code_indexer.server.auto_update.deployment_executor import (
            DeploymentExecutor,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            executor = DeploymentExecutor(repo_path=Path(tmpdir))
            assert executor.drain_poll_interval == 10


class TestDeploymentExecutorMaintenanceMethods:
    """Test maintenance mode methods."""

    def test_enter_maintenance_mode_success(self):
        """_enter_maintenance_mode should call server API and return True on success."""
        from code_indexer.server.auto_update.deployment_executor import (
            DeploymentExecutor,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            executor = DeploymentExecutor(repo_path=Path(tmpdir))

            with patch("requests.post") as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"maintenance_mode": True}
                mock_post.return_value = mock_response

                result = executor._enter_maintenance_mode()

                assert result is True
                mock_post.assert_called_once()
                call_url = mock_post.call_args[0][0]
                assert "/api/admin/maintenance/enter" in call_url

    def test_wait_for_drain_succeeds_when_already_drained(self):
        """_wait_for_drain should return True immediately when already drained."""
        from code_indexer.server.auto_update.deployment_executor import (
            DeploymentExecutor,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            executor = DeploymentExecutor(repo_path=Path(tmpdir))

            with patch("requests.get") as mock_get:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"drained": True}
                mock_get.return_value = mock_response

                result = executor._wait_for_drain()

                assert result is True

    def test_exit_maintenance_mode_success(self):
        """_exit_maintenance_mode should call server API and return True on success."""
        from code_indexer.server.auto_update.deployment_executor import (
            DeploymentExecutor,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            executor = DeploymentExecutor(repo_path=Path(tmpdir))

            with patch("requests.post") as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"maintenance_mode": False}
                mock_post.return_value = mock_response

                result = executor._exit_maintenance_mode()

                assert result is True
                mock_post.assert_called_once()
                call_url = mock_post.call_args[0][0]
                assert "/api/admin/maintenance/exit" in call_url


class TestDeploymentExecutorRestartFlow:
    """Test restart_server maintenance mode flow."""

    def test_restart_server_uses_maintenance_flow(self):
        """restart_server should call maintenance flow methods in order."""
        from code_indexer.server.auto_update.deployment_executor import (
            DeploymentExecutor,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            executor = DeploymentExecutor(repo_path=Path(tmpdir))

            with (
                patch.object(executor, "_enter_maintenance_mode") as mock_enter,
                patch.object(executor, "_wait_for_drain") as mock_drain,
                patch("subprocess.run") as mock_run,
            ):
                mock_enter.return_value = True
                mock_drain.return_value = True
                mock_run.return_value = MagicMock(returncode=0)

                result = executor.restart_server()

                assert result is True
                mock_enter.assert_called_once()
                mock_drain.assert_called_once()

    def test_restart_server_proceeds_on_drain_timeout(self):
        """AC4: restart_server should proceed with restart even when drain times out."""
        from code_indexer.server.auto_update.deployment_executor import (
            DeploymentExecutor,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            executor = DeploymentExecutor(repo_path=Path(tmpdir))

            with (
                patch.object(executor, "_enter_maintenance_mode") as mock_enter,
                patch.object(executor, "_wait_for_drain") as mock_drain,
                patch("subprocess.run") as mock_run,
            ):
                mock_enter.return_value = True
                mock_drain.return_value = False  # Drain timeout exceeded
                mock_run.return_value = MagicMock(returncode=0)

                result = executor.restart_server()

                # Should still succeed - force restart after timeout
                assert result is True
                mock_enter.assert_called_once()
                mock_drain.assert_called_once()
                mock_run.assert_called_once()  # Restart still executed


class TestDeploymentExecutorForceRestartLogging:
    """Test AC4: Log running jobs at WARNING level when forcing restart."""

    def test_force_restart_logs_running_jobs(self):
        """AC4: When drain times out, should log running jobs at WARNING level."""
        from code_indexer.server.auto_update.deployment_executor import (
            DeploymentExecutor,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            executor = DeploymentExecutor(repo_path=Path(tmpdir))

            mock_jobs = [
                {
                    "job_id": "job-123",
                    "operation_type": "add_golden_repo",
                    "started_at": "2025-01-17T10:00:00Z",
                    "progress": 50,
                },
            ]

            with (
                patch.object(executor, "_enter_maintenance_mode") as mock_enter,
                patch.object(executor, "_wait_for_drain") as mock_drain,
                patch.object(
                    executor, "_get_running_jobs_for_logging"
                ) as mock_get_jobs,
                patch("subprocess.run") as mock_run,
                patch(
                    "code_indexer.server.auto_update.deployment_executor.logger"
                ) as mock_logger,
            ):
                mock_enter.return_value = True
                mock_drain.return_value = False  # Drain timeout exceeded
                mock_get_jobs.return_value = mock_jobs
                mock_run.return_value = MagicMock(returncode=0)

                result = executor.restart_server()

                assert result is True
                mock_logger.warning.assert_called()
                warning_calls = [
                    str(call) for call in mock_logger.warning.call_args_list
                ]
                assert any(
                    "job-123" in str(call) or "running" in str(call).lower()
                    for call in warning_calls
                )

    def test_get_running_jobs_for_logging_fetches_from_drain_status(self):
        """_get_running_jobs_for_logging should fetch jobs from drain-status endpoint."""
        from code_indexer.server.auto_update.deployment_executor import (
            DeploymentExecutor,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            executor = DeploymentExecutor(repo_path=Path(tmpdir))

            mock_jobs = [
                {
                    "job_id": "job-789",
                    "operation_type": "refresh_repo",
                    "started_at": "2025-01-17T10:10:00Z",
                    "progress": 75,
                }
            ]

            with patch("requests.get") as mock_get:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "drained": False,
                    "running_jobs": 1,
                    "queued_jobs": 0,
                    "jobs": mock_jobs,
                }
                mock_get.return_value = mock_response

                result = executor._get_running_jobs_for_logging()

                assert result == mock_jobs
                mock_get.assert_called_once()
                call_url = mock_get.call_args[0][0]
                assert "/api/admin/maintenance/drain-status" in call_url

    def test_get_running_jobs_for_logging_handles_connection_error(self):
        """_get_running_jobs_for_logging should return empty list on connection error."""
        from code_indexer.server.auto_update.deployment_executor import (
            DeploymentExecutor,
        )
        import requests

        with tempfile.TemporaryDirectory() as tmpdir:
            executor = DeploymentExecutor(repo_path=Path(tmpdir))

            with patch("requests.get") as mock_get:
                mock_get.side_effect = requests.exceptions.ConnectionError()

                result = executor._get_running_jobs_for_logging()

                assert result == []


class TestDeploymentExecutorDrainSuccessLogging:
    """Test that successful drain emits a log message."""

    def test_drain_success_logs_info_message(self):
        """When drain succeeds, should log info message before restart."""
        from code_indexer.server.auto_update.deployment_executor import (
            DeploymentExecutor,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            executor = DeploymentExecutor(repo_path=Path(tmpdir))

            with (
                patch.object(executor, "_enter_maintenance_mode") as mock_enter,
                patch.object(executor, "_wait_for_drain") as mock_drain,
                patch("subprocess.run") as mock_run,
                patch(
                    "code_indexer.server.auto_update.deployment_executor.logger"
                ) as mock_logger,
            ):
                mock_enter.return_value = True
                mock_drain.return_value = True  # Drain succeeds
                mock_run.return_value = MagicMock(returncode=0)

                result = executor.restart_server()

                assert result is True
                # Verify info log for successful drain
                info_calls = [str(call) for call in mock_logger.info.call_args_list]
                assert any(
                    "drained successfully" in str(call).lower()
                    or "proceeding with restart" in str(call).lower()
                    for call in info_calls
                ), f"Expected drain success log, got: {info_calls}"
