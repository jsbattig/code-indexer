"""Tests for SSH Keys Web UI (Scenario 23)."""

from pathlib import Path


class TestSSHKeysWebUI:
    """Tests for Scenario 23: Web UI Migration Status Display."""

    def test_ssh_keys_template_exists(self):
        """SSH keys template file should exist."""
        template_path = (
            Path(__file__).parent.parent.parent.parent
            / "src"
            / "code_indexer"
            / "server"
            / "web"
            / "templates"
            / "ssh_keys.html"
        )
        assert template_path.exists(), f"Template not found at {template_path}"

    def test_ssh_keys_template_no_migration_status_section(self):
        """Template should NOT contain migration status section (removed as useless)."""
        template_path = (
            Path(__file__).parent.parent.parent.parent
            / "src"
            / "code_indexer"
            / "server"
            / "web"
            / "templates"
            / "ssh_keys.html"
        )

        content = template_path.read_text()

        # Migration status section should be removed
        assert "migration_result" not in content
        assert "Migration Status" not in content

        # Should still have key listing
        assert "key" in content.lower()
        assert "managed" in content.lower()

    def test_ssh_keys_template_has_copy_button(self):
        """Template should have copy public key functionality."""
        template_path = (
            Path(__file__).parent.parent.parent.parent
            / "src"
            / "code_indexer"
            / "server"
            / "web"
            / "templates"
            / "ssh_keys.html"
        )

        content = template_path.read_text()

        # Should have copy functionality
        assert "copy" in content.lower()

    def test_ssh_keys_route_exists(self):
        """SSH keys route should be registered."""
        from code_indexer.server.web.routes import web_router

        route_paths = [route.path for route in web_router.routes]

        # Check for ssh-keys route
        assert any("ssh" in path.lower() for path in route_paths)
