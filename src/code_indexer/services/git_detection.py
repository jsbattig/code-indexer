"""
Git detection and state management service.

This service detects git repository initialization and state changes,
triggering appropriate re-indexing when needed.
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Tuple

from ..config import Config
from .file_identifier import FileIdentifier


class GitDetectionService:
    """
    Service for detecting git repository initialization and state changes.

    This service monitors git repository state and detects when:
    - Git is newly initialized in a project
    - Branch switches occur
    - Other significant git state changes that require re-indexing
    """

    def __init__(self, project_dir: Path, config: Config):
        """
        Initialize GitDetectionService.

        Args:
            project_dir: Path to the project directory
            config: Project configuration
        """
        self.project_dir = project_dir
        self.config = config
        # Create metadata directory path
        metadata_dir = project_dir / ".code-indexer"
        self.git_state_file = metadata_dir / "git_state.json"

        # Ensure metadata directory exists
        metadata_dir.mkdir(parents=True, exist_ok=True)

    def detect_git_initialization(self) -> bool:
        """
        Detect if git was just initialized in this project.

        Returns:
            True if git was newly initialized, False otherwise
        """
        current_git_state = self._get_current_git_state()
        previous_git_state = self._load_previous_git_state()

        # Check if git became available
        git_newly_available = current_git_state[
            "git_available"
        ] and not previous_git_state.get("git_available", False)

        if git_newly_available:
            self._save_git_state(current_git_state)
            return True

        # Update state for next check
        self._save_git_state(current_git_state)
        return False

    def detect_branch_change(self) -> bool:
        """
        Detect if the current branch has changed since last check.

        Returns:
            True if branch changed, False otherwise
        """
        current_git_state = self._get_current_git_state()
        previous_git_state = self._load_previous_git_state()

        # Only check branch changes if git is available
        if not current_git_state["git_available"]:
            return False

        current_branch = current_git_state.get("branch")
        previous_branch = previous_git_state.get("branch")

        branch_changed = (
            current_branch and previous_branch and current_branch != previous_branch
        )

        if branch_changed:
            self._save_git_state(current_git_state)
            return True

        # Update state for next check
        self._save_git_state(current_git_state)
        return False

    def should_reindex_for_git(self) -> Tuple[bool, str]:
        """
        Check if full re-indexing is needed due to git changes.

        Returns:
            Tuple of (should_reindex, reason)
        """
        if self.detect_git_initialization():
            return True, "Git repository detected - enabling git-aware indexing"

        if self.detect_branch_change():
            current_state = self._get_current_git_state()
            branch = current_state.get("branch", "unknown")
            return True, f"Branch changed to '{branch}' - updating index context"

        return False, ""

    def _get_current_git_state(self) -> Dict[str, Any]:
        """
        Get current git repository state.

        Returns:
            Dictionary containing current git state
        """
        identifier = FileIdentifier(self.project_dir, self.config)

        state = {
            "git_available": identifier.git_available,
            "checked_at": datetime.utcnow().isoformat() + "Z",
        }

        if identifier.git_available:
            state.update(self._get_detailed_git_state())

        return state

    def _get_detailed_git_state(self) -> Dict[str, Any]:
        """
        Get detailed git state information.

        Returns:
            Dictionary containing detailed git state
        """
        git_state: Dict[str, Any] = {}

        try:
            # Current commit hash
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            git_state["commit_hash"] = result.stdout.strip()
        except subprocess.CalledProcessError:
            git_state["commit_hash"] = None

        try:
            # Current branch
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            branch = result.stdout.strip()

            if not branch:
                # Handle detached HEAD
                try:
                    result = subprocess.run(
                        ["git", "rev-parse", "--short", "HEAD"],
                        cwd=self.project_dir,
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    branch = f"detached-{result.stdout.strip()}"
                except subprocess.CalledProcessError:
                    branch = "unknown"

            git_state["branch"] = branch
        except subprocess.CalledProcessError:
            git_state["branch"] = None

        try:
            # Repository root
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            git_state["repo_root"] = result.stdout.strip()
        except subprocess.CalledProcessError:
            git_state["repo_root"] = None

        try:
            # Check if there are uncommitted changes
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            git_state["has_uncommitted_changes"] = bool(result.stdout.strip())
        except subprocess.CalledProcessError:
            git_state["has_uncommitted_changes"] = None

        return git_state

    def _load_previous_git_state(self) -> Dict[str, Any]:
        """
        Load previously saved git state from file.

        Returns:
            Dictionary containing previous git state, empty dict if none exists
        """
        try:
            if self.git_state_file.exists():
                with open(self.git_state_file, "r", encoding="utf-8") as f:
                    return dict(json.load(f))
        except (IOError, json.JSONDecodeError):
            pass

        return {}

    def _save_git_state(self, state: Dict[str, Any]) -> None:
        """
        Save current git state to file.

        Args:
            state: Git state dictionary to save
        """
        try:
            with open(self.git_state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except IOError:
            # Fail silently if we can't save state
            pass

    def get_branch_files_summary(self) -> Dict[str, Any]:
        """
        Get a summary of files in the current branch/context.

        Returns:
            Dictionary containing file count and other summary information
        """
        identifier = FileIdentifier(self.project_dir, self.config)
        current_files = identifier.get_current_files()

        summary = {
            "total_files": len(current_files),
            "git_available": identifier.git_available,
            "project_id": identifier._get_project_id(),
        }

        if identifier.git_available:
            state = self._get_current_git_state()
            summary.update(
                {
                    "branch": state.get("branch"),
                    "commit_hash": (
                        state.get("commit_hash", "")[:8]
                        if state.get("commit_hash")
                        else None
                    ),
                    "has_uncommitted_changes": state.get("has_uncommitted_changes"),
                }
            )

        return summary

    def clear_git_state(self) -> None:
        """
        Clear saved git state. Useful for testing or manual reset.
        """
        try:
            if self.git_state_file.exists():
                self.git_state_file.unlink()
        except OSError:
            pass
