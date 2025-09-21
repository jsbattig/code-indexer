"""Sync Conflict Detection and Resolution for Enhanced Sync Integration.

Provides functionality for detecting uncommitted changes, merge conflicts,
and providing resolution guidance during sync operations.
"""

import subprocess
from pathlib import Path
from typing import List
from dataclasses import dataclass
from enum import Enum


class ConflictType(Enum):
    """Types of sync conflicts that can be detected."""

    UNCOMMITTED_CHANGES = "uncommitted_changes"
    MERGE_CONFLICTS = "merge_conflicts"
    DIVERGED_BRANCH = "diverged_branch"


class ResolutionAction(Enum):
    """Actions that can be taken to resolve conflicts."""

    STASH = "stash"
    COMMIT = "commit"
    MANUAL_RESOLVE = "manual_resolve"
    ABORT = "abort"


@dataclass
class SyncConflict:
    """Represents a sync conflict that needs resolution."""

    conflict_type: ConflictType
    description: str
    affected_files: List[str]
    suggested_actions: List[ResolutionAction]


@dataclass
class ResolutionResult:
    """Result of a conflict resolution attempt."""

    success: bool
    message: str
    requires_manual_intervention: bool = False


class ConflictResolutionError(Exception):
    """Exception raised when conflict resolution fails."""

    pass


class ConflictDetector:
    """Detects various types of sync conflicts in a repository."""

    def detect_conflicts(self, repo_path: Path) -> List[SyncConflict]:
        """Detect all types of conflicts in the repository.

        Args:
            repo_path: Path to repository root

        Returns:
            List of detected conflicts

        Raises:
            ConflictResolutionError: If conflict detection fails
        """
        conflicts = []

        # Check for merge conflicts first (priority over uncommitted changes)
        if self._has_merge_conflicts(repo_path):
            conflict_files = self._get_conflict_files(repo_path)
            conflicts.append(
                SyncConflict(
                    conflict_type=ConflictType.MERGE_CONFLICTS,
                    description=f"Merge conflicts in: {', '.join(conflict_files)}",
                    affected_files=conflict_files,
                    suggested_actions=[ResolutionAction.MANUAL_RESOLVE],
                )
            )
        # Check for uncommitted changes (only if no merge conflicts)
        elif self._has_uncommitted_changes(repo_path):
            uncommitted_files = self._get_uncommitted_files(repo_path)
            conflicts.append(
                SyncConflict(
                    conflict_type=ConflictType.UNCOMMITTED_CHANGES,
                    description=f"Uncommitted changes in: {', '.join(uncommitted_files)}",
                    affected_files=uncommitted_files,
                    suggested_actions=[
                        ResolutionAction.STASH,
                        ResolutionAction.COMMIT,
                        ResolutionAction.ABORT,
                    ],
                )
            )

        # Check for diverged branches
        if self._has_diverged_branches(repo_path):
            conflicts.append(
                SyncConflict(
                    conflict_type=ConflictType.DIVERGED_BRANCH,
                    description="Local branch has diverged from remote (contains local commits and remote has new commits)",
                    affected_files=[],
                    suggested_actions=[
                        ResolutionAction.MANUAL_RESOLVE,
                        ResolutionAction.ABORT,
                    ],
                )
            )

        return conflicts

    def _has_uncommitted_changes(self, repo_path: Path) -> bool:
        """Check if repository has uncommitted changes."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise ConflictResolutionError(f"Git status failed: {result.stderr}")

            # Filter out merge conflict markers - they're handled separately
            lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
            non_conflict_lines = [
                line
                for line in lines
                if not line.startswith("UU ") and not line.startswith("AA ")
            ]

            return len(non_conflict_lines) > 0

        except subprocess.TimeoutExpired:
            raise ConflictResolutionError("Git status command timed out")
        except Exception as e:
            raise ConflictResolutionError(f"Failed to check uncommitted changes: {e}")

    def _has_merge_conflicts(self, repo_path: Path) -> bool:
        """Check if repository has merge conflicts."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise ConflictResolutionError(f"Git status failed: {result.stderr}")

            # Look for conflict markers (UU, AA status)
            status_output = result.stdout.strip()
            return any(
                line.startswith("UU ") or line.startswith("AA ")
                for line in status_output.split("\n")
            )

        except subprocess.TimeoutExpired:
            raise ConflictResolutionError("Git status command timed out")
        except Exception as e:
            raise ConflictResolutionError(f"Failed to check merge conflicts: {e}")

    def _has_diverged_branches(self, repo_path: Path) -> bool:
        """Check if local branch has diverged from remote."""
        try:
            # Check for local commits not in remote
            local_commits_result = subprocess.run(
                ["git", "rev-list", "origin/main..HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )

            # Check for remote commits not in local
            remote_commits_result = subprocess.run(
                ["git", "rev-list", "HEAD..origin/main"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )

            has_local_commits = local_commits_result.returncode == 0 and bool(
                local_commits_result.stdout.strip()
            )
            has_remote_commits = remote_commits_result.returncode == 0 and bool(
                remote_commits_result.stdout.strip()
            )

            return has_local_commits and has_remote_commits

        except subprocess.TimeoutExpired:
            raise ConflictResolutionError("Git rev-list command timed out")
        except Exception:
            # Branch divergence check is optional - don't fail sync for this
            return False

    def _get_uncommitted_files(self, repo_path: Path) -> List[str]:
        """Get list of files with uncommitted changes."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )

            files = []
            for line in result.stdout.strip().split("\n"):
                if line and not line.startswith("UU ") and not line.startswith("AA "):
                    # Extract filename from git status output (format: XY filename)
                    # X = index status, Y = worktree status, then filename
                    if len(line) >= 3:
                        # Git status format: XY filename (where XY are status codes)
                        # Skip the first 2 characters (status codes) and any leading whitespace
                        filename = line[2:].strip()
                        if filename:  # Only add non-empty filenames
                            files.append(filename)

            return files

        except Exception:
            return []

    def _get_conflict_files(self, repo_path: Path) -> List[str]:
        """Get list of files with merge conflicts."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )

            files = []
            for line in result.stdout.strip().split("\n"):
                if line.startswith("UU ") or line.startswith("AA "):
                    # Extract filename from git status output (format: XY filename)
                    # X = index status, Y = worktree status, then filename
                    if len(line) >= 3:
                        # Git status format: XY filename (where XY are status codes)
                        # Skip the first 2 characters (status codes) and any leading whitespace
                        filename = line[2:].strip()
                        if filename:  # Only add non-empty filenames
                            files.append(filename)

            return files

        except Exception:
            return []


class ConflictResolver:
    """Resolves detected sync conflicts."""

    def resolve_conflict(
        self, conflict: SyncConflict, repo_path: Path, action: ResolutionAction
    ) -> ResolutionResult:
        """Resolve a specific conflict with the given action.

        Args:
            conflict: The conflict to resolve
            repo_path: Path to repository root
            action: Action to take for resolution

        Returns:
            ResolutionResult indicating success or failure
        """
        if action == ResolutionAction.STASH:
            return self._stash_changes(repo_path)
        elif action == ResolutionAction.COMMIT:
            return self._commit_changes(repo_path)
        elif action == ResolutionAction.MANUAL_RESOLVE:
            return self._require_manual_resolution(conflict)
        elif action == ResolutionAction.ABORT:
            return ResolutionResult(
                success=False,
                message="Sync aborted by user request",
                requires_manual_intervention=False,
            )
        else:
            return ResolutionResult(
                success=False,
                message=f"Unknown resolution action: {action}",
                requires_manual_intervention=False,
            )

    def generate_resolution_guidance(self, conflict: SyncConflict) -> str:
        """Generate human-readable guidance for resolving a conflict.

        Args:
            conflict: The conflict to provide guidance for

        Returns:
            Formatted guidance string
        """
        guidance = f"Conflict detected: {conflict.description}\n\n"

        if conflict.affected_files:
            guidance += "Affected files:\n"
            for file in conflict.affected_files:
                guidance += f"  - {file}\n"
            guidance += "\n"

        guidance += "Options:\n"
        for i, action in enumerate(conflict.suggested_actions, 1):
            if action == ResolutionAction.STASH:
                guidance += f"  {i}. Stash changes (temporarily save changes and restore later)\n"
            elif action == ResolutionAction.COMMIT:
                guidance += f"  {i}. Commit changes (permanently save changes)\n"
            elif action == ResolutionAction.MANUAL_RESOLVE:
                guidance += f"  {i}. Manual resolution (resolve conflicts manually)\n"
            elif action == ResolutionAction.ABORT:
                guidance += f"  {i}. Abort sync (cancel sync operation)\n"

        return guidance

    def interactive_resolution(
        self, conflict: SyncConflict, repo_path: Path
    ) -> ResolutionResult:
        """Provide interactive conflict resolution.

        Args:
            conflict: The conflict to resolve
            repo_path: Path to repository root

        Returns:
            ResolutionResult indicating success or failure
        """
        import click

        guidance = self.generate_resolution_guidance(conflict)
        click.echo(guidance)

        while True:
            try:
                choice = click.prompt("Select option", type=int)
                if 1 <= choice <= len(conflict.suggested_actions):
                    action = conflict.suggested_actions[choice - 1]
                    return self.resolve_conflict(conflict, repo_path, action)
                else:
                    click.echo(
                        f"Invalid choice. Please select 1-{len(conflict.suggested_actions)}"
                    )
            except (click.Abort, KeyboardInterrupt):
                return ResolutionResult(
                    success=False,
                    message="Resolution cancelled by user",
                    requires_manual_intervention=False,
                )

    def _stash_changes(self, repo_path: Path) -> ResolutionResult:
        """Stash uncommitted changes."""
        try:
            result = subprocess.run(
                ["git", "stash", "push", "-m", "Auto-stash before sync"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return ResolutionResult(
                    success=True,
                    message="Changes successfully stashed. Use 'git stash pop' to restore them after sync.",
                    requires_manual_intervention=False,
                )
            else:
                return ResolutionResult(
                    success=False,
                    message=f"Failed to stash changes: {result.stderr}",
                    requires_manual_intervention=False,
                )

        except subprocess.TimeoutExpired:
            return ResolutionResult(
                success=False,
                message="Stash operation timed out",
                requires_manual_intervention=False,
            )
        except Exception as e:
            return ResolutionResult(
                success=False,
                message=f"Stash operation failed: {e}",
                requires_manual_intervention=False,
            )

    def _commit_changes(self, repo_path: Path) -> ResolutionResult:
        """Commit uncommitted changes."""
        try:
            # Stage all changes
            add_result = subprocess.run(
                ["git", "add", "."],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if add_result.returncode != 0:
                return ResolutionResult(
                    success=False,
                    message=f"Failed to stage changes: {add_result.stderr}",
                    requires_manual_intervention=False,
                )

            # Commit changes
            commit_result = subprocess.run(
                ["git", "commit", "-m", "Auto-commit before sync"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if commit_result.returncode == 0:
                return ResolutionResult(
                    success=True,
                    message="Changes successfully committed.",
                    requires_manual_intervention=False,
                )
            else:
                return ResolutionResult(
                    success=False,
                    message=f"Failed to commit changes: {commit_result.stderr}",
                    requires_manual_intervention=False,
                )

        except subprocess.TimeoutExpired:
            return ResolutionResult(
                success=False,
                message="Commit operation timed out",
                requires_manual_intervention=False,
            )
        except Exception as e:
            return ResolutionResult(
                success=False,
                message=f"Commit operation failed: {e}",
                requires_manual_intervention=False,
            )

    def _require_manual_resolution(self, conflict: SyncConflict) -> ResolutionResult:
        """Handle conflicts that require manual resolution."""
        message = f"Manual resolution required for {conflict.conflict_type.value}.\n"

        if conflict.affected_files:
            message += (
                f"Please resolve conflicts in: {', '.join(conflict.affected_files)}\n"
            )

        if conflict.conflict_type == ConflictType.MERGE_CONFLICTS:
            message += "Use your preferred merge tool or editor to resolve conflicts, then commit the results."
        elif conflict.conflict_type == ConflictType.DIVERGED_BRANCH:
            message += (
                "Consider rebasing or merging to reconcile local and remote changes."
            )

        return ResolutionResult(
            success=False, message=message, requires_manual_intervention=True
        )
