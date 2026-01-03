"""
GitLab CI API client.

Story #634: Complete GitLab CI Monitoring
Provides pipeline monitoring, log search, and pipeline control operations.
"""

import re
import logging
import httpx
from typing import Optional, List, Dict, Any
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
    before_sleep_log,
)

logger = logging.getLogger(__name__)


class GitLabAuthenticationError(Exception):
    """Raised when GitLab API authentication fails (401)."""
    pass


class GitLabProjectNotFoundError(Exception):
    """Raised when project is not found or not accessible (404)."""
    pass


def _is_retryable_error(exception: Exception) -> bool:
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
    # GitLabAuthenticationError and GitLabProjectNotFoundError
    non_retryable_types = (GitLabAuthenticationError, GitLabProjectNotFoundError)
    if isinstance(exception, non_retryable_types):
        return False

    return has_retryable_code


class GitLabCIClient:
    """
    Client for GitLab CI API operations.

    Provides pipeline listing, detailed pipeline information, log search,
    and pipeline control (retry, cancel).
    """

    def __init__(self, token: str, base_url: str = "https://gitlab.com"):
        """
        Initialize GitLab CI client.

        Args:
            token: GitLab authentication token (from GITLAB_TOKEN env var or token storage)
            base_url: Base URL for GitLab instance (default: https://gitlab.com for GitLab SaaS)
                     Use custom URL for self-hosted instances (e.g., https://gitlab.company.com)
        """
        self.token = token
        self.base_url = base_url.rstrip("/")  # Remove trailing slash
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
    async def list_pipelines(
        self,
        project_id: str,
        ref: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List pipelines for a project.

        AC1: List recent pipelines
        AC2: Filter by branch (ref)
        AC3: Filter by status
        AC9: Rate limiting tracking
        AC10: Authentication errors
        AC11: Self-hosted GitLab support

        Args:
            project_id: Project in "namespace/project" format or numeric ID
            ref: Optional branch/tag filter
            status: Optional status filter (e.g., "failed", "success", "running")

        Returns:
            List of pipelines with fields:
            - id: Pipeline ID
            - status: Pipeline status (e.g., "success", "failed", "running")
            - ref: Branch/tag name
            - created_at: ISO 8601 timestamp
            - web_url: URL to view pipeline in browser

        Raises:
            GitLabAuthenticationError: When authentication fails (401)
            GitLabProjectNotFoundError: When project not found (404)
        """
        # URL-encode project ID (namespace/project -> namespace%2Fproject)
        encoded_project_id = project_id.replace("/", "%2F")

        # Build API URL
        url = f"{self.base_url}/api/v4/projects/{encoded_project_id}/pipelines"

        # Build query parameters
        params = []
        if ref:
            params.append(f"ref={ref}")
        if status:
            params.append(f"status={status}")

        # Add query string if parameters exist
        if params:
            url = f"{url}?{'&'.join(params)}"

        # Build headers
        headers = {
            "PRIVATE-TOKEN": self.token,
            "Accept": "application/json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)

            # AC10: Check for authentication failure
            if response.status_code == 401:
                raise GitLabAuthenticationError(
                    "GitLab authentication failed. Please check your token is valid and has the required permissions."
                )

            # AC11: Check for project not found
            if response.status_code == 404:
                raise GitLabProjectNotFoundError(
                    f"Project '{project_id}' not found or not accessible. Please check the project path and your access permissions."
                )

            if response.status_code != 200:
                raise Exception(f"GitLab API error: {response.status_code}")

            # AC9: Capture rate limit headers
            self._last_rate_limit = {
                "limit": int(response.headers.get("ratelimit-limit", 0)),
                "remaining": int(response.headers.get("ratelimit-remaining", 0)),
                "reset": int(response.headers.get("ratelimit-reset", 0)),
            }

            data = response.json()

            # Transform API response to expected format
            pipelines = []
            for pipeline in data:
                pipelines.append({
                    "id": pipeline["id"],
                    "status": pipeline["status"],
                    "ref": pipeline["ref"],
                    "created_at": pipeline["created_at"],
                    "web_url": pipeline["web_url"],
                })

            return pipelines

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=before_sleep_log(logger, logging.DEBUG),
        reraise=True,
    )
    async def get_pipeline(
        self,
        project_id: str,
        pipeline_id: int,
    ) -> Dict[str, Any]:
        """
        Get detailed information for a specific pipeline.

        AC4: Get detailed pipeline information

        Args:
            project_id: Project in "namespace/project" format or numeric ID
            pipeline_id: Pipeline ID

        Returns:
            Detailed pipeline information including:
            - id: Pipeline ID
            - status: Pipeline status
            - ref: Branch/tag name
            - sha: Commit SHA
            - created_at: Creation timestamp
            - updated_at: Last update timestamp
            - web_url: URL to view pipeline in browser
            - duration: Duration in seconds
            - coverage: Code coverage percentage (if available)
            - jobs: List of jobs with stages
        """
        # URL-encode project ID
        encoded_project_id = project_id.replace("/", "%2F")

        # Get pipeline details
        pipeline_url = f"{self.base_url}/api/v4/projects/{encoded_project_id}/pipelines/{pipeline_id}"

        headers = {
            "PRIVATE-TOKEN": self.token,
            "Accept": "application/json",
        }

        async with httpx.AsyncClient() as client:
            # Get main pipeline data
            pipeline_response = await client.get(pipeline_url, headers=headers)

            if pipeline_response.status_code != 200:
                raise Exception(f"GitLab API error: {pipeline_response.status_code}")

            pipeline_data = pipeline_response.json()

            # Get jobs for this pipeline
            jobs_url = f"{self.base_url}/api/v4/projects/{encoded_project_id}/pipelines/{pipeline_id}/jobs"
            jobs_response = await client.get(jobs_url, headers=headers)

            jobs = []
            if jobs_response.status_code == 200:
                jobs_data = jobs_response.json()
                for job in jobs_data:
                    jobs.append({
                        "id": job.get("id"),
                        "name": job.get("name"),
                        "stage": job.get("stage"),
                        "status": job.get("status"),
                        "created_at": job.get("created_at"),
                        "started_at": job.get("started_at"),
                        "finished_at": job.get("finished_at"),
                    })

            # Transform API response to expected format
            return {
                "id": pipeline_data["id"],
                "status": pipeline_data["status"],
                "ref": pipeline_data["ref"],
                "sha": pipeline_data.get("sha"),
                "created_at": pipeline_data["created_at"],
                "updated_at": pipeline_data["updated_at"],
                "web_url": pipeline_data["web_url"],
                "duration": pipeline_data.get("duration"),
                "coverage": pipeline_data.get("coverage"),
                "jobs": jobs,
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
        project_id: str,
        pipeline_id: int,
        pattern: str,
        case_sensitive: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Search pipeline logs for a pattern using regex matching.

        AC5: Search logs with regex pattern

        Args:
            project_id: Project in "namespace/project" format or numeric ID
            pipeline_id: Pipeline ID
            pattern: Pattern to search for
            case_sensitive: Whether to use case-sensitive matching (default: False)

        Returns:
            List of matching log lines with context:
            - job_id: Job ID that produced the log line
            - job_name: Name of the job
            - stage: Stage name
            - line: The matching log line
            - line_number: Line number in the job logs
        """
        # URL-encode project ID
        encoded_project_id = project_id.replace("/", "%2F")

        # First, get list of jobs for this pipeline
        jobs_url = f"{self.base_url}/api/v4/projects/{encoded_project_id}/pipelines/{pipeline_id}/jobs"

        headers = {
            "PRIVATE-TOKEN": self.token,
            "Accept": "application/json",
        }

        async with httpx.AsyncClient() as client:
            # Get jobs
            jobs_response = await client.get(jobs_url, headers=headers)

            if jobs_response.status_code != 200:
                raise Exception(f"GitLab API error getting jobs: {jobs_response.status_code}")

            jobs_data = jobs_response.json()

            # Search logs for each job
            matches = []
            # Compile regex with case-sensitivity based on parameter
            regex_flags = 0 if case_sensitive else re.IGNORECASE
            pattern_re = re.compile(pattern, regex_flags)

            for job in jobs_data:
                job_id = job["id"]
                job_name = job["name"]
                stage = job["stage"]

                # Get logs for this job
                logs_url = f"{self.base_url}/api/v4/projects/{encoded_project_id}/jobs/{job_id}/trace"
                logs_response = await client.get(logs_url, headers=headers)

                if logs_response.status_code != 200:
                    continue  # Skip jobs with no logs or access issues

                log_text = logs_response.text

                # Search for pattern in logs
                for line_number, line in enumerate(log_text.split("\n"), 1):
                    if pattern_re.search(line):
                        matches.append({
                            "job_id": job_id,
                            "job_name": job_name,
                            "stage": stage,
                            "line": line,
                            "line_number": line_number,
                        })

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
        project_id: str,
        job_id: int,
    ) -> str:
        """
        Get logs for a specific job.

        AC6: Get job logs

        Args:
            project_id: Project in "namespace/project" format or numeric ID
            job_id: Job ID

        Returns:
            Full log output as text
        """
        # URL-encode project ID
        encoded_project_id = project_id.replace("/", "%2F")

        url = f"{self.base_url}/api/v4/projects/{encoded_project_id}/jobs/{job_id}/trace"

        headers = {
            "PRIVATE-TOKEN": self.token,
            "Accept": "application/json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)

            if response.status_code != 200:
                raise Exception(f"GitLab API error getting job logs: {response.status_code}")

            return response.text

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=before_sleep_log(logger, logging.DEBUG),
        reraise=True,
    )
    async def retry_pipeline(
        self,
        project_id: str,
        pipeline_id: int,
    ) -> Dict[str, Any]:
        """
        Retry a failed pipeline.

        AC7: Retry pipeline

        Args:
            project_id: Project in "namespace/project" format or numeric ID
            pipeline_id: Pipeline ID to retry

        Returns:
            Confirmation dictionary with:
            - success: Boolean indicating retry was triggered
            - pipeline_id: The pipeline ID that was retried
        """
        # URL-encode project ID
        encoded_project_id = project_id.replace("/", "%2F")

        url = f"{self.base_url}/api/v4/projects/{encoded_project_id}/pipelines/{pipeline_id}/retry"

        headers = {
            "PRIVATE-TOKEN": self.token,
            "Accept": "application/json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers)

            if response.status_code != 201:
                raise Exception(f"GitLab API error retrying pipeline: {response.status_code}")

            return {
                "success": True,
                "pipeline_id": pipeline_id,
            }

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=before_sleep_log(logger, logging.DEBUG),
        reraise=True,
    )
    async def cancel_pipeline(
        self,
        project_id: str,
        pipeline_id: int,
    ) -> Dict[str, Any]:
        """
        Cancel a running pipeline.

        AC8: Cancel pipeline

        Args:
            project_id: Project in "namespace/project" format or numeric ID
            pipeline_id: Pipeline ID to cancel

        Returns:
            Confirmation dictionary with:
            - success: Boolean indicating cancellation was triggered
            - pipeline_id: The pipeline ID that was cancelled
        """
        # URL-encode project ID
        encoded_project_id = project_id.replace("/", "%2F")

        url = f"{self.base_url}/api/v4/projects/{encoded_project_id}/pipelines/{pipeline_id}/cancel"

        headers = {
            "PRIVATE-TOKEN": self.token,
            "Accept": "application/json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers)

            if response.status_code != 200:
                raise Exception(f"GitLab API error cancelling pipeline: {response.status_code}")

            return {
                "success": True,
                "pipeline_id": pipeline_id,
            }
