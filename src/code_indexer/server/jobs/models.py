"""
Sync Job data models for CIDX Server repository synchronization.

Provides Pydantic models for sync job data structures with validation,
serialization, and persistence support. Following CLAUDE.md Foundation #1:
No mocks - these represent real data structures.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator, field_serializer, ConfigDict


class JobType(str, Enum):
    """Job type enumeration for different operations."""

    REPOSITORY_SYNC = "repository_sync"
    REPOSITORY_ACTIVATION = "repository_activation"
    REPOSITORY_DEACTIVATION = "repository_deactivation"


class JobStatus(str, Enum):
    """Job status enumeration for lifecycle states."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PhaseStatus(str, Enum):
    """Phase status enumeration for multi-phase job operations."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class JobPhase(BaseModel):
    """
    Individual phase within a multi-phase job.

    Represents a single phase of work (e.g., git_pull, indexing) with
    its own progress tracking, timing, and result information.
    """

    phase_name: str = Field(..., description="Name of the phase")

    status: PhaseStatus = Field(
        default=PhaseStatus.PENDING, description="Current status of the phase"
    )

    progress: int = Field(
        default=0, ge=0, le=100, description="Phase progress percentage (0-100)"
    )

    started_at: Optional[datetime] = Field(
        default=None, description="Timestamp when phase started"
    )

    completed_at: Optional[datetime] = Field(
        default=None, description="Timestamp when phase completed"
    )

    duration_seconds: Optional[float] = Field(
        default=None, description="Phase duration in seconds"
    )

    info: Optional[str] = Field(
        default=None, description="Current phase information/status message"
    )

    error_message: Optional[str] = Field(
        default=None, description="Error message if phase failed"
    )

    error_code: Optional[str] = Field(
        default=None, description="Error code if phase failed"
    )

    skip_reason: Optional[str] = Field(
        default=None, description="Reason for skipping phase"
    )

    result: Optional[Dict[str, Any]] = Field(
        default=None, description="Phase result data"
    )

    # Progress tracking fields
    current_file: Optional[str] = Field(
        default=None, description="Current file being processed"
    )

    files_processed: Optional[int] = Field(
        default=None, description="Number of files processed"
    )

    total_files: Optional[int] = Field(
        default=None, description="Total number of files to process"
    )

    metrics: Optional[Dict[str, Any]] = Field(
        default=None, description="Detailed metrics for this phase"
    )

    @field_validator("started_at", "completed_at")
    @classmethod
    def validate_timezone_aware_phase(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Ensure datetime fields are timezone-aware."""
        if v is not None and v.tzinfo is None:
            raise ValueError("Datetime must be timezone-aware")
        return v

    @field_serializer("started_at", "completed_at")
    def serialize_datetime_phase(self, v: Optional[datetime]) -> Optional[str]:
        """Serialize datetime fields to ISO format."""
        if v is None:
            return None
        return v.isoformat()

    model_config = ConfigDict(use_enum_values=True)


class ProgressHistoryEntry(BaseModel):
    """Individual progress history entry for analytics and debugging."""

    timestamp: datetime = Field(..., description="When this progress update occurred")
    phase: str = Field(..., description="Phase name at time of update")
    progress: float = Field(
        ..., ge=0, le=100, description="Progress percentage at this time"
    )
    files_processed: Optional[int] = Field(
        default=None, description="Files processed at this time"
    )
    total_files: Optional[int] = Field(
        default=None, description="Total files at this time"
    )
    info: Optional[str] = Field(default=None, description="Progress info message")
    processing_speed: Optional[float] = Field(
        default=None, description="Processing speed at this time"
    )

    @field_validator("timestamp")
    @classmethod
    def validate_timezone_aware_entry(cls, v: datetime) -> datetime:
        """Ensure timestamp is timezone-aware."""
        if v.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware")
        return v

    @field_serializer("timestamp")
    def serialize_timestamp(self, v: datetime) -> str:
        """Serialize timestamp to ISO format."""
        return v.isoformat()

    model_config = ConfigDict(use_enum_values=True)


class RecoveryCheckpoint(BaseModel):
    """Recovery checkpoint for job interruption recovery."""

    phase: str = Field(..., description="Phase at checkpoint")
    progress: float = Field(..., ge=0, le=100, description="Progress at checkpoint")
    last_file: Optional[str] = Field(default=None, description="Last file processed")
    checkpoint_time: datetime = Field(..., description="When checkpoint was created")
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional checkpoint data"
    )

    @field_validator("checkpoint_time")
    @classmethod
    def validate_timezone_aware_checkpoint(cls, v: datetime) -> datetime:
        """Ensure checkpoint time is timezone-aware."""
        if v.tzinfo is None:
            raise ValueError("Checkpoint time must be timezone-aware")
        return v

    @field_serializer("checkpoint_time")
    def serialize_checkpoint_time(self, v: datetime) -> str:
        """Serialize checkpoint time to ISO format."""
        return v.isoformat()

    model_config = ConfigDict(use_enum_values=True)


class AnalyticsData(BaseModel):
    """Analytics data for job performance monitoring and optimization."""

    performance_metrics: Optional[Dict[str, Dict[str, Any]]] = Field(
        default=None, description="Performance metrics by phase"
    )
    resource_utilization: Optional[Dict[str, Any]] = Field(
        default=None, description="Resource utilization during job"
    )
    progress_patterns: Optional[Dict[str, Any]] = Field(
        default=None, description="Progress pattern analysis"
    )
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When analytics were collected",
    )

    @field_validator("collected_at")
    @classmethod
    def validate_timezone_aware_analytics(cls, v: datetime) -> datetime:
        """Ensure collected_at is timezone-aware."""
        if v.tzinfo is None:
            raise ValueError("Analytics collection time must be timezone-aware")
        return v

    @field_serializer("collected_at")
    def serialize_collected_at(self, v: datetime) -> str:
        """Serialize collection time to ISO format."""
        return v.isoformat()

    model_config = ConfigDict(use_enum_values=True)


class SyncJob(BaseModel):
    """
    Sync job data model.

    Represents a repository synchronization job with comprehensive
    lifecycle tracking, user attribution, and progress monitoring.
    """

    job_id: str = Field(
        ..., min_length=1, description="Unique identifier for the sync job"
    )

    username: str = Field(
        ..., min_length=1, description="Username of the user who created the job"
    )

    user_alias: str = Field(
        ...,
        min_length=1,
        description="Display name/alias of the user who created the job",
    )

    job_type: JobType = Field(..., description="Type of sync job to perform")

    status: JobStatus = Field(
        default=JobStatus.PENDING, description="Current status of the job"
    )

    created_at: datetime = Field(..., description="Timestamp when the job was created")

    started_at: Optional[datetime] = Field(
        default=None, description="Timestamp when the job started execution"
    )

    completed_at: Optional[datetime] = Field(
        default=None, description="Timestamp when the job completed or failed"
    )

    progress: int = Field(
        default=0, ge=0, le=100, description="Progress percentage (0-100)"
    )

    error_message: Optional[str] = Field(
        default=None, description="Error message if job failed"
    )

    repository_url: Optional[str] = Field(
        default=None, description="Repository URL for sync operations"
    )

    queue_position: Optional[int] = Field(
        default=None, description="Position in queue (1-based, only for queued jobs)"
    )

    estimated_wait_minutes: Optional[int] = Field(
        default=None, description="Estimated wait time in minutes for queued jobs"
    )

    queued_at: Optional[datetime] = Field(
        default=None, description="Timestamp when job was added to queue"
    )

    # Multi-phase support
    phases: Optional[Dict[str, JobPhase]] = Field(
        default=None, description="Dictionary of phase name to phase information"
    )

    current_phase: Optional[str] = Field(
        default=None, description="Name of the currently active phase"
    )

    phase_weights: Optional[Dict[str, float]] = Field(
        default=None, description="Weight of each phase for progress calculation"
    )

    # Progress state persistence fields
    overall_progress: float = Field(
        default=0.0,
        ge=0,
        le=100,
        description="Overall weighted progress across all phases",
    )

    progress_history: Optional[List[ProgressHistoryEntry]] = Field(
        default=None, description="Chronological history of progress updates"
    )

    recovery_checkpoint: Optional[RecoveryCheckpoint] = Field(
        default=None, description="Latest recovery checkpoint for interruption recovery"
    )

    analytics_data: Optional[AnalyticsData] = Field(
        default=None, description="Performance analytics and monitoring data"
    )

    start_time: Optional[datetime] = Field(
        default=None, description="Actual start time for progress calculation"
    )

    estimated_completion: Optional[datetime] = Field(
        default=None, description="Estimated completion time based on current progress"
    )

    interrupted_at: Optional[datetime] = Field(
        default=None, description="Timestamp when job was interrupted"
    )

    # Phase details for compatibility with tests
    phase_details: Optional[Dict[str, Dict[str, Any]]] = Field(
        default=None, description="Detailed phase information for persistence"
    )

    @field_validator(
        "created_at",
        "started_at",
        "completed_at",
        "queued_at",
        "start_time",
        "estimated_completion",
        "interrupted_at",
    )
    @classmethod
    def validate_timezone_aware(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Ensure all datetime fields are timezone-aware."""
        if v is not None and v.tzinfo is None:
            raise ValueError("Datetime must be timezone-aware")
        return v

    @field_serializer(
        "created_at",
        "started_at",
        "completed_at",
        "queued_at",
        "start_time",
        "estimated_completion",
        "interrupted_at",
    )
    def serialize_datetime(self, v: Optional[datetime]) -> Optional[str]:
        """Serialize datetime fields to ISO format."""
        if v is None:
            return None
        return v.isoformat()

    model_config = ConfigDict(use_enum_values=True)
