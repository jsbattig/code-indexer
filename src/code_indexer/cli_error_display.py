"""
CLI Error Display Enhancement for CIDX Repository Sync Operations.

Provides user-friendly error messages, recovery guidance, and comprehensive
error reporting for CLI sync operations with rich console formatting and
actionable next steps.
"""

import logging
from typing import Optional, Dict, Any, List
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
import sys

# Import comprehensive error handling system
try:
    from .server.sync.error_handler import (
        SyncError,
        ErrorSeverity,
        ErrorCategory,
        classify_error,
    )
    from .server.sync.error_reporter import ErrorReporter
    from .server.sync.recovery_strategies import RecoveryResult, RecoveryOutcome

    COMPREHENSIVE_ERROR_HANDLING_AVAILABLE = True
except ImportError:
    COMPREHENSIVE_ERROR_HANDLING_AVAILABLE = False

logger = logging.getLogger(__name__)


class CLIErrorDisplay:
    """Enhanced CLI error display with user-friendly messaging and recovery guidance."""

    def __init__(self, console: Optional[Console] = None):
        """Initialize CLI error display."""
        self.console = console or Console()
        self.error_reporter = (
            ErrorReporter() if COMPREHENSIVE_ERROR_HANDLING_AVAILABLE else None
        )

    def display_sync_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        recovery_attempts: Optional[List[RecoveryResult]] = None,
        show_technical_details: bool = False,
    ):
        """
        Display comprehensive sync error with user-friendly messaging.

        Args:
            error: The exception that occurred
            context: Additional context information
            recovery_attempts: List of recovery attempts made
            show_technical_details: Whether to show technical error details
        """
        # Classify error if comprehensive handling is available
        if COMPREHENSIVE_ERROR_HANDLING_AVAILABLE:
            sync_error = classify_error(error)
            self._display_comprehensive_error(
                sync_error, context, recovery_attempts, show_technical_details
            )
        else:
            self._display_legacy_error(error, context, show_technical_details)

    def _display_comprehensive_error(
        self,
        sync_error: SyncError,
        context: Optional[Dict[str, Any]],
        recovery_attempts: Optional[List[RecoveryResult]],
        show_technical_details: bool,
    ):
        """Display error using comprehensive error handling system."""
        # Main error message with severity-based styling
        severity_styles = {
            ErrorSeverity.INFO: "blue",
            ErrorSeverity.WARNING: "yellow",
            ErrorSeverity.RECOVERABLE: "orange3",
            ErrorSeverity.FATAL: "red",
            ErrorSeverity.CRITICAL: "red bold",
        }

        severity_icons = {
            ErrorSeverity.INFO: "ℹ️",
            ErrorSeverity.WARNING: "⚠️",
            ErrorSeverity.RECOVERABLE: "🔄",
            ErrorSeverity.FATAL: "💥",
            ErrorSeverity.CRITICAL: "🚨",
        }

        style = severity_styles.get(sync_error.severity, "red")
        icon = severity_icons.get(sync_error.severity, "❌")

        # Create main error panel
        error_text = Text()
        error_text.append(f"{icon} ", style=style)
        error_text.append(sync_error.message, style=f"{style} bold")

        # Add error code and category
        error_details = Text()
        error_details.append(f"Error Code: {sync_error.error_code}", style="dim")
        error_details.append(f" | Category: {sync_error.category.value}", style="dim")
        if sync_error.context.phase:
            error_details.append(f" | Phase: {sync_error.context.phase}", style="dim")

        panel_content = [error_text, "", error_details]

        # Add recovery information if available
        if recovery_attempts:
            panel_content.extend(["", self._format_recovery_summary(recovery_attempts)])

        error_panel = Panel(
            "\n".join(str(item) for item in panel_content),
            title="🚨 Sync Operation Error",
            title_align="left",
            border_style=style,
            width=80,
        )

        self.console.print()
        self.console.print(error_panel)

        # Display recovery suggestions
        if sync_error.context.recovery_suggestions:
            self._display_recovery_suggestions(sync_error.context.recovery_suggestions)

        # Display technical details if requested
        if show_technical_details:
            self._display_technical_details(sync_error, context, recovery_attempts)

        # Display user-friendly next steps
        self._display_next_steps(sync_error, recovery_attempts)

    def _display_legacy_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]],
        show_technical_details: bool,
    ):
        """Display error using legacy error handling."""
        error_text = Text()
        error_text.append("❌ ", style="red")
        error_text.append(str(error), style="red bold")

        error_panel = Panel(
            error_text,
            title="🚨 Sync Operation Error",
            title_align="left",
            border_style="red",
            width=80,
        )

        self.console.print()
        self.console.print(error_panel)

        # Basic troubleshooting suggestions
        self._display_basic_troubleshooting()

        if show_technical_details:
            import traceback

            self.console.print()
            self.console.print("Technical Details:", style="dim")
            self.console.print(traceback.format_exc(), style="dim red")

    def _format_recovery_summary(self, recovery_attempts: List[RecoveryResult]) -> Text:
        """Format recovery attempt summary."""
        if not recovery_attempts:
            return Text("No recovery attempts made", style="dim")

        summary = Text()
        successful_recoveries = sum(
            1 for attempt in recovery_attempts if attempt.success
        )
        total_attempts = len(recovery_attempts)

        if successful_recoveries > 0:
            summary.append("✅ ", style="green")
            summary.append(
                f"Recovery successful ({successful_recoveries}/{total_attempts} attempts)",
                style="green",
            )
        else:
            summary.append("❌ ", style="red")
            summary.append(f"Recovery failed ({total_attempts} attempts)", style="red")

        return summary

    def _display_recovery_suggestions(self, suggestions: List[str]):
        """Display recovery suggestions in a formatted manner."""
        if not suggestions:
            return

        self.console.print()
        suggestions_text = Text("🔧 Suggested Actions:", style="cyan bold")
        self.console.print(suggestions_text)

        for i, suggestion in enumerate(suggestions, 1):
            suggestion_text = Text()
            suggestion_text.append(f"   {i}. ", style="cyan")
            suggestion_text.append(suggestion, style="white")
            self.console.print(suggestion_text)

    def _display_technical_details(
        self,
        sync_error: SyncError,
        context: Optional[Dict[str, Any]],
        recovery_attempts: Optional[List[RecoveryResult]],
    ):
        """Display technical error details."""
        self.console.print()
        self.console.print("🔍 Technical Details:", style="dim bold")

        # Error details table
        details_table = Table(show_header=False, box=None, pad_edge=False)
        details_table.add_column("Field", style="dim", width=20)
        details_table.add_column("Value", style="white")

        details_table.add_row("Error ID", sync_error.context.error_id)
        details_table.add_row("Timestamp", sync_error.context.timestamp.isoformat())
        details_table.add_row("Severity", sync_error.severity.value)
        details_table.add_row("Category", sync_error.category.value)

        if sync_error.context.repository:
            details_table.add_row("Repository", sync_error.context.repository)
        if sync_error.context.job_id:
            details_table.add_row("Job ID", sync_error.context.job_id)
        if sync_error.cause:
            details_table.add_row("Root Cause", str(sync_error.cause))

        self.console.print(details_table)

        # Recovery attempts details
        if recovery_attempts:
            self.console.print()
            self.console.print("🔄 Recovery Attempts:", style="dim bold")

            for i, attempt in enumerate(recovery_attempts, 1):
                recovery_text = Text()
                recovery_text.append(f"   {i}. ", style="dim")
                recovery_text.append(f"{attempt.action_taken.value}", style="cyan")

                outcome_styles = {
                    RecoveryOutcome.SUCCESS: "green",
                    RecoveryOutcome.PARTIAL_SUCCESS: "yellow",
                    RecoveryOutcome.FAILED: "red",
                    RecoveryOutcome.ESCALATED: "orange3",
                    RecoveryOutcome.ABORTED: "red",
                }

                outcome_style = outcome_styles.get(attempt.outcome, "white")
                recovery_text.append(f" → {attempt.outcome.value}", style=outcome_style)
                recovery_text.append(
                    f" ({attempt.recovery_time_seconds:.2f}s)", style="dim"
                )

                self.console.print(recovery_text)

        # System information
        if sync_error.context.system_info:
            self.console.print()
            self.console.print("💻 System Information:", style="dim bold")

            for key, value in list(sync_error.context.system_info.items())[
                :5
            ]:  # Limit to first 5
                info_text = Text()
                info_text.append(f"   {key}: ", style="dim")
                info_text.append(str(value), style="white")
                self.console.print(info_text)

    def _display_next_steps(
        self, sync_error: SyncError, recovery_attempts: Optional[List[RecoveryResult]]
    ):
        """Display user-friendly next steps based on error type."""
        self.console.print()
        self.console.print("📋 Next Steps:", style="blue bold")

        next_steps = self._generate_next_steps(sync_error, recovery_attempts)

        for i, step in enumerate(next_steps, 1):
            step_text = Text()
            step_text.append(f"   {i}. ", style="blue")
            step_text.append(step, style="white")
            self.console.print(step_text)

    def _generate_next_steps(
        self, sync_error: SyncError, recovery_attempts: Optional[List[RecoveryResult]]
    ) -> List[str]:
        """Generate context-specific next steps."""
        steps = []

        # Recovery-based steps
        if recovery_attempts and any(attempt.success for attempt in recovery_attempts):
            steps.append(
                "The operation was automatically recovered - you may retry the sync"
            )
        elif recovery_attempts:
            steps.append("Automatic recovery failed - manual intervention required")

        # Category-specific steps
        if sync_error.category == ErrorCategory.NETWORK:
            steps.extend(
                [
                    "Check your internet connection and network settings",
                    "Verify the server URL is accessible: ping or curl test",
                    "Try again in a few moments (temporary network issues)",
                    "If problem persists, contact your network administrator",
                ]
            )

        elif sync_error.category == ErrorCategory.AUTHENTICATION:
            steps.extend(
                [
                    "Verify your credentials are correct and not expired",
                    "Run 'cidx auth update' to refresh your credentials",
                    "Check if two-factor authentication is required",
                    "Contact your repository administrator for access issues",
                ]
            )

        elif sync_error.category == ErrorCategory.GIT_OPERATION:
            steps.extend(
                [
                    "Check if you have uncommitted changes: git status",
                    "Resolve any merge conflicts manually if present",
                    "Ensure you have proper git access to the repository",
                    "Try running 'git pull' manually to identify issues",
                ]
            )

        elif sync_error.category == ErrorCategory.INDEXING:
            steps.extend(
                [
                    "Check if the indexing service is running and healthy",
                    "Verify API credentials for embedding providers",
                    "Ensure sufficient disk space and memory are available",
                    "Try with '--full-reindex' flag to rebuild the index",
                ]
            )

        elif sync_error.category == ErrorCategory.SYSTEM_RESOURCE:
            steps.extend(
                [
                    "Check available system resources (CPU, memory, disk)",
                    "Close other resource-intensive applications",
                    "Try running the sync during off-peak hours",
                    "Consider upgrading system resources if consistently failing",
                ]
            )

        elif sync_error.category == ErrorCategory.CONFIGURATION:
            steps.extend(
                [
                    "Review your configuration file for errors",
                    "Run 'cidx init' to recreate configuration if corrupted",
                    "Check file permissions on configuration directories",
                    "Restore configuration from backup if available",
                ]
            )

        # Severity-specific steps
        if sync_error.severity == ErrorSeverity.CRITICAL:
            steps.insert(
                0, "🚨 This is a critical error - immediate attention required"
            )
            steps.append(
                "Contact support immediately with error ID: "
                + sync_error.context.error_id
            )

        elif sync_error.severity == ErrorSeverity.FATAL:
            steps.insert(0, "💥 This error requires manual resolution before retrying")

        # Generic fallback steps
        if not steps or len(steps) < 2:
            steps.extend(
                [
                    "Try running the command again with --verbose for more details",
                    "Check the system logs for additional error information",
                    "Review the documentation for this operation",
                    "Contact support if the problem persists",
                ]
            )

        # Add error reporting step
        steps.append(
            f"Report persistent issues with error ID: {sync_error.context.error_id}"
        )

        return steps[:6]  # Limit to 6 steps for readability

    def _display_basic_troubleshooting(self):
        """Display basic troubleshooting suggestions for legacy error handling."""
        self.console.print()
        self.console.print("🔧 Troubleshooting:", style="cyan bold")

        basic_steps = [
            "Check your internet connection and server accessibility",
            "Verify your credentials are correct and not expired",
            "Ensure you have proper permissions for the repository",
            "Try running the command with --verbose for more details",
            "Review the configuration and fix any errors",
            "Contact support if the problem persists",
        ]

        for i, step in enumerate(basic_steps, 1):
            step_text = Text()
            step_text.append(f"   {i}. ", style="cyan")
            step_text.append(step, style="white")
            self.console.print(step_text)

    def display_error_statistics(self, stats: Dict[str, Any]):
        """Display error statistics in a formatted table."""
        if not stats or stats.get("total_errors", 0) == 0:
            self.console.print("📊 No recent errors to display", style="green")
            return

        self.console.print()
        self.console.print("📊 Error Statistics:", style="blue bold")

        # Summary statistics
        summary_table = Table(show_header=False, box=None, pad_edge=False)
        summary_table.add_column("Metric", style="cyan", width=25)
        summary_table.add_column("Value", style="white")

        summary_table.add_row("Total Errors", str(stats.get("total_errors", 0)))
        summary_table.add_row(
            "Unique Error Types", str(stats.get("unique_error_codes", 0))
        )

        recovery_stats = stats.get("recovery_statistics", {})
        if recovery_stats.get("total_attempts", 0) > 0:
            success_rate = recovery_stats.get("success_rate", 0) * 100
            summary_table.add_row("Recovery Success Rate", f"{success_rate:.1f}%")

        self.console.print(summary_table)

        # Most common errors
        most_common = stats.get("most_common_errors", {})
        if most_common:
            self.console.print()
            self.console.print("Most Common Errors:", style="dim bold")

            for error_code, count in list(most_common.items())[:5]:
                error_text = Text()
                error_text.append(f"   • {error_code}: ", style="dim")
                error_text.append(f"{count} occurrences", style="white")
                self.console.print(error_text)

    def display_error_report_summary(self, report_data: Dict[str, Any]):
        """Display error report summary."""
        if not report_data:
            return

        self.console.print()
        self.console.print("📋 Error Report Summary:", style="blue bold")

        summary_text = report_data.get("summary", "No summary available")
        self.console.print(f"   {summary_text}", style="white")

        # Recommendations
        recommendations = report_data.get("recommendations", [])
        if recommendations:
            self.console.print()
            self.console.print("💡 Recommendations:", style="yellow bold")

            for i, rec in enumerate(recommendations[:3], 1):  # Limit to top 3
                rec_text = Text()
                rec_text.append(f"   {i}. ", style="yellow")
                rec_text.append(rec, style="white")
                self.console.print(rec_text)

    def suggest_command_alternatives(
        self, failed_command: str, error_category: ErrorCategory
    ):
        """Suggest alternative commands based on the error category."""
        self.console.print()
        self.console.print("💡 Alternative Commands:", style="yellow bold")

        alternatives = []

        if error_category == ErrorCategory.NETWORK:
            alternatives = [
                "cidx sync --timeout 600  # Try with longer timeout",
                "cidx sync --dry-run      # Preview sync without execution",
                "cidx status              # Check current sync status",
            ]

        elif error_category == ErrorCategory.AUTHENTICATION:
            alternatives = [
                "cidx auth update         # Update credentials",
                "cidx status              # Check authentication status",
                "cidx init --remote       # Reconfigure remote settings",
            ]

        elif error_category == ErrorCategory.GIT_OPERATION:
            alternatives = [
                "cidx sync --no-pull     # Sync without git operations",
                "git status               # Check git repository status",
                "git pull                 # Manual git pull to identify issues",
            ]

        elif error_category == ErrorCategory.INDEXING:
            alternatives = [
                "cidx sync --full-reindex # Force complete re-indexing",
                "cidx sync --no-pull     # Index existing files only",
                "cidx status              # Check indexing service status",
            ]

        for alt in alternatives:
            alt_text = Text()
            alt_text.append("   ", style="yellow")
            alt_text.append(alt, style="white")
            self.console.print(alt_text)


def enhance_cli_error_handling(func):
    """Decorator to enhance CLI functions with comprehensive error handling."""

    def wrapper(*args, **kwargs):
        console = Console()
        error_display = CLIErrorDisplay(console)

        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Get context from CLI arguments if available
            ctx = kwargs.get("ctx") or (args[0] if args else None)
            show_verbose = ctx and hasattr(ctx, "obj") and ctx.obj.get("verbose", False)

            error_display.display_sync_error(
                error=e, show_technical_details=show_verbose
            )

            sys.exit(1)

    return wrapper
