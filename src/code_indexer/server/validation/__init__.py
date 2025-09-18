"""
Index validation system for CIDX Server - Story 9 Implementation.

Provides comprehensive index validation including completeness verification,
quality assurance, consistency checking, and health metrics collection.
"""

from .engine import IndexValidationEngine
from .health_checker import IndexHealthChecker
from .models import (
    ValidationResult,
    ValidationMetrics,
    ValidationError,
    HealthCheckResult,
    RecoveryAction,
    RecoveryResult,
    ValidationHistoryEntry,
)
from .exceptions import ValidationFailedError, IndexCorruptionError, RecoveryFailedError
from .metrics_collector import ValidationMetricsCollector
from .reporter import ValidationReporter
from .auto_recovery import AutoRecoveryEngine

__all__ = [
    "IndexValidationEngine",
    "IndexHealthChecker",
    "ValidationResult",
    "ValidationMetrics",
    "ValidationError",
    "HealthCheckResult",
    "RecoveryAction",
    "RecoveryResult",
    "ValidationHistoryEntry",
    "ValidationFailedError",
    "IndexCorruptionError",
    "RecoveryFailedError",
    "ValidationMetricsCollector",
    "ValidationReporter",
    "AutoRecoveryEngine",
]
