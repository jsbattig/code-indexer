"""
Server installation utilities for CIDX Server.

Handles server installation, port allocation, configuration setup,
and startup script generation.
"""

from code_indexer.server.middleware.correlation import get_correlation_id
import getpass
import logging
import socket
import stat
import subprocess
import sys
from pathlib import Path
from typing import Tuple, Optional

from .auth.user_manager import UserManager
from .utils.config_manager import ServerConfigManager
from .utils.jwt_secret_manager import JWTSecretManager

logger = logging.getLogger(__name__)


class ServerInstaller:
    """
    Handles CIDX server installation and setup.

    Creates server directory structure, allocates ports, generates startup scripts,
    and seeds initial admin user.
    """

    def __init__(self, base_port: int = 8090):
        """
        Initialize server installer.

        Args:
            base_port: Starting port to try for server allocation
        """
        self.base_port = base_port
        self.home_dir = Path.home()
        self.server_dir = self.home_dir / ".cidx-server"

        # Initialize configuration and JWT managers
        self.config_manager = ServerConfigManager(str(self.server_dir))
        self.jwt_manager = JWTSecretManager(str(self.server_dir))

    def find_available_port(self, start_port: Optional[int] = None) -> int:
        """
        Find available port starting from base_port.

        Args:
            start_port: Port to start searching from (defaults to base_port)

        Returns:
            Available port number
        """
        if start_port is None:
            start_port = self.base_port

        port = start_port
        while port < start_port + 100:  # Try up to 100 ports
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("127.0.0.1", port))
                    return port
            except OSError:
                port += 1

        raise RuntimeError(
            f"No available port found in range {start_port}-{start_port + 99}"
        )

    def create_server_directory_structure(self) -> bool:
        """
        Create ~/.cidx-server directory structure using ServerConfigManager.

        Returns:
            True if created, False if already exists
        """
        created = not self.server_dir.exists()

        # Use ServerConfigManager to create proper directory structure
        self.config_manager.create_server_directories()

        return created

    def create_server_config(self, port: int) -> Path:
        """
        Create server configuration file using ServerConfigManager.

        Args:
            port: Allocated server port

        Returns:
            Path to created config file
        """
        # Create configuration using ServerConfigManager
        config = self.config_manager.create_default_config()
        config.port = port  # Set allocated port

        # Apply environment overrides
        config = self.config_manager.apply_env_overrides(config)

        # Validate configuration
        self.config_manager.validate_config(config)

        # Save configuration
        self.config_manager.save_config(config)

        return self.config_manager.config_file_path

    def create_startup_script(self, port: int) -> Path:
        """
        Create startup script for the server.

        Args:
            port: Server port

        Returns:
            Path to created startup script
        """
        # Get current Python executable
        python_exe = sys.executable

        script_content = f"""#!/bin/bash
# CIDX Server Startup Script
# Generated automatically by cidx install-server

echo "🚀 Starting CIDX Server..."
echo "📂 Server directory: {self.server_dir}"
echo "🌐 Server will be available at: http://127.0.0.1:{port}"
echo "📚 API documentation: http://127.0.0.1:{port}/docs"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Change to home directory to ensure proper Python path
cd "{self.home_dir}"

# Start server with full Python path
{python_exe} -m code_indexer.server.main --port {port} --host 127.0.0.1
"""

        script_path = self.server_dir / "start-server.sh"
        with open(script_path, "w") as f:
            f.write(script_content)

        # Make script executable
        script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)

        return script_path

    def create_systemd_service(
        self,
        port: int,
        issuer_url: Optional[str] = None,
        voyage_api_key: Optional[str] = None,
    ) -> Path:
        """
        Create systemd service file for the server.

        Args:
            port: Server port
            issuer_url: OAuth issuer URL (e.g., https://linner.ddns.net:8383)
            voyage_api_key: VoyageAI API key (WARNING: stored in plaintext in service file)

        Returns:
            Path to created service file

        Security Note:
            If voyage_api_key is provided, it will be stored in PLAINTEXT in the systemd
            service file. For production, prefer using systemd EnvironmentFile with
            restricted permissions instead.
        """
        import sys

        python_exe = sys.executable
        current_user = getpass.getuser()

        # Build environment variables
        env_vars = [
            f'Environment="PATH={self.home_dir}/.local/bin:/usr/local/bin:/usr/bin"',
            'Environment="PYTHONUNBUFFERED=1"',
        ]

        if voyage_api_key:
            env_vars.append(f'Environment="VOYAGE_API_KEY={voyage_api_key}"')

        if issuer_url:
            env_vars.append(f'Environment="CIDX_ISSUER_URL={issuer_url}"')

        service_content = f"""[Unit]
Description=CIDX Multi-User Server with MCP Integration
After=network.target

[Service]
Type=simple
User={current_user}
WorkingDirectory={self.home_dir}
{chr(10).join(env_vars)}
ExecStart={python_exe} -m code_indexer.server.main --host 0.0.0.0 --port {port}
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=cidx-server

[Install]
WantedBy=multi-user.target
"""

        service_path = self.server_dir / "cidx-server.service"
        with open(service_path, "w") as f:
            f.write(service_content)

        return service_path

    def seed_initial_admin_user(self) -> bool:
        """
        Seed initial admin user (admin/admin).

        Returns:
            True if user was created, False if already exists
        """
        user_manager = UserManager()

        # Check if admin user already exists
        existing_admin = user_manager.get_user("admin")
        if existing_admin:
            return False  # Already exists

        # Seed initial admin
        user_manager.seed_initial_admin()
        return True

    def install(self) -> Tuple[int, Path, Path, bool]:
        """
        Perform complete server installation.

        Returns:
            Tuple of (port, config_path, script_path, is_new_installation)

        Raises:
            RuntimeError: If installation fails
        """
        try:
            # Check if already installed
            is_new_installation = not self.server_dir.exists()

            # Create directory structure
            self.create_server_directory_structure()

            # Create or ensure JWT secret exists
            self.jwt_manager.get_or_create_secret()

            # Find available port
            port = self.find_available_port()

            # Create configuration
            config_path = self.create_server_config(port)

            # Create startup script
            script_path = self.create_startup_script(port)

            # Try to install Claude CLI (non-fatal if fails)
            self.install_claude_cli()

            # Try to install SCIP indexers (non-fatal if fails)
            self.install_scip_indexers()

            # Seed initial admin user
            self.seed_initial_admin_user()

            return port, config_path, script_path, is_new_installation

        except Exception as e:
            raise RuntimeError(f"Server installation failed: {str(e)}")

    def get_installation_info(self) -> dict:
        """
        Get current installation information.

        Returns:
            Installation info dictionary
        """
        if not self.server_dir.exists():
            return {"installed": False}

        # Try to load config using ServerConfigManager
        try:
            config = self.config_manager.load_config()
            if config:
                return {
                    "installed": True,
                    "configured": True,
                    "port": config.port,
                    "host": config.host,
                    "log_level": config.log_level,
                    "jwt_expiration_minutes": config.jwt_expiration_minutes,
                }
            else:
                return {"installed": True, "configured": False}
        except Exception:
            return {"installed": True, "configured": False, "error": "Invalid config"}

    def uninstall(self) -> bool:
        """
        Remove server installation.

        Returns:
            True if uninstalled, False if not installed
        """
        if not self.server_dir.exists():
            return False

        import shutil

        shutil.rmtree(self.server_dir)
        return True

    def _is_claude_cli_installed(self) -> bool:
        """
        Check if claude command exists.

        Returns:
            True if Claude CLI is installed and responds to --version
        """
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _is_npm_available(self) -> bool:
        """
        Check if npm command exists.

        Returns:
            True if npm is available
        """
        try:
            result = subprocess.run(
                ["npm", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def install_claude_cli(self) -> bool:
        """
        Install Claude CLI if not present.

        Returns:
            True if Claude CLI is available after this method
            (either already installed or successfully installed),
            False if installation failed or npm not available.
        """
        # Check if already installed (idempotent)
        if self._is_claude_cli_installed():
            logger.info("Claude CLI already installed", extra={"correlation_id": get_correlation_id()})
            return True

        # Check if npm available
        if not self._is_npm_available():
            logger.warning("npm not found - Claude CLI installation skipped", extra={"correlation_id": get_correlation_id()})
            logger.info("Install manually: npm install -g @anthropic-ai/claude-code", extra={"correlation_id": get_correlation_id()})
            return False

        # Install via npm
        try:
            logger.info("Installing Claude CLI via npm...", extra={"correlation_id": get_correlation_id()})
            result = subprocess.run(
                ["npm", "install", "-g", "@anthropic-ai/claude-code"],
                capture_output=True,
                text=True,
                timeout=120,  # 2 minute timeout for npm install
            )

            if result.returncode != 0:
                logger.error(f"Claude CLI installation failed: {result.stderr}", extra={"correlation_id": get_correlation_id()})
                return False

            # Verify installation succeeded
            if self._is_claude_cli_installed():
                logger.info("Claude CLI installed successfully", extra={"correlation_id": get_correlation_id()})
                return True
            else:
                logger.error("Claude CLI installation failed: verification failed", extra={"correlation_id": get_correlation_id()})
                return False

        except subprocess.TimeoutExpired:
            logger.error("Claude CLI installation failed: timeout", extra={"correlation_id": get_correlation_id()})
            return False
        except Exception as e:
            logger.error(f"Claude CLI installation failed: {e}", extra={"correlation_id": get_correlation_id()})
            return False

    def _is_scip_indexer_installed(self, indexer_name: str) -> bool:
        """
        Check if a SCIP indexer command exists.

        Args:
            indexer_name: Name of the indexer command (e.g., "scip-python", "scip-typescript")

        Returns:
            True if the indexer is installed and responds to --version
        """
        try:
            result = subprocess.run(
                [indexer_name, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def install_scip_indexers(self) -> bool:
        """
        Install SCIP indexers for all supported languages.

        Installs:
        - @sourcegraph/scip-python for Python code
        - @sourcegraph/scip-typescript for TypeScript/JavaScript
        - scip-dotnet for C#/.NET code

        Returns:
            True if all indexers are available after this method
            (either already installed or successfully installed),
            False if installation failed or npm not available.
        """
        indexers = {
            "scip-python": "@sourcegraph/scip-python",
            "scip-typescript": "@sourcegraph/scip-typescript",
        }

        # Check if npm available
        if not self._is_npm_available():
            logger.warning("npm not found - SCIP indexers installation skipped", extra={"correlation_id": get_correlation_id()})
            logger.info("Install manually:", extra={"correlation_id": get_correlation_id()})
            for package in indexers.values():
                logger.info(f"  npm install -g {package}", extra={"correlation_id": get_correlation_id()})
            return False

        all_installed = True
        for indexer_cmd, npm_package in indexers.items():
            # Check if already installed (idempotent)
            if self._is_scip_indexer_installed(indexer_cmd):
                logger.info(f"{indexer_cmd} already installed", extra={"correlation_id": get_correlation_id()})
                continue

            # Install via npm
            try:
                logger.info(f"Installing {indexer_cmd} via npm...", extra={"correlation_id": get_correlation_id()})
                result = subprocess.run(
                    ["npm", "install", "-g", npm_package],
                    capture_output=True,
                    text=True,
                    timeout=180,  # 3 minute timeout for npm install
                )

                if result.returncode != 0:
                    logger.error(f"{indexer_cmd} installation failed: {result.stderr}", extra={"correlation_id": get_correlation_id()})
                    all_installed = False
                    continue

                # Verify installation succeeded
                if self._is_scip_indexer_installed(indexer_cmd):
                    logger.info(f"{indexer_cmd} installed successfully", extra={"correlation_id": get_correlation_id()})
                else:
                    logger.error(
                        f"{indexer_cmd} installation failed: verification failed"
                    , extra={"correlation_id": get_correlation_id()})
                    all_installed = False

            except subprocess.TimeoutExpired:
                logger.error(f"{indexer_cmd} installation failed: timeout", extra={"correlation_id": get_correlation_id()})
                all_installed = False
            except Exception as e:
                logger.error(f"{indexer_cmd} installation failed: {e}", extra={"correlation_id": get_correlation_id()})
                all_installed = False

        # Install scip-dotnet (non-fatal if fails)
        self.install_scip_dotnet()

        # Install scip-go (non-fatal if fails)
        self.install_scip_go()

        return all_installed

    def _is_dotnet_sdk_available(self) -> bool:
        """
        Check if .NET SDK is available.

        Returns:
            True if dotnet command is available
        """
        try:
            result = subprocess.run(
                ["dotnet", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _is_scip_dotnet_installed(self) -> bool:
        """
        Check if scip-dotnet is installed.

        Returns:
            True if scip-dotnet command is available
        """
        try:
            result = subprocess.run(
                ["scip-dotnet", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def install_scip_dotnet(self) -> bool:
        """
        Install scip-dotnet if .NET SDK is available.

        Returns:
            True if scip-dotnet is available after this method
            (either already installed or successfully installed),
            False if installation failed or .NET SDK not available.
        """
        # Check if already installed (idempotent)
        if self._is_scip_dotnet_installed():
            logger.info("scip-dotnet already installed", extra={"correlation_id": get_correlation_id()})
            return True

        # Check if .NET SDK available
        if not self._is_dotnet_sdk_available():
            logger.warning(".NET SDK not found - scip-dotnet installation skipped", extra={"correlation_id": get_correlation_id()})
            logger.info("Install .NET SDK manually to enable C# SCIP indexing", extra={"correlation_id": get_correlation_id()})
            return False

        # Install via dotnet tool
        try:
            logger.info("Installing scip-dotnet via dotnet tool...", extra={"correlation_id": get_correlation_id()})
            result = subprocess.run(
                ["dotnet", "tool", "install", "--global", "scip-dotnet"],
                capture_output=True,
                text=True,
                timeout=180,  # 3 minute timeout
            )

            if result.returncode != 0:
                logger.error(f"scip-dotnet installation failed: {result.stderr}", extra={"correlation_id": get_correlation_id()})
                return False

            # Verify installation succeeded
            if self._is_scip_dotnet_installed():
                logger.info("scip-dotnet installed successfully", extra={"correlation_id": get_correlation_id()})
                return True
            else:
                logger.error("scip-dotnet installation failed: verification failed", extra={"correlation_id": get_correlation_id()})
                return False

        except subprocess.TimeoutExpired:
            logger.error("scip-dotnet installation failed: timeout", extra={"correlation_id": get_correlation_id()})
            return False
        except Exception as e:
            logger.error(f"scip-dotnet installation failed: {e}", extra={"correlation_id": get_correlation_id()})
            return False

    def _is_go_sdk_available(self) -> bool:
        """
        Check if Go SDK is available.

        Returns:
            True if go command is available
        """
        try:
            result = subprocess.run(
                ["go", "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _is_scip_go_installed(self) -> bool:
        """
        Check if scip-go is installed.

        Returns:
            True if scip-go command is available
        """
        try:
            result = subprocess.run(
                ["scip-go", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def install_scip_go(self) -> bool:
        """
        Install scip-go if Go SDK is available.

        Returns:
            True if scip-go is available after this method
            (either already installed or successfully installed),
            False if installation failed or Go SDK not available.
        """
        # Check if already installed (idempotent)
        if self._is_scip_go_installed():
            logger.info("scip-go already installed", extra={"correlation_id": get_correlation_id()})
            return True

        # Check if Go SDK available
        if not self._is_go_sdk_available():
            logger.warning("Go SDK not found - scip-go installation skipped", extra={"correlation_id": get_correlation_id()})
            logger.info("Install Go from https://go.dev/dl/", extra={"correlation_id": get_correlation_id()})
            return False

        # Install via go install
        try:
            logger.info("Installing scip-go via go install...", extra={"correlation_id": get_correlation_id()})
            result = subprocess.run(
                ["go", "install", "github.com/sourcegraph/scip-go/cmd/scip-go@latest"],
                capture_output=True,
                text=True,
                timeout=180,  # 3 minute timeout
            )

            if result.returncode != 0:
                logger.error(f"scip-go installation failed: {result.stderr}", extra={"correlation_id": get_correlation_id()})
                return False

            # Verify installation succeeded
            if self._is_scip_go_installed():
                logger.info("scip-go installed successfully", extra={"correlation_id": get_correlation_id()})
                return True
            else:
                logger.error("scip-go installation failed: verification failed", extra={"correlation_id": get_correlation_id()})
                return False

        except subprocess.TimeoutExpired:
            logger.error("scip-go installation failed: timeout", extra={"correlation_id": get_correlation_id()})
            return False
        except Exception as e:
            logger.error(f"scip-go installation failed: {e}", extra={"correlation_id": get_correlation_id()})
            return False
