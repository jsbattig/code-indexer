"""
Server installation utilities for CIDX Server.

Handles server installation, port allocation, configuration setup,
and startup script generation.
"""

import socket
import stat
import sys
from pathlib import Path
from typing import Tuple, Optional

from .auth.user_manager import UserManager
from .utils.config_manager import ServerConfigManager
from .utils.jwt_secret_manager import JWTSecretManager


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
            voyage_api_key: VoyageAI API key for embeddings

        Returns:
            Path to created service file
        """
        import sys

        python_exe = sys.executable

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
User={Path.home().name}
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
