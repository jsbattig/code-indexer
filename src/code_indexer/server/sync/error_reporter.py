"""
Error Reporting and Diagnostics System for CIDX Repository Sync Operations.

Provides structured error logging, error aggregation, diagnostic information
collection, and user-friendly error reporting with actionable next steps
and comprehensive troubleshooting guidance.
"""

import json
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any
import threading

from code_indexer.server.middleware.correlation import get_correlation_id
from .error_handler import SyncError, ErrorSeverity, ErrorCategory, ErrorContext
from .recovery_strategies import RecoveryResult


logger = logging.getLogger(__name__)


class ReportFormat(Enum):
    """Format options for error reports."""

    JSON = "json"
    YAML = "yaml"
    MARKDOWN = "markdown"
    TEXT = "text"
    HTML = "html"


class ReportLevel(Enum):
    """Level of detail for error reports."""

    SUMMARY = "summary"
    DETAILED = "detailed"
    DIAGNOSTIC = "diagnostic"
    FULL = "full"


@dataclass
class ErrorPattern:
    """Represents a pattern of recurring errors."""

    error_code: str
    category: ErrorCategory
    severity: ErrorSeverity
    count: int
    first_occurrence: datetime
    last_occurrence: datetime
    affected_users: List[str] = field(default_factory=list)
    affected_repositories: List[str] = field(default_factory=list)
    recovery_success_rate: float = 0.0
    common_contexts: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DiagnosticData:
    """Comprehensive diagnostic information for troubleshooting."""

    system_environment: Dict[str, Any] = field(default_factory=dict)
    configuration_state: Dict[str, Any] = field(default_factory=dict)
    resource_utilization: Dict[str, Any] = field(default_factory=dict)
    network_connectivity: Dict[str, Any] = field(default_factory=dict)
    git_repository_state: Dict[str, Any] = field(default_factory=dict)
    index_health_metrics: Dict[str, Any] = field(default_factory=dict)
    recent_operations: List[Dict[str, Any]] = field(default_factory=list)
    log_excerpts: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class ErrorReport:
    """Comprehensive error report with analysis and recommendations."""

    report_id: str
    timestamp: datetime
    summary: str
    errors: List[SyncError]
    patterns: List[ErrorPattern]
    diagnostics: DiagnosticData
    recommendations: List[str]
    recovery_attempts: List[RecoveryResult]
    severity_distribution: Dict[str, int]
    category_distribution: Dict[str, int]
    time_range: Dict[str, datetime]
    affected_users: List[str]
    affected_repositories: List[str]
    resolution_suggestions: List[Dict[str, Any]]


class ErrorAggregator:
    """Aggregates and analyzes error patterns over time."""

    def __init__(self, max_history_size: int = 10000):
        self.max_history_size = max_history_size
        self.error_history: List[SyncError] = []
        self.recovery_history: List[RecoveryResult] = []
        self.patterns: Dict[str, ErrorPattern] = {}
        self._lock = threading.Lock()

        self.logger = logging.getLogger(f"{__name__}.ErrorAggregator")

    def add_error(
        self, error: SyncError, recovery_result: Optional[RecoveryResult] = None
    ):
        """Add an error to the aggregation system."""
        with self._lock:
            # Add to history
            self.error_history.append(error)
            if len(self.error_history) > self.max_history_size:
                self.error_history.pop(0)

            if recovery_result:
                self.recovery_history.append(recovery_result)
                if len(self.recovery_history) > self.max_history_size:
                    self.recovery_history.pop(0)

            # Update patterns
            self._update_error_pattern(error, recovery_result)

    def _update_error_pattern(
        self, error: SyncError, recovery_result: Optional[RecoveryResult]
    ):
        """Update error patterns with new error occurrence."""
        pattern_key = f"{error.error_code}_{error.category.value}"

        if pattern_key not in self.patterns:
            self.patterns[pattern_key] = ErrorPattern(
                error_code=error.error_code,
                category=error.category,
                severity=error.severity,
                count=0,
                first_occurrence=error.context.timestamp,
                last_occurrence=error.context.timestamp,
            )

        pattern = self.patterns[pattern_key]
        pattern.count += 1
        pattern.last_occurrence = error.context.timestamp

        # Update affected users and repositories
        if (
            error.context.user_id
            and error.context.user_id not in pattern.affected_users
        ):
            pattern.affected_users.append(error.context.user_id)

        if (
            error.context.repository
            and error.context.repository not in pattern.affected_repositories
        ):
            pattern.affected_repositories.append(error.context.repository)

        # Update recovery success rate
        if recovery_result:
            successful_recoveries = sum(
                1
                for r in self.recovery_history
                if r.success
                and any(
                    attempt.error_before
                    and attempt.error_before.error_code == error.error_code
                    for attempt in r.attempts
                )
            )
            total_recoveries = sum(
                1
                for r in self.recovery_history
                if any(
                    attempt.error_before
                    and attempt.error_before.error_code == error.error_code
                    for attempt in r.attempts
                )
            )
            if total_recoveries > 0:
                pattern.recovery_success_rate = successful_recoveries / total_recoveries

    def get_error_patterns(
        self,
        time_window_hours: Optional[int] = None,
        min_occurrences: int = 1,
        severity_filter: Optional[List[ErrorSeverity]] = None,
    ) -> List[ErrorPattern]:
        """Get error patterns with optional filtering."""
        with self._lock:
            patterns = list(self.patterns.values())

            # Filter by time window
            if time_window_hours:
                cutoff_time = datetime.now(timezone.utc) - timedelta(
                    hours=time_window_hours
                )
                patterns = [p for p in patterns if p.last_occurrence >= cutoff_time]

            # Filter by minimum occurrences
            patterns = [p for p in patterns if p.count >= min_occurrences]

            # Filter by severity
            if severity_filter:
                patterns = [p for p in patterns if p.severity in severity_filter]

            # Sort by count (most frequent first)
            patterns.sort(key=lambda p: p.count, reverse=True)

            return patterns

    def get_error_statistics(
        self, time_window_hours: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get comprehensive error statistics."""
        with self._lock:
            errors = self.error_history
            recoveries = self.recovery_history

            # Filter by time window if specified
            if time_window_hours:
                cutoff_time = datetime.now(timezone.utc) - timedelta(
                    hours=time_window_hours
                )
                errors = [e for e in errors if e.context.timestamp >= cutoff_time]
                recoveries = [
                    r
                    for r in recoveries
                    if r.attempts and r.attempts[0].timestamp >= cutoff_time
                ]

            if not errors:
                return {"total_errors": 0, "time_window_hours": time_window_hours}

            # Basic statistics
            total_errors = len(errors)
            unique_error_codes = len(set(e.error_code for e in errors))

            # Severity distribution
            severity_counts = Counter(e.severity.value for e in errors)
            category_counts = Counter(e.category.value for e in errors)

            # Recovery statistics
            total_recoveries = len(recoveries)
            successful_recoveries = sum(1 for r in recoveries if r.success)
            recovery_success_rate = (
                successful_recoveries / total_recoveries if total_recoveries > 0 else 0
            )

            # Time-based analysis
            error_times = [e.context.timestamp for e in errors]
            time_range = {
                "first_error": min(error_times),
                "last_error": max(error_times),
                "span_hours": (max(error_times) - min(error_times)).total_seconds()
                / 3600,
            }

            # Most common errors
            most_common_errors = Counter(e.error_code for e in errors).most_common(10)

            # User and repository impact
            affected_users = len(
                set(e.context.user_id for e in errors if e.context.user_id)
            )
            affected_repositories = len(
                set(e.context.repository for e in errors if e.context.repository)
            )

            return {
                "total_errors": total_errors,
                "unique_error_codes": unique_error_codes,
                "time_window_hours": time_window_hours,
                "severity_distribution": dict(severity_counts),
                "category_distribution": dict(category_counts),
                "recovery_statistics": {
                    "total_attempts": total_recoveries,
                    "successful_recoveries": successful_recoveries,
                    "success_rate": recovery_success_rate,
                },
                "time_analysis": time_range,
                "most_common_errors": dict(most_common_errors),
                "impact": {
                    "affected_users": affected_users,
                    "affected_repositories": affected_repositories,
                },
            }


class DiagnosticCollector:
    """Collects comprehensive diagnostic information for error analysis."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.DiagnosticCollector")

    def collect_diagnostics(
        self, error: SyncError, context: Optional[ErrorContext] = None
    ) -> DiagnosticData:
        """Collect comprehensive diagnostic information."""
        diagnostics = DiagnosticData()

        try:
            # System environment
            diagnostics.system_environment = self._collect_system_environment()

            # Configuration state
            if context and context.repository:
                diagnostics.configuration_state = self._collect_configuration_state(
                    Path(context.repository)
                )

            # Resource utilization
            diagnostics.resource_utilization = self._collect_resource_utilization()

            # Network connectivity
            if error.category == ErrorCategory.NETWORK:
                diagnostics.network_connectivity = self._collect_network_diagnostics()

            # Git repository state
            if (
                error.category == ErrorCategory.GIT_OPERATION
                and context
                and context.repository
            ):
                diagnostics.git_repository_state = self._collect_git_state(
                    Path(context.repository)
                )

            # Index health metrics
            if error.category == ErrorCategory.INDEXING:
                diagnostics.index_health_metrics = self._collect_index_health()

            # Recent operations log
            diagnostics.recent_operations = self._collect_recent_operations()

            # Relevant log excerpts
            diagnostics.log_excerpts = self._collect_log_excerpts(error)

        except Exception as e:
            self.logger.error(
                f"Failed to collect diagnostics: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            diagnostics.system_environment["diagnostic_collection_error"] = str(e)

        return diagnostics

    def _collect_system_environment(self) -> Dict[str, Any]:
        """Collect system environment information."""
        try:
            import platform
            import sys
            import os

            return {
                "platform": platform.platform(),
                "python_version": sys.version,
                "python_executable": sys.executable,
                "os_name": os.name,
                "cpu_count": os.cpu_count(),
                "environment_variables": {
                    k: v
                    for k, v in os.environ.items()
                    if any(
                        keyword in k.lower()
                        for keyword in ["path", "python", "git", "home", "user"]
                    )
                },
            }
        except Exception as e:
            return {"error": str(e)}

    def _collect_configuration_state(self, repository_path: Path) -> Dict[str, Any]:
        """Collect configuration state information."""
        try:
            config_info: Dict[str, Any] = {}

            # Check for CIDX configuration
            config_file = repository_path / ".code-indexer" / "config.yaml"
            if config_file.exists():
                config_info["cidx_config_exists"] = True
                config_info["cidx_config_size"] = config_file.stat().st_size
                config_info["cidx_config_modified"] = datetime.fromtimestamp(
                    config_file.stat().st_mtime
                ).isoformat()

            # Check git configuration
            git_config_file = repository_path / ".git" / "config"
            if git_config_file.exists():
                config_info["git_config_exists"] = True

            return config_info

        except Exception as e:
            return {"error": str(e)}

    def _collect_resource_utilization(self) -> Dict[str, Any]:
        """Collect system resource utilization information."""
        try:
            import psutil

            memory = psutil.virtual_memory()
            disk_usage = psutil.disk_usage(".")

            return {
                "memory": {
                    "total_gb": memory.total / (1024**3),
                    "available_gb": memory.available / (1024**3),
                    "percent_used": memory.percent,
                },
                "disk": {
                    "total_gb": disk_usage.total / (1024**3),
                    "free_gb": disk_usage.free / (1024**3),
                    "percent_used": (disk_usage.used / disk_usage.total) * 100,
                },
                "cpu": {
                    "percent": psutil.cpu_percent(interval=1),
                    "load_average": (
                        psutil.getloadavg() if hasattr(psutil, "getloadavg") else None
                    ),
                },
            }

        except Exception as e:
            return {"error": str(e)}

    def _collect_network_diagnostics(self) -> Dict[str, Any]:
        """Collect network connectivity diagnostics."""
        try:
            import socket

            diagnostics: Dict[str, Any] = {}

            # Test basic connectivity
            try:
                socket.create_connection(("8.8.8.8", 53), timeout=5)
                diagnostics["internet_connectivity"] = True
            except Exception:
                diagnostics["internet_connectivity"] = False

            # Test DNS resolution
            try:
                socket.gethostbyname("github.com")
                diagnostics["dns_resolution"] = True
            except Exception:
                diagnostics["dns_resolution"] = False

            # Network interfaces
            try:
                import psutil

                diagnostics["network_interfaces"] = [
                    {"name": interface, "addresses": [addr.address for addr in addrs]}
                    for interface, addrs in psutil.net_if_addrs().items()
                ]
            except Exception:
                pass

            return diagnostics

        except Exception as e:
            return {"error": str(e)}

    def _collect_git_state(self, repository_path: Path) -> Dict[str, Any]:
        """Collect git repository state information."""
        try:
            from ...utils.git_runner import run_git_command, is_git_repository

            if not is_git_repository(repository_path):
                return {"is_git_repository": False}

            state: Dict[str, Any] = {"is_git_repository": True}

            try:
                # Current branch
                result = run_git_command(
                    ["branch", "--show-current"], cwd=repository_path
                )
                state["current_branch"] = result.stdout.strip()
            except Exception:
                state["current_branch"] = None

            try:
                # Repository status
                result = run_git_command(["status", "--porcelain"], cwd=repository_path)
                state["has_uncommitted_changes"] = bool(result.stdout.strip())
                state["uncommitted_files_count"] = (
                    len(result.stdout.strip().split("\n"))
                    if result.stdout.strip()
                    else 0
                )
            except Exception:
                pass

            try:
                # Remote information
                result = run_git_command(["remote", "-v"], cwd=repository_path)
                state["remotes"] = result.stdout.strip()
            except Exception:
                pass

            try:
                # Last commit
                result = run_git_command(
                    ["log", "-1", "--oneline"], cwd=repository_path
                )
                state["last_commit"] = result.stdout.strip()
            except Exception:
                pass

            return state

        except Exception as e:
            return {"error": str(e)}

    def _collect_index_health(self) -> Dict[str, Any]:
        """Collect index health metrics."""
        try:
            # This would integrate with the actual indexing system
            # For now, return placeholder data
            return {
                "placeholder": "Index health metrics would be collected here",
                "last_indexed": None,
                "index_size": None,
                "health_score": None,
            }

        except Exception as e:
            return {"error": str(e)}

    def _collect_recent_operations(self) -> List[Dict[str, Any]]:
        """Collect recent operation history."""
        try:
            # This would integrate with the operation logging system
            # For now, return placeholder data
            return [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "operation": "placeholder",
                    "status": "placeholder",
                }
            ]

        except Exception as e:
            return [{"error": str(e)}]

    def _collect_log_excerpts(self, error: SyncError) -> Dict[str, List[str]]:
        """Collect relevant log excerpts related to the error."""
        try:
            excerpts = {}

            # This would search actual log files
            # For now, return placeholder
            excerpts["recent_errors"] = [
                f"Placeholder log entry related to {error.error_code}"
            ]

            return excerpts

        except Exception as e:
            return {"error": [str(e)]}


class ErrorReporter:
    """Generates comprehensive error reports with analysis and recommendations."""

    def __init__(self):
        self.aggregator = ErrorAggregator()
        self.diagnostic_collector = DiagnosticCollector()
        self.logger = logging.getLogger(f"{__name__}.ErrorReporter")

    def report_error(
        self,
        error: SyncError,
        recovery_result: Optional[RecoveryResult] = None,
        collect_diagnostics: bool = True,
    ):
        """Report an error to the system."""
        self.aggregator.add_error(error, recovery_result)

        # Log the error appropriately
        log_level = {
            ErrorSeverity.INFO: logging.INFO,
            ErrorSeverity.WARNING: logging.WARNING,
            ErrorSeverity.RECOVERABLE: logging.WARNING,
            ErrorSeverity.FATAL: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL,
        }.get(error.severity, logging.ERROR)

        self.logger.log(
            log_level,
            f"Error reported: {error.error_code} - {error.message} "
            f"(category={error.category.value}, severity={error.severity.value})",
        )

        # Collect diagnostics if requested
        if collect_diagnostics and error.severity in [
            ErrorSeverity.FATAL,
            ErrorSeverity.CRITICAL,
        ]:
            try:
                self.diagnostic_collector.collect_diagnostics(error, error.context)
                self.logger.debug(f"Diagnostics collected for error {error.error_code}")
            except Exception as e:
                self.logger.warning(
                    f"Failed to collect diagnostics for {error.error_code}: {e}",
                    extra={"correlation_id": get_correlation_id()},
                )

    def generate_report(
        self,
        time_window_hours: Optional[int] = 24,
        report_level: ReportLevel = ReportLevel.DETAILED,
        format: ReportFormat = ReportFormat.JSON,
        include_diagnostics: bool = True,
        min_pattern_occurrences: int = 2,
    ) -> str:
        """Generate a comprehensive error report."""
        report_id = f"error_report_{int(time.time())}"
        timestamp = datetime.now(timezone.utc)

        # Get error statistics
        stats = self.aggregator.get_error_statistics(time_window_hours)

        # Get error patterns
        patterns = self.aggregator.get_error_patterns(
            time_window_hours=time_window_hours, min_occurrences=min_pattern_occurrences
        )

        # Get recent errors for analysis
        recent_errors = [
            error
            for error in self.aggregator.error_history
            if (
                not time_window_hours
                or error.context.timestamp
                >= datetime.now(timezone.utc) - timedelta(hours=time_window_hours)
            )
        ]

        # Generate diagnostics if requested
        diagnostics = DiagnosticData()
        if include_diagnostics and recent_errors:
            # Use the most recent critical/fatal error for diagnostics
            critical_errors = [
                e
                for e in recent_errors
                if e.severity in [ErrorSeverity.CRITICAL, ErrorSeverity.FATAL]
            ]
            if critical_errors:
                diagnostics = self.diagnostic_collector.collect_diagnostics(
                    critical_errors[-1], critical_errors[-1].context
                )

        # Generate recommendations
        recommendations = self._generate_recommendations(patterns, stats, recent_errors)

        # Generate resolution suggestions
        resolution_suggestions = self._generate_resolution_suggestions(patterns)

        # Create report
        report = ErrorReport(
            report_id=report_id,
            timestamp=timestamp,
            summary=self._generate_summary(stats, patterns),
            errors=recent_errors,
            patterns=patterns,
            diagnostics=diagnostics,
            recommendations=recommendations,
            recovery_attempts=self.aggregator.recovery_history[
                -50:
            ],  # Last 50 recovery attempts
            severity_distribution=stats.get("severity_distribution", {}),
            category_distribution=stats.get("category_distribution", {}),
            time_range={
                "start": datetime.now(timezone.utc)
                - timedelta(hours=time_window_hours or 24),
                "end": timestamp,
            },
            affected_users=list(
                set(e.context.user_id for e in recent_errors if e.context.user_id)
            ),
            affected_repositories=list(
                set(e.context.repository for e in recent_errors if e.context.repository)
            ),
            resolution_suggestions=resolution_suggestions,
        )

        # Format report based on requested format
        return self._format_report(report, format, report_level)

    def _generate_summary(
        self, stats: Dict[str, Any], patterns: List[ErrorPattern]
    ) -> str:
        """Generate executive summary of error report."""
        total_errors = stats.get("total_errors", 0)
        if total_errors == 0:
            return "No errors reported in the specified time window."

        summary_parts = [
            f"Total errors: {total_errors}",
            f"Unique error types: {stats.get('unique_error_codes', 0)}",
        ]

        # Most severe errors
        severity_dist = stats.get("severity_distribution", {})
        if severity_dist.get("critical", 0) > 0:
            summary_parts.append(f"Critical errors: {severity_dist['critical']}")
        if severity_dist.get("fatal", 0) > 0:
            summary_parts.append(f"Fatal errors: {severity_dist['fatal']}")

        # Most common patterns
        if patterns:
            top_pattern = patterns[0]
            summary_parts.append(
                f"Most frequent error: {top_pattern.error_code} ({top_pattern.count} occurrences)"
            )

        # Recovery success
        recovery_stats = stats.get("recovery_statistics", {})
        if recovery_stats.get("total_attempts", 0) > 0:
            success_rate = recovery_stats.get("success_rate", 0) * 100
            summary_parts.append(f"Recovery success rate: {success_rate:.1f}%")

        return ". ".join(summary_parts) + "."

    def _generate_recommendations(
        self,
        patterns: List[ErrorPattern],
        stats: Dict[str, Any],
        recent_errors: List[SyncError],
    ) -> List[str]:
        """Generate actionable recommendations based on error analysis."""
        recommendations = []

        # High-frequency error recommendations
        if patterns:
            top_pattern = patterns[0]
            if top_pattern.count >= 5:
                recommendations.append(
                    f"Address recurring {top_pattern.error_code} errors ({top_pattern.count} occurrences) "
                    f"by investigating root cause and implementing preventive measures"
                )

        # Network-related recommendations
        network_errors = [p for p in patterns if p.category == ErrorCategory.NETWORK]
        if network_errors:
            recommendations.append(
                "Network connectivity issues detected. Consider implementing longer timeouts, "
                "retry policies, and network health monitoring"
            )

        # Authentication-related recommendations
        auth_errors = [
            p for p in patterns if p.category == ErrorCategory.AUTHENTICATION
        ]
        if auth_errors:
            recommendations.append(
                "Authentication failures detected. Review credential management, "
                "token refresh policies, and access permissions"
            )

        # System resource recommendations
        resource_errors = [
            p for p in patterns if p.category == ErrorCategory.SYSTEM_RESOURCE
        ]
        if resource_errors:
            recommendations.append(
                "System resource constraints detected. Monitor system resources, "
                "optimize resource usage, and consider scaling up infrastructure"
            )

        # Recovery success rate recommendations
        recovery_stats = stats.get("recovery_statistics", {})
        if recovery_stats.get("success_rate", 1.0) < 0.7:
            recommendations.append(
                "Low recovery success rate detected. Review recovery strategies "
                "and consider implementing additional recovery mechanisms"
            )

        # Add default recommendations if no specific ones generated
        if not recommendations:
            recommendations.append(
                "Monitor error trends and implement proactive error handling measures"
            )

        return recommendations

    def _generate_resolution_suggestions(
        self, patterns: List[ErrorPattern]
    ) -> List[Dict[str, Any]]:
        """Generate specific resolution suggestions for error patterns."""
        suggestions = []

        for pattern in patterns[:5]:  # Top 5 patterns
            suggestion = {
                "error_code": pattern.error_code,
                "category": pattern.category.value,
                "severity": pattern.severity.value,
                "occurrences": pattern.count,
                "actions": self._get_specific_actions(pattern),
            }
            suggestions.append(suggestion)

        return suggestions

    def _get_specific_actions(self, pattern: ErrorPattern) -> List[str]:
        """Get specific actions for resolving an error pattern."""
        actions = []

        # Category-specific actions
        if pattern.category == ErrorCategory.NETWORK:
            actions.extend(
                [
                    "Verify network connectivity and DNS resolution",
                    "Check firewall and proxy settings",
                    "Implement exponential backoff retry logic",
                    "Consider alternative endpoints or mirrors",
                ]
            )

        elif pattern.category == ErrorCategory.AUTHENTICATION:
            actions.extend(
                [
                    "Verify credentials are valid and not expired",
                    "Check access permissions for the resource",
                    "Refresh authentication tokens",
                    "Review two-factor authentication requirements",
                ]
            )

        elif pattern.category == ErrorCategory.GIT_OPERATION:
            actions.extend(
                [
                    "Ensure working directory is clean",
                    "Check repository integrity with git fsck",
                    "Verify remote repository accessibility",
                    "Consider using different merge strategies",
                ]
            )

        elif pattern.category == ErrorCategory.INDEXING:
            actions.extend(
                [
                    "Check embedding provider API status and limits",
                    "Verify vector database connectivity and health",
                    "Review indexing configuration and parameters",
                    "Monitor disk space and memory usage",
                ]
            )

        elif pattern.category == ErrorCategory.FILE_SYSTEM:
            actions.extend(
                [
                    "Check file and directory permissions",
                    "Verify available disk space",
                    "Ensure paths exist and are accessible",
                    "Review file system quotas and limits",
                ]
            )

        elif pattern.category == ErrorCategory.SYSTEM_RESOURCE:
            actions.extend(
                [
                    "Monitor and optimize memory usage",
                    "Check CPU load and system performance",
                    "Review system limits and quotas",
                    "Consider scaling up resources",
                ]
            )

        # Add recovery-based actions
        if pattern.recovery_success_rate < 0.5:
            actions.append(
                f"Improve recovery success rate (currently {pattern.recovery_success_rate:.1%})"
            )

        return actions

    def _format_report(
        self, report: ErrorReport, format: ReportFormat, level: ReportLevel
    ) -> str:
        """Format error report in the requested format."""
        if format == ReportFormat.JSON:
            return self._format_json_report(report, level)
        elif format == ReportFormat.MARKDOWN:
            return self._format_markdown_report(report, level)
        elif format == ReportFormat.TEXT:
            return self._format_text_report(report, level)
        else:
            # Default to JSON
            return self._format_json_report(report, level)

    def _format_json_report(self, report: ErrorReport, level: ReportLevel) -> str:
        """Format report as JSON."""
        # Manually serialize to avoid deepcopy issues with custom exception classes
        report_dict = {
            "report_id": report.report_id,
            "timestamp": report.timestamp.isoformat(),
            "summary": report.summary,
            "severity_distribution": report.severity_distribution,
            "category_distribution": report.category_distribution,
            "affected_users": report.affected_users,
            "affected_repositories": report.affected_repositories,
            "recommendations": report.recommendations,
            "resolution_suggestions": report.resolution_suggestions,
            "time_range": {
                "start": report.time_range["start"].isoformat(),
                "end": report.time_range["end"].isoformat(),
            },
        }

        # Add level-specific content
        if level != ReportLevel.SUMMARY:
            # Include error details
            report_dict["errors"] = [
                {
                    "message": error.message,
                    "error_code": error.error_code,
                    "severity": error.severity.value,
                    "category": error.category.value,
                    "timestamp": error.context.timestamp.isoformat(),
                    "phase": error.context.phase,
                    "repository": error.context.repository,
                    "user_id": error.context.user_id,
                    "job_id": error.context.job_id,
                    "recovery_suggestions": error.context.recovery_suggestions,
                }
                for error in report.errors
            ]

            # Include pattern details
            report_dict["patterns"] = [
                {
                    "error_code": pattern.error_code,
                    "category": pattern.category.value,
                    "severity": pattern.severity.value,
                    "count": pattern.count,
                    "first_occurrence": pattern.first_occurrence.isoformat(),
                    "last_occurrence": pattern.last_occurrence.isoformat(),
                    "affected_users": pattern.affected_users,
                    "affected_repositories": pattern.affected_repositories,
                    "recovery_success_rate": pattern.recovery_success_rate,
                }
                for pattern in report.patterns
            ]

        # Add recovery attempts for detailed level and above
        if level in [ReportLevel.DETAILED, ReportLevel.DIAGNOSTIC, ReportLevel.FULL]:
            report_dict["recovery_attempts"] = [
                {
                    "success": attempt.success,
                    "action_taken": attempt.action_taken.value,
                    "outcome": attempt.outcome.value,
                    "recovery_time_seconds": attempt.recovery_time_seconds,
                    "rollback_performed": attempt.rollback_performed,
                    "escalation_reason": attempt.escalation_reason,
                }
                for attempt in report.recovery_attempts
            ]

        # Add diagnostics for diagnostic level and above
        if level in [ReportLevel.DIAGNOSTIC, ReportLevel.FULL]:
            report_dict["diagnostics"] = {
                "system_environment": report.diagnostics.system_environment,
                "configuration_state": report.diagnostics.configuration_state,
                "resource_utilization": report.diagnostics.resource_utilization,
                "network_connectivity": report.diagnostics.network_connectivity,
                "git_repository_state": report.diagnostics.git_repository_state,
                "index_health_metrics": report.diagnostics.index_health_metrics,
            }

        return json.dumps(report_dict, indent=2, default=str)

    def _format_markdown_report(self, report: ErrorReport, level: ReportLevel) -> str:
        """Format report as Markdown."""
        md_parts = []

        # Title and summary
        md_parts.append(f"# Error Report: {report.report_id}")
        md_parts.append(f"**Generated:** {report.timestamp.isoformat()}")
        md_parts.append(f"**Summary:** {report.summary}")
        md_parts.append("")

        # Statistics
        md_parts.append("## Error Statistics")
        md_parts.append(f"- **Total Errors:** {len(report.errors)}")
        md_parts.append(f"- **Error Patterns:** {len(report.patterns)}")
        md_parts.append(f"- **Affected Users:** {len(report.affected_users)}")
        md_parts.append(
            f"- **Affected Repositories:** {len(report.affected_repositories)}"
        )
        md_parts.append("")

        # Top patterns
        if report.patterns:
            md_parts.append("## Top Error Patterns")
            for i, pattern in enumerate(report.patterns[:5], 1):
                md_parts.append(
                    f"{i}. **{pattern.error_code}** ({pattern.category.value}) - "
                    f"{pattern.count} occurrences"
                )
            md_parts.append("")

        # Recommendations
        if report.recommendations:
            md_parts.append("## Recommendations")
            for i, rec in enumerate(report.recommendations, 1):
                md_parts.append(f"{i}. {rec}")
            md_parts.append("")

        return "\n".join(md_parts)

    def _format_text_report(self, report: ErrorReport, level: ReportLevel) -> str:
        """Format report as plain text."""
        lines = []

        # Title and summary
        lines.append(f"ERROR REPORT: {report.report_id}")
        lines.append("=" * 50)
        lines.append(f"Generated: {report.timestamp.isoformat()}")
        lines.append(f"Summary: {report.summary}")
        lines.append("")

        # Statistics
        lines.append("ERROR STATISTICS:")
        lines.append(f"  Total Errors: {len(report.errors)}")
        lines.append(f"  Error Patterns: {len(report.patterns)}")
        lines.append(f"  Affected Users: {len(report.affected_users)}")
        lines.append(f"  Affected Repositories: {len(report.affected_repositories)}")
        lines.append("")

        # Top patterns
        if report.patterns:
            lines.append("TOP ERROR PATTERNS:")
            for i, pattern in enumerate(report.patterns[:5], 1):
                lines.append(
                    f"  {i}. {pattern.error_code} ({pattern.category.value}) - "
                    f"{pattern.count} occurrences"
                )
            lines.append("")

        # Recommendations
        if report.recommendations:
            lines.append("RECOMMENDATIONS:")
            for i, rec in enumerate(report.recommendations, 1):
                lines.append(f"  {i}. {rec}")
            lines.append("")

        return "\n".join(lines)

    def get_user_friendly_error_message(self, error: SyncError) -> str:
        """Generate user-friendly error message with recovery guidance."""
        message_parts = []

        # Main error message
        message_parts.append(f"❌ {error.message}")

        # Add context if available
        if error.context.phase:
            message_parts.append(f"📍 Phase: {error.context.phase}")

        # Add severity indicator
        severity_icons = {
            ErrorSeverity.INFO: "ℹ️",
            ErrorSeverity.WARNING: "⚠️",
            ErrorSeverity.RECOVERABLE: "🔄",
            ErrorSeverity.FATAL: "💥",
            ErrorSeverity.CRITICAL: "🚨",
        }
        severity_icon = severity_icons.get(error.severity, "❓")
        message_parts.append(f"{severity_icon} Severity: {error.severity.value}")

        # Add recovery suggestions
        if error.context.recovery_suggestions:
            message_parts.append("\n🔧 Suggested actions:")
            for i, suggestion in enumerate(error.context.recovery_suggestions, 1):
                message_parts.append(f"   {i}. {suggestion}")

        # Add error ID for reference
        message_parts.append(f"\n🔍 Error ID: {error.context.error_id}")

        return "\n".join(message_parts)
