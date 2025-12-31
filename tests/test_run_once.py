"""Unit tests for run_once - auto-update service entry point."""

import sys
from pathlib import Path
from unittest.mock import Mock, patch, call


class TestRunOnceMainFunction:
    """Test run_once.py main() function execution."""

    @patch("code_indexer.server.auto_update.run_once.AutoUpdateService")
    @patch("code_indexer.server.auto_update.run_once.DeploymentExecutor")
    @patch("code_indexer.server.auto_update.run_once.DeploymentLock")
    @patch("code_indexer.server.auto_update.run_once.ChangeDetector")
    @patch.dict("os.environ", {"CIDX_SERVER_REPO_PATH": "/custom/repo/path"})
    def test_main_uses_custom_repo_path_from_env(
        self,
        mock_change_detector,
        mock_deployment_lock,
        mock_deployment_executor,
        mock_service,
    ):
        """main() should use CIDX_SERVER_REPO_PATH environment variable."""
        from code_indexer.server.auto_update.run_once import main

        # Mock service instance
        mock_service_instance = Mock()
        mock_service.return_value = mock_service_instance

        with patch.object(sys, "exit") as mock_exit:
            main()

        # Verify ChangeDetector initialized with custom path
        mock_change_detector.assert_called_once_with(
            repo_path=Path("/custom/repo/path"), branch="master"
        )

        # Verify service initialized with custom path
        mock_service.assert_called_once_with(
            repo_path=Path("/custom/repo/path"),
            check_interval=60,
            lock_file=Path("/var/run/cidx-auto-update.lock"),
        )

        mock_exit.assert_called_once_with(0)

    @patch("code_indexer.server.auto_update.run_once.AutoUpdateService")
    @patch("code_indexer.server.auto_update.run_once.DeploymentExecutor")
    @patch("code_indexer.server.auto_update.run_once.DeploymentLock")
    @patch("code_indexer.server.auto_update.run_once.ChangeDetector")
    @patch.dict("os.environ", {}, clear=True)
    def test_main_uses_default_repo_path_when_env_not_set(
        self,
        mock_change_detector,
        mock_deployment_lock,
        mock_deployment_executor,
        mock_service,
    ):
        """main() should use default repo path when CIDX_SERVER_REPO_PATH not set."""
        from code_indexer.server.auto_update.run_once import main

        # Mock service instance
        mock_service_instance = Mock()
        mock_service.return_value = mock_service_instance

        with patch.object(sys, "exit") as mock_exit:
            main()

        # Verify ChangeDetector initialized with default path
        mock_change_detector.assert_called_once_with(
            repo_path=Path("/home/sebabattig/cidx-server"), branch="master"
        )

        mock_exit.assert_called_once_with(0)

    @patch("code_indexer.server.auto_update.run_once.AutoUpdateService")
    @patch("code_indexer.server.auto_update.run_once.DeploymentExecutor")
    @patch("code_indexer.server.auto_update.run_once.DeploymentLock")
    @patch("code_indexer.server.auto_update.run_once.ChangeDetector")
    def test_main_initializes_all_components(
        self,
        mock_change_detector,
        mock_deployment_lock,
        mock_deployment_executor,
        mock_service,
    ):
        """main() should initialize all required components."""
        from code_indexer.server.auto_update.run_once import main

        # Mock service instance
        mock_service_instance = Mock()
        mock_service.return_value = mock_service_instance

        with patch.object(sys, "exit") as mock_exit:
            main()

        # Verify all components initialized
        mock_change_detector.assert_called_once()
        mock_deployment_lock.assert_called_once_with(
            lock_file=Path("/var/run/cidx-auto-update.lock")
        )
        mock_deployment_executor.assert_called_once_with(
            repo_path=Path("/home/sebabattig/cidx-server"),
            service_name="cidx-server",
        )
        mock_service.assert_called_once()

        mock_exit.assert_called_once_with(0)

    @patch("code_indexer.server.auto_update.run_once.AutoUpdateService")
    @patch("code_indexer.server.auto_update.run_once.DeploymentExecutor")
    @patch("code_indexer.server.auto_update.run_once.DeploymentLock")
    @patch("code_indexer.server.auto_update.run_once.ChangeDetector")
    def test_main_injects_dependencies_into_service(
        self,
        mock_change_detector,
        mock_deployment_lock,
        mock_deployment_executor,
        mock_service,
    ):
        """main() should inject component dependencies into service."""
        from code_indexer.server.auto_update.run_once import main

        # Mock component instances
        mock_detector_instance = Mock()
        mock_change_detector.return_value = mock_detector_instance

        mock_lock_instance = Mock()
        mock_deployment_lock.return_value = mock_lock_instance

        mock_executor_instance = Mock()
        mock_deployment_executor.return_value = mock_executor_instance

        # Mock service instance
        mock_service_instance = Mock()
        mock_service.return_value = mock_service_instance

        with patch.object(sys, "exit") as mock_exit:
            main()

        # Verify dependencies injected
        assert mock_service_instance.change_detector == mock_detector_instance
        assert mock_service_instance.deployment_lock == mock_lock_instance
        assert mock_service_instance.deployment_executor == mock_executor_instance

        mock_exit.assert_called_once_with(0)

    @patch("code_indexer.server.auto_update.run_once.AutoUpdateService")
    @patch("code_indexer.server.auto_update.run_once.DeploymentExecutor")
    @patch("code_indexer.server.auto_update.run_once.DeploymentLock")
    @patch("code_indexer.server.auto_update.run_once.ChangeDetector")
    def test_main_calls_poll_once(
        self,
        mock_change_detector,
        mock_deployment_lock,
        mock_deployment_executor,
        mock_service,
    ):
        """main() should call service.poll_once() to execute one iteration."""
        from code_indexer.server.auto_update.run_once import main

        # Mock service instance
        mock_service_instance = Mock()
        mock_service.return_value = mock_service_instance

        with patch.object(sys, "exit") as mock_exit:
            main()

        # Verify poll_once called
        mock_service_instance.poll_once.assert_called_once()

        mock_exit.assert_called_once_with(0)

    @patch("code_indexer.server.auto_update.run_once.AutoUpdateService")
    @patch("code_indexer.server.auto_update.run_once.DeploymentExecutor")
    @patch("code_indexer.server.auto_update.run_once.DeploymentLock")
    @patch("code_indexer.server.auto_update.run_once.ChangeDetector")
    def test_main_exits_with_zero_on_success(
        self,
        mock_change_detector,
        mock_deployment_lock,
        mock_deployment_executor,
        mock_service,
    ):
        """main() should exit with code 0 on successful completion."""
        from code_indexer.server.auto_update.run_once import main

        # Mock service instance
        mock_service_instance = Mock()
        mock_service.return_value = mock_service_instance

        with patch.object(sys, "exit") as mock_exit:
            main()

        mock_exit.assert_called_once_with(0)

    @patch("code_indexer.server.auto_update.run_once.AutoUpdateService")
    @patch("code_indexer.server.auto_update.run_once.DeploymentExecutor")
    @patch("code_indexer.server.auto_update.run_once.DeploymentLock")
    @patch("code_indexer.server.auto_update.run_once.ChangeDetector")
    def test_main_exits_with_one_on_exception(
        self,
        mock_change_detector,
        mock_deployment_lock,
        mock_deployment_executor,
        mock_service,
    ):
        """main() should exit with code 1 when exception occurs."""
        from code_indexer.server.auto_update.run_once import main

        # Mock service instance that raises exception
        mock_service_instance = Mock()
        mock_service_instance.poll_once.side_effect = RuntimeError("Polling failed")
        mock_service.return_value = mock_service_instance

        with patch.object(sys, "exit") as mock_exit:
            main()

        mock_exit.assert_called_once_with(1)

    @patch("code_indexer.server.auto_update.run_once.AutoUpdateService")
    @patch("code_indexer.server.auto_update.run_once.DeploymentExecutor")
    @patch("code_indexer.server.auto_update.run_once.DeploymentLock")
    @patch("code_indexer.server.auto_update.run_once.ChangeDetector")
    @patch("code_indexer.server.auto_update.run_once.logger")
    def test_main_logs_exception_on_failure(
        self,
        mock_logger,
        mock_change_detector,
        mock_deployment_lock,
        mock_deployment_executor,
        mock_service,
    ):
        """main() should log exception details when polling fails."""
        from code_indexer.server.auto_update.run_once import main

        # Mock service instance that raises exception
        mock_service_instance = Mock()
        error = RuntimeError("Polling failed")
        mock_service_instance.poll_once.side_effect = error
        mock_service.return_value = mock_service_instance

        with patch.object(sys, "exit"):
            main()

        # Verify exception was logged
        mock_logger.exception.assert_called_once()
        call_args = mock_logger.exception.call_args[0][0]
        assert "Auto-update polling failed" in call_args
        assert error == mock_service_instance.poll_once.side_effect
