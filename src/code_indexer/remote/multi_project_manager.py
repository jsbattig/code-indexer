"""Multi-project credential management utilities.

Provides utilities for managing credentials across multiple projects,
including secure cleanup and validation functions.
"""

from pathlib import Path
from typing import Optional, Dict, Any

from .credential_manager import (
    load_encrypted_credentials,
    CredentialNotFoundError,
    InsecureCredentialStorageError,
)
from .exceptions import RemoteConfigurationError


class ProjectCleanupError(RemoteConfigurationError):
    """Raised when project credential cleanup fails."""

    pass


class MultiProjectValidationError(RemoteConfigurationError):
    """Raised when multi-project validation fails."""

    pass


def cleanup_project_credentials(project_root: Path) -> Dict[str, Any]:
    """Clean up all credential-related data for a project.

    Removes all credential files, token files, and empty configuration
    directories associated with a project. This function should be called
    when a project is being removed or when credentials need to be reset.

    Args:
        project_root: The root directory of the project to clean up

    Returns:
        Dict with cleanup results: {
            "credentials_removed": bool,
            "tokens_removed": bool,
            "config_dir_removed": bool,
            "files_cleaned": List[str]
        }

    Raises:
        ProjectCleanupError: If cleanup operations fail
    """
    try:
        results: Dict[str, Any] = {
            "credentials_removed": False,
            "tokens_removed": False,
            "config_dir_removed": False,
            "files_cleaned": [],
        }

        config_dir = project_root / ".code-indexer"

        if not config_dir.exists():
            return results

        # Remove credential file
        creds_file = config_dir / ".creds"
        if creds_file.exists():
            creds_file.unlink()
            results["credentials_removed"] = True
            results["files_cleaned"].append(str(creds_file))

        # Remove token file
        token_file = config_dir / ".token"
        if token_file.exists():
            token_file.unlink()
            results["tokens_removed"] = True
            results["files_cleaned"].append(str(token_file))

        # Remove any other sensitive files in the config directory
        for file_path in config_dir.iterdir():
            if file_path.is_file() and file_path.name.startswith("."):
                file_path.unlink()
                results["files_cleaned"].append(str(file_path))

        # Remove config directory if empty
        if config_dir.exists() and not any(config_dir.iterdir()):
            config_dir.rmdir()
            results["config_dir_removed"] = True

        return results

    except Exception as e:
        raise ProjectCleanupError(f"Failed to clean up project credentials: {e}")


def validate_multi_project_isolation(
    projects: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Validate that multiple projects have proper credential isolation.

    Tests that credentials from different projects cannot be cross-accessed
    and that each project has independent credential storage.

    Args:
        projects: Dict mapping project names to project config:
            {
                "project_name": {
                    "path": Path,
                    "username": str,
                    "server_url": str,
                    "repo_path": str
                }
            }

    Returns:
        Dict with validation results: {
            "isolation_verified": bool,
            "projects_validated": List[str],
            "cross_access_prevented": bool,
            "independent_storage": bool,
            "issues": List[str]
        }

    Raises:
        MultiProjectValidationError: If validation fails critically
    """
    try:
        results: Dict[str, Any] = {
            "isolation_verified": True,
            "projects_validated": [],
            "cross_access_prevented": True,
            "independent_storage": True,
            "issues": [],
        }

        # Check that each project has independent credential storage
        credential_files = []
        for project_name, config in projects.items():
            try:
                project_path = config["path"]
                creds_file = project_path / ".code-indexer" / ".creds"

                if creds_file.exists():
                    # Verify file permissions
                    file_mode = creds_file.stat().st_mode & 0o777
                    if file_mode != 0o600:
                        results["issues"].append(
                            f"Project {project_name} has insecure credential file permissions: {oct(file_mode)}"
                        )
                        results["isolation_verified"] = False

                    # Load and verify credentials exist
                    try:
                        load_encrypted_credentials(project_path)
                        results["projects_validated"].append(project_name)
                        credential_files.append((project_name, creds_file))
                    except (
                        CredentialNotFoundError,
                        InsecureCredentialStorageError,
                    ) as e:
                        results["issues"].append(
                            f"Project {project_name} credential validation failed: {e}"
                        )
                        results["independent_storage"] = False

            except Exception as e:
                results["issues"].append(
                    f"Project {project_name} validation error: {e}"
                )
                results["isolation_verified"] = False

        # Verify all credential files are different (no shared storage)
        if len(credential_files) > 1:
            file_contents = {}
            for project_name, creds_file in credential_files:
                try:
                    with open(creds_file, "rb") as f:
                        content = f.read()
                    file_contents[project_name] = content
                except Exception as e:
                    results["issues"].append(
                        f"Failed to read credentials for {project_name}: {e}"
                    )
                    results["independent_storage"] = False

            # Check that no two projects share identical credential data
            project_names = list(file_contents.keys())
            for i in range(len(project_names)):
                for j in range(i + 1, len(project_names)):
                    project1, project2 = project_names[i], project_names[j]
                    if file_contents[project1] == file_contents[project2]:
                        results["issues"].append(
                            f"Projects {project1} and {project2} have identical credential data"
                        )
                        results["independent_storage"] = False
                        results["isolation_verified"] = False

        # Update overall validation status
        if results["issues"]:
            results["isolation_verified"] = False

        return results

    except Exception as e:
        raise MultiProjectValidationError(f"Multi-project validation failed: {e}")


def list_project_credentials(project_root: Path) -> Optional[Dict[str, Any]]:
    """List credential information for a project without exposing sensitive data.

    Args:
        project_root: The root directory of the project

    Returns:
        Dict with credential info or None if no credentials found:
        {
            "has_credentials": bool,
            "has_tokens": bool,
            "credentials_file_size": int,
            "token_file_size": int,
            "file_permissions_secure": bool,
            "created_at": Optional[float]  # File creation timestamp
        }
    """
    try:
        config_dir = project_root / ".code-indexer"

        if not config_dir.exists():
            return None

        info: Dict[str, Any] = {
            "has_credentials": False,
            "has_tokens": False,
            "credentials_file_size": 0,
            "token_file_size": 0,
            "file_permissions_secure": True,
            "created_at": None,
        }

        # Check credentials file
        creds_file = config_dir / ".creds"
        if creds_file.exists():
            info["has_credentials"] = True
            stat = creds_file.stat()
            info["credentials_file_size"] = stat.st_size
            info["created_at"] = stat.st_ctime

            # Check permissions
            file_mode = stat.st_mode & 0o777
            if file_mode != 0o600:
                info["file_permissions_secure"] = False

        # Check token file
        token_file = config_dir / ".token"
        if token_file.exists():
            info["has_tokens"] = True
            stat = token_file.stat()
            info["token_file_size"] = stat.st_size

            # Check permissions
            file_mode = stat.st_mode & 0o777
            if file_mode != 0o600:
                info["file_permissions_secure"] = False

        return info

    except Exception:
        return None


def secure_project_migration(
    source_project: Path, target_project: Path, username: str, server_url: str
) -> Dict[str, Any]:
    """Securely migrate credentials from one project to another.

    This function does NOT copy encrypted credentials directly (which would
    be insecure), but rather facilitates re-authentication in the target project.

    Args:
        source_project: Source project root path
        target_project: Target project root path
        username: Username for the credentials
        server_url: Server URL for the credentials

    Returns:
        Dict with migration results: {
            "source_has_credentials": bool,
            "migration_required": bool,
            "target_prepared": bool,
            "security_notes": List[str]
        }

    Note:
        This function intentionally does NOT copy encrypted credentials
        between projects to maintain security isolation. Users must
        re-authenticate in the target project.
    """
    try:
        results: Dict[str, Any] = {
            "source_has_credentials": False,
            "migration_required": False,
            "target_prepared": False,
            "security_notes": [],
        }

        # Check source project
        source_info = list_project_credentials(source_project)
        if source_info and source_info["has_credentials"]:
            results["source_has_credentials"] = True
            results["migration_required"] = True
            results["security_notes"].append(
                "Source project has credentials - target project will need re-authentication"
            )

        # Prepare target project directory structure
        target_config_dir = target_project / ".code-indexer"
        target_config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        results["target_prepared"] = True

        results["security_notes"].extend(
            [
                "Encrypted credentials cannot be copied between projects for security reasons",
                "Each project must authenticate independently",
                f"Target project prepared for authentication with username: {username}",
                f"Target project prepared for server: {server_url}",
            ]
        )

        return results

    except Exception as e:
        raise ProjectCleanupError(f"Project migration preparation failed: {e}")
