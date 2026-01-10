"""
GitStateManager: Git state management for SCIP self-healing workflows.

Provides git operations orchestration for:
- Pre-refresh clearing (git reset + clean before pulls)
- PR creation after successful SCIP fixes
- Token authentication resolution
- Audit logging

Story #659: Git State Management for SCIP Self-Healing with PR Workflow
"""

from code_indexer.server.middleware.correlation import get_correlation_id

import httpx
import logging
import os
import subprocess
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, List, Union, cast

from code_indexer.utils.git_runner import run_git_command

logger = logging.getLogger(__name__)

# AC4: PR description length limit (max characters in PR title description field)
MAX_PR_TITLE_DESCRIPTION_LENGTH = 100

# GitHub API timeout for PR creation requests
GITHUB_API_TIMEOUT_SECONDS = 30.0

# GitLab API timeout for MR creation requests
GITLAB_API_TIMEOUT_SECONDS = 30.0


class GitStateError(Exception):
    """Exception raised during git state management operations."""

    pass


@dataclass
class CleanupResult:
    """Result of pre-refresh clearing operation."""

    was_dirty: bool
    files_cleared: int


@dataclass
class PRCreationResult:
    """Result of PR creation operation."""

    success: bool
    pr_url: Optional[str]
    branch_name: Optional[str]
    message: str


class GitStateManager:
    """
    Git state management service for SCIP self-healing workflows.

    Handles:
    - Pre-refresh clearing (AC2): git reset + clean before repository refresh
    - PR creation after successful SCIP fix (AC1): branch + commit + push + PR
    - Configuration control (AC6): feature enablement
    - Audit logging (AC7): operation tracking
    """

    def __init__(self, config: Any, audit_logger: Optional[Any] = None):
        """
        Initialize GitStateManager.

        Args:
            config: Configuration object with enable_pr_creation, default_branch fields
            audit_logger: Optional audit logger for operation tracking
        """
        self.config = config
        self.audit_logger = audit_logger

    def clear_repo_before_refresh(self, repo_path: Path) -> CleanupResult:
        """
        Clear repository state before git pull operation.

        Implements AC2: Pre-Refresh Clearing Workflow
        - Checks if repository has uncommitted changes
        - Executes git reset --hard HEAD to discard tracked changes
        - Executes git clean -fd to remove untracked files/directories
        - Verifies repository is clean after operations

        Args:
            repo_path: Path to repository to clear

        Returns:
            CleanupResult with was_dirty flag and files_cleared count

        Raises:
            GitStateError: If git reset, git clean, or verification fails
        """
        # Check current status
        try:
            status_result = run_git_command(
                ["git", "status", "--porcelain"], cwd=repo_path, check=True
            )
        except subprocess.CalledProcessError as e:
            raise GitStateError(f"git status failed: {e}")

        # Parse status output to count files
        status_output = status_result.stdout.strip()
        if not status_output:
            # Already clean, no action needed
            logger.info(
                f"Repository {repo_path} is already clean, skipping clearing",
                extra={"correlation_id": get_correlation_id()},
            )
            return CleanupResult(was_dirty=False, files_cleared=0)

        # Count files to be cleared
        files_to_clear = len(
            [line for line in status_output.split("\n") if line.strip()]
        )
        logger.info(
            f"Repository {repo_path} has {files_to_clear} uncommitted changes, clearing",
            extra={"correlation_id": get_correlation_id()},
        )

        # Execute git reset --hard HEAD
        try:
            run_git_command(
                ["git", "reset", "--hard", "HEAD"], cwd=repo_path, check=True
            )
            logger.debug(
                f"git reset --hard HEAD succeeded for {repo_path}",
                extra={"correlation_id": get_correlation_id()},
            )
        except subprocess.CalledProcessError as e:
            error_msg = f"git reset --hard failed: {e.stderr if hasattr(e, 'stderr') else str(e)}"
            logger.error(error_msg, extra={"correlation_id": get_correlation_id()})
            raise GitStateError(error_msg)

        # Execute git clean -fd
        try:
            run_git_command(["git", "clean", "-fd"], cwd=repo_path, check=True)
            logger.debug(
                f"git clean -fd succeeded for {repo_path}",
                extra={"correlation_id": get_correlation_id()},
            )
        except subprocess.CalledProcessError as e:
            error_msg = (
                f"git clean -fd failed: {e.stderr if hasattr(e, 'stderr') else str(e)}"
            )
            logger.error(error_msg, extra={"correlation_id": get_correlation_id()})
            raise GitStateError(error_msg)

        # Verify clean state
        try:
            final_status = run_git_command(
                ["git", "status", "--porcelain"], cwd=repo_path, check=True
            )
        except subprocess.CalledProcessError as e:
            raise GitStateError(f"git status verification failed: {e}")

        if final_status.stdout.strip():
            # Still dirty after reset/clean - should never happen
            error_msg = f"Repository not clean after reset/clean: {final_status.stdout}"
            logger.error(error_msg, extra={"correlation_id": get_correlation_id()})
            raise GitStateError(error_msg)

        logger.info(
            f"Successfully cleared {files_to_clear} files from {repo_path}",
            extra={"correlation_id": get_correlation_id()},
        )

        # Log to audit if available
        if self.audit_logger:
            self.audit_logger.log_cleanup(
                repo_path=str(repo_path), files_cleared=files_to_clear
            )

        return CleanupResult(was_dirty=True, files_cleared=files_to_clear)

    def create_pr_after_fix(
        self,
        repo_path: Path,
        fix_description: str,
        files_modified: List[Path],
        pr_description: str,
        platform: str,
        job_id: Optional[str] = None,
    ) -> PRCreationResult:
        """
        Create pull request after successful SCIP fix.

        Implements AC1: PR Creation After Successful SCIP Fix
        Orchestrates: config check, branch creation, commit, push, PR creation.

        Args:
            repo_path: Path to repository
            fix_description: Full description of what was fixed
            files_modified: List of files that were modified
            pr_description: Short description for PR title (max 100 chars)
            platform: "github" or "gitlab"
            job_id: Optional unique identifier for SCIP fix job (for audit logging)

        Returns:
            PRCreationResult with success status, PR URL, branch name, message
        """
        # AC6: Check if PR creation is enabled
        if not self.config.enable_pr_creation:
            logger.info(
                "PR creation disabled in configuration",
                extra={"correlation_id": get_correlation_id()},
            )

            # AC7: Audit log that PR creation was disabled
            if self.audit_logger and job_id:
                self.audit_logger.log_pr_creation_disabled(
                    job_id=job_id, repo_alias=repo_path.name
                )

            return PRCreationResult(
                success=True,
                pr_url=None,
                branch_name=None,
                message="PR creation disabled in configuration",
            )

        original_branch = None
        branch_name = None
        commit_hash = None

        try:
            # Get current branch (to return to later)
            original_branch = self._get_current_branch(repo_path)

            # Create new SCIP fix branch and check it out
            branch_name = self._create_and_checkout_fix_branch(repo_path)

            # Stage modified files and commit changes (capture commit hash)
            commit_hash = self._stage_and_commit_changes(
                repo_path, files_modified, fix_description
            )

            # Push branch to remote
            self._push_branch_to_remote(repo_path, branch_name)

            # Create PR/MR via API
            pr_url = self._create_pr_via_api(
                repo_path,
                branch_name,
                pr_description,
                fix_description,
                files_modified,
                platform,
            )

            # AC7: Audit log successful PR creation
            if self.audit_logger and job_id:
                self.audit_logger.log_pr_creation_success(
                    job_id=job_id,
                    repo_alias=repo_path.name,
                    branch_name=branch_name,
                    pr_url=pr_url,
                    commit_hash=commit_hash,
                    files_modified=[str(f) for f in files_modified],
                )

            # Return to original branch
            self._return_to_branch(repo_path, original_branch)

            return PRCreationResult(
                success=True,
                pr_url=pr_url,
                branch_name=branch_name,
                message=f"Successfully created PR and returned to {original_branch}",
            )

        except GitStateError as e:
            # Git operation failed - return to original branch if known
            if original_branch:
                self._return_to_branch(repo_path, original_branch)

            # AC7: Audit log failure
            if self.audit_logger and job_id:
                self.audit_logger.log_pr_creation_failure(
                    job_id=job_id,
                    repo_alias=repo_path.name,
                    reason=str(e),
                    branch_name=branch_name,
                )

            return PRCreationResult(
                success=False, pr_url=None, branch_name=None, message=str(e)
            )

        except Exception as e:
            # PR creation or other failure - return to original branch if known
            if original_branch:
                self._return_to_branch(repo_path, original_branch)

            # AC7: Audit log failure
            if self.audit_logger and job_id:
                self.audit_logger.log_pr_creation_failure(
                    job_id=job_id,
                    repo_alias=repo_path.name,
                    reason=f"PR creation failed: {str(e)}",
                    branch_name=branch_name,
                )

            return PRCreationResult(
                success=False,
                pr_url=None,
                branch_name=branch_name,
                message=f"PR creation failed: {str(e)}",
            )

    def _get_current_branch(self, repo_path: Path) -> str:
        """
        Get the current git branch name.

        Args:
            repo_path: Path to repository

        Returns:
            Current branch name

        Raises:
            GitStateError: If unable to determine current branch
        """
        try:
            result = run_git_command(
                ["git", "branch", "--show-current"], cwd=repo_path, check=True
            )
            branch_name = result.stdout.strip()
            logger.debug(
                f"Current branch: {branch_name}",
                extra={"correlation_id": get_correlation_id()},
            )
            return cast(str, branch_name)
        except subprocess.CalledProcessError as e:
            raise GitStateError(f"Failed to get current branch: {e}")

    def _create_and_checkout_fix_branch(self, repo_path: Path) -> str:
        """
        Create and checkout a new SCIP fix branch with timestamp.

        Args:
            repo_path: Path to repository

        Returns:
            Name of created branch

        Raises:
            GitStateError: If branch creation fails
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        branch_name = f"scip-fix-{timestamp}"

        try:
            run_git_command(
                ["git", "checkout", "-b", branch_name], cwd=repo_path, check=True
            )
            logger.info(
                f"Created and checked out branch: {branch_name}",
                extra={"correlation_id": get_correlation_id()},
            )
            return branch_name
        except subprocess.CalledProcessError as e:
            raise GitStateError(f"Failed to create branch {branch_name}: {e}")

    def _stage_and_commit_changes(
        self, repo_path: Path, files_modified: List[Path], fix_description: str
    ) -> str:
        """
        Stage modified files and create commit.

        Args:
            repo_path: Path to repository
            files_modified: List of modified files to stage
            fix_description: Description of fix for commit message

        Returns:
            Commit hash of the created commit

        Raises:
            GitStateError: If staging or commit fails
        """
        # Stage files
        try:
            file_paths = [str(f) for f in files_modified]
            run_git_command(["git", "add"] + file_paths, cwd=repo_path, check=True)
            logger.debug(
                f"Staged {len(files_modified)} files",
                extra={"correlation_id": get_correlation_id()},
            )
        except subprocess.CalledProcessError as e:
            raise GitStateError(f"Failed to stage files: {e}")

        # Create commit
        commit_message = (
            f"[SCIP Auto-Fix] {fix_description}\n\n"
            f"Files modified:\n" + "\n".join(f"- {f}" for f in files_modified)
        )

        try:
            run_git_command(
                ["git", "commit", "-m", commit_message], cwd=repo_path, check=True
            )
            logger.info(
                f"Committed changes: {fix_description}",
                extra={"correlation_id": get_correlation_id()},
            )

            # Get commit hash
            result = run_git_command(
                ["git", "rev-parse", "HEAD"], cwd=repo_path, check=True
            )
            commit_hash = result.stdout.strip()
            logger.debug(
                f"Commit hash: {commit_hash}",
                extra={"correlation_id": get_correlation_id()},
            )
            return cast(str, commit_hash)

        except subprocess.CalledProcessError as e:
            error_detail = e.stderr if hasattr(e, "stderr") else str(e)
            raise GitStateError(f"Failed to commit: {error_detail}")

    def _push_branch_to_remote(self, repo_path: Path, branch_name: str) -> None:
        """
        Push branch to remote repository.

        Args:
            repo_path: Path to repository
            branch_name: Branch name to push

        Raises:
            GitStateError: If push fails
        """
        try:
            run_git_command(
                ["git", "push", "-u", "origin", branch_name], cwd=repo_path, check=True
            )
            logger.info(
                f"Pushed branch {branch_name} to remote",
                extra={"correlation_id": get_correlation_id()},
            )
        except subprocess.CalledProcessError as e:
            error_detail = e.stderr if hasattr(e, "stderr") else str(e)
            raise GitStateError(f"git push failed: {error_detail}")

    def _create_pr_via_api(
        self,
        repo_path: Path,
        branch_name: str,
        pr_description: str,
        fix_description: str,
        files_modified: List[Path],
        platform: str,
    ) -> str:
        """
        Create PR/MR via GitHub/GitLab API.

        Args:
            repo_path: Path to repository
            branch_name: Source branch name
            pr_description: Short PR description (max 100 chars)
            fix_description: Full fix description for PR body
            files_modified: List of modified files
            platform: "github" or "gitlab"

        Returns:
            PR/MR URL

        Raises:
            Exception: If PR creation fails or platform unsupported
        """
        # Resolve authentication token
        token = TokenAuthenticator.resolve_token(platform)
        if not token:
            raise Exception(f"No {platform} token available")

        # Build PR title and body
        pr_title = f"[SCIP Auto-Fix] {pr_description[:MAX_PR_TITLE_DESCRIPTION_LENGTH]}"
        pr_body = (
            f"{fix_description}\n\n"
            f"Auto-generated by SCIP self-healing service.\n\n"
            f"**Files Modified:**\n" + "\n".join(f"- `{f}`" for f in files_modified)
        )

        base_branch = getattr(self.config, "pr_base_branch", self.config.default_branch)

        # Create PR/MR using platform-specific client
        client: Union[GitHubPRClient, GitLabPRClient]
        if platform == "github":
            client = GitHubPRClient(repo_path, token)
            pr_url = client.create_pull_request(
                title=pr_title, body=pr_body, head=branch_name, base=base_branch
            )
        elif platform == "gitlab":
            client = GitLabPRClient(repo_path, token)
            pr_url = client.create_merge_request(
                title=pr_title,
                body=pr_body,
                source_branch=branch_name,
                target_branch=base_branch,
            )
        else:
            raise ValueError(f"Unsupported platform: {platform}")

        logger.info(
            f"Created PR: {pr_url}", extra={"correlation_id": get_correlation_id()}
        )
        return pr_url

    def _return_to_branch(self, repo_path: Path, branch_name: str) -> None:
        """
        Return to original branch after PR workflow.

        Args:
            repo_path: Path to repository
            branch_name: Branch name to return to
        """
        try:
            run_git_command(["git", "checkout", branch_name], cwd=repo_path, check=True)
            logger.info(
                f"Returned to branch: {branch_name}",
                extra={"correlation_id": get_correlation_id()},
            )
        except subprocess.CalledProcessError as e:
            logger.error(
                f"Failed to return to branch {branch_name}: {e}",
                extra={"correlation_id": get_correlation_id()},
            )


class TokenAuthenticator:
    """
    Token authentication resolver for GitHub/GitLab API operations.

    Implements AC3: Token Authentication Resolution
    - Priority 1: Environment variables (GH_TOKEN, GITLAB_TOKEN)
    - Priority 2: File-based storage (~/.cidx-server/ci_tokens.json)
    - Returns None if token not found
    """

    @staticmethod
    def resolve_token(platform: str) -> Optional[str]:
        """
        Resolve authentication token for specified platform.

        Args:
            platform: Platform identifier ("github" or "gitlab")

        Returns:
            Token string if found, None otherwise
        """
        # Priority 1: Environment variables
        if platform == "github":
            env_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
            if env_token:
                logger.debug(
                    "Resolved GitHub token from environment variable",
                    extra={"correlation_id": get_correlation_id()},
                )
                return env_token
        elif platform == "gitlab":
            env_token = os.environ.get("GITLAB_TOKEN")
            if env_token:
                logger.debug(
                    "Resolved GitLab token from environment variable",
                    extra={"correlation_id": get_correlation_id()},
                )
                return env_token

        # Priority 2: File-based token storage (with decryption)
        try:
            from .ci_token_manager import CITokenManager

            server_dir = Path.home() / ".cidx-server"
            db_path = server_dir / "data" / "cidx_server.db"

            # Ensure database directory exists before opening SQLite
            db_path.parent.mkdir(parents=True, exist_ok=True)

            token_manager = CITokenManager(
                server_dir_path=str(server_dir),
                use_sqlite=True,
                db_path=str(db_path),
            )
            token_data = token_manager.get_token(platform)

            if token_data:
                logger.debug(
                    f"Resolved {platform} token from encrypted file storage",
                    extra={"correlation_id": get_correlation_id()},
                )
                return token_data.token
        except Exception as e:
            logger.warning(
                f"Failed to load token from encrypted storage: {e}",
                extra={"correlation_id": get_correlation_id()},
            )

        # No token found
        logger.warning(
            f"No {platform} token found in environment or file storage",
            extra={"correlation_id": get_correlation_id()},
        )
        return None


class GitHubPRClient:
    """
    GitHub Pull Request API client.

    Implements AC1: GitHub PR creation via REST API

    NOTE: Current implementation returns placeholder URLs for testing.
    Production implementation would use GitHub API (requests library or gh CLI).
    """

    # Placeholder PR number for testing (production uses actual API response)
    _PLACEHOLDER_PR_NUMBER = 123

    def __init__(self, repo_path: Path, token: str):
        """
        Initialize GitHub PR client.

        Args:
            repo_path: Path to repository
            token: GitHub authentication token
        """
        self.repo_path = repo_path
        self.token = token

    def create_pull_request(self, title: str, body: str, head: str, base: str) -> str:
        """
        Create GitHub pull request via REST API.

        Args:
            title: PR title
            body: PR description
            head: Source branch name
            base: Target branch name

        Returns:
            PR URL

        Raises:
            Exception: If PR creation fails
        """
        # Extract owner and repo from git remote URL
        try:
            result = run_git_command(
                ["git", "remote", "get-url", "origin"], cwd=self.repo_path, check=True
            )
            remote_url = result.stdout.strip()

            # Parse GitHub URL (supports both HTTPS and SSH)
            # HTTPS: https://github.com/owner/repo.git
            # SSH: git@github.com:owner/repo.git
            if "github.com" not in remote_url:
                raise ValueError(f"Not a GitHub repository: {remote_url}")

            parts = remote_url.replace(".git", "").split("/")
            repo = parts[-1]
            owner = parts[-2].split(":")[-1]  # Handle SSH format

        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to get remote URL: {e}")

        # Call GitHub API to create pull request
        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }
        payload = {
            "title": title,
            "body": body,
            "head": head,
            "base": base,
        }

        try:
            with httpx.Client(timeout=GITHUB_API_TIMEOUT_SECONDS) as client:
                response = client.post(api_url, headers=headers, json=payload)
                response.raise_for_status()

                pr_data = response.json()
                pr_url = pr_data["html_url"]
                pr_number = pr_data["number"]

                logger.info(
                    f"Created GitHub PR #{pr_number}: {pr_url}",
                    extra={"correlation_id": get_correlation_id()},
                )
                return cast(str, pr_url)

        except httpx.HTTPStatusError as e:
            error_body = e.response.text
            raise Exception(
                f"GitHub API error (HTTP {e.response.status_code}): {error_body}"
            )
        except httpx.RequestError as e:
            raise Exception(f"GitHub API request failed: {str(e)}")
        except (KeyError, ValueError) as e:
            raise Exception(f"Invalid GitHub API response: {str(e)}")


class GitLabPRClient:
    """
    GitLab Merge Request API client.

    Implements AC1: GitLab MR creation via REST API

    NOTE: Current implementation returns placeholder URLs for testing.
    Production implementation would use GitLab API (requests library or glab CLI).
    """

    # Placeholder MR number for testing (production uses actual API response)
    _PLACEHOLDER_MR_NUMBER = 456

    def __init__(self, repo_path: Path, token: str):
        """
        Initialize GitLab MR client.

        Args:
            repo_path: Path to repository
            token: GitLab authentication token
        """
        self.repo_path = repo_path
        self.token = token

    def create_merge_request(
        self, title: str, body: str, source_branch: str, target_branch: str
    ) -> str:
        """
        Create GitLab merge request via REST API.

        Args:
            title: MR title
            body: MR description
            source_branch: Source branch name
            target_branch: Target branch name

        Returns:
            MR URL

        Raises:
            Exception: If MR creation fails
        """
        # Extract project path from git remote URL
        try:
            result = run_git_command(
                ["git", "remote", "get-url", "origin"], cwd=self.repo_path, check=True
            )
            remote_url = result.stdout.strip()

            # Parse GitLab URL
            # HTTPS: https://gitlab.com/owner/repo.git
            # SSH: git@gitlab.com:owner/repo.git
            if "gitlab.com" not in remote_url:
                raise ValueError(f"Not a GitLab repository: {remote_url}")

            parts = remote_url.replace(".git", "").split("/")
            repo = parts[-1]
            owner = parts[-2].split(":")[-1]

            # GitLab uses URL-encoded project path (owner/repo)
            project_path = f"{owner}/{repo}"

        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to get remote URL: {e}")

        # Call GitLab API to create merge request
        # Use URL-encoded project path as project_id
        project_id_encoded = urllib.parse.quote(project_path, safe="")
        api_url = (
            f"https://gitlab.com/api/v4/projects/{project_id_encoded}/merge_requests"
        )
        headers = {
            "PRIVATE-TOKEN": self.token,
            "Content-Type": "application/json",
        }
        payload = {
            "title": title,
            "description": body,
            "source_branch": source_branch,
            "target_branch": target_branch,
        }

        try:
            with httpx.Client(timeout=GITLAB_API_TIMEOUT_SECONDS) as client:
                response = client.post(api_url, headers=headers, json=payload)
                response.raise_for_status()

                mr_data = response.json()
                mr_url = mr_data["web_url"]
                mr_iid = mr_data["iid"]

                logger.info(
                    f"Created GitLab MR !{mr_iid}: {mr_url}",
                    extra={"correlation_id": get_correlation_id()},
                )
                return cast(str, mr_url)

        except httpx.HTTPStatusError as e:
            error_body = e.response.text
            raise Exception(
                f"GitLab API error (HTTP {e.response.status_code}): {error_body}"
            )
        except httpx.RequestError as e:
            raise Exception(f"GitLab API request failed: {str(e)}")
        except (KeyError, ValueError) as e:
            raise Exception(f"Invalid GitLab API response: {str(e)}")
