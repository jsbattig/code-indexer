"""
Validation Metrics Collector for CIDX Server - Story 9 Implementation.

Collects and aggregates validation metrics for analysis and trend detection.
Following CLAUDE.md Foundation #1: Real metrics collection, not mocked data.
"""

from code_indexer.server.middleware.correlation import get_correlation_id

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import json

from .models import ValidationResult, ValidationMetrics, ValidationHistoryEntry

logger = logging.getLogger(__name__)


class ValidationMetricsCollector:
    """
    Collects and aggregates validation metrics for trend analysis.

    Stores validation history and provides aggregated metrics for
    health monitoring and performance tracking.
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize ValidationMetricsCollector.

        Args:
            storage_path: Optional path for persistent storage of metrics
        """
        # Set up storage path
        if storage_path:
            self.storage_path = storage_path
        else:
            # Default to user's tmp directory
            self.storage_path = Path.home() / ".tmp" / "cidx_validation_metrics"

        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.history_file = self.storage_path / "validation_history.json"

        # In-memory metrics
        self._validation_results: List[ValidationResult] = []
        self._history_entries: List[ValidationHistoryEntry] = []

        # Load existing history
        self._load_history()

        logger.info(
            f"ValidationMetricsCollector initialized with storage at {self.storage_path}"
        , extra={"correlation_id": get_correlation_id()})

    def add_validation_result(self, result: ValidationResult) -> None:
        """
        Add a validation result to the metrics collection.

        Args:
            result: ValidationResult to add to metrics
        """
        try:
            # Add to in-memory collection
            self._validation_results.append(result)

            # Create history entry
            duration_seconds = 0.0
            if hasattr(result, "validation_duration") and result.validation_duration:
                if (
                    hasattr(result, "validation_timestamp")
                    and result.validation_timestamp
                ):
                    duration = result.validation_duration - result.validation_timestamp
                    duration_seconds = duration.total_seconds()

            history_entry = ValidationHistoryEntry(
                timestamp=result.validation_timestamp or datetime.now(timezone.utc),
                health_score=result.overall_health_score,
                validation_duration_seconds=duration_seconds,
                errors_count=len(result.validation_errors),
                validation_type=result.validation_metadata.get(
                    "validation_type", "unknown"
                ),
            )

            self._history_entries.append(history_entry)

            # Persist to storage
            self._save_history()

            logger.debug(
                f"Added validation result with health score {result.overall_health_score:.2f}"
            , extra={"correlation_id": get_correlation_id()})

        except Exception as e:
            logger.error(f"Failed to add validation result to metrics: {e}", extra={"correlation_id": get_correlation_id()})

    def get_aggregated_metrics(self, days_back: int = 30) -> ValidationMetrics:
        """
        Get aggregated validation metrics for the specified time period.

        Args:
            days_back: Number of days back to include in aggregation

        Returns:
            ValidationMetrics with aggregated data
        """
        try:
            # Filter recent results
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
            recent_results = [
                result
                for result in self._validation_results
                if (result.validation_timestamp or datetime.now(timezone.utc))
                >= cutoff_date
            ]

            # Filter recent history entries
            recent_history = [
                entry
                for entry in self._history_entries
                if entry.timestamp >= cutoff_date
            ]

            if not recent_results:
                # Return default metrics if no data
                return ValidationMetrics(
                    current_health_score=1.0,
                    health_trend_7_days=0.0,
                    validation_history=recent_history,
                    total_validations=0,
                    success_rate=1.0,
                    average_health_score=1.0,
                    average_validation_time=0.0,
                    total_errors=0,
                )

            # Calculate aggregated metrics
            total_validations = len(recent_results)
            successful_validations = len([r for r in recent_results if r.is_valid])
            success_rate = (
                successful_validations / total_validations
                if total_validations > 0
                else 1.0
            )

            health_scores = [r.overall_health_score for r in recent_results]
            average_health_score = sum(health_scores) / len(health_scores)

            # Calculate validation time average
            validation_times = []
            for result in recent_results:
                if (
                    hasattr(result, "validation_duration")
                    and result.validation_duration
                ):
                    if (
                        hasattr(result, "validation_timestamp")
                        and result.validation_timestamp
                    ):
                        duration = (
                            result.validation_duration - result.validation_timestamp
                        )
                        validation_times.append(duration.total_seconds())

            average_validation_time = (
                sum(validation_times) / len(validation_times)
                if validation_times
                else 0.0
            )

            # Count total errors
            total_errors = sum(len(r.validation_errors) for r in recent_results)

            # Calculate 7-day health trend
            health_trend_7_days = self._calculate_health_trend(recent_history, days=7)

            # Get current health score
            current_health_score = (
                recent_results[-1].overall_health_score if recent_results else 1.0
            )

            return ValidationMetrics(
                current_health_score=current_health_score,
                health_trend_7_days=health_trend_7_days,
                validation_history=recent_history,
                total_validations=total_validations,
                success_rate=success_rate,
                average_health_score=average_health_score,
                average_validation_time=average_validation_time,
                total_errors=total_errors,
            )

        except Exception as e:
            logger.error(f"Failed to calculate aggregated metrics: {e}", extra={"correlation_id": get_correlation_id()})
            # Return minimal metrics on error
            return ValidationMetrics(
                current_health_score=0.0,
                health_trend_7_days=0.0,
                validation_history=[],
                total_validations=0,
                success_rate=0.0,
                average_health_score=0.0,
                average_validation_time=0.0,
                total_errors=0,
            )

    def get_trend_analysis(self, days_back: int = 14) -> Dict[str, Any]:
        """
        Analyze trends in validation metrics.

        Args:
            days_back: Number of days back to analyze

        Returns:
            Dictionary with trend analysis results
        """
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
            recent_history = [
                entry
                for entry in self._history_entries
                if entry.timestamp >= cutoff_date
            ]

            if len(recent_history) < 2:
                return {
                    "health_declining": False,
                    "performance_degrading": False,
                    "error_rate_increasing": False,
                    "requires_attention": False,
                    "data_points": len(recent_history),
                }

            # Use the analyze_trends method from ValidationMetrics
            metrics = ValidationMetrics(
                current_health_score=recent_history[-1].health_score,
                validation_history=recent_history,
            )

            trend_analysis = metrics.analyze_trends()
            trend_analysis["data_points"] = len(recent_history)

            return trend_analysis

        except Exception as e:
            logger.error(f"Failed to analyze trends: {e}", extra={"correlation_id": get_correlation_id()})
            return {
                "health_declining": False,
                "performance_degrading": False,
                "error_rate_increasing": False,
                "requires_attention": False,
                "data_points": 0,
                "error": str(e),
            }

    def cleanup_old_metrics(self, keep_days: int = 90) -> int:
        """
        Clean up old validation metrics to prevent unlimited storage growth.

        Args:
            keep_days: Number of days of metrics to keep

        Returns:
            Number of entries removed
        """
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=keep_days)

            # Clean validation results
            original_results_count = len(self._validation_results)
            self._validation_results = [
                result
                for result in self._validation_results
                if (result.validation_timestamp or datetime.now(timezone.utc))
                >= cutoff_date
            ]

            # Clean history entries
            original_history_count = len(self._history_entries)
            self._history_entries = [
                entry
                for entry in self._history_entries
                if entry.timestamp >= cutoff_date
            ]

            # Save cleaned data
            self._save_history()

            entries_removed = (
                original_results_count - len(self._validation_results)
            ) + (original_history_count - len(self._history_entries))

            logger.info(f"Cleaned up {entries_removed} old validation metrics entries", extra={"correlation_id": get_correlation_id()})
            return entries_removed

        except Exception as e:
            logger.error(f"Failed to cleanup old metrics: {e}", extra={"correlation_id": get_correlation_id()})
            return 0

    def _calculate_health_trend(
        self, history: List[ValidationHistoryEntry], days: int
    ) -> float:
        """Calculate health trend over the specified number of days."""
        if len(history) < 2:
            return 0.0

        try:
            # Get entries for the specified period
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            trend_entries = [
                entry for entry in history if entry.timestamp >= cutoff_date
            ]

            if len(trend_entries) < 2:
                return 0.0

            # Sort by timestamp to ensure chronological order
            trend_entries.sort(key=lambda x: x.timestamp)

            # Calculate simple linear trend
            first_score = trend_entries[0].health_score
            last_score = trend_entries[-1].health_score

            return last_score - first_score

        except Exception as e:
            logger.error(f"Failed to calculate health trend: {e}", extra={"correlation_id": get_correlation_id()})
            return 0.0

    def _load_history(self) -> None:
        """Load validation history from persistent storage."""
        try:
            if not self.history_file.exists():
                return

            with open(self.history_file, "r") as f:
                data = json.load(f)

            # Load history entries
            for entry_data in data.get("history", []):
                try:
                    entry = ValidationHistoryEntry(
                        timestamp=datetime.fromisoformat(entry_data["timestamp"]),
                        health_score=entry_data["health_score"],
                        validation_duration_seconds=entry_data[
                            "validation_duration_seconds"
                        ],
                        errors_count=entry_data["errors_count"],
                        validation_type=entry_data.get("validation_type", "unknown"),
                    )
                    self._history_entries.append(entry)
                except (KeyError, ValueError) as e:
                    logger.warning(f"Skipping invalid history entry: {e}", extra={"correlation_id": get_correlation_id()})
                    continue

            logger.info(
                f"Loaded {len(self._history_entries)} validation history entries"
            , extra={"correlation_id": get_correlation_id()})

        except Exception as e:
            logger.error(f"Failed to load validation history: {e}", extra={"correlation_id": get_correlation_id()})

    def _save_history(self) -> None:
        """Save validation history to persistent storage."""
        try:
            # Prepare data for JSON serialization
            history_data = []
            for entry in self._history_entries:
                history_data.append(
                    {
                        "timestamp": entry.timestamp.isoformat(),
                        "health_score": entry.health_score,
                        "validation_duration_seconds": entry.validation_duration_seconds,
                        "errors_count": entry.errors_count,
                        "validation_type": entry.validation_type,
                    }
                )

            data = {
                "version": "1.0",
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "history": history_data,
            }

            # Write to temporary file first, then rename for atomic operation
            temp_file = self.history_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2)

            # Atomic rename
            temp_file.replace(self.history_file)

        except Exception as e:
            logger.error(f"Failed to save validation history: {e}", extra={"correlation_id": get_correlation_id()})

    def get_summary_stats(self) -> Dict[str, Any]:
        """
        Get summary statistics for all collected metrics.

        Returns:
            Dictionary with summary statistics
        """
        try:
            if not self._validation_results:
                return {
                    "total_validations": 0,
                    "health_score_range": {"min": 0, "max": 0, "avg": 0},
                    "error_summary": {},
                    "validation_types": {},
                    "storage_path": str(self.storage_path),
                }

            health_scores = [r.overall_health_score for r in self._validation_results]

            # Error type summary
            error_summary = {}
            for result in self._validation_results:
                for error in result.validation_errors:
                    error_type = error.error_type
                    if error_type not in error_summary:
                        error_summary[error_type] = 0
                    error_summary[error_type] += 1

            # Validation types summary
            validation_types = {}
            for result in self._validation_results:
                vtype = result.validation_metadata.get("validation_type", "unknown")
                if vtype not in validation_types:
                    validation_types[vtype] = 0
                validation_types[vtype] += 1

            return {
                "total_validations": len(self._validation_results),
                "health_score_range": {
                    "min": min(health_scores),
                    "max": max(health_scores),
                    "avg": sum(health_scores) / len(health_scores),
                },
                "error_summary": error_summary,
                "validation_types": validation_types,
                "history_entries": len(self._history_entries),
                "storage_path": str(self.storage_path),
            }

        except Exception as e:
            logger.error(f"Failed to get summary stats: {e}", extra={"correlation_id": get_correlation_id()})
            return {"error": str(e)}
