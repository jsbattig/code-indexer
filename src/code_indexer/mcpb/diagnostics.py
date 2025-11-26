"""Configuration diagnostics for MCP Stdio Bridge.

This module provides diagnostic functionality to inspect configuration sources,
validate settings, and test server connectivity.
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .config import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_LOG_LEVEL,
    DEFAULT_TIMEOUT,
    load_config,
)
from .http_client import BridgeHttpClient


def mask_token(token: str) -> str:
    """Mask bearer token for security.

    Args:
        token: Bearer token to mask

    Returns:
        Masked token showing only last 3 characters
    """
    if not token:
        return "****"
    if len(token) <= 3:
        return f"****{token}"
    return f"****{token[-3:]}"


async def test_server_connectivity(
    server_url: str, bearer_token: str, timeout: int = 30
) -> Tuple[str, str, Optional[str]]:
    """Test connectivity to CIDX server.

    Args:
        server_url: Server URL to test
        bearer_token: Bearer token for authentication
        timeout: Request timeout in seconds

    Returns:
        Tuple of (status, message, version):
            status: "success" or "error"
            message: Description of result
            version: Server version if available, else None
    """
    client = BridgeHttpClient(
        server_url=server_url, bearer_token=bearer_token, timeout=timeout
    )

    try:
        # Try to get server version via health/status endpoint
        # For now, just test basic connectivity with a simple request
        test_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        }

        response = await client.forward_request(test_request)

        # If we got a response, server is reachable
        # Try to extract version from response if available
        version = None
        if isinstance(response, dict):
            # Check for version in result
            if "result" in response and isinstance(response["result"], dict):
                version = response["result"].get("version")

        return ("success", "Server reachable", version)

    except Exception as e:
        return ("error", f"Connection failed: {str(e)}", None)

    finally:
        await client.close()


@dataclass
class DiagnosticsResult:
    """Result of configuration diagnostics.

    Attributes:
        env_vars: Environment variables found (with masked tokens)
        file_config: Configuration from file (with masked tokens)
        effective_config: Final effective configuration (with masked tokens)
        sources: Source of each config value (environment/file/default)
        connectivity_status: Server connectivity test status
        connectivity_message: Server connectivity test message
        server_version: Server version if available
    """

    env_vars: Dict[str, str] = field(default_factory=dict)
    file_config: Dict[str, Any] = field(default_factory=dict)
    effective_config: Dict[str, Any] = field(default_factory=dict)
    sources: Dict[str, str] = field(default_factory=dict)
    connectivity_status: str = "not_tested"
    connectivity_message: str = ""
    server_version: Optional[str] = None

    def format_output(self) -> str:
        """Format diagnostics result as human-readable string.

        Returns:
            Formatted diagnostics output
        """
        lines = []
        lines.append("Configuration Diagnostics")
        lines.append("=" * 50)
        lines.append("")

        # Environment Variables section
        lines.append("Environment Variables:")
        if self.env_vars:
            for key, value in sorted(self.env_vars.items()):
                lines.append(f"  {key}: {value}")
        else:
            lines.append("  (none set)")
        lines.append("")

        # Config File section
        lines.append("Config File (~/.mcpb/config.json):")
        if self.file_config:
            for key, value in sorted(self.file_config.items()):
                lines.append(f"  {key}: {value}")
        else:
            lines.append("  (not used)")
        lines.append("")

        # Effective Configuration section
        lines.append("Effective Configuration:")
        for key, value in sorted(self.effective_config.items()):
            source = self.sources.get(key, "unknown")
            lines.append(f"  {key}: {value} (from {source})")
        lines.append("")

        # Server Connectivity section
        lines.append("Server Connectivity:")
        if self.connectivity_status == "success":
            lines.append(f"  Status: {self.connectivity_message}")
            if self.server_version:
                lines.append(f"  Server version: {self.server_version}")
        elif self.connectivity_status == "error":
            lines.append(f"  Status: {self.connectivity_message}")
        else:
            lines.append("  Status: Not tested")
        lines.append("")

        return "\n".join(lines)


def diagnose_configuration(
    config_path: Optional[str] = None, use_env: bool = True
) -> DiagnosticsResult:
    """Diagnose configuration sources and settings.

    Args:
        config_path: Path to config file (default: ~/.mcpb/config.json)
        use_env: Whether to use environment variables

    Returns:
        DiagnosticsResult with all diagnostic information
    """
    result = DiagnosticsResult()

    # Collect environment variables (masked)
    env_var_names = [
        "CIDX_SERVER_URL",
        "CIDX_TOKEN",
        "CIDX_TIMEOUT",
        "CIDX_LOG_LEVEL",
        "MCPB_SERVER_URL",
        "MCPB_BEARER_TOKEN",
        "MCPB_TIMEOUT",
        "MCPB_LOG_LEVEL",
    ]

    for var_name in env_var_names:
        if var_name in os.environ:
            value = os.environ[var_name]
            # Mask tokens
            if "TOKEN" in var_name:
                value = mask_token(value)
            result.env_vars[var_name] = value

    # Collect file config (masked)
    file_config_data = {}
    if config_path is not None or (not use_env):
        path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        path = path.expanduser().resolve()

        if path.exists():
            with open(path) as f:
                file_config_data = json.load(f)

            # Mask token in file config
            for key, value in file_config_data.items():
                if key == "bearer_token":
                    result.file_config[key] = mask_token(str(value))
                else:
                    result.file_config[key] = value

    # Load actual configuration
    config = load_config(config_path=config_path, use_env=use_env)

    # Build effective config (masked) and track sources
    result.effective_config = {
        "server_url": config.server_url,
        "bearer_token": mask_token(config.bearer_token),
        "timeout": config.timeout,
        "log_level": config.log_level,
    }

    # Determine source of each value
    # Server URL
    if use_env and "CIDX_SERVER_URL" in os.environ:
        result.sources["server_url"] = "environment"
    elif use_env and "MCPB_SERVER_URL" in os.environ:
        result.sources["server_url"] = "environment"
    elif "server_url" in file_config_data:
        result.sources["server_url"] = "file"
    else:
        result.sources["server_url"] = "unknown"

    # Bearer token
    if use_env and "CIDX_TOKEN" in os.environ:
        result.sources["bearer_token"] = "environment"
    elif use_env and "MCPB_BEARER_TOKEN" in os.environ:
        result.sources["bearer_token"] = "environment"
    elif "bearer_token" in file_config_data:
        result.sources["bearer_token"] = "file"
    else:
        result.sources["bearer_token"] = "unknown"

    # Timeout
    if use_env and "CIDX_TIMEOUT" in os.environ:
        result.sources["timeout"] = "environment"
    elif use_env and "MCPB_TIMEOUT" in os.environ:
        result.sources["timeout"] = "environment"
    elif "timeout" in file_config_data:
        result.sources["timeout"] = "file"
    elif config.timeout == DEFAULT_TIMEOUT:
        result.sources["timeout"] = "default"
    else:
        result.sources["timeout"] = "unknown"

    # Log level
    if use_env and "CIDX_LOG_LEVEL" in os.environ:
        result.sources["log_level"] = "environment"
    elif use_env and "MCPB_LOG_LEVEL" in os.environ:
        result.sources["log_level"] = "environment"
    elif "log_level" in file_config_data:
        result.sources["log_level"] = "file"
    elif config.log_level == DEFAULT_LOG_LEVEL:
        result.sources["log_level"] = "default"
    else:
        result.sources["log_level"] = "unknown"

    # Test server connectivity
    try:
        status, message, version = asyncio.run(
            test_server_connectivity(
                server_url=config.server_url,
                bearer_token=config.bearer_token,
                timeout=config.timeout,
            )
        )
        result.connectivity_status = status
        result.connectivity_message = message
        result.server_version = version
    except Exception as e:
        result.connectivity_status = "error"
        result.connectivity_message = f"Connectivity test failed: {str(e)}"

    return result
