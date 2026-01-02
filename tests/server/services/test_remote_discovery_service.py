"""Unit tests for RemoteDiscoveryService."""

from code_indexer.server.services.remote_discovery_service import (
    RemoteDiscoveryService,
)


class TestRemoteDiscoveryServiceExtractHostname:
    """Tests for RemoteDiscoveryService.extract_hostname()."""

    def test_extract_hostname_from_ssh_git_format(self):
        """Should extract hostname from git@host:user/repo.git format."""
        service = RemoteDiscoveryService()

        hostname = service.extract_hostname("git@github.com:user/repo.git")

        assert hostname == "github.com"

    def test_extract_hostname_from_ssh_url_format(self):
        """Should extract hostname from ssh://git@host/user/repo.git format."""
        service = RemoteDiscoveryService()

        hostname = service.extract_hostname("ssh://git@gitlab.com/user/repo.git")

        assert hostname == "gitlab.com"

    def test_extract_hostname_from_https_format(self):
        """Should extract hostname from https URL format."""
        service = RemoteDiscoveryService()

        hostname = service.extract_hostname("https://github.com/user/repo.git")

        assert hostname == "github.com"

    def test_extract_hostname_returns_none_for_invalid(self):
        """Should return None for invalid/unrecognized URL formats."""
        service = RemoteDiscoveryService()

        hostname = service.extract_hostname("not-a-valid-url")

        assert hostname is None

    def test_extract_hostname_handles_port_in_ssh_url(self):
        """Should handle custom port in SSH URL format."""
        service = RemoteDiscoveryService()

        # ssh://git@hostname:port/path format
        hostname = service.extract_hostname(
            "ssh://git@private.server.com:2222/user/repo.git"
        )

        assert hostname == "private.server.com"


class TestRemoteDiscoveryServiceDiscoverRemotes:
    """Tests for RemoteDiscoveryService.discover_remote_hostnames()."""

    def test_discover_remotes_empty_when_no_config(self, tmp_path):
        """Should return empty set when CIDX config doesn't exist."""
        config_path = tmp_path / "config.json"
        service = RemoteDiscoveryService(config_path=config_path)

        hostnames = service.discover_remote_hostnames()

        assert hostnames == set()

    def test_discover_remotes_from_config_file(self, tmp_path):
        """Should discover hostnames from activated repositories in config."""
        config_path = tmp_path / "config.json"
        config_content = """{
            "activated_repositories": [
                {"path": "/repo1", "remote_url": "git@github.com:user/repo1.git"},
                {"path": "/repo2", "remote_url": "git@gitlab.com:user/repo2.git"}
            ]
        }"""
        config_path.write_text(config_content)

        service = RemoteDiscoveryService(config_path=config_path)
        hostnames = service.discover_remote_hostnames()

        assert "github.com" in hostnames
        assert "gitlab.com" in hostnames

    def test_discover_remotes_deduplicates_hostnames(self, tmp_path):
        """Should deduplicate hostnames when multiple repos use same host."""
        config_path = tmp_path / "config.json"
        config_content = """{
            "activated_repositories": [
                {"path": "/repo1", "remote_url": "git@github.com:user/repo1.git"},
                {"path": "/repo2", "remote_url": "git@github.com:org/repo2.git"},
                {"path": "/repo3", "remote_url": "git@github.com:team/repo3.git"}
            ]
        }"""
        config_path.write_text(config_content)

        service = RemoteDiscoveryService(config_path=config_path)
        hostnames = service.discover_remote_hostnames()

        assert len(hostnames) == 1
        assert "github.com" in hostnames
