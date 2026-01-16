"""Unit tests for DaemonConfig schema updates."""

from typing import get_args

import pytest
from pydantic import ValidationError

from code_indexer.config import DaemonConfig


class TestDaemonConfigSocketFields:
    """Tests for socket-related fields in DaemonConfig."""

    def test_daemon_config_has_socket_mode_field(self):
        """DaemonConfig should have socket_mode field."""
        config = DaemonConfig()
        assert hasattr(config, 'socket_mode')

    def test_daemon_config_socket_mode_defaults_to_shared(self):
        """socket_mode should default to 'shared'."""
        config = DaemonConfig()
        assert config.socket_mode == "shared"

    def test_daemon_config_has_socket_base_field(self):
        """DaemonConfig should have optional socket_base field."""
        config = DaemonConfig()
        assert hasattr(config, 'socket_base')
        assert config.socket_base is None

    def test_daemon_config_validates_socket_mode_values(self):
        """socket_mode should only accept 'shared' or 'user'."""
        # Valid modes
        config_shared = DaemonConfig(socket_mode="shared")
        assert config_shared.socket_mode == "shared"

        config_user = DaemonConfig(socket_mode="user")
        assert config_user.socket_mode == "user"

        # Invalid mode should raise validation error
        with pytest.raises(ValidationError) as excinfo:
            DaemonConfig(socket_mode="invalid")

        errors = excinfo.value.errors()
        assert len(errors) == 1
        assert "socket_mode" in str(errors[0])

    def test_socket_base_can_be_set(self):
        """socket_base should accept string paths."""
        config = DaemonConfig(socket_base="/custom/socket/path")
        assert config.socket_base == "/custom/socket/path"

    def test_socket_base_remains_optional(self):
        """socket_base should remain None if not provided."""
        config = DaemonConfig()
        assert config.socket_base is None

    def test_existing_fields_still_work(self):
        """Existing DaemonConfig fields should continue to work."""
        config = DaemonConfig(
            enabled=True,
            ttl_minutes=30,
            auto_shutdown_on_idle=False,
            max_retries=5,
            retry_delays_ms=[100, 200, 300],
            eviction_check_interval_seconds=120,
        )
        assert config.enabled is True
        assert config.ttl_minutes == 30
        assert config.auto_shutdown_on_idle is False
        assert config.max_retries == 5
        assert config.retry_delays_ms == [100, 200, 300]
        assert config.eviction_check_interval_seconds == 120

    def test_model_dump_includes_socket_fields(self):
        """model_dump should include socket_mode and socket_base."""
        config = DaemonConfig(socket_mode="user", socket_base="/tmp/custom")
        dumped = config.model_dump()

        assert "socket_mode" in dumped
        assert dumped["socket_mode"] == "user"
        assert "socket_base" in dumped
        assert dumped["socket_base"] == "/tmp/custom"