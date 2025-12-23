"""
Unit tests for SCIP indexers installation in ServerInstaller.

Tests the automatic SCIP indexers installation feature that ensures
scip-python and scip-typescript are available without manual npm commands.
"""

import subprocess
from unittest.mock import Mock, patch

import pytest

from code_indexer.server.installer import ServerInstaller


class TestIsScipIndexerInstalled:
    """Tests for _is_scip_indexer_installed method."""

    @pytest.fixture
    def installer(self, tmp_path):
        """Create installer with temporary directory."""
        with patch.object(ServerInstaller, "__init__", lambda self, **kwargs: None):
            inst = ServerInstaller.__new__(ServerInstaller)
            inst.server_dir = tmp_path / ".cidx-server"
            return inst

    def test_returns_true_when_scip_python_installed(self, installer):
        """Test returns True when scip-python --version succeeds."""
        mock_result = Mock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = installer._is_scip_indexer_installed("scip-python")

        assert result is True
        mock_run.assert_called_once_with(
            ["scip-python", "--version"], capture_output=True, text=True, timeout=10
        )

    def test_returns_true_when_scip_typescript_installed(self, installer):
        """Test returns True when scip-typescript --version succeeds."""
        mock_result = Mock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = installer._is_scip_indexer_installed("scip-typescript")

        assert result is True
        mock_run.assert_called_once_with(
            ["scip-typescript", "--version"], capture_output=True, text=True, timeout=10
        )

    def test_returns_false_when_indexer_not_found(self, installer):
        """Test returns False when indexer command not found."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = installer._is_scip_indexer_installed("scip-python")

        assert result is False

    def test_returns_false_when_indexer_returns_nonzero(self, installer):
        """Test returns False when indexer returns non-zero exit code."""
        mock_result = Mock()
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            result = installer._is_scip_indexer_installed("scip-python")

        assert result is False

    def test_returns_false_on_timeout(self, installer):
        """Test returns False when command times out."""
        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("scip-python", 10)
        ):
            result = installer._is_scip_indexer_installed("scip-python")

        assert result is False


class TestInstallScipIndexers:
    """Tests for install_scip_indexers method."""

    @pytest.fixture
    def installer(self, tmp_path):
        """Create installer with temporary directory."""
        with patch.object(ServerInstaller, "__init__", lambda self, **kwargs: None):
            inst = ServerInstaller.__new__(ServerInstaller)
            inst.server_dir = tmp_path / ".cidx-server"
            return inst

    def test_skips_installation_when_both_already_installed(self, installer):
        """Test skips npm install when both indexers already present."""
        with patch.object(
            installer, "_is_scip_indexer_installed", return_value=True
        ) as mock_check:
            with patch.object(installer, "_is_npm_available", return_value=True):
                with patch.object(
                    installer, "install_scip_dotnet", return_value=True
                ) as mock_dotnet:
                    with patch.object(
                        installer, "install_scip_go", return_value=True
                    ) as mock_go:
                        with patch("subprocess.run") as mock_run:
                            result = installer.install_scip_indexers()

        assert result is True
        # Should check both npm indexers but not run npm install
        assert mock_check.call_count == 2
        # Should call install_scip_dotnet and install_scip_go
        mock_dotnet.assert_called_once()
        mock_go.assert_called_once()
        # subprocess.run should not be called for npm install
        mock_run.assert_not_called()

    def test_skips_installation_when_npm_not_available(self, installer):
        """Test skips installation and logs warning when npm not found."""
        with patch.object(installer, "_is_npm_available", return_value=False):
            result = installer.install_scip_indexers()

        assert result is False

    def test_installs_both_indexers_when_not_installed(self, installer):
        """Test runs npm install for both indexers when not present."""
        mock_npm_result = Mock()
        mock_npm_result.returncode = 0

        # First check returns False (not installed), after install returns True
        check_results = [False, True, False, True]  # Two indexers, each checked twice

        with patch.object(
            installer, "_is_scip_indexer_installed", side_effect=check_results
        ):
            with patch.object(installer, "_is_npm_available", return_value=True):
                with patch.object(
                    installer, "install_scip_dotnet", return_value=True
                ) as mock_dotnet:
                    with patch.object(
                        installer, "install_scip_go", return_value=True
                    ) as mock_go:
                        with patch(
                            "subprocess.run",
                            side_effect=[mock_npm_result, mock_npm_result],
                        ) as mock_run:
                            result = installer.install_scip_indexers()

        assert result is True
        assert mock_run.call_count == 2
        mock_run.assert_any_call(
            ["npm", "install", "-g", "@sourcegraph/scip-python"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        mock_run.assert_any_call(
            ["npm", "install", "-g", "@sourcegraph/scip-typescript"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        # Should call install_scip_dotnet and install_scip_go
        mock_dotnet.assert_called_once()
        mock_go.assert_called_once()

    def test_installs_only_missing_indexer(self, installer):
        """Test installs only the indexer that is missing."""
        mock_npm_result = Mock()
        mock_npm_result.returncode = 0

        # scip-python already installed, scip-typescript needs install
        check_results = [
            True,
            False,
            True,
        ]  # python(yes), typescript(no), typescript(yes after install)

        with patch.object(
            installer, "_is_scip_indexer_installed", side_effect=check_results
        ):
            with patch.object(installer, "_is_npm_available", return_value=True):
                with patch.object(
                    installer, "install_scip_dotnet", return_value=True
                ) as mock_dotnet:
                    with patch.object(
                        installer, "install_scip_go", return_value=True
                    ) as mock_go:
                        with patch(
                            "subprocess.run",
                            side_effect=[mock_npm_result],
                        ) as mock_run:
                            result = installer.install_scip_indexers()

        assert result is True
        # Should have 1 npm install call
        assert mock_run.call_count == 1
        # Only call: install scip-typescript
        assert mock_run.call_args_list[0] == (
            (["npm", "install", "-g", "@sourcegraph/scip-typescript"],),
            {"capture_output": True, "text": True, "timeout": 180},
        )
        # Should call install_scip_dotnet and install_scip_go
        mock_dotnet.assert_called_once()
        mock_go.assert_called_once()

    def test_returns_false_when_npm_install_fails(self, installer):
        """Test returns False when npm install returns non-zero."""
        mock_npm_result = Mock()
        mock_npm_result.returncode = 1
        mock_npm_result.stderr = "npm ERR! code EACCES"

        with patch.object(installer, "_is_scip_indexer_installed", return_value=False):
            with patch.object(installer, "_is_npm_available", return_value=True):
                with patch("subprocess.run", return_value=mock_npm_result):
                    result = installer.install_scip_indexers()

        assert result is False

    def test_returns_false_when_verification_fails(self, installer):
        """Test returns False when post-install verification fails."""
        mock_npm_result = Mock()
        mock_npm_result.returncode = 0

        # Both checks return False (verification fails for first indexer)
        with patch.object(installer, "_is_scip_indexer_installed", return_value=False):
            with patch.object(installer, "_is_npm_available", return_value=True):
                with patch("subprocess.run", return_value=mock_npm_result):
                    result = installer.install_scip_indexers()

        assert result is False

    def test_handles_npm_timeout(self, installer):
        """Test returns False when npm install times out."""
        with patch.object(installer, "_is_scip_indexer_installed", return_value=False):
            with patch.object(installer, "_is_npm_available", return_value=True):
                with patch(
                    "subprocess.run",
                    side_effect=subprocess.TimeoutExpired("npm", 180),
                ):
                    result = installer.install_scip_indexers()

        assert result is False

    def test_handles_generic_exception(self, installer):
        """Test returns False when npm install raises unexpected exception."""
        # Mock npm result for second indexer attempt
        mock_npm_result = Mock()
        mock_npm_result.returncode = 0

        with patch.object(installer, "_is_scip_indexer_installed", return_value=False):
            with patch.object(installer, "_is_npm_available", return_value=True):
                with patch.object(
                    installer, "install_scip_dotnet", return_value=True
                ) as mock_dotnet:
                    with patch.object(
                        installer, "install_scip_go", return_value=True
                    ) as mock_go:
                        with patch(
                            "subprocess.run",
                            side_effect=[
                                RuntimeError(
                                    "unexpected error"
                                ),  # scip-python install fails
                                mock_npm_result,  # scip-typescript install succeeds
                            ],
                        ):
                            result = installer.install_scip_indexers()

        assert result is False
        # Should still call install_scip_dotnet and install_scip_go
        mock_dotnet.assert_called_once()
        mock_go.assert_called_once()

    def test_continues_installation_after_one_failure(self, installer):
        """Test continues installing second indexer even if first fails."""
        mock_npm_result_fail = Mock()
        mock_npm_result_fail.returncode = 1
        mock_npm_result_fail.stderr = "failed"

        mock_npm_result_success = Mock()
        mock_npm_result_success.returncode = 0

        # Both not installed initially
        check_results = [
            False,
            False,
            True,
        ]  # python(no), typescript(no), typescript(yes after install)

        with patch.object(
            installer, "_is_scip_indexer_installed", side_effect=check_results
        ):
            with patch.object(installer, "_is_npm_available", return_value=True):
                with patch.object(
                    installer, "install_scip_dotnet", return_value=True
                ) as mock_dotnet:
                    with patch.object(
                        installer, "install_scip_go", return_value=True
                    ) as mock_go:
                        with patch(
                            "subprocess.run",
                            side_effect=[
                                mock_npm_result_fail,
                                mock_npm_result_success,
                            ],
                        ) as mock_run:
                            result = installer.install_scip_indexers()

        # Should return False because not all succeeded
        assert result is False
        # But should have attempted both npm installs
        assert mock_run.call_count == 2
        # Should still call install_scip_dotnet and install_scip_go
        mock_dotnet.assert_called_once()
        mock_go.assert_called_once()


class TestIsDotnetSdkAvailable:
    """Tests for _is_dotnet_sdk_available method."""

    @pytest.fixture
    def installer(self, tmp_path):
        """Create installer with temporary directory."""
        with patch.object(ServerInstaller, "__init__", lambda self, **kwargs: None):
            inst = ServerInstaller.__new__(ServerInstaller)
            inst.server_dir = tmp_path / ".cidx-server"
            return inst

    def test_returns_true_when_dotnet_sdk_available(self, installer):
        """Test returns True when dotnet --version succeeds."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "8.0.100"

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = installer._is_dotnet_sdk_available()

        assert result is True
        mock_run.assert_called_once_with(
            ["dotnet", "--version"], capture_output=True, text=True, timeout=10
        )

    def test_returns_false_when_dotnet_not_found(self, installer):
        """Test returns False when dotnet command not found."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = installer._is_dotnet_sdk_available()

        assert result is False

    def test_returns_false_when_dotnet_returns_nonzero(self, installer):
        """Test returns False when dotnet returns non-zero exit code."""
        mock_result = Mock()
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            result = installer._is_dotnet_sdk_available()

        assert result is False

    def test_returns_false_on_timeout(self, installer):
        """Test returns False when dotnet command times out."""
        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("dotnet", 10)
        ):
            result = installer._is_dotnet_sdk_available()

        assert result is False


class TestIsScipDotnetInstalled:
    """Tests for _is_scip_dotnet_installed method."""

    @pytest.fixture
    def installer(self, tmp_path):
        """Create installer with temporary directory."""
        with patch.object(ServerInstaller, "__init__", lambda self, **kwargs: None):
            inst = ServerInstaller.__new__(ServerInstaller)
            inst.server_dir = tmp_path / ".cidx-server"
            return inst

    def test_returns_true_when_scip_dotnet_installed(self, installer):
        """Test returns True when scip-dotnet --version succeeds."""
        mock_result = Mock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = installer._is_scip_dotnet_installed()

        assert result is True
        mock_run.assert_called_once_with(
            ["scip-dotnet", "--version"], capture_output=True, text=True, timeout=10
        )

    def test_returns_false_when_scip_dotnet_not_found(self, installer):
        """Test returns False when scip-dotnet command not found."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = installer._is_scip_dotnet_installed()

        assert result is False

    def test_returns_false_when_scip_dotnet_returns_nonzero(self, installer):
        """Test returns False when scip-dotnet returns non-zero exit code."""
        mock_result = Mock()
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            result = installer._is_scip_dotnet_installed()

        assert result is False

    def test_returns_false_on_timeout(self, installer):
        """Test returns False when scip-dotnet command times out."""
        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("scip-dotnet", 10)
        ):
            result = installer._is_scip_dotnet_installed()

        assert result is False


class TestInstallScipDotnet:
    """Tests for install_scip_dotnet method."""

    @pytest.fixture
    def installer(self, tmp_path):
        """Create installer with temporary directory."""
        with patch.object(ServerInstaller, "__init__", lambda self, **kwargs: None):
            inst = ServerInstaller.__new__(ServerInstaller)
            inst.server_dir = tmp_path / ".cidx-server"
            return inst

    def test_skips_installation_when_already_installed(self, installer):
        """Test skips dotnet tool install when scip-dotnet already present."""
        with patch.object(
            installer, "_is_scip_dotnet_installed", return_value=True
        ) as mock_check:
            with patch("subprocess.run") as mock_run:
                result = installer.install_scip_dotnet()

        assert result is True
        mock_check.assert_called_once()
        mock_run.assert_not_called()

    def test_skips_installation_when_dotnet_sdk_not_available(self, installer):
        """Test skips installation and logs warning when .NET SDK not found."""
        with patch.object(installer, "_is_scip_dotnet_installed", return_value=False):
            with patch.object(
                installer, "_is_dotnet_sdk_available", return_value=False
            ):
                result = installer.install_scip_dotnet()

        assert result is False

    def test_installs_scip_dotnet_when_not_installed(self, installer):
        """Test runs dotnet tool install when scip-dotnet not present."""
        mock_install_result = Mock()
        mock_install_result.returncode = 0

        # First check returns False (not installed), after install returns True
        check_results = [False, True]

        with patch.object(
            installer, "_is_scip_dotnet_installed", side_effect=check_results
        ):
            with patch.object(installer, "_is_dotnet_sdk_available", return_value=True):
                with patch(
                    "subprocess.run", return_value=mock_install_result
                ) as mock_run:
                    result = installer.install_scip_dotnet()

        assert result is True
        mock_run.assert_called_once_with(
            ["dotnet", "tool", "install", "--global", "scip-dotnet"],
            capture_output=True,
            text=True,
            timeout=180,
        )

    def test_returns_false_when_dotnet_tool_install_fails(self, installer):
        """Test returns False when dotnet tool install returns non-zero."""
        mock_install_result = Mock()
        mock_install_result.returncode = 1
        mock_install_result.stderr = "dotnet tool install failed"

        with patch.object(installer, "_is_scip_dotnet_installed", return_value=False):
            with patch.object(installer, "_is_dotnet_sdk_available", return_value=True):
                with patch("subprocess.run", return_value=mock_install_result):
                    result = installer.install_scip_dotnet()

        assert result is False

    def test_returns_false_when_verification_fails(self, installer):
        """Test returns False when post-install verification fails."""
        mock_install_result = Mock()
        mock_install_result.returncode = 0

        # Both checks return False (verification fails)
        with patch.object(installer, "_is_scip_dotnet_installed", return_value=False):
            with patch.object(installer, "_is_dotnet_sdk_available", return_value=True):
                with patch("subprocess.run", return_value=mock_install_result):
                    result = installer.install_scip_dotnet()

        assert result is False

    def test_handles_dotnet_tool_timeout(self, installer):
        """Test returns False when dotnet tool install times out."""
        with patch.object(installer, "_is_scip_dotnet_installed", return_value=False):
            with patch.object(installer, "_is_dotnet_sdk_available", return_value=True):
                with patch(
                    "subprocess.run",
                    side_effect=subprocess.TimeoutExpired("dotnet", 180),
                ):
                    result = installer.install_scip_dotnet()

        assert result is False

    def test_handles_generic_exception(self, installer):
        """Test returns False when dotnet tool install raises unexpected exception."""
        with patch.object(installer, "_is_scip_dotnet_installed", return_value=False):
            with patch.object(installer, "_is_dotnet_sdk_available", return_value=True):
                with patch(
                    "subprocess.run",
                    side_effect=RuntimeError("unexpected error"),
                ):
                    result = installer.install_scip_dotnet()

        assert result is False


class TestIsGoSdkAvailable:
    """Tests for _is_go_sdk_available method."""

    @pytest.fixture
    def installer(self, tmp_path):
        """Create installer with temporary directory."""
        with patch.object(ServerInstaller, "__init__", lambda self, **kwargs: None):
            inst = ServerInstaller.__new__(ServerInstaller)
            inst.server_dir = tmp_path / ".cidx-server"
            return inst

    def test_returns_true_when_go_sdk_available(self, installer):
        """Test returns True when go version succeeds."""
        mock_result = Mock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = installer._is_go_sdk_available()

        assert result is True
        mock_run.assert_called_once_with(
            ["go", "version"], capture_output=True, text=True, timeout=10
        )

    def test_returns_false_when_go_not_found(self, installer):
        """Test returns False when go command not found."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = installer._is_go_sdk_available()

        assert result is False

    def test_returns_false_when_go_returns_nonzero(self, installer):
        """Test returns False when go returns non-zero exit code."""
        mock_result = Mock()
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            result = installer._is_go_sdk_available()

        assert result is False

    def test_returns_false_on_timeout(self, installer):
        """Test returns False when go command times out."""
        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("go", 10)
        ):
            result = installer._is_go_sdk_available()

        assert result is False


class TestIsScipGoInstalled:
    """Tests for _is_scip_go_installed method."""

    @pytest.fixture
    def installer(self, tmp_path):
        """Create installer with temporary directory."""
        with patch.object(ServerInstaller, "__init__", lambda self, **kwargs: None):
            inst = ServerInstaller.__new__(ServerInstaller)
            inst.server_dir = tmp_path / ".cidx-server"
            return inst

    def test_returns_true_when_scip_go_installed(self, installer):
        """Test returns True when scip-go --version succeeds."""
        mock_result = Mock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = installer._is_scip_go_installed()

        assert result is True
        mock_run.assert_called_once_with(
            ["scip-go", "--version"], capture_output=True, text=True, timeout=10
        )

    def test_returns_false_when_scip_go_not_found(self, installer):
        """Test returns False when scip-go command not found."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = installer._is_scip_go_installed()

        assert result is False

    def test_returns_false_when_scip_go_returns_nonzero(self, installer):
        """Test returns False when scip-go returns non-zero exit code."""
        mock_result = Mock()
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            result = installer._is_scip_go_installed()

        assert result is False

    def test_returns_false_on_timeout(self, installer):
        """Test returns False when scip-go command times out."""
        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("scip-go", 10)
        ):
            result = installer._is_scip_go_installed()

        assert result is False


class TestInstallScipGo:
    """Tests for install_scip_go method."""

    @pytest.fixture
    def installer(self, tmp_path):
        """Create installer with temporary directory."""
        with patch.object(ServerInstaller, "__init__", lambda self, **kwargs: None):
            inst = ServerInstaller.__new__(ServerInstaller)
            inst.server_dir = tmp_path / ".cidx-server"
            return inst

    def test_skips_installation_when_already_installed(self, installer):
        """Test skips go install when scip-go already present."""
        with patch.object(
            installer, "_is_scip_go_installed", return_value=True
        ) as mock_check:
            with patch("subprocess.run") as mock_run:
                result = installer.install_scip_go()

        assert result is True
        mock_check.assert_called_once()
        mock_run.assert_not_called()

    def test_skips_installation_when_go_sdk_not_available(self, installer):
        """Test skips installation and logs warning when Go SDK not found."""
        with patch.object(installer, "_is_scip_go_installed", return_value=False):
            with patch.object(
                installer, "_is_go_sdk_available", return_value=False
            ):
                result = installer.install_scip_go()

        assert result is False

    def test_installs_scip_go_when_not_installed(self, installer):
        """Test runs go install when scip-go not present."""
        mock_install_result = Mock()
        mock_install_result.returncode = 0

        check_results = [False, True]

        with patch.object(
            installer, "_is_scip_go_installed", side_effect=check_results
        ):
            with patch.object(installer, "_is_go_sdk_available", return_value=True):
                with patch(
                    "subprocess.run", return_value=mock_install_result
                ) as mock_run:
                    result = installer.install_scip_go()

        assert result is True
        mock_run.assert_called_once_with(
            ["go", "install", "github.com/sourcegraph/scip-go/cmd/scip-go@latest"],
            capture_output=True,
            text=True,
            timeout=180,
        )

    def test_returns_false_when_go_install_fails(self, installer):
        """Test returns False when go install returns non-zero."""
        mock_install_result = Mock()
        mock_install_result.returncode = 1
        mock_install_result.stderr = "go install failed"

        with patch.object(installer, "_is_scip_go_installed", return_value=False):
            with patch.object(installer, "_is_go_sdk_available", return_value=True):
                with patch("subprocess.run", return_value=mock_install_result):
                    result = installer.install_scip_go()

        assert result is False

    def test_returns_false_when_verification_fails(self, installer):
        """Test returns False when post-install verification fails."""
        mock_install_result = Mock()
        mock_install_result.returncode = 0

        with patch.object(installer, "_is_scip_go_installed", return_value=False):
            with patch.object(installer, "_is_go_sdk_available", return_value=True):
                with patch("subprocess.run", return_value=mock_install_result):
                    result = installer.install_scip_go()

        assert result is False

    def test_handles_go_install_timeout(self, installer):
        """Test returns False when go install times out."""
        with patch.object(installer, "_is_scip_go_installed", return_value=False):
            with patch.object(installer, "_is_go_sdk_available", return_value=True):
                with patch(
                    "subprocess.run",
                    side_effect=subprocess.TimeoutExpired("go", 180),
                ):
                    result = installer.install_scip_go()

        assert result is False

    def test_handles_generic_exception(self, installer):
        """Test returns False when go install raises unexpected exception."""
        with patch.object(installer, "_is_scip_go_installed", return_value=False):
            with patch.object(installer, "_is_go_sdk_available", return_value=True):
                with patch(
                    "subprocess.run",
                    side_effect=RuntimeError("unexpected error"),
                ):
                    result = installer.install_scip_go()

        assert result is False
