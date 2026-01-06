"""Remote initialization orchestrator for CIDX."""

from pathlib import Path
from typing import Optional
from rich.console import Console

from .url_validator import validate_and_normalize_server_url
from .connectivity import test_server_connectivity
from .auth import validate_credentials
from .config import create_remote_configuration, RemoteConfig
from .exceptions import RemoteInitializationError
from .server_compatibility import ServerCompatibilityValidator


async def initialize_remote_mode(
    project_root: Path,
    server_url: str,
    username: str,
    password: str,
    console: Optional[Console] = None,
) -> None:
    """Initialize remote mode with comprehensive validation.

    This function orchestrates the complete remote initialization process:
    1. URL validation and normalization
    2. Server connectivity testing
    3. Credential validation
    4. Configuration creation

    Args:
        project_root: The root directory of the project
        server_url: The remote server URL
        username: Username for authentication
        password: Password for authentication
        console: Rich console for output (optional)

    Raises:
        RemoteInitializationError: If any step of initialization fails
    """
    if console is None:
        console = Console()

    try:
        # Step 1: Validate and normalize server URL
        console.print("🔗 Validating server URL...", style="blue")
        normalized_url = validate_and_normalize_server_url(server_url)
        console.print(f"✅ Server URL normalized: {normalized_url}")

        # Step 2: Test server connectivity
        console.print("🌐 Testing server connectivity...", style="blue")
        await test_server_connectivity(normalized_url)
        console.print("✅ Server is reachable")

        # Step 3: Validate credentials
        console.print("🔐 Validating credentials...", style="blue")
        user_info = await validate_credentials(normalized_url, username, password)
        console.print(f"✅ Authentication successful for user: {user_info['username']}")

        # Step 4: Create remote configuration (without credentials initially)
        console.print("📝 Creating remote configuration...", style="blue")
        create_remote_configuration(
            project_root=project_root,
            server_url=normalized_url,
            username=username,
            encrypted_credentials="",  # Will be set with actual encrypted credentials
        )
        console.print("✅ Remote configuration created")

        # Step 5: Store encrypted credentials using project-specific encryption
        console.print("🔒 Encrypting and storing credentials...", style="blue")
        remote_config = RemoteConfig(project_root)
        remote_config.store_credentials(password)
        console.print("✅ Credentials encrypted and stored securely")

        # Success message
        console.print()
        console.print("🎉 Remote mode initialized successfully!", style="bold green")
        console.print()
        console.print("Next steps:", style="bold")
        console.print("1. Start remote operations:", style="cyan")
        console.print("   cidx start")
        console.print()
        console.print("2. Query the remote index:", style="cyan")
        console.print("   cidx query 'your search terms'")
        console.print()

    except Exception as e:
        # Clean up any partial configuration on failure
        await _cleanup_on_failure(project_root)

        # Re-raise as RemoteInitializationError if it isn't already
        if isinstance(e, RemoteInitializationError):
            raise
        else:
            raise RemoteInitializationError(f"Remote initialization failed: {str(e)}")


async def _cleanup_on_failure(project_root: Path) -> None:
    """Clean up any partial configuration files created during failed initialization.

    Args:
        project_root: The root directory of the project
    """
    try:
        config_dir = project_root / ".code-indexer"
        remote_config_file = config_dir / ".remote-config"
        credentials_file = config_dir / ".creds"

        if remote_config_file.exists():
            remote_config_file.unlink()

        if credentials_file.exists():
            credentials_file.unlink()

        # Only remove the config directory if it's empty and we created it
        if config_dir.exists() and not any(config_dir.iterdir()):
            config_dir.rmdir()

    except Exception:
        # Ignore cleanup failures - we don't want to mask the original error
        pass


async def initialize_remote_mode_with_validation(
    project_root: Path,
    server_url: str,
    username: str,
    password: str,
    console: Optional[Console] = None,
) -> None:
    """Initialize remote mode with comprehensive server compatibility validation.

    This function orchestrates the complete remote initialization process with
    comprehensive server compatibility validation:
    1. URL validation and normalization
    2. Comprehensive server compatibility validation (API version, health, connectivity, auth, endpoints)
    3. Configuration creation based on validation results

    Args:
        project_root: The root directory of the project
        server_url: The remote server URL
        username: Username for authentication
        password: Password for authentication
        console: Rich console for output (optional)

    Raises:
        RemoteInitializationError: If any step of initialization fails or server is incompatible
    """
    if console is None:
        console = Console()

    try:
        # Step 1: Validate and normalize server URL
        console.print("🔗 Validating server URL...", style="blue")
        normalized_url = validate_and_normalize_server_url(server_url)
        console.print(f"✅ Server URL normalized: {normalized_url}")

        # Step 2: Comprehensive server compatibility validation
        console.print(
            "🔍 Performing comprehensive server compatibility validation...",
            style="blue",
        )
        validator = ServerCompatibilityValidator(normalized_url)
        compatibility_result = await validator.validate_compatibility(
            username, password
        )

        if not compatibility_result.compatible:
            # Display compatibility issues
            console.print(
                "❌ Server compatibility validation failed:", style="bold red"
            )
            console.print()
            for issue in compatibility_result.issues:
                console.print(f"• {issue}", style="red")

            console.print()
            if compatibility_result.recommendations:
                console.print("💡 Recommendations:", style="bold yellow")
                for recommendation in compatibility_result.recommendations:
                    console.print(f"• {recommendation}", style="yellow")

            # Create detailed error message for exception
            error_details = [
                "Server compatibility validation failed:",
                *compatibility_result.issues,
                "",
                "Recommendations:",
                *compatibility_result.recommendations,
            ]

            raise RemoteInitializationError("\n".join(error_details))

        # Display compatibility validation success
        console.print("✅ Server compatibility validation passed", style="green")

        # Display any warnings
        if compatibility_result.warnings:
            console.print()
            console.print("⚠️ Compatibility warnings:", style="bold yellow")
            for warning in compatibility_result.warnings:
                console.print(f"• {warning}", style="yellow")

        # Display server information
        if compatibility_result.server_info:
            console.print()
            console.print("📊 Server Information:", style="bold cyan")
            if "version" in compatibility_result.server_info:
                console.print(
                    f"• API Version: {compatibility_result.server_info['version']}"
                )
            if "health" in compatibility_result.server_info:
                console.print(
                    f"• Health Status: {compatibility_result.server_info['health']}"
                )
            if "authenticated_user" in compatibility_result.server_info:
                console.print(
                    f"• Authenticated User: {compatibility_result.server_info['authenticated_user']}"
                )

        # Display recommendations if any
        if compatibility_result.recommendations:
            console.print()
            console.print("💡 Recommendations:", style="bold blue")
            for recommendation in compatibility_result.recommendations:
                console.print(f"• {recommendation}", style="blue")

        # Step 3: Create remote configuration (without credentials initially)
        console.print()
        console.print("📝 Creating remote configuration...", style="blue")
        create_remote_configuration(
            project_root=project_root,
            server_url=normalized_url,
            username=username,
            encrypted_credentials="",  # Will be set with actual encrypted credentials
        )
        console.print("✅ Remote configuration created")

        # Step 4: Store encrypted credentials using project-specific encryption
        console.print("🔒 Encrypting and storing credentials...", style="blue")
        remote_config = RemoteConfig(project_root)
        remote_config.store_credentials(password)
        console.print("✅ Credentials encrypted and stored securely")

        # Success message
        console.print()
        console.print("🎉 Remote mode initialized successfully!", style="bold green")
        console.print()
        console.print("Next steps:", style="bold")
        console.print("1. Start remote operations:", style="cyan")
        console.print("   cidx start")
        console.print()
        console.print("2. Query the remote index:", style="cyan")
        console.print("   cidx query 'your search terms'")
        console.print()

    except Exception as e:
        # Clean up any partial configuration on failure
        await _cleanup_on_failure(project_root)

        # Re-raise as RemoteInitializationError if it isn't already
        if isinstance(e, RemoteInitializationError):
            raise
        else:
            raise RemoteInitializationError(f"Remote initialization failed: {str(e)}")
