"""Unit tests for AutoUpdateService - auto-deployment polling service."""

from pathlib import Path

from code_indexer.server.auto_update.service import AutoUpdateService, ServiceState


class TestAutoUpdateServiceInitialization:
    """Test AutoUpdateService initialization and configuration."""

    def test_service_initializes_in_idle_state(self):
        """AutoUpdateService should initialize in IDLE state."""
        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        assert service.current_state == ServiceState.IDLE
        assert service.check_interval == 60
        assert service.repo_path == Path("/tmp/test-repo")

    def test_service_initializes_with_custom_lock_path(self):
        """AutoUpdateService should support custom lock file path."""
        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=30,
            lock_file=Path("/tmp/custom.lock"),
        )

        assert service.lock_file == Path("/tmp/custom.lock")

    def test_service_initializes_with_default_lock_path(self):
        """AutoUpdateService should use default lock path when not specified."""
        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        assert service.lock_file == Path("/var/run/cidx-auto-update.lock")

    def test_service_initializes_last_deployment_as_none(self):
        """AutoUpdateService should initialize last_deployment as None."""
        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        assert service.last_deployment is None

    def test_service_initializes_last_error_as_none(self):
        """AutoUpdateService should initialize last_error as None."""
        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        assert service.last_error is None


class TestAutoUpdateServiceStateTransitions:
    """Test AutoUpdateService state machine transitions."""

    def test_state_transition_from_idle_to_checking(self):
        """State should transition from IDLE to CHECKING when polling."""
        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        service.transition_to(ServiceState.CHECKING)

        assert service.current_state == ServiceState.CHECKING

    def test_state_transition_from_checking_to_deploying(self):
        """State should transition from CHECKING to DEPLOYING when changes detected."""
        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        service.transition_to(ServiceState.CHECKING)
        service.transition_to(ServiceState.DEPLOYING)

        assert service.current_state == ServiceState.DEPLOYING

    def test_state_transition_from_deploying_to_restarting(self):
        """State should transition from DEPLOYING to RESTARTING on successful deployment."""
        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        service.transition_to(ServiceState.DEPLOYING)
        service.transition_to(ServiceState.RESTARTING)

        assert service.current_state == ServiceState.RESTARTING

    def test_state_transition_from_restarting_to_idle(self):
        """State should transition from RESTARTING to IDLE after restart completes."""
        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        service.transition_to(ServiceState.RESTARTING)
        service.transition_to(ServiceState.IDLE)

        assert service.current_state == ServiceState.IDLE

    def test_state_transition_from_checking_to_idle_when_no_changes(self):
        """State should transition from CHECKING to IDLE when no changes detected."""
        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        service.transition_to(ServiceState.CHECKING)
        service.transition_to(ServiceState.IDLE)

        assert service.current_state == ServiceState.IDLE

    def test_state_transition_from_deploying_to_idle_on_failure(self):
        """State should transition from DEPLOYING to IDLE on deployment failure."""
        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        service.transition_to(ServiceState.DEPLOYING)
        service.transition_to(ServiceState.IDLE)

        assert service.current_state == ServiceState.IDLE

    def test_transition_to_deploying_records_timestamp(self):
        """Transition to DEPLOYING should record last_deployment timestamp."""
        from datetime import datetime

        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        before_transition = datetime.now()
        service.transition_to(ServiceState.DEPLOYING)
        after_transition = datetime.now()

        assert service.last_deployment is not None
        assert before_transition <= service.last_deployment <= after_transition


class TestAutoUpdateServicePollingLoop:
    """Test AutoUpdateService polling loop behavior."""

    def test_poll_once_checks_for_changes_when_idle(self):
        """poll_once should check for changes when in IDLE state."""
        from unittest.mock import Mock

        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        mock_detector = Mock()
        mock_detector.has_changes.return_value = False
        service.change_detector = mock_detector

        # Inject required components (needed for assertions in poll_once)
        service.deployment_lock = Mock()
        service.deployment_executor = Mock()

        service.poll_once()

        mock_detector.has_changes.assert_called_once()

    def test_poll_once_returns_to_idle_when_no_changes(self):
        """poll_once should return to IDLE state when no changes detected."""
        from unittest.mock import Mock

        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        mock_detector = Mock()
        mock_detector.has_changes.return_value = False
        service.change_detector = mock_detector

        # Inject required components (needed for assertions in poll_once)
        service.deployment_lock = Mock()
        service.deployment_executor = Mock()

        service.poll_once()

        assert service.current_state == ServiceState.IDLE

    def test_poll_once_triggers_deployment_when_changes_detected(self):
        """poll_once should trigger deployment when changes detected."""
        from unittest.mock import Mock

        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        mock_detector = Mock()
        mock_detector.has_changes.return_value = True
        service.change_detector = mock_detector

        mock_executor = Mock()
        mock_executor.execute.return_value = True
        service.deployment_executor = mock_executor

        mock_lock = Mock()
        mock_lock.acquire.return_value = True
        mock_lock.release.return_value = None
        service.deployment_lock = mock_lock

        service.poll_once()

        mock_executor.execute.assert_called_once()

    def test_poll_once_skips_when_not_idle(self):
        """poll_once should skip when not in IDLE state."""
        from unittest.mock import Mock

        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        service.current_state = ServiceState.DEPLOYING

        mock_detector = Mock()
        service.change_detector = mock_detector

        # Inject required components (needed for assertions in poll_once)
        service.deployment_lock = Mock()
        service.deployment_executor = Mock()

        service.poll_once()

        mock_detector.has_changes.assert_not_called()

    def test_poll_once_restarts_server_after_successful_deployment(self):
        """poll_once should restart CIDX server after successful deployment."""
        from unittest.mock import Mock

        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        mock_detector = Mock()
        mock_detector.has_changes.return_value = True
        service.change_detector = mock_detector

        mock_executor = Mock()
        mock_executor.execute.return_value = True
        mock_executor.restart_server = Mock()
        service.deployment_executor = mock_executor

        mock_lock = Mock()
        mock_lock.acquire.return_value = True
        mock_lock.release.return_value = None
        service.deployment_lock = mock_lock

        service.poll_once()

        mock_executor.restart_server.assert_called_once()


class TestAutoUpdateServiceDeploymentWorkflow:
    """Test AutoUpdateService deployment workflow integration."""

    def test_deployment_acquires_lock_before_executing(self):
        """Deployment should acquire lock before executing."""
        from unittest.mock import Mock

        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        mock_lock = Mock()
        mock_lock.acquire.return_value = True
        service.deployment_lock = mock_lock

        mock_detector = Mock()
        mock_detector.has_changes.return_value = True
        service.change_detector = mock_detector

        mock_executor = Mock()
        mock_executor.execute.return_value = True
        service.deployment_executor = mock_executor

        service.poll_once()

        mock_lock.acquire.assert_called_once()

    def test_deployment_skips_when_lock_unavailable(self):
        """Deployment should skip when lock cannot be acquired."""
        from unittest.mock import Mock

        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        mock_lock = Mock()
        mock_lock.acquire.return_value = False
        service.deployment_lock = mock_lock

        mock_detector = Mock()
        mock_detector.has_changes.return_value = True
        service.change_detector = mock_detector

        mock_executor = Mock()
        service.deployment_executor = mock_executor

        service.poll_once()

        mock_executor.execute.assert_not_called()

    def test_deployment_releases_lock_after_success(self):
        """Deployment should release lock after successful execution."""
        from unittest.mock import Mock

        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        mock_lock = Mock()
        mock_lock.acquire.return_value = True
        service.deployment_lock = mock_lock

        mock_detector = Mock()
        mock_detector.has_changes.return_value = True
        service.change_detector = mock_detector

        mock_executor = Mock()
        mock_executor.execute.return_value = True
        service.deployment_executor = mock_executor

        service.poll_once()

        mock_lock.release.assert_called_once()

    def test_deployment_releases_lock_after_failure(self):
        """Deployment should release lock even when execution fails."""
        from unittest.mock import Mock

        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        mock_lock = Mock()
        mock_lock.acquire.return_value = True
        service.deployment_lock = mock_lock

        mock_detector = Mock()
        mock_detector.has_changes.return_value = True
        service.change_detector = mock_detector

        mock_executor = Mock()
        mock_executor.execute.side_effect = Exception("Deployment failed")
        service.deployment_executor = mock_executor

        service.poll_once()

        mock_lock.release.assert_called_once()

    def test_deployment_records_error_on_failure(self):
        """Deployment should record error when execution fails."""
        from unittest.mock import Mock

        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        mock_lock = Mock()
        mock_lock.acquire.return_value = True
        service.deployment_lock = mock_lock

        mock_detector = Mock()
        mock_detector.has_changes.return_value = True
        service.change_detector = mock_detector

        mock_executor = Mock()
        error = Exception("Git pull failed")
        mock_executor.execute.side_effect = error
        service.deployment_executor = mock_executor

        service.poll_once()

        assert service.last_error is not None
        assert "Git pull failed" in str(service.last_error)

    def test_deployment_returns_to_idle_after_failure(self):
        """Deployment should return to IDLE state after failure."""
        from unittest.mock import Mock

        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        mock_lock = Mock()
        mock_lock.acquire.return_value = True
        service.deployment_lock = mock_lock

        mock_detector = Mock()
        mock_detector.has_changes.return_value = True
        service.change_detector = mock_detector

        mock_executor = Mock()
        mock_executor.execute.side_effect = Exception("Deployment failed")
        service.deployment_executor = mock_executor

        service.poll_once()

        assert service.current_state == ServiceState.IDLE


class TestAutoUpdateServiceExceptionHandling:
    """Test AutoUpdateService exception handling during operations."""

    def test_poll_once_handles_deployment_execute_returning_false(self):
        """poll_once should handle deployment executor returning False (failure)."""
        from unittest.mock import Mock

        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        mock_lock = Mock()
        mock_lock.acquire.return_value = True
        service.deployment_lock = mock_lock

        mock_detector = Mock()
        mock_detector.has_changes.return_value = True
        service.change_detector = mock_detector

        mock_executor = Mock()
        mock_executor.execute.return_value = False  # Deployment failed
        service.deployment_executor = mock_executor

        service.poll_once()

        # Should not restart server when deployment fails
        mock_executor.restart_server.assert_not_called()
        # Should release lock and return to IDLE
        mock_lock.release.assert_called_once()
        assert service.current_state == ServiceState.IDLE

    def test_poll_once_handles_exception_during_checking_state(self):
        """poll_once should handle exceptions during CHECKING state."""
        from unittest.mock import Mock

        service = AutoUpdateService(
            repo_path=Path("/tmp/test-repo"),
            check_interval=60,
        )

        mock_detector = Mock()
        mock_detector.has_changes.side_effect = RuntimeError("Git command failed")
        service.change_detector = mock_detector

        # Inject required components
        service.deployment_lock = Mock()
        service.deployment_executor = Mock()

        service.poll_once()

        # Should record error and return to IDLE
        assert service.last_error is not None
        assert "Git command failed" in str(service.last_error)
        assert service.current_state == ServiceState.IDLE
