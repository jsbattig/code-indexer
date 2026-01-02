"""Unit tests for DeploymentExecutor - deployment command execution."""

from pathlib import Path
from unittest.mock import Mock, patch

from code_indexer.server.auto_update.deployment_executor import DeploymentExecutor


class TestDeploymentExecutorInitialization:
    """Test DeploymentExecutor initialization."""

    def test_initializes_with_repo_path(self):
        """DeploymentExecutor should initialize with repository path."""
        executor = DeploymentExecutor(repo_path=Path("/tmp/test-repo"))

        assert executor.repo_path == Path("/tmp/test-repo")

    def test_initializes_with_default_service_name(self):
        """DeploymentExecutor should use cidx-server as default service name."""
        executor = DeploymentExecutor(repo_path=Path("/tmp/test-repo"))

        assert executor.service_name == "cidx-server"

    def test_initializes_with_custom_service_name(self):
        """DeploymentExecutor should support custom service name."""
        executor = DeploymentExecutor(
            repo_path=Path("/tmp/test-repo"),
            service_name="custom-service",
        )

        assert executor.service_name == "custom-service"


class TestDeploymentExecutorGitPull:
    """Test DeploymentExecutor git pull operation."""

    @patch("subprocess.run")
    def test_git_pull_executes_correct_command(self, mock_run):
        """git_pull() should execute git pull origin master."""
        mock_run.return_value = Mock(returncode=0, stdout="Already up to date.")

        executor = DeploymentExecutor(repo_path=Path("/tmp/test-repo"))
        result = executor.git_pull()

        assert result is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["git", "pull", "origin", "master"]

    @patch("subprocess.run")
    def test_git_pull_uses_correct_working_directory(self, mock_run):
        """git_pull() should run command in repository directory."""
        mock_run.return_value = Mock(returncode=0, stdout="Already up to date.")

        executor = DeploymentExecutor(repo_path=Path("/tmp/test-repo"))
        executor.git_pull()

        kwargs = mock_run.call_args[1]
        assert kwargs["cwd"] == Path("/tmp/test-repo")

    @patch("subprocess.run")
    def test_git_pull_returns_false_on_failure(self, mock_run):
        """git_pull() should return False when command fails."""
        mock_run.return_value = Mock(
            returncode=1,
            stderr="fatal: unable to access repository",
        )

        executor = DeploymentExecutor(repo_path=Path("/tmp/test-repo"))
        result = executor.git_pull()

        assert result is False

    @patch("subprocess.run")
    def test_git_pull_handles_exception(self, mock_run):
        """git_pull() should handle exceptions and return False."""
        mock_run.side_effect = Exception("Unexpected error during git pull")

        executor = DeploymentExecutor(repo_path=Path("/tmp/test-repo"))
        result = executor.git_pull()

        assert result is False


class TestDeploymentExecutorPipInstall:
    """Test DeploymentExecutor pip install operation."""

    @patch("subprocess.run")
    def test_pip_install_executes_correct_command(self, mock_run):
        """pip_install() should execute pip install with --break-system-packages."""
        mock_run.return_value = Mock(returncode=0, stdout="Successfully installed")

        executor = DeploymentExecutor(repo_path=Path("/tmp/test-repo"))
        result = executor.pip_install()

        assert result is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == [
            "python3",
            "-m",
            "pip",
            "install",
            "--break-system-packages",
            "-e",
            ".",
        ]

    @patch("subprocess.run")
    def test_pip_install_uses_correct_working_directory(self, mock_run):
        """pip_install() should run command in repository directory."""
        mock_run.return_value = Mock(returncode=0, stdout="Successfully installed")

        executor = DeploymentExecutor(repo_path=Path("/tmp/test-repo"))
        executor.pip_install()

        kwargs = mock_run.call_args[1]
        assert kwargs["cwd"] == Path("/tmp/test-repo")

    @patch("subprocess.run")
    def test_pip_install_returns_false_on_failure(self, mock_run):
        """pip_install() should return False when command fails."""
        mock_run.return_value = Mock(
            returncode=1,
            stderr="ERROR: Could not install packages",
        )

        executor = DeploymentExecutor(repo_path=Path("/tmp/test-repo"))
        result = executor.pip_install()

        assert result is False

    @patch("subprocess.run")
    def test_pip_install_handles_exception(self, mock_run):
        """pip_install() should handle exceptions and return False."""
        mock_run.side_effect = Exception("Unexpected error during pip install")

        executor = DeploymentExecutor(repo_path=Path("/tmp/test-repo"))
        result = executor.pip_install()

        assert result is False


class TestDeploymentExecutorRestartServer:
    """Test DeploymentExecutor systemd restart operation."""

    @patch("subprocess.run")
    def test_restart_server_executes_systemctl_restart(self, mock_run):
        """restart_server() should execute systemctl restart."""
        mock_run.return_value = Mock(returncode=0)

        executor = DeploymentExecutor(repo_path=Path("/tmp/test-repo"))
        result = executor.restart_server()

        assert result is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["sudo", "systemctl", "restart", "cidx-server"]

    @patch("subprocess.run")
    def test_restart_server_uses_custom_service_name(self, mock_run):
        """restart_server() should use configured service name."""
        mock_run.return_value = Mock(returncode=0)

        executor = DeploymentExecutor(
            repo_path=Path("/tmp/test-repo"),
            service_name="custom-service",
        )
        executor.restart_server()

        args = mock_run.call_args[0][0]
        assert args == ["sudo", "systemctl", "restart", "custom-service"]

    @patch("subprocess.run")
    def test_restart_server_returns_false_on_failure(self, mock_run):
        """restart_server() should return False when command fails."""
        mock_run.return_value = Mock(
            returncode=1,
            stderr="Failed to restart service",
        )

        executor = DeploymentExecutor(repo_path=Path("/tmp/test-repo"))
        result = executor.restart_server()

        assert result is False

    @patch("subprocess.run")
    def test_restart_server_handles_exception(self, mock_run):
        """restart_server() should handle exceptions and return False."""
        mock_run.side_effect = Exception("Unexpected error during server restart")

        executor = DeploymentExecutor(repo_path=Path("/tmp/test-repo"))
        result = executor.restart_server()

        assert result is False


class TestDeploymentExecutorExecute:
    """Test DeploymentExecutor complete deployment workflow."""

    @patch("subprocess.run")
    def test_execute_runs_git_pull_then_pip_install(self, mock_run):
        """execute() should run git pull followed by pip install."""
        mock_run.return_value = Mock(returncode=0, stdout="Success")

        executor = DeploymentExecutor(repo_path=Path("/tmp/test-repo"))
        result = executor.execute()

        assert result is True
        assert mock_run.call_count == 2
        # First call: git pull
        assert mock_run.call_args_list[0][0][0][0] == "git"
        # Second call: pip install
        assert mock_run.call_args_list[1][0][0][0] == "python3"

    @patch("subprocess.run")
    def test_execute_returns_false_when_git_pull_fails(self, mock_run):
        """execute() should return False when git pull fails."""
        mock_run.return_value = Mock(returncode=1, stderr="Git pull failed")

        executor = DeploymentExecutor(repo_path=Path("/tmp/test-repo"))
        result = executor.execute()

        assert result is False
        # Should only call git pull, not pip install
        assert mock_run.call_count == 1

    @patch("subprocess.run")
    def test_execute_returns_false_when_pip_install_fails(self, mock_run):
        """execute() should return False when pip install fails."""
        # Git pull succeeds, pip install fails
        mock_run.side_effect = [
            Mock(returncode=0, stdout="Git success"),
            Mock(returncode=1, stderr="Pip failed"),
        ]

        executor = DeploymentExecutor(repo_path=Path("/tmp/test-repo"))
        result = executor.execute()

        assert result is False
