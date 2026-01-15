"""
Delegation Callback Receiver Router.

Story #720: Callback-Based Delegation Job Completion

Provides REST endpoint for receiving callbacks from Claude Server
when delegation jobs complete.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..services.delegation_job_tracker import DelegationJobTracker, JobResult

logger = logging.getLogger(__name__)


# Request/Response Models


class CallbackPayload(BaseModel):
    """
    Callback payload from Claude Server.

    Matches the JobCallbackPayload structure from Claude Server C# codebase.
    Uses PascalCase field names to match the C# JSON serialization.
    """

    JobId: str = Field(..., description="Job identifier (Guid as string)")
    Status: str = Field(..., description="Job status (completed, failed, etc)")
    Output: str = Field(..., description="Job output/result content")
    ExitCode: Optional[int] = Field(None, description="Exit code (0 for success)")
    Title: Optional[str] = Field(None, description="Job title")
    Username: Optional[str] = Field(None, description="Username who created the job")
    Repository: Optional[str] = Field(None, description="Repository alias")
    CreatedAt: Optional[datetime] = Field(None, description="Job creation timestamp")
    StartedAt: Optional[datetime] = Field(None, description="Job start timestamp")
    CompletedAt: Optional[datetime] = Field(None, description="Job completion timestamp")
    ReferenceId: Optional[str] = Field(None, description="Reference ID for tracking")
    AffinityToken: Optional[str] = Field(None, description="Affinity token for routing")


class CallbackResponse(BaseModel):
    """Response after receiving a callback."""

    received: bool = Field(..., description="Whether the callback was received")
    job_found: bool = Field(..., description="Whether the job was found in tracker")


# Router definition

router = APIRouter(prefix="/api/delegation", tags=["delegation"])


@router.post("/callback/{job_id}", response_model=CallbackResponse)
async def receive_delegation_callback(
    job_id: str, payload: CallbackPayload
) -> CallbackResponse:
    """
    Receive callback from Claude Server when job completes.

    This endpoint is called by Claude Server when a delegation job finishes
    (either successfully or with failure). The callback resolves the Future
    in DelegationJobTracker, allowing any waiting poll_delegation_job calls
    to receive the result.

    Args:
        job_id: Job identifier from URL path (authoritative)
        payload: Callback payload from Claude Server

    Returns:
        CallbackResponse indicating receipt and whether job was found
    """
    logger.info(
        f"Received callback for job {job_id}: status={payload.Status}"
    )

    tracker = DelegationJobTracker.get_instance()

    # Determine error field - for failed jobs, output may contain error message
    error = None
    if payload.Status.lower() == "failed":
        error = payload.Output

    # Create JobResult from callback payload
    # Use job_id from path (authoritative) rather than payload.JobId
    result = JobResult(
        job_id=job_id,
        status=payload.Status.lower(),
        output=payload.Output,
        exit_code=payload.ExitCode,
        error=error,
    )

    # Complete the job in tracker (resolves the Future)
    job_found = await tracker.complete_job(result)

    if not job_found:
        logger.warning(
            f"Callback received for unknown or already completed job: {job_id}"
        )

    return CallbackResponse(received=True, job_found=job_found)
