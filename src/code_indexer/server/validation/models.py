"""
Validation data models for CIDX Server - Story 9 Implementation.

Comprehensive data models for validation results, metrics, and reporting.
Following CLAUDE.md Foundation #1: Real data structures, not mocked models.
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class ValidationErrorType(str, Enum):
    """Enumeration of validation error types."""

    MISSING_FILES = "MISSING_FILES"
    EXTRA_INDEXED_FILES = "EXTRA_INDEXED_FILES"
    INDEX_CORRUPTION = "INDEX_CORRUPTION"
    METADATA_INCONSISTENT = "METADATA_INCONSISTENT"
    METADATA_CORRUPTION = "METADATA_CORRUPTION"
    OUTDATED_INDEX_ENTRIES = "OUTDATED_INDEX_ENTRIES"
    PERFORMANCE_DEGRADATION = "PERFORMANCE_DEGRADATION"
    INDEX_FRAGMENTATION = "INDEX_FRAGMENTATION"
    QUALITY_DEGRADATION = "QUALITY_DEGRADATION"
    OPTIMIZATION_OPPORTUNITY = "OPTIMIZATION_OPPORTUNITY"
    MINOR_INCONSISTENCY = "MINOR_INCONSISTENCY"


class ValidationSeverity(str, Enum):
    """Severity levels for validation errors."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class RecoveryType(str, Enum):
    """Types of recovery actions."""

    NONE = "none"
    INCREMENTAL = "incremental"
    FULL = "full"
    OPTIMIZATION = "optimization"


class RecoveryPriority(str, Enum):
    """Priority levels for recovery actions."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ValidationError:
    """Represents a specific validation error with detailed information."""

    error_type: str
    message: str
    affected_files: List[str] = field(default_factory=list)
    severity: str = "warning"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_critical(self) -> bool:
        """Check if this error is critical severity."""
        return self.severity == ValidationSeverity.CRITICAL.value


@dataclass
class ValidationResult:
    """Comprehensive validation result containing all validation outcomes."""

    # Overall validation status
    is_valid: bool

    # Component scores (0.0 - 1.0)
    completeness_score: float
    quality_score: float
    consistency_score: float
    performance_score: float

    # Validation errors and recommendations
    validation_errors: List[ValidationError] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    # Validation metadata
    validation_timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    validation_duration: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    validation_metadata: Dict[str, Any] = field(default_factory=dict)

    # Component weights for overall score calculation
    component_weights: Dict[str, float] = field(
        default_factory=lambda: {
            "completeness": 0.3,
            "quality": 0.25,
            "consistency": 0.25,
            "performance": 0.2,
        }
    )

    # Completeness-specific results
    missing_files: List[str] = field(default_factory=list)
    extra_indexed_files: List[str] = field(default_factory=list)

    # Quality-specific results
    corruption_detected: bool = False

    # Consistency-specific results
    outdated_files: List[str] = field(default_factory=list)

    # Recovery recommendations
    requires_full_reindex: bool = False

    @property
    def overall_health_score(self) -> float:
        """Calculate weighted overall health score."""
        weights = self.component_weights
        return (
            (self.completeness_score * weights.get("completeness", 0.3))
            + (self.quality_score * weights.get("quality", 0.25))
            + (self.consistency_score * weights.get("consistency", 0.25))
            + (self.performance_score * weights.get("performance", 0.2))
        )

    @property
    def critical_errors(self) -> List[ValidationError]:
        """Get only critical validation errors."""
        return [error for error in self.validation_errors if error.is_critical]

    @property
    def warning_errors(self) -> List[ValidationError]:
        """Get warning-level validation errors."""
        return [
            error for error in self.validation_errors if error.severity == "warning"
        ]


@dataclass
class HealthCheckResult:
    """Result of health check operations on index components."""

    # Overall health status
    is_healthy: bool

    # Dimension validation
    dimension_consistency_score: float = 1.0
    expected_dimensions: int = 0
    actual_dimensions: List[int] = field(default_factory=list)
    dimension_violations: List[Dict[str, Any]] = field(default_factory=list)

    # Vector quality metrics
    quality_score: float = 1.0
    zero_vector_count: int = 0
    nan_vector_count: int = 0
    variance_score: float = 0.0
    corrupt_files: List[str] = field(default_factory=list)

    # Metadata integrity
    completeness_score: float = 1.0
    missing_metadata_count: int = 0
    invalid_metadata_count: int = 0
    metadata_errors: List[Dict[str, Any]] = field(default_factory=list)

    # Performance metrics
    is_performant: bool = True
    average_query_time_ms: float = 0.0
    slowest_query_time_ms: float = 0.0
    performance_score: float = 1.0
    slow_queries: List[Dict[str, Any]] = field(default_factory=list)

    # Index statistics
    total_documents: int = 0
    total_vectors: int = 0
    index_status: str = "unknown"
    vector_dimensions: int = 0
    distance_metric: str = "unknown"
    storage_usage_mb: float = 0.0

    # Comprehensive health results
    overall_health_score: float = 0.0
    critical_issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    @property
    def performance_tier(self) -> str:
        """Classify performance tier based on metrics."""
        if self.performance_score >= 0.9:
            return "excellent"
        elif self.performance_score >= 0.7:
            return "good"
        else:
            return "poor"


@dataclass
class ValidationHistoryEntry:
    """Single entry in validation history for trending analysis."""

    timestamp: datetime
    health_score: float
    validation_duration_seconds: float
    errors_count: int
    validation_type: str = "comprehensive"


@dataclass
class ValidationMetrics:
    """Aggregated validation metrics for analysis and reporting."""

    # Current metrics
    current_health_score: float

    # Trending analysis
    health_trend_7_days: float = 0.0
    validation_history: List[ValidationHistoryEntry] = field(default_factory=list)

    # Aggregated statistics
    total_validations: int = 0
    success_rate: float = 1.0
    average_health_score: float = 1.0
    average_validation_time: float = 0.0
    total_errors: int = 0

    def analyze_trends(self) -> Dict[str, Any]:
        """Analyze trends from validation history."""
        if len(self.validation_history) < 2:
            return {
                "health_declining": False,
                "performance_degrading": False,
                "error_rate_increasing": False,
                "requires_attention": False,
            }

        # Calculate trends
        recent_scores = [entry.health_score for entry in self.validation_history[-5:]]
        older_scores = (
            [entry.health_score for entry in self.validation_history[-10:-5]]
            if len(self.validation_history) >= 10
            else []
        )

        health_declining = False
        if older_scores:
            avg_recent = sum(recent_scores) / len(recent_scores)
            avg_older = sum(older_scores) / len(older_scores)
            health_declining = avg_recent < avg_older * 0.95  # 5% decline threshold

        recent_times = [
            entry.validation_duration_seconds for entry in self.validation_history[-5:]
        ]
        older_times = (
            [
                entry.validation_duration_seconds
                for entry in self.validation_history[-10:-5]
            ]
            if len(self.validation_history) >= 10
            else []
        )

        performance_degrading = False
        if older_times:
            avg_recent_time = sum(recent_times) / len(recent_times)
            avg_older_time = sum(older_times) / len(older_times)
            performance_degrading = (
                avg_recent_time > avg_older_time * 1.2
            )  # 20% slowdown threshold

        recent_errors = [entry.errors_count for entry in self.validation_history[-5:]]
        older_errors = (
            [entry.errors_count for entry in self.validation_history[-10:-5]]
            if len(self.validation_history) >= 10
            else []
        )

        error_rate_increasing = False
        if older_errors:
            avg_recent_errors = sum(recent_errors) / len(recent_errors)
            avg_older_errors = sum(older_errors) / len(older_errors)
            error_rate_increasing = (
                avg_recent_errors > avg_older_errors * 1.5
            )  # 50% increase threshold

        requires_attention = (
            health_declining or performance_degrading or error_rate_increasing
        )

        return {
            "health_declining": health_declining,
            "performance_degrading": performance_degrading,
            "error_rate_increasing": error_rate_increasing,
            "requires_attention": requires_attention,
        }


@dataclass
class EmbeddingQualityReport:
    """Detailed report on embedding quality analysis."""

    total_embeddings_checked: int
    healthy_embeddings: int
    corrupted_embeddings: int
    dimension_issues: int
    zero_vectors: int
    nan_vectors: int
    quality_score: float
    recommendations: List[str] = field(default_factory=list)


@dataclass
class RecoveryAction:
    """Describes a recovery action to be taken based on validation results."""

    recovery_type: str
    is_required: bool
    priority: str
    description: str
    estimated_duration_minutes: int

    # Action details
    affected_files: List[str] = field(default_factory=list)
    pre_recovery_steps: List[str] = field(default_factory=list)
    post_recovery_verification: List[str] = field(default_factory=list)

    # Execution metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_critical_priority(self) -> bool:
        """Check if this recovery action has critical priority."""
        return self.priority == RecoveryPriority.CRITICAL.value


@dataclass
class RecoveryResult:
    """Result of executing a recovery action."""

    success: bool
    recovery_type: str
    duration_seconds: float

    # Recovery details
    files_processed: int = 0
    chunks_created: int = 0
    backup_created: bool = False
    backup_path: Optional[str] = None
    optimization_performed: bool = False

    # Post-recovery validation
    post_recovery_health_score: float = 0.0
    improvement_score: float = 0.0

    # Execution metadata
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
