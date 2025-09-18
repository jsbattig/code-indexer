"""
Validation Reporter for CIDX Server - Story 9 Implementation.

Generates comprehensive validation reports and recommendations.
Following CLAUDE.md Foundation #1: Real reporting, not mocked output.
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any
import textwrap

from .models import ValidationResult

logger = logging.getLogger(__name__)


class ValidationReporter:
    """
    Generates comprehensive validation reports and recommendations.

    Creates human-readable reports with actionable insights based on
    validation results and health check outcomes.
    """

    def __init__(self):
        """Initialize ValidationReporter."""
        logger.info("ValidationReporter initialized")

    def generate_summary_report(self, validation_result: ValidationResult) -> str:
        """
        Generate a concise summary report of validation results.

        Args:
            validation_result: ValidationResult to report on

        Returns:
            Formatted summary report string
        """
        try:
            # Report header
            timestamp = validation_result.validation_timestamp or datetime.now(
                timezone.utc
            )
            report_lines = [
                "=" * 60,
                "INDEX HEALTH SUMMARY",
                "=" * 60,
                f"Validation Date: {timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                f"Validation Status: {'✓ PASSED' if validation_result.is_valid else '✗ FAILED'}",
                "",
            ]

            # Overall health score
            health_score = validation_result.overall_health_score
            health_status = self._get_health_status(health_score)
            report_lines.extend(
                [f"Overall Health Score: {health_score:.2f} ({health_status})", ""]
            )

            # Component scores
            report_lines.extend(
                [
                    "Component Scores:",
                    f"  Completeness: {validation_result.completeness_score:.2f}",
                    f"  Quality: {validation_result.quality_score:.2f}",
                    f"  Consistency: {validation_result.consistency_score:.2f}",
                    f"  Performance: {validation_result.performance_score:.2f}",
                    "",
                ]
            )

            # Validation issues
            if validation_result.validation_errors:
                report_lines.extend(["Validation Issues:", "-" * 20])

                for error in validation_result.validation_errors:
                    severity_icon = self._get_severity_icon(error.severity)
                    report_lines.append(f"{severity_icon} {error.message}")

                    if error.affected_files:
                        files_preview = error.affected_files[:3]  # Show first 3 files
                        for file_path in files_preview:
                            report_lines.append(f"    - {file_path}")
                        if len(error.affected_files) > 3:
                            report_lines.append(
                                f"    ... and {len(error.affected_files) - 3} more files"
                            )

                report_lines.append("")
            else:
                report_lines.extend(["No issues detected - index is healthy!", ""])

            # Recommendations
            if validation_result.recommendations:
                report_lines.extend(["Recommendations:", "-" * 15])
                for i, recommendation in enumerate(
                    validation_result.recommendations, 1
                ):
                    report_lines.append(f"{i}. {recommendation}")
                report_lines.append("")

            # Key metrics
            metadata = validation_result.validation_metadata
            if metadata:
                report_lines.extend(["Key Metrics:", "-" * 12])

                if "total_repository_files" in metadata:
                    report_lines.append(
                        f"Repository Files: {metadata['total_repository_files']:,}"
                    )
                if "total_indexed_files" in metadata:
                    report_lines.append(
                        f"Indexed Files: {metadata['total_indexed_files']:,}"
                    )
                if "validation_duration_seconds" in metadata:
                    duration = metadata["validation_duration_seconds"]
                    report_lines.append(f"Validation Time: {duration:.1f} seconds")

            report_lines.append("=" * 60)

            return "\n".join(report_lines)

        except Exception as e:
            logger.error(f"Failed to generate summary report: {e}")
            return f"Error generating summary report: {str(e)}"

    def generate_detailed_report(self, validation_result: ValidationResult) -> str:
        """
        Generate a detailed technical report of validation results.

        Args:
            validation_result: ValidationResult to report on

        Returns:
            Formatted detailed report string
        """
        try:
            timestamp = validation_result.validation_timestamp or datetime.now(
                timezone.utc
            )

            report_lines = [
                "=" * 80,
                "DETAILED INDEX VALIDATION REPORT",
                "=" * 80,
                f"Generated: {timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                f"Validation Type: {validation_result.validation_metadata.get('validation_type', 'unknown')}",
                "",
            ]

            # Executive Summary
            report_lines.extend(
                [
                    "EXECUTIVE SUMMARY",
                    "-" * 20,
                    f"Overall Status: {'HEALTHY' if validation_result.is_valid else 'REQUIRES ATTENTION'}",
                    f"Health Score: {validation_result.overall_health_score:.3f}",
                    f"Critical Issues: {len([e for e in validation_result.validation_errors if e.is_critical])}",
                    f"Warnings: {len([e for e in validation_result.validation_errors if e.severity == 'warning'])}",
                    "",
                ]
            )

            # Index Statistics
            metadata = validation_result.validation_metadata
            if metadata:
                report_lines.extend(["INDEX STATISTICS", "-" * 16])

                stats_map = {
                    "total_repository_files": "Repository Files",
                    "total_indexed_files": "Indexed Files",
                    "correctly_indexed_files": "Correctly Indexed",
                    "total_documents": "Total Documents",
                    "total_vectors": "Total Vectors",
                    "index_size_mb": "Index Size (MB)",
                    "validation_duration_seconds": "Validation Duration (sec)",
                }

                for key, label in stats_map.items():
                    if key in metadata:
                        value = metadata[key]
                        if isinstance(value, (int, float)):
                            if key.endswith("_seconds"):
                                report_lines.append(f"{label}: {value:.1f}")
                            elif key.endswith("_mb"):
                                report_lines.append(f"{label}: {value:.1f}")
                            elif isinstance(value, int):
                                report_lines.append(f"{label}: {value:,}")
                            else:
                                report_lines.append(f"{label}: {value:.2f}")
                        else:
                            report_lines.append(f"{label}: {value}")

                report_lines.append("")

            # Detailed Component Analysis
            report_lines.extend(["DETAILED COMPONENT ANALYSIS", "-" * 30])

            # Completeness Analysis
            report_lines.extend(
                [
                    f"Completeness Score: {validation_result.completeness_score:.3f}",
                    f"  Missing Files: {len(validation_result.missing_files)}",
                    f"  Extra Indexed Files: {len(validation_result.extra_indexed_files)}",
                    "",
                ]
            )

            # Quality Analysis
            report_lines.extend(
                [
                    f"Quality Score: {validation_result.quality_score:.3f}",
                    f"  Corruption Detected: {'Yes' if validation_result.corruption_detected else 'No'}",
                    "",
                ]
            )

            # Consistency Analysis
            report_lines.extend(
                [
                    f"Consistency Score: {validation_result.consistency_score:.3f}",
                    f"  Outdated Files: {len(validation_result.outdated_files)}",
                    "",
                ]
            )

            # Performance Analysis
            report_lines.extend(
                [f"Performance Score: {validation_result.performance_score:.3f}", ""]
            )

            # Detailed Error Analysis
            if validation_result.validation_errors:
                report_lines.extend(["DETAILED ERROR ANALYSIS", "-" * 23])

                # Group errors by type
                errors_by_type: Dict[str, List[Any]] = {}
                for error in validation_result.validation_errors:
                    error_type = error.error_type
                    if error_type not in errors_by_type:
                        errors_by_type[error_type] = []
                    errors_by_type[error_type].append(error)

                for error_type, errors in errors_by_type.items():
                    report_lines.append(f"{error_type} ({len(errors)} occurrences):")

                    for error in errors[:3]:  # Limit to first 3 errors per type
                        report_lines.append(f"  • {error.message}")
                        if error.affected_files:
                            file_preview = error.affected_files[:5]
                            for file_path in file_preview:
                                report_lines.append(f"    - {file_path}")
                            if len(error.affected_files) > 5:
                                report_lines.append(
                                    f"    ... and {len(error.affected_files) - 5} more"
                                )

                        # Show metadata if available
                        if error.metadata:
                            for key, value in error.metadata.items():
                                report_lines.append(f"    {key}: {value}")

                    if len(errors) > 3:
                        report_lines.append(
                            f"  ... and {len(errors) - 3} more similar errors"
                        )

                    report_lines.append("")

            # Action Plan
            if validation_result.recommendations:
                report_lines.extend(["RECOMMENDED ACTION PLAN", "-" * 23])

                for i, recommendation in enumerate(
                    validation_result.recommendations, 1
                ):
                    wrapped_text = textwrap.fill(
                        recommendation,
                        width=70,
                        initial_indent=f"{i}. ",
                        subsequent_indent="   ",
                    )
                    report_lines.append(wrapped_text)

                report_lines.append("")

            # Footer
            report_lines.extend(
                [
                    "=" * 80,
                    f"Report completed at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
                    "For questions or support, refer to validation documentation.",
                ]
            )

            return "\n".join(report_lines)

        except Exception as e:
            logger.error(f"Failed to generate detailed report: {e}")
            return f"Error generating detailed report: {str(e)}"

    def generate_recommendations(
        self, validation_result: ValidationResult
    ) -> List[str]:
        """
        Generate actionable recommendations based on validation results.

        Args:
            validation_result: ValidationResult to analyze

        Returns:
            List of actionable recommendation strings
        """
        try:
            recommendations = []

            # Critical issues first
            critical_errors = [
                e for e in validation_result.validation_errors if e.is_critical
            ]
            if critical_errors:
                recommendations.append(
                    f"URGENT: Address {len(critical_errors)} critical validation errors immediately"
                )

            # Analyze errors by type and generate specific recommendations
            error_types = set(
                error.error_type for error in validation_result.validation_errors
            )

            for error_type in error_types:
                type_errors = [
                    e
                    for e in validation_result.validation_errors
                    if e.error_type == error_type
                ]

                if error_type == "MISSING_FILES":
                    missing_count = sum(len(e.affected_files) for e in type_errors)
                    if missing_count < 20:
                        recommendations.append(
                            f"Run incremental indexing to add {missing_count} missing files to the index"
                        )
                    else:
                        recommendations.append(
                            f"Consider full re-indexing due to {missing_count} missing files"
                        )

                elif error_type == "EXTRA_INDEXED_FILES":
                    extra_count = sum(len(e.affected_files) for e in type_errors)
                    recommendations.append(
                        f"Clean up {extra_count} stale index entries for deleted/moved files"
                    )

                elif error_type == "INDEX_CORRUPTION":
                    recommendations.append(
                        "Perform full re-index immediately due to detected index corruption"
                    )

                elif error_type == "OUTDATED_INDEX_ENTRIES":
                    outdated_count = sum(len(e.affected_files) for e in type_errors)
                    if outdated_count < 10:
                        recommendations.append(
                            f"Update index for {outdated_count} modified files using incremental indexing"
                        )
                    else:
                        recommendations.append(
                            f"Perform full re-index due to {outdated_count} outdated files"
                        )

                elif error_type == "PERFORMANCE_DEGRADATION":
                    recommendations.append(
                        "Optimize index performance through collection compaction or tuning"
                    )

                elif error_type == "METADATA_INCONSISTENT":
                    recommendations.append(
                        "Repair metadata inconsistencies through incremental re-indexing"
                    )

                elif error_type == "QUALITY_DEGRADATION":
                    recommendations.append(
                        "Improve embedding quality by re-indexing affected files"
                    )

            # Overall health-based recommendations
            health_score = validation_result.overall_health_score

            if health_score < 0.3:
                recommendations.append(
                    "Index health is critically low - immediate full re-indexing required"
                )
            elif health_score < 0.6:
                recommendations.append(
                    "Index health is poor - consider comprehensive re-indexing"
                )
            elif health_score < 0.8:
                recommendations.append(
                    "Index health needs improvement - selective re-indexing recommended"
                )

            # Performance-specific recommendations
            if validation_result.performance_score < 0.7:
                recommendations.append(
                    "Query performance is below optimal - consider index optimization"
                )

            # If full re-index is required, make it the top recommendation
            if validation_result.requires_full_reindex and recommendations:
                full_reindex_rec = (
                    "Perform full re-index to address multiple critical issues"
                )
                if full_reindex_rec not in recommendations:
                    recommendations.insert(0, full_reindex_rec)

            # If no issues, provide maintenance recommendations
            if not recommendations and validation_result.is_valid:
                recommendations.extend(
                    [
                        "Index is healthy - continue regular validation monitoring",
                        "Consider periodic optimization for sustained performance",
                    ]
                )

            return recommendations

        except Exception as e:
            logger.error(f"Failed to generate recommendations: {e}")
            return [f"Error generating recommendations: {str(e)}"]

    def _get_health_status(self, score: float) -> str:
        """Get human-readable health status from score."""
        if score >= 0.95:
            return "Excellent"
        elif score >= 0.85:
            return "Very Good"
        elif score >= 0.75:
            return "Good"
        elif score >= 0.65:
            return "Fair"
        elif score >= 0.5:
            return "Poor"
        else:
            return "Critical"

    def _get_severity_icon(self, severity: str) -> str:
        """Get icon for error severity level."""
        severity_icons = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
        return severity_icons.get(severity.lower(), "⚪")

    def format_metrics_for_json(
        self, validation_result: ValidationResult
    ) -> Dict[str, Any]:
        """
        Format validation result as JSON-serializable dictionary.

        Args:
            validation_result: ValidationResult to format

        Returns:
            Dictionary suitable for JSON serialization
        """
        try:
            return {
                "validation_timestamp": (
                    validation_result.validation_timestamp.isoformat()
                    if validation_result.validation_timestamp
                    else None
                ),
                "is_valid": validation_result.is_valid,
                "overall_health_score": validation_result.overall_health_score,
                "component_scores": {
                    "completeness": validation_result.completeness_score,
                    "quality": validation_result.quality_score,
                    "consistency": validation_result.consistency_score,
                    "performance": validation_result.performance_score,
                },
                "validation_errors": [
                    {
                        "type": error.error_type,
                        "message": error.message,
                        "severity": error.severity,
                        "affected_files_count": len(error.affected_files),
                        "affected_files": error.affected_files[:10],  # Limit for size
                        "metadata": error.metadata,
                    }
                    for error in validation_result.validation_errors
                ],
                "recommendations": validation_result.recommendations,
                "summary_stats": {
                    "missing_files": len(validation_result.missing_files),
                    "extra_indexed_files": len(validation_result.extra_indexed_files),
                    "outdated_files": len(validation_result.outdated_files),
                    "corruption_detected": validation_result.corruption_detected,
                    "requires_full_reindex": validation_result.requires_full_reindex,
                },
                "validation_metadata": validation_result.validation_metadata,
            }

        except Exception as e:
            logger.error(f"Failed to format metrics for JSON: {e}")
            return {
                "error": f"Failed to format validation result: {str(e)}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
