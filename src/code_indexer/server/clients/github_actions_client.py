"""
GitHub Actions API client.

Story #633: Complete GitHub Actions Monitoring
Provides workflow run monitoring, log search, and workflow control operations.
"""

from code_indexer.server.middleware.correlation import get_correlation_id
import re
import logging
import httpx
from datetime import datetime
from typing import Optional, List, Dict, Any, cast
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
    before_sleep_log,
)

logger = logging.getLogger(__name__)


def _is_retryable_error(exception: BaseException) -> bool:
    """
    Check if exception is retryable (network errors or server errors).

    Retryable conditions:
    - httpx.NetworkError (connection failures)
    - Exceptions with status codes: 429, 500, 502, 503, 504

    Non-retryable conditions:
    - 401 (authentication errors)
    - 404 (not found errors)
    """
    # Always retry network errors
    if isinstance(exception, httpx.NetworkError):
        return True

    # Check for retryable HTTP status codes in exception message
    error_message = str(exception)
    retryable_codes = ["429", "500", "502", "503", "504"]
    has_retryable_code = any(code in error_message for code in retryable_codes)

    # Don't retry client errors (401, 404) - these are raised as custom exceptions
    # GitHubAuthenticationError and GitHubRepositoryNotFoundError
    non_retryable_types = (GitHubAuthenticationError, GitHubRepositoryNotFoundError)
    if isinstance(exception, non_retryable_types):
        return False

    return has_retryable_code


class GitHubAuthenticationError(Exception):
    """Raised when GitHub API authentication fails (401)."""

    pass


class GitHubRepositoryNotFoundError(Exception):
    """Raised when repository is not found or not accessible (404)."""

    pass


class GitHubActionsClient:
    """
    Client for GitHub Actions API operations.

    Provides workflow run listing, detailed run information, log search,
    and workflow control (retry, cancel).
    """

    def __init__(self, token: str):
        """
        Initialize GitHub Actions client.

        Args:
            token: GitHub authentication token (from GH_TOKEN env var or token storage)
        """
        self.token = token
        self.base_url = "https://api.github.com"
        self._last_rate_limit: Optional[Dict[str, int]] = None

    @property
    def last_rate_limit(self) -> Optional[Dict[str, int]]:
        """
        Get rate limit information from the last API response.

        AC9: Rate limiting tracking

        Returns:
            Dictionary with rate limit info:
            - limit: Maximum requests per hour
            - remaining: Remaining requests in current window
            - reset: Unix timestamp when rate limit resets
        """
        return self._last_rate_limit

    @retry(
        stop=stop_after_attempt(4),  # 1 initial + 3 retries
        wait=wait_exponential(multiplier=1, min=1, max=4),  # 1s, 2s, 4s
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=before_sleep_log(logger, logging.DEBUG),
        reraise=True,
    )
    async def list_runs(
        self,
        repository: str,
        branch: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List workflow runs for a repository.

        AC1: List recent workflow runs
        AC2: Filter by branch
        AC3: Filter by status
        AC9: Rate limiting tracking
        AC10: Authentication errors
        AC11: Repository not found

        Args:
            repository: Repository in "owner/repo" format
            branch: Optional branch filter
            status: Optional status filter (e.g., "failure", "success")

        Returns:
            List of workflow runs with fields:
            - id: Workflow run ID
            - name: Workflow name
            - status: Run status (e.g., "completed", "in_progress")
            - conclusion: Run conclusion (e.g., "success", "failure")
            - branch: Branch name
            - created_at: ISO 8601 timestamp

        Raises:
            GitHubAuthenticationError: When authentication fails (401)
            GitHubRepositoryNotFoundError: When repository not found (404)
        """
        # Build API URL
        url = f"{self.base_url}/repos/{repository}/actions/runs"

        # Build query parameters
        params = {}
        if branch:
            params["branch"] = branch
        if status:
            params["status"] = status

        # Build query string
        if params:
            query_parts = [f"{k}={v}" for k, v in params.items()]
            url = f"{url}?{'&'.join(query_parts)}"

        # Make API request
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)

            # AC10: Check for authentication failure
            if response.status_code == 401:
                raise GitHubAuthenticationError(
                    "GitHub authentication failed. Please check your token is valid and has the required permissions."
                )

            # AC11: Check for repository not found
            if response.status_code == 404:
                raise GitHubRepositoryNotFoundError(
                    f"Repository '{repository}' not found or not accessible. Please check the repository name and your access permissions."
                )

            if response.status_code != 200:
                raise Exception(f"GitHub API error: {response.status_code}")

            # AC9: Capture rate limit headers
            self._last_rate_limit = {
                "limit": int(response.headers.get("x-ratelimit-limit", 0)),
                "remaining": int(response.headers.get("x-ratelimit-remaining", 0)),
                "reset": int(response.headers.get("x-ratelimit-reset", 0)),
            }

            data = response.json()

            # Transform API response to expected format
            runs = []
            for run in data.get("workflow_runs", []):
                runs.append(
                    {
                        "id": run["id"],
                        "name": run["name"],
                        "status": run["status"],
                        "conclusion": run.get("conclusion"),
                        "branch": run["head_branch"],
                        "created_at": run["created_at"],
                    }
                )

            return runs

    def _calculate_duration(
        self, created_at: Optional[str], updated_at: Optional[str]
    ) -> Optional[int]:
        """Calculate duration in seconds between two ISO timestamps."""
        if not created_at or not updated_at:
            return None
        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            return int((updated - created).total_seconds())
        except (ValueError, AttributeError) as e:
            logger.warning(
                f"Failed to calculate duration: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return None

    async def _fetch_jobs(
        self,
        client: httpx.AsyncClient,
        jobs_url: str,
        headers: Dict[str, str],
        run_id: int,
    ) -> List[Dict[str, Any]]:
        """Fetch and transform jobs for a workflow run."""
        try:
            response = await client.get(jobs_url, headers=headers)
            if response.status_code != 200:
                logger.warning(
                    f"Failed to fetch jobs for run {run_id}: HTTP {response.status_code}",
                    extra={"correlation_id": get_correlation_id()},
                )
                return []

            jobs_data = response.json()
            jobs = []
            for job in jobs_data.get("jobs", []):
                jobs.append(
                    {
                        "id": job.get("id"),
                        "name": job.get("name"),
                        "status": job.get("status"),
                        "conclusion": job.get("conclusion"),
                        "started_at": job.get("started_at"),
                        "completed_at": job.get("completed_at"),
                        "steps": [
                            {
                                "name": step.get("name"),
                                "status": step.get("status"),
                                "conclusion": step.get("conclusion"),
                                "number": step.get("number"),
                            }
                            for step in job.get("steps", [])
                        ],
                    }
                )
            return jobs
        except Exception as e:
            logger.error(
                f"Error fetching jobs for run {run_id}: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return []

    async def _fetch_artifacts(
        self,
        client: httpx.AsyncClient,
        artifacts_url: str,
        headers: Dict[str, str],
        run_id: int,
    ) -> List[Dict[str, Any]]:
        """Fetch and transform artifacts for a workflow run."""
        try:
            response = await client.get(artifacts_url, headers=headers)
            if response.status_code != 200:
                logger.warning(
                    f"Failed to fetch artifacts for run {run_id}: HTTP {response.status_code}",
                    extra={"correlation_id": get_correlation_id()},
                )
                return []

            artifacts_data = response.json()
            artifacts = []
            for artifact in artifacts_data.get("artifacts", []):
                artifacts.append(
                    {
                        "id": artifact.get("id"),
                        "name": artifact.get("name"),
                        "size_in_bytes": artifact.get("size_in_bytes"),
                        "created_at": artifact.get("created_at"),
                        "expired": artifact.get("expired"),
                    }
                )
            return artifacts
        except Exception as e:
            logger.error(
                f"Error fetching artifacts for run {run_id}: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return []

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=before_sleep_log(logger, logging.DEBUG),
        reraise=True,
    )
    async def get_run(
        self,
        repository: str,
        run_id: int,
    ) -> Dict[str, Any]:
        """
        Get detailed information for a specific workflow run.

        AC4: Get detailed run information

        Args:
            repository: Repository in "owner/repo" format
            run_id: Workflow run ID

        Returns:
            Detailed run information including:
            - id: Workflow run ID
            - name: Workflow name
            - status: Run status
            - conclusion: Run conclusion
            - branch: Branch name
            - commit_sha: Commit SHA that triggered the run (AC4 required)
            - duration_seconds: Duration in seconds (AC4 required)
            - created_at: Creation timestamp
            - updated_at: Last update timestamp
            - html_url: URL to view run in browser
            - jobs_url: API URL to get jobs for this run
            - jobs: List of jobs with steps (AC4 required)
            - artifacts: List of artifacts (AC4 required)
            - run_started_at: When run actually started execution
        """
        url = f"{self.base_url}/repos/{repository}/actions/runs/{run_id}"

        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)

            if response.status_code != 200:
                raise Exception(f"GitHub API error: {response.status_code}")

            data = response.json()

            # Fetch additional data required by AC4
            duration_seconds = self._calculate_duration(
                data.get("created_at"), data.get("updated_at")
            )
            jobs = await self._fetch_jobs(client, data["jobs_url"], headers, run_id)
            artifacts_url = (
                f"{self.base_url}/repos/{repository}/actions/runs/{run_id}/artifacts"
            )
            artifacts = await self._fetch_artifacts(
                client, artifacts_url, headers, run_id
            )

            # Transform API response to expected format with all AC4 fields
            return {
                "id": data["id"],
                "name": data["name"],
                "status": data["status"],
                "conclusion": data.get("conclusion"),
                "branch": data["head_branch"],
                "commit_sha": data.get("head_sha"),
                "duration_seconds": duration_seconds,
                "created_at": data["created_at"],
                "updated_at": data["updated_at"],
                "html_url": data["html_url"],
                "jobs_url": data["jobs_url"],
                "jobs": jobs,
                "artifacts": artifacts,
                "run_started_at": data["run_started_at"],
            }

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=before_sleep_log(logger, logging.DEBUG),
        reraise=True,
    )
    async def search_logs(
        self,
        repository: str,
        run_id: int,
        pattern: str,
    ) -> List[Dict[str, Any]]:
        """
        Search workflow run logs for a pattern using Python regex.

        AC5: Search logs with pattern matching

        Args:
            repository: Repository in "owner/repo" format
            run_id: Workflow run ID
            pattern: Pattern to search for (case-insensitive)

        Returns:
            List of matching log lines with context:
            - job_id: Job ID that produced the log line
            - job_name: Name of the job
            - line: The matching log line
            - line_number: Line number in the job logs
        """
        # First, get list of jobs for this run
        jobs_url = f"{self.base_url}/repos/{repository}/actions/runs/{run_id}/jobs"

        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

        async with httpx.AsyncClient() as client:
            # Get jobs
            jobs_response = await client.get(jobs_url, headers=headers)

            if jobs_response.status_code != 200:
                raise Exception(
                    f"GitHub API error getting jobs: {jobs_response.status_code}"
                )

            jobs_data = jobs_response.json()
            jobs = jobs_data.get("jobs", [])

            # Search logs for each job
            matches = []
            pattern_re = re.compile(pattern, re.IGNORECASE)

            for job in jobs:
                job_id = job["id"]
                job_name = job["name"]

                # Get logs for this job
                logs_url = (
                    f"{self.base_url}/repos/{repository}/actions/jobs/{job_id}/logs"
                )
                logs_response = await client.get(logs_url, headers=headers)

                if logs_response.status_code != 200:
                    continue  # Skip jobs with no logs or access issues

                log_text = logs_response.text

                # Search for pattern in logs
                for line_number, line in enumerate(log_text.split("\n"), 1):
                    if pattern_re.search(line):
                        matches.append(
                            {
                                "job_id": job_id,
                                "job_name": job_name,
                                "line": line,
                                "line_number": line_number,
                            }
                        )

            return matches

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=before_sleep_log(logger, logging.DEBUG),
        reraise=True,
    )
    async def get_job_logs(
        self,
        repository: str,
        job_id: int,
    ) -> str:
        """
        Get logs for a specific job.

        AC6: Get job logs

        Args:
            repository: Repository in "owner/repo" format
            job_id: Job ID

        Returns:
            Full log output as text
        """
        url = f"{self.base_url}/repos/{repository}/actions/jobs/{job_id}/logs"

        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)

            if response.status_code != 200:
                raise Exception(
                    f"GitHub API error getting job logs: {response.status_code}"
                )

            return cast(str, response.text)

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=before_sleep_log(logger, logging.DEBUG),
        reraise=True,
    )
    async def retry_run(
        self,
        repository: str,
        run_id: int,
    ) -> Dict[str, Any]:
        """
        Retry a failed workflow run.

        AC7: Retry workflow run

        Args:
            repository: Repository in "owner/repo" format
            run_id: Workflow run ID to retry

        Returns:
            Confirmation dictionary with:
            - success: Boolean indicating retry was triggered
            - run_id: The workflow run ID that was retried
        """
        url = f"{self.base_url}/repos/{repository}/actions/runs/{run_id}/rerun"

        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers)

            if response.status_code != 201:
                raise Exception(
                    f"GitHub API error retrying run: {response.status_code}"
                )

            return {
                "success": True,
                "run_id": run_id,
            }

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=before_sleep_log(logger, logging.DEBUG),
        reraise=True,
    )
    async def cancel_run(
        self,
        repository: str,
        run_id: int,
    ) -> Dict[str, Any]:
        """
        Cancel a running workflow.

        AC8: Cancel workflow run

        Args:
            repository: Repository in "owner/repo" format
            run_id: Workflow run ID to cancel

        Returns:
            Confirmation dictionary with:
            - success: Boolean indicating cancellation was triggered
            - run_id: The workflow run ID that was cancelled
        """
        url = f"{self.base_url}/repos/{repository}/actions/runs/{run_id}/cancel"

        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers)

            if response.status_code != 202:
                raise Exception(
                    f"GitHub API error cancelling run: {response.status_code}"
                )

            return {
                "success": True,
                "run_id": run_id,
            }
