"""Remote Mode Uninstall Functionality.

Provides safe removal of remote configuration and credentials while preserving
local project files and structure.
"""

import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


class RemoteUninstaller:
    """Safely removes remote mode configuration and credentials."""

    def __init__(self, project_root: Path):
        """Initialize remote uninstaller.

        Args:
            project_root: Path to the project root directory
        """
        self.project_root = project_root
        self.config_dir = project_root / ".code-indexer"

    def uninstall(self, confirm: bool = False) -> bool:
        """Uninstall remote mode configuration safely.

        Args:
            confirm: If True, skip confirmation prompt

        Returns:
            True if uninstall was successful, False if cancelled
        """
        try:
            # Get preview of what will be removed and preserved
            preview = self.get_uninstall_preview()

            # Show preview and get confirmation if needed
            if not confirm:
                if not self._get_user_confirmation(preview):
                    print("Uninstall cancelled by user.")
                    return False

            # Remove remote configuration files
            success = self._remove_remote_files(preview["files_to_remove"])

            if success:
                print("✅ Remote configuration successfully removed.")
                self._provide_reinitialize_guidance()
                return True
            else:
                print("❌ Some files could not be removed. Check permissions.")
                return False

        except Exception as e:
            logger.error(f"Error during remote uninstall: {e}")
            print(f"❌ Uninstall failed: {e}")
            return False

    def get_uninstall_preview(self) -> Dict[str, List[str]]:
        """Get preview of what will be removed and what will be preserved.

        Returns:
            Dictionary with 'files_to_remove' and 'files_to_preserve' lists
        """
        files_to_remove = []
        files_to_preserve = []

        # Files that will be removed
        remote_config_files = [
            ".remote-config",
            ".credential-cache",
            ".server-session",
            ".remote-metadata",
        ]

        for filename in remote_config_files:
            file_path = self.config_dir / filename
            if file_path.exists():
                files_to_remove.append(str(file_path.relative_to(self.project_root)))

        # Files that will be preserved
        preserve_patterns = [
            "*.py",
            "*.md",
            "*.txt",
            "*.json",
            "*.yaml",
            "*.yml",
            ".git/*",
            "src/*",
            "docs/*",
            "tests/*",
            "requirements.*",
            "pyproject.toml",
            "setup.py",
            "README.*",
        ]

        # Scan project for files to preserve
        for pattern in preserve_patterns:
            for file_path in self.project_root.glob(pattern):
                if file_path.is_file():
                    rel_path = str(file_path.relative_to(self.project_root))
                    if rel_path not in files_to_preserve:
                        files_to_preserve.append(rel_path)

        return {
            "files_to_remove": files_to_remove,
            "files_to_preserve": files_to_preserve,
        }

    def _get_user_confirmation(self, preview: Dict[str, List[str]]) -> bool:
        """Get user confirmation for uninstall operation.

        Args:
            preview: Preview of files to remove and preserve

        Returns:
            True if user confirms, False otherwise
        """
        print("\n🗑️  Remote Configuration Uninstall Preview:")
        print("=" * 50)

        print("\n📄 Files to be REMOVED:")
        if preview["files_to_remove"]:
            for file_path in preview["files_to_remove"]:
                print(f"  ❌ {file_path}")
        else:
            print("  (No remote configuration files found)")

        print("\n💾 Files to be PRESERVED:")
        if preview["files_to_preserve"]:
            # Show first 10 files to avoid overwhelming output
            for file_path in preview["files_to_preserve"][:10]:
                print(f"  ✅ {file_path}")
            if len(preview["files_to_preserve"]) > 10:
                remaining = len(preview["files_to_preserve"]) - 10
                print(f"  ... and {remaining} more files")
        else:
            print("  (No project files found)")

        print("\n⚠️  This will disconnect your project from the remote repository.")
        print("💡 You can re-initialize with 'cidx init --remote' later.")

        while True:
            response = input("\nProceed with uninstall? (y/N): ").strip().lower()
            if response in ["y", "yes"]:
                return True
            elif response in ["n", "no", ""]:
                return False
            else:
                print("Please enter 'y' for yes or 'n' for no.")

    def _remove_remote_files(self, files_to_remove: List[str]) -> bool:
        """Remove remote configuration files safely.

        Args:
            files_to_remove: List of file paths to remove

        Returns:
            True if all files were removed successfully
        """
        success = True

        for file_path_str in files_to_remove:
            try:
                file_path = self.project_root / file_path_str
                if file_path.exists():
                    file_path.unlink()
                    logger.info(f"Removed remote configuration file: {file_path}")
                    print(f"  ✅ Removed {file_path_str}")
            except PermissionError:
                logger.error(f"Permission denied removing file: {file_path}")
                print(f"  ❌ Permission denied: {file_path_str}")
                success = False
            except OSError as e:
                logger.error(f"OS error removing file {file_path}: {e}")
                print(f"  ❌ Error removing {file_path_str}: {e}")
                success = False

        return success

    def _provide_reinitialize_guidance(self):
        """Provide guidance for re-initializing remote configuration."""
        print("\n💡 Re-initialization Options:")
        print("=" * 30)
        print("🔗 To reconnect to a remote repository:")
        print("   cidx init --remote --server-url <server_url>")
        print()
        print("🏠 To set up local indexing instead:")
        print("   cidx init")
        print()
        print("📚 For more options:")
        print("   cidx init --help")
