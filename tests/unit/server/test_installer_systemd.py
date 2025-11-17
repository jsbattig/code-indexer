"""
Unit tests for ServerInstaller.create_systemd_service method.

Tests systemd service file generation with OAuth issuer URL and API key configuration.
"""

import tempfile
from pathlib import Path

from code_indexer.server.installer import ServerInstaller


class TestServerInstallerSystemd:
    """Test suite for ServerInstaller systemd service creation."""

    def test_create_systemd_service_basic(self):
        """Test creating systemd service file with basic configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Patch home directory to use temp directory
            test_server_dir = Path(temp_dir) / ".cidx-server"
            test_server_dir.mkdir(parents=True)

            installer = ServerInstaller(base_port=8090)
            installer.server_dir = test_server_dir

            # Create systemd service file
            service_path = installer.create_systemd_service(port=8090)

            # Verify file was created
            assert service_path.exists()
            assert service_path.name == "cidx-server.service"

            # Read and verify content
            content = service_path.read_text()
            assert "[Unit]" in content
            assert "Description=CIDX Multi-User Server with MCP Integration" in content
            assert "[Service]" in content
            assert "ExecStart=" in content
            assert "--port 8090" in content
            assert "[Install]" in content
            assert "WantedBy=multi-user.target" in content
