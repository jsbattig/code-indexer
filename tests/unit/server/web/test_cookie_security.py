"""Tests for cookie security helper functions."""
import pytest
from code_indexer.server.web.auth import should_use_secure_cookies
from code_indexer.server.utils.config_manager import ServerConfig


class TestCookieSecurity:
    """Test secure cookie configuration based on server host."""

    def test_localhost_127_uses_insecure_cookies(self):
        """Test that 127.0.0.1 uses secure=False for HTTP compatibility."""
        config = ServerConfig(server_dir="/tmp", host="127.0.0.1", port=8090)
        assert should_use_secure_cookies(config) is False

    def test_localhost_name_uses_insecure_cookies(self):
        """Test that 'localhost' uses secure=False for HTTP compatibility."""
        config = ServerConfig(server_dir="/tmp", host="localhost", port=8090)
        assert should_use_secure_cookies(config) is False

    def test_localhost_ipv6_uses_insecure_cookies(self):
        """Test that ::1 (IPv6 localhost) uses secure=False for HTTP compatibility."""
        config = ServerConfig(server_dir="/tmp", host="::1", port=8090)
        assert should_use_secure_cookies(config) is False

    def test_production_binding_uses_secure_cookies(self):
        """Test that 0.0.0.0 (production binding) uses secure=True for HTTPS."""
        config = ServerConfig(server_dir="/tmp", host="0.0.0.0", port=8090)
        assert should_use_secure_cookies(config) is True

    def test_public_ip_uses_secure_cookies(self):
        """Test that public IP addresses use secure=True for HTTPS."""
        config = ServerConfig(server_dir="/tmp", host="192.168.1.100", port=8090)
        assert should_use_secure_cookies(config) is True

    def test_domain_name_uses_secure_cookies(self):
        """Test that domain names use secure=True for HTTPS."""
        config = ServerConfig(server_dir="/tmp", host="example.com", port=8090)
        assert should_use_secure_cookies(config) is True
