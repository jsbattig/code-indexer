#!/usr/bin/env python3
"""
CIDX MCPB Token Refresh Utility

Automatically refreshes CIDX server authentication tokens and updates configuration.
Designed to be run via cron or manually when tokens expire.

Usage:
    cidx-token-refresh [--config PATH]

The command will:
1. Read current tokens from ~/.mcpb/config.json
2. Call the /auth/refresh endpoint on the CIDX server
3. Update the config file with new access and refresh tokens
4. Set secure permissions (600) on the config file
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict

import httpx
from rich.console import Console

console = Console()

DEFAULT_CONFIG_PATH = Path.home() / ".mcpb" / "config.json"


def load_config(config_path: Path) -> Dict:
    """Load MCPB configuration file."""
    if not config_path.exists():
        console.print(f"[red]❌ Config file not found: {config_path}[/red]")
        console.print(f"[yellow]Expected location: {DEFAULT_CONFIG_PATH}[/yellow]")
        sys.exit(1)

    try:
        with open(config_path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        console.print(f"[red]❌ Invalid JSON in config file: {e}[/red]")
        sys.exit(1)


def save_config(config_path: Path, config: Dict) -> None:
    """Save MCPB configuration file with secure permissions."""
    try:
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        # Set secure permissions (owner read/write only)
        config_path.chmod(0o600)
    except Exception as e:
        console.print(f"[red]❌ Failed to save config: {e}[/red]")
        sys.exit(1)


def refresh_token(server_url: str, refresh_token: str) -> Dict:
    """Call the /auth/refresh endpoint to get new tokens."""
    refresh_url = f"{server_url.rstrip('/')}/auth/refresh"

    try:
        with httpx.Client(timeout=30.0, verify=True) as client:
            response = client.post(
                refresh_url,
                json={"refresh_token": refresh_token},
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                console.print("[red]❌ Refresh token is invalid or expired[/red]")
                console.print(
                    "[yellow]You need to log in again to get a new refresh token[/yellow]"
                )
                sys.exit(1)
            else:
                console.print(
                    f"[red]❌ Server returned error: {response.status_code}[/red]"
                )
                console.print(f"Response: {response.text}")
                sys.exit(1)

    except httpx.RequestError as e:
        console.print(f"[red]❌ Connection failed: {e}[/red]")
        sys.exit(1)


def main():
    """Main entry point for token refresh command."""
    parser = argparse.ArgumentParser(
        description="Refresh CIDX server authentication tokens",
        epilog="Configuration file: ~/.mcpb/config.json",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to config file (default: {DEFAULT_CONFIG_PATH})",
    )

    args = parser.parse_args()

    console.print("[blue]🔄 CIDX Token Refresh[/blue]")
    console.print(f"Config file: {args.config}")
    console.print()

    # Load configuration
    config = load_config(args.config)

    # Validate required fields
    if "server_url" not in config:
        console.print("[red]❌ Missing 'server_url' in config file[/red]")
        sys.exit(1)

    if "refresh_token" not in config:
        console.print("[red]❌ Missing 'refresh_token' in config file[/red]")
        console.print("[yellow]Initial login required to obtain refresh token[/yellow]")
        sys.exit(1)

    server_url = config["server_url"]
    old_refresh_token = config["refresh_token"]

    console.print(f"Server: {server_url}")
    console.print()

    # Call refresh endpoint
    console.print("Refreshing tokens...")
    result = refresh_token(server_url, old_refresh_token)

    # Update configuration with new tokens
    config["bearer_token"] = result["access_token"]
    config["refresh_token"] = result.get("refresh_token", old_refresh_token)

    # Save updated configuration
    save_config(args.config, config)

    console.print("[green]✅ Tokens refreshed successfully[/green]")
    console.print(f"Access token: {result['access_token'][:50]}...")
    console.print(f"Expires in: {result.get('access_token_expires_in', 'unknown')}s")
    console.print()
    console.print(f"[dim]Configuration updated: {args.config}[/dim]")


if __name__ == "__main__":
    main()
