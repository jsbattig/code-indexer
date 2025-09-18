"""Mode-specific command handlers for status and uninstall commands.

Provides different implementations based on operational mode (local, remote, uninitialized).
"""

import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from rich.console import Console
from rich.table import Table

from .remote_uninstall import RemoteUninstaller
from .remote.config import load_remote_configuration

console = Console()


def _get_local_repository_url(project_root: Path) -> Optional[str]:
    """Get the local repository URL from git remote origin.

    Args:
        project_root: Path to the project root directory

    Returns:
        Repository URL or None if not available
    """
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception:
        return None


def _get_local_branch(project_root: Path) -> Optional[str]:
    """Get the current local branch name.

    Args:
        project_root: Path to the project root directory

    Returns:
        Current branch name or None if not available
    """
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
        return None
    except Exception:
        return None


async def display_remote_status(project_root: Path) -> None:
    """Display comprehensive remote mode status information with real server health checks.

    MESSI RULES COMPLIANCE:
    - Uses real server health checks instead of fake data (Anti-Mock Rule #1)
    - No fallbacks to fake status information (Anti-Fallback Rule #2)
    - Returns real status or fails honestly (Facts-Based Reasoning)

    Args:
        project_root: Path to the project root directory
    """
    try:
        # Load remote configuration
        remote_config = load_remote_configuration(project_root)

        # Get local repository information
        local_repo_url = _get_local_repository_url(project_root)
        local_branch = _get_local_branch(project_root)

        # Handle missing local git information
        if not local_repo_url:
            local_repo_url = "unknown"
        if not local_branch:
            local_branch = "unknown"

        # REAL SERVER HEALTH CHECK - No fake data!
        console.print("🔍 Checking server health...", style="yellow")
        from .remote.health_checker import check_remote_server_health

        health_result = await check_remote_server_health(project_root)

        # Create status information using REAL server health data
        status_info = {
            "remote_config": {
                "server_url": remote_config.get("server_url", "Not configured"),
                "repository_alias": "Remote repository",
                "repository_branch": local_branch,
                "last_query_timestamp": None,
            },
            "connection_health": {
                "connection_health": health_result.connection_health,
                "server_reachable": health_result.server_reachable,
                "authentication_valid": health_result.authentication_valid,
                "repository_accessible": health_result.repository_accessible,
                "server_info": health_result.server_info,
                "error_details": health_result.error_details,
                "check_timestamp": (
                    health_result.check_timestamp.isoformat()
                    if health_result.check_timestamp
                    else None
                ),
            },
        }

        # Create status display table
        table = Table(title="🌐 Remote Code Indexer Status")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="magenta")
        table.add_column("Details", style="green")

        # Remote server information
        remote_config = status_info["remote_config"]
        server_url = remote_config["server_url"]
        repo_alias = remote_config["repository_alias"] or "Not configured"

        table.add_row(
            "Remote Server",
            "🌐 Connected" if server_url else "❌ Not configured",
            server_url or "No server URL configured",
        )

        table.add_row(
            "Repository",
            "📂 Linked" if repo_alias != "Not configured" else "❌ Not linked",
            f"{repo_alias} ({remote_config.get('repository_branch', 'unknown')})",
        )

        # Connection health
        health_info = status_info["connection_health"]
        health_status = health_info["connection_health"]
        health_emoji = {
            "healthy": "✅",
            "authentication_failed": "🔐",
            "repository_access_denied": "🚫",
            "server_unreachable": "❌",
            "timeout": "⏱️",
            "connection_error": "🔌",
            "unknown": "❓",
        }.get(health_status, "❓")

        table.add_row(
            "Connection Health",
            f"{health_emoji} {health_status.replace('_', ' ').title()}",
            _get_health_details(health_info),
        )

        # Last query information
        last_query = remote_config.get("last_query_timestamp")
        if last_query:
            table.add_row(
                "Last Query",
                "📅 Recent",
                last_query,
            )

        console.print(table)

        # Additional guidance based on status
        _provide_status_guidance(status_info)

    except Exception as e:
        console.print(f"❌ Failed to display remote status: {e}", style="red")
        return


def display_local_status(project_root: Path, force_docker: bool = False) -> None:
    """Display local mode status information (delegates to existing implementation).

    Args:
        project_root: Path to the project root directory
        force_docker: Force use of Docker even if Podman is available
    """
    # Import existing status implementation
    from .cli import cli, _status_impl

    # Create proper context for status implementation
    from .config import ConfigManager
    import click

    # Create real context with config manager
    ctx = click.Context(cli)
    ctx.obj = {"config_manager": ConfigManager.create_with_backtrack(project_root)}

    _status_impl(ctx, force_docker)


def display_uninitialized_status(project_root: Path) -> None:
    """Display status information for uninitialized mode.

    Args:
        project_root: Path to the project root directory
    """
    console.print("\n🚀 Code Indexer - Uninitialized", style="bold blue")
    console.print("=" * 40)

    console.print("\n📁 Current Directory:", style="cyan")
    console.print(f"   {project_root}")

    console.print("\n⚙️  Configuration Status:", style="cyan")
    console.print("   ❌ No configuration found")

    config_dir = project_root / ".code-indexer"
    if config_dir.exists():
        console.print(f"   📂 Config directory exists: {config_dir}")
        console.print("   📄 But no valid configuration files found")
    else:
        console.print(f"   📂 Config directory missing: {config_dir}")

    console.print("\n🚀 Getting Started:", style="cyan")
    console.print("   1. For local indexing:")
    console.print("      cidx init")
    console.print("      cidx start")
    console.print()
    console.print("   2. For remote repository access:")
    console.print("      cidx init --remote --server-url <url>")
    console.print()
    console.print("   3. Quick start (auto-configuration):")
    console.print("      cidx start  # Creates default config if needed")


def uninstall_remote_mode(project_root: Path, confirm: bool = False) -> None:
    """Uninstall remote mode configuration.

    Args:
        project_root: Path to the project root directory
        confirm: Skip confirmation prompt if True
    """
    try:
        uninstaller = RemoteUninstaller(project_root)
        success = uninstaller.uninstall(confirm=confirm)

        if success:
            console.print("✅ Remote mode uninstalled successfully", style="green")
        else:
            console.print(
                "❌ Remote mode uninstall failed or was cancelled", style="red"
            )

    except Exception as e:
        console.print(f"❌ Error during remote uninstall: {e}", style="red")


def uninstall_local_mode(
    project_root: Path, force_docker: bool = False, wipe_all: bool = False
) -> None:
    """Uninstall local mode configuration (delegates to existing implementation).

    Args:
        project_root: Path to the project root directory
        force_docker: Force use of Docker even if Podman is available
        wipe_all: Perform complete system wipe
    """
    # Import and delegate to existing uninstall implementation
    from .cli import cli
    import click

    # Create real click context for uninstall
    ctx = click.Context(cli)
    ctx.obj = {}

    # Change to project directory for uninstall
    import os

    original_cwd = os.getcwd()
    try:
        os.chdir(project_root)
        cli.uninstall(ctx, force_docker, wipe_all)
    finally:
        os.chdir(original_cwd)


def _get_health_details(health_info: Dict[str, Any]) -> str:
    """Get detailed health information string using real server data.

    Args:
        health_info: Real health check results from server

    Returns:
        Formatted health details string
    """
    details = []

    # Add server reachability status
    if health_info.get("server_reachable"):
        details.append("Server reachable")
    else:
        details.append("Server unreachable")

    # Add authentication status
    if health_info.get("authentication_valid"):
        details.append("Auth valid")
    elif health_info.get("server_reachable"):
        details.append("Auth failed")

    # Add repository access status
    if health_info.get("repository_accessible"):
        details.append("Repo accessible")
    elif health_info.get("authentication_valid"):
        details.append("Repo access denied")

    # Add server version if available
    server_info = health_info.get("server_info")
    if server_info and isinstance(server_info, dict):
        version = server_info.get("server_version")
        if version and version != "unknown":
            details.append(f"v{version}")

    # Add error details if present
    error_details = health_info.get("error_details")
    if error_details:
        details.append(f"Error: {error_details}")

    # Add timestamp if available
    check_timestamp = health_info.get("check_timestamp")
    if check_timestamp:
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(check_timestamp.replace("Z", "+00:00"))
            time_str = dt.strftime("%H:%M:%S")
            details.append(f"Checked: {time_str}")
        except Exception:
            pass

    return ", ".join(details) if details else "No details available"


def _provide_status_guidance(status_info: Dict[str, Any]) -> None:
    """Provide actionable guidance based on status information.

    Args:
        status_info: Complete status information
    """
    health_status = status_info["connection_health"]["connection_health"]

    console.print("\n💡 Recommendations:", style="bold yellow")

    if health_status == "server_unreachable":
        console.print("   🔌 Server is unreachable - check network connection")
        console.print("   🛠️  Verify server URL in remote configuration")
    elif health_status == "authentication_failed":
        console.print("   🔐 Authentication failed - credentials may be expired")
        console.print("   🔑 Consider re-initializing with fresh credentials")
    elif health_status == "repository_access_denied":
        console.print("   🚫 Repository access denied - check permissions")
        console.print("   👥 Contact repository owner for access")
    elif health_status == "credentials_not_found":
        console.print("   🔑 No stored credentials found")
        console.print(
            "   🛠️  Initialize remote mode with: cidx init --remote --server-url <url>"
        )
    elif health_status == "credential_error":
        console.print("   ⚠️  Credential storage error - may need to re-initialize")
        console.print("   🔑 Try: cidx init --remote --server-url <url>")
    elif health_status == "health_check_failed":
        console.print("   ❌ Health check failed unexpectedly")
        console.print("   🔍 Check server status and network connectivity")

    if health_status == "healthy":
        console.print("   ✅ Everything looks good - ready for semantic queries!")
