"""
Git hook manager for branch change detection.

This module manages git hooks to detect branch changes during indexing operations.
When a branch switch occurs, it updates the progressive metadata file to ensure
subsequent file indexing uses the correct branch information.
"""

from pathlib import Path
from typing import Optional


class GitHookManager:
    """Manages git hooks for branch change detection."""

    def __init__(self, repo_path: Path, metadata_file: Optional[Path] = None):
        """
        Initialize git hook manager.

        Args:
            repo_path: Path to the git repository
            metadata_file: Path to the progressive metadata file to update
        """
        self.repo_path = Path(repo_path)
        self.metadata_file = metadata_file
        self.hooks_dir = self.repo_path / ".git" / "hooks"

    def is_git_repository(self) -> bool:
        """Check if the path is a git repository."""
        return (self.repo_path / ".git").exists()

    def install_branch_change_hook(self) -> None:
        """Install post-checkout hook to detect branch changes."""
        if not self.is_git_repository():
            raise ValueError(f"Not a git repository: {self.repo_path}")

        if not self.metadata_file:
            raise ValueError("Metadata file path is required for hook installation")

        hook_file = self.hooks_dir / "post-checkout"

        # Ensure hooks directory exists
        self.hooks_dir.mkdir(parents=True, exist_ok=True)

        # Generate hook content
        hook_content = self._generate_hook_content()

        if hook_file.exists():
            # Preserve existing hook and append our code
            existing_content = hook_file.read_text()
            if "# Code Indexer Branch Tracking" not in existing_content:
                # Add our hook to existing content
                new_content = existing_content.rstrip() + "\n\n" + hook_content
                hook_file.write_text(new_content)
        else:
            # Create new hook file
            hook_file.write_text(f"#!/bin/bash\n\n{hook_content}")

        # Make executable
        hook_file.chmod(0o755)

    def _generate_hook_content(self) -> str:
        """Generate the hook script content."""
        python_script = f"""
# Code Indexer Branch Tracking
# This section updates the progressive metadata file when branch changes occur

# Check if this is a branch switch (not file checkout)
if [ "$3" = "1" ]; then
    # Get current branch name
    CURRENT_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "unknown")
    
    # Update metadata file using Python
    python3 -c "
import sys
import json
import fcntl
from pathlib import Path

metadata_file = Path('{self.metadata_file}')
if metadata_file.exists():
    try:
        with open(metadata_file, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.seek(0)
            try:
                data = json.load(f)
                data['current_branch'] = '$CURRENT_BRANCH'
                f.seek(0)
                f.truncate()
                json.dump(data, f, indent=2)
            except (json.JSONDecodeError, KeyError):
                # If corrupted or missing structure, skip update
                pass
    except (OSError, IOError):
        # File access issues, skip update
        pass
"
fi
"""
        return python_script

    def ensure_hook_installed(self) -> None:
        """Ensure the branch change hook is installed, installing if missing."""
        if not self.is_git_repository():
            return  # Not a git repo, nothing to do

        hook_file = self.hooks_dir / "post-checkout"

        if (
            not hook_file.exists()
            or "# Code Indexer Branch Tracking" not in hook_file.read_text()
        ):
            self.install_branch_change_hook()

    def remove_hook(self) -> None:
        """Remove our branch tracking hook from post-checkout."""
        if not self.is_git_repository():
            return

        hook_file = self.hooks_dir / "post-checkout"
        if not hook_file.exists():
            return

        content = hook_file.read_text()

        # Remove our section
        lines = content.split("\n")
        filtered_lines = []
        skip_section = False

        for line in lines:
            if "# Code Indexer Branch Tracking" in line:
                skip_section = True
                continue
            elif (
                skip_section
                and line.strip() == ""
                and not line.startswith(" ")
                and not line.startswith("\t")
            ):
                skip_section = False
                continue
            elif not skip_section:
                filtered_lines.append(line)

        new_content = "\n".join(filtered_lines).strip()

        if new_content == "#!/bin/bash" or not new_content:
            # If only shebang left or empty, remove the file
            hook_file.unlink()
        else:
            hook_file.write_text(new_content + "\n")
