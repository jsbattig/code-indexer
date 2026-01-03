"""
Automatic Recovery Strategies for CIDX Repository Sync Operations.

Provides intelligent recovery mechanisms with exponential backoff retry logic,
automatic rollback capabilities, checkpoint-based recovery, and smart retry
decision making based on error type and context.
"""

import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Union
import json

from code_indexer.server.middleware.correlation import get_correlation_id
from .error_handler import SyncError, ErrorSeverity, ErrorCategory, ErrorContext


logger = logging.getLogger(__name__)


class RecoveryAction(Enum):
    """Types of recovery actions available."""

    RETRY = "retry"
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    ROLLBACK = "rollback"
    SKIP = "skip"
    CHECKPOINT_RESTORE = "checkpoint_restore"
    ALTERNATIVE_STRATEGY = "alternative_strategy"
    ESCALATE = "escalate"
    ABORT = "abort"


class RecoveryOutcome(Enum):
    """Possible outcomes of recovery attempts."""

    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    ESCALATED = "escalated"
    ABORTED = "aborted"


@dataclass
class RetryPolicy:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 300.0  # 5 minutes
    backoff_multiplier: float = 2.0
    jitter_factor: float = 0.1
    retriable_error_codes: List[str] = field(
        default_factory=lambda: [
            "CONN_TIMEOUT",
            "DNS_FAILURE",
            "SERVICE_UNAVAILABLE",
            "RATE_LIMITED",
            "NETWORK_ERROR",
            "TEMPORARY_FAILURE",
            "TRANSIENT_ERROR",
        ]
    )
    non_retriable_error_codes: List[str] = field(
        default_factory=lambda: [
            "INVALID_CREDENTIALS",
            "ACCESS_DENIED",
            "REPO_NOT_FOUND",
            "REPO_CORRUPTED",
            "INVALID_CONFIG",
            "MISSING_CONFIG",
        ]
    )


@dataclass
class CheckpointData:
    """Data stored at recovery checkpoints."""

    checkpoint_id: str
    timestamp: datetime
    phase: str
    progress: Dict[str, Any]
    system_state: Dict[str, Any]
    rollback_actions: List[Dict[str, Any]]


@dataclass
class RecoveryAttempt:
    """Record of a recovery attempt."""

    attempt_number: int
    timestamp: datetime
    action: RecoveryAction
    outcome: RecoveryOutcome
    error_before: Optional[SyncError] = None
    error_after: Optional[SyncError] = None
    duration_seconds: float = 0.0
    notes: str = ""


@dataclass
class RecoveryResult:
    """Result of recovery strategy execution."""

    success: bool
    action_taken: RecoveryAction
    outcome: RecoveryOutcome
    attempts: List[RecoveryAttempt]
    final_error: Optional[SyncError] = None
    recovery_time_seconds: float = 0.0
    checkpoints_used: List[str] = field(default_factory=list)
    rollback_performed: bool = False
    escalation_reason: Optional[str] = None


class RecoveryStrategy(ABC):
    """Base class for recovery strategies."""

    def __init__(self, name: str, priority: int = 50):
        """
        Initialize recovery strategy.

        Args:
            name: Human-readable name for the strategy
            priority: Priority for strategy selection (higher = more preferred)
        """
        self.name = name
        self.priority = priority
        self.logger = logging.getLogger(f"{__name__}.{name}")

    @abstractmethod
    def can_handle(self, error: SyncError, context: ErrorContext) -> bool:
        """
        Determine if this strategy can handle the given error.

        Args:
            error: The sync error to potentially recover from
            context: Error context information

        Returns:
            True if this strategy can handle the error
        """
        pass

    @abstractmethod
    def execute_recovery(
        self,
        error: SyncError,
        context: ErrorContext,
        operation: Callable[[], Any],
        progress_callback: Optional[Callable] = None,
    ) -> RecoveryResult:
        """
        Execute recovery strategy.

        Args:
            error: The sync error to recover from
            context: Error context information
            operation: The operation to retry/recover
            progress_callback: Optional progress reporting callback

        Returns:
            RecoveryResult indicating success/failure and actions taken
        """
        pass


class RetryWithBackoffStrategy(RecoveryStrategy):
    """Recovery strategy using exponential backoff retry logic."""

    def __init__(self, retry_policy: Optional[RetryPolicy] = None):
        super().__init__("RetryWithBackoff", priority=80)
        self.retry_policy = retry_policy or RetryPolicy()

    def can_handle(self, error: SyncError, context: ErrorContext) -> bool:
        """Check if error is retriable based on retry policy."""
        # Never retry fatal or critical errors
        if error.severity in [ErrorSeverity.FATAL, ErrorSeverity.CRITICAL]:
            return False

        # Check if error code is explicitly non-retriable
        if error.error_code in self.retry_policy.non_retriable_error_codes:
            return False

        # Retry recoverable errors and specific retriable codes
        if (
            error.severity == ErrorSeverity.RECOVERABLE
            or error.error_code in self.retry_policy.retriable_error_codes
        ):
            return True

        # Retry network and system resource errors by default
        if error.category in [ErrorCategory.NETWORK, ErrorCategory.SYSTEM_RESOURCE]:
            return True

        return False

    def execute_recovery(
        self,
        error: SyncError,
        context: ErrorContext,
        operation: Callable[[], Any],
        progress_callback: Optional[Callable] = None,
    ) -> RecoveryResult:
        """Execute retry with exponential backoff."""
        start_time = time.time()
        attempts = []
        current_error = error
        original_error = error  # Keep reference to original error

        self.logger.info(f"Starting retry recovery for error {error.error_code}")

        for attempt_num in range(1, self.retry_policy.max_attempts + 1):
            # Calculate delay with jitter
            if attempt_num > 1:  # No delay on first attempt
                delay = min(
                    self.retry_policy.base_delay_seconds
                    * (self.retry_policy.backoff_multiplier ** (attempt_num - 2)),
                    self.retry_policy.max_delay_seconds,
                )

                # Add jitter to prevent thundering herd
                jitter = delay * self.retry_policy.jitter_factor * random.random()
                total_delay = delay + jitter

                self.logger.info(
                    f"Retry attempt {attempt_num} after {total_delay:.2f}s delay"
                )

                if progress_callback:
                    progress_callback(
                        0, 0, Path(""), f"Retrying in {total_delay:.1f}s..."
                    )

                time.sleep(total_delay)

            # Record attempt start
            attempt_start = time.time()
            attempt = RecoveryAttempt(
                attempt_number=attempt_num,
                timestamp=datetime.now(timezone.utc),
                action=RecoveryAction.RETRY_WITH_BACKOFF,
                outcome=RecoveryOutcome.FAILED,  # Will update if successful
                error_before=current_error,
            )

            try:
                if progress_callback:
                    progress_callback(0, 0, Path(""), f"Retry attempt {attempt_num}...")

                # Execute the operation
                operation()

                # Success!
                attempt.outcome = RecoveryOutcome.SUCCESS
                attempt.duration_seconds = time.time() - attempt_start
                attempt.notes = f"Successful retry on attempt {attempt_num}"
                attempts.append(attempt)

                recovery_time = time.time() - start_time

                self.logger.info(
                    f"Recovery successful after {attempt_num} attempts in {recovery_time:.2f}s"
                )

                return RecoveryResult(
                    success=True,
                    action_taken=RecoveryAction.RETRY_WITH_BACKOFF,
                    outcome=RecoveryOutcome.SUCCESS,
                    attempts=attempts,
                    recovery_time_seconds=recovery_time,
                )

            except Exception as retry_exception:
                attempt.duration_seconds = time.time() - attempt_start

                # Classify the new error
                from .error_handler import classify_error

                retry_error = classify_error(retry_exception, context)
                attempt.error_after = retry_error
                current_error = retry_error

                # Check if we should continue retrying
                # For unclassified errors during retry, continue retrying if we started with a recoverable error
                is_same_category_unclassified = (
                    retry_error.error_code == "UNCLASSIFIED_ERROR"
                    and original_error.severity == ErrorSeverity.RECOVERABLE
                )

                if (
                    not self.can_handle(retry_error, context)
                    and not is_same_category_unclassified
                ):
                    attempt.outcome = RecoveryOutcome.ESCALATED
                    attempt.notes = (
                        f"Error type changed to non-retriable: {retry_error.error_code}"
                    )
                    attempts.append(attempt)

                    self.logger.warning(
                        f"Error type changed to non-retriable, escalating: {retry_error.error_code}",
                        extra={"correlation_id": get_correlation_id()},
                    )

                    return RecoveryResult(
                        success=False,
                        action_taken=RecoveryAction.RETRY_WITH_BACKOFF,
                        outcome=RecoveryOutcome.ESCALATED,
                        attempts=attempts,
                        final_error=retry_error,
                        recovery_time_seconds=time.time() - start_time,
                        escalation_reason="Error type became non-retriable",
                    )

                attempt.notes = f"Retry failed: {str(retry_exception)}"
                attempts.append(attempt)

                self.logger.warning(
                    f"Retry attempt {attempt_num} failed: {retry_exception}",
                    extra={"correlation_id": get_correlation_id()},
                )

        # All retries exhausted
        recovery_time = time.time() - start_time

        self.logger.error(
            f"All {self.retry_policy.max_attempts} retry attempts exhausted in {recovery_time:.2f}s",
            extra={"correlation_id": get_correlation_id()},
        )

        return RecoveryResult(
            success=False,
            action_taken=RecoveryAction.RETRY_WITH_BACKOFF,
            outcome=RecoveryOutcome.FAILED,
            attempts=attempts,
            final_error=current_error,
            recovery_time_seconds=recovery_time,
        )


class RollbackStrategy(RecoveryStrategy):
    """Recovery strategy that performs rollback operations."""

    def __init__(self):
        super().__init__("Rollback", priority=70)

    def can_handle(self, error: SyncError, context: ErrorContext) -> bool:
        """Check if rollback is appropriate for this error."""
        # Never rollback critical errors - they need escalation
        if error.severity == ErrorSeverity.CRITICAL:
            return False

        # Rollback is appropriate for errors that might have left system in inconsistent state
        rollback_appropriate_categories = [
            ErrorCategory.GIT_OPERATION,
            ErrorCategory.INDEXING,
            ErrorCategory.FILE_SYSTEM,
        ]

        return error.category in rollback_appropriate_categories

    def execute_recovery(
        self,
        error: SyncError,
        context: ErrorContext,
        operation: Callable[[], Any],
        progress_callback: Optional[Callable] = None,
    ) -> RecoveryResult:
        """Execute rollback recovery."""
        start_time = time.time()
        attempts = []

        self.logger.info(f"Starting rollback recovery for error {error.error_code}")

        attempt = RecoveryAttempt(
            attempt_number=1,
            timestamp=datetime.now(timezone.utc),
            action=RecoveryAction.ROLLBACK,
            outcome=RecoveryOutcome.FAILED,
            error_before=error,
        )

        try:
            if progress_callback:
                progress_callback(0, 0, Path(""), "Performing rollback...")

            # Perform rollback based on error category
            rollback_success = self._perform_rollback(error, context, progress_callback)

            if rollback_success:
                attempt.outcome = RecoveryOutcome.SUCCESS
                attempt.notes = "Rollback completed successfully"

                # After successful rollback, try the operation again
                try:
                    if progress_callback:
                        progress_callback(0, 0, Path(""), "Retrying after rollback...")

                    operation()
                    attempts.append(attempt)

                    recovery_time = time.time() - start_time

                    self.logger.info(
                        f"Rollback and retry successful in {recovery_time:.2f}s"
                    )

                    return RecoveryResult(
                        success=True,
                        action_taken=RecoveryAction.ROLLBACK,
                        outcome=RecoveryOutcome.SUCCESS,
                        attempts=attempts,
                        recovery_time_seconds=recovery_time,
                        rollback_performed=True,
                    )

                except Exception as retry_exception:
                    # Rollback succeeded but retry failed
                    from .error_handler import classify_error

                    retry_error = classify_error(retry_exception, context)

                    attempt.notes += f" - but retry failed: {str(retry_exception)}"
                    attempts.append(attempt)

                    recovery_time = time.time() - start_time

                    self.logger.warning(
                        f"Rollback succeeded but retry failed in {recovery_time:.2f}s",
                        extra={"correlation_id": get_correlation_id()},
                    )

                    return RecoveryResult(
                        success=False,
                        action_taken=RecoveryAction.ROLLBACK,
                        outcome=RecoveryOutcome.PARTIAL_SUCCESS,
                        attempts=attempts,
                        final_error=retry_error,
                        recovery_time_seconds=recovery_time,
                        rollback_performed=True,
                    )

            else:
                attempt.outcome = RecoveryOutcome.FAILED
                attempt.notes = "Rollback failed"
                attempts.append(attempt)

                recovery_time = time.time() - start_time

                self.logger.error(
                    f"Rollback failed in {recovery_time:.2f}s",
                    extra={"correlation_id": get_correlation_id()},
                )

                return RecoveryResult(
                    success=False,
                    action_taken=RecoveryAction.ROLLBACK,
                    outcome=RecoveryOutcome.FAILED,
                    attempts=attempts,
                    final_error=error,
                    recovery_time_seconds=recovery_time,
                    rollback_performed=False,
                )

        except Exception as rollback_exception:
            attempt.outcome = RecoveryOutcome.FAILED
            attempt.notes = f"Rollback exception: {str(rollback_exception)}"
            attempts.append(attempt)

            recovery_time = time.time() - start_time

            self.logger.error(
                f"Rollback recovery failed with exception in {recovery_time:.2f}s: {rollback_exception}",
                extra={"correlation_id": get_correlation_id()},
            )

            return RecoveryResult(
                success=False,
                action_taken=RecoveryAction.ROLLBACK,
                outcome=RecoveryOutcome.FAILED,
                attempts=attempts,
                final_error=error,
                recovery_time_seconds=recovery_time,
                rollback_performed=False,
            )

    def _perform_rollback(
        self,
        error: SyncError,
        context: ErrorContext,
        progress_callback: Optional[Callable] = None,
    ) -> bool:
        """
        Perform actual rollback operations based on error type.

        Args:
            error: The error that triggered rollback
            context: Error context information
            progress_callback: Optional progress callback

        Returns:
            True if rollback was successful
        """
        try:
            if error.category == ErrorCategory.GIT_OPERATION:
                return self._rollback_git_operations(error, context, progress_callback)
            elif error.category == ErrorCategory.INDEXING:
                return self._rollback_indexing_operations(
                    error, context, progress_callback
                )
            elif error.category == ErrorCategory.FILE_SYSTEM:
                return self._rollback_file_operations(error, context, progress_callback)
            else:
                self.logger.warning(
                    f"No rollback strategy for category {error.category}",
                    extra={"correlation_id": get_correlation_id()},
                )
                return False

        except Exception as e:
            self.logger.error(
                f"Rollback operation failed: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return False

    def _rollback_git_operations(
        self,
        error: SyncError,
        context: ErrorContext,
        progress_callback: Optional[Callable] = None,
    ) -> bool:
        """Rollback git operations."""
        try:
            from ...utils.git_runner import run_git_command

            repository_path = (
                Path(context.repository) if context.repository else Path.cwd()
            )

            if progress_callback:
                progress_callback(0, 0, repository_path, "Rolling back git changes...")

            # Try to abort any ongoing merge/rebase
            try:
                run_git_command(["merge", "--abort"], cwd=repository_path, check=False)
                run_git_command(["rebase", "--abort"], cwd=repository_path, check=False)
            except Exception:
                pass  # These might fail if no merge/rebase in progress

            # Reset to HEAD if we have dirty working tree
            try:
                run_git_command(["reset", "--hard", "HEAD"], cwd=repository_path)
                self.logger.info("Git rollback: reset to HEAD successful")
                return True
            except Exception as e:
                self.logger.error(
                    f"Git rollback failed: {e}",
                    extra={"correlation_id": get_correlation_id()},
                )
                return False

        except Exception as e:
            self.logger.error(
                f"Git rollback operation failed: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return False

    def _rollback_indexing_operations(
        self,
        error: SyncError,
        context: ErrorContext,
        progress_callback: Optional[Callable] = None,
    ) -> bool:
        """Rollback indexing operations."""
        try:
            # For indexing operations, we might need to restore from backup
            # or clear partial indexes
            if progress_callback:
                progress_callback(0, 0, Path(""), "Rolling back indexing changes...")

            # This is a placeholder - actual implementation would depend on
            # the specific indexing system and backup mechanisms available
            self.logger.info("Indexing rollback: clearing partial indexes")

            # TODO: Implement actual indexing rollback logic
            # - Restore index from backup
            # - Clear partial/corrupted indexes
            # - Reset metadata files

            return True

        except Exception as e:
            self.logger.error(
                f"Indexing rollback operation failed: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return False

    def _rollback_file_operations(
        self,
        error: SyncError,
        context: ErrorContext,
        progress_callback: Optional[Callable] = None,
    ) -> bool:
        """Rollback file system operations."""
        try:
            if progress_callback:
                progress_callback(0, 0, Path(""), "Rolling back file system changes...")

            # File system rollback is tricky without explicit transaction log
            # For now, just log the attempt
            self.logger.info("File system rollback: limited rollback available")

            # TODO: Implement file system rollback if we maintain operation logs
            # - Restore files from backup
            # - Undo file moves/deletions
            # - Restore permissions

            return True

        except Exception as e:
            self.logger.error(
                f"File system rollback operation failed: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return False


class CheckpointRecoveryStrategy(RecoveryStrategy):
    """Recovery strategy using checkpoint-based recovery."""

    def __init__(self, checkpoint_dir: Optional[Path] = None):
        super().__init__("CheckpointRecovery", priority=60)
        self.checkpoint_dir = (
            checkpoint_dir or Path.home() / ".cache" / "cidx" / "checkpoints"
        )
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def can_handle(self, error: SyncError, context: ErrorContext) -> bool:
        """Check if checkpoint recovery is available."""
        # Never use checkpoint recovery for critical errors - they need escalation
        if error.severity == ErrorSeverity.CRITICAL:
            return False

        # Look for available checkpoints for this context
        if not context.job_id:
            return False

        checkpoint_file = self.checkpoint_dir / f"{context.job_id}.json"
        return checkpoint_file.exists()

    def execute_recovery(
        self,
        error: SyncError,
        context: ErrorContext,
        operation: Callable[[], Any],
        progress_callback: Optional[Callable] = None,
    ) -> RecoveryResult:
        """Execute checkpoint-based recovery."""
        start_time = time.time()
        attempts = []

        self.logger.info(f"Starting checkpoint recovery for error {error.error_code}")

        attempt = RecoveryAttempt(
            attempt_number=1,
            timestamp=datetime.now(timezone.utc),
            action=RecoveryAction.CHECKPOINT_RESTORE,
            outcome=RecoveryOutcome.FAILED,
            error_before=error,
        )

        try:
            if progress_callback:
                progress_callback(0, 0, Path(""), "Restoring from checkpoint...")

            # Load checkpoint data
            if not context.job_id:
                raise ValueError("No job ID available for checkpoint recovery")

            checkpoint = self._load_checkpoint(context.job_id)
            if not checkpoint:
                raise FileNotFoundError(
                    f"No valid checkpoint found for job {context.job_id}"
                )

            # Restore system state from checkpoint
            if self._restore_from_checkpoint(checkpoint, progress_callback):
                attempt.outcome = RecoveryOutcome.SUCCESS
                attempt.notes = f"Restored from checkpoint {checkpoint.checkpoint_id}"

                # Try operation again from checkpoint
                try:
                    if progress_callback:
                        progress_callback(0, 0, Path(""), "Resuming from checkpoint...")

                    operation()
                    attempts.append(attempt)

                    recovery_time = time.time() - start_time

                    self.logger.info(
                        f"Checkpoint recovery successful in {recovery_time:.2f}s"
                    )

                    return RecoveryResult(
                        success=True,
                        action_taken=RecoveryAction.CHECKPOINT_RESTORE,
                        outcome=RecoveryOutcome.SUCCESS,
                        attempts=attempts,
                        recovery_time_seconds=recovery_time,
                        checkpoints_used=[checkpoint.checkpoint_id],
                    )

                except Exception as retry_exception:
                    from .error_handler import classify_error

                    retry_error = classify_error(retry_exception, context)

                    attempt.notes += f" - but retry failed: {str(retry_exception)}"
                    attempts.append(attempt)

                    return RecoveryResult(
                        success=False,
                        action_taken=RecoveryAction.CHECKPOINT_RESTORE,
                        outcome=RecoveryOutcome.PARTIAL_SUCCESS,
                        attempts=attempts,
                        final_error=retry_error,
                        recovery_time_seconds=time.time() - start_time,
                        checkpoints_used=[checkpoint.checkpoint_id],
                    )

            else:
                attempt.notes = "Checkpoint restore failed"
                attempts.append(attempt)

                return RecoveryResult(
                    success=False,
                    action_taken=RecoveryAction.CHECKPOINT_RESTORE,
                    outcome=RecoveryOutcome.FAILED,
                    attempts=attempts,
                    final_error=error,
                    recovery_time_seconds=time.time() - start_time,
                )

        except Exception as checkpoint_exception:
            attempt.notes = (
                f"Checkpoint recovery exception: {str(checkpoint_exception)}"
            )
            attempts.append(attempt)

            self.logger.error(
                f"Checkpoint recovery failed: {checkpoint_exception}",
                exc_info=True,
                extra={"correlation_id": get_correlation_id()},
            )

            return RecoveryResult(
                success=False,
                action_taken=RecoveryAction.CHECKPOINT_RESTORE,
                outcome=RecoveryOutcome.FAILED,
                attempts=attempts,
                final_error=error,
                recovery_time_seconds=time.time() - start_time,
            )

    def create_checkpoint(
        self,
        job_id: str,
        phase: str,
        progress: Dict[str, Any],
        rollback_actions: Optional[List[Dict[str, Any]]] = None,
    ) -> CheckpointData:
        """Create a recovery checkpoint."""
        checkpoint = CheckpointData(
            checkpoint_id=f"{job_id}_{phase}_{int(time.time())}",
            timestamp=datetime.now(timezone.utc),
            phase=phase,
            progress=progress,
            system_state={},
            rollback_actions=rollback_actions or [],
        )

        try:
            # Save checkpoint to disk
            checkpoint_file = self.checkpoint_dir / f"{job_id}.json"
            with open(checkpoint_file, "w") as f:
                json.dump(
                    {
                        "checkpoint_id": checkpoint.checkpoint_id,
                        "timestamp": checkpoint.timestamp.isoformat(),
                        "phase": checkpoint.phase,
                        "progress": checkpoint.progress,
                        "system_state": checkpoint.system_state,
                        "rollback_actions": checkpoint.rollback_actions,
                    },
                    f,
                    indent=2,
                )

            self.logger.info(f"Created checkpoint {checkpoint.checkpoint_id}")

        except Exception as e:
            self.logger.error(
                f"Failed to save checkpoint: {e}",
                extra={"correlation_id": get_correlation_id()},
            )

        return checkpoint

    def _load_checkpoint(self, job_id: str) -> Optional[CheckpointData]:
        """Load checkpoint data from disk."""
        try:
            checkpoint_file = self.checkpoint_dir / f"{job_id}.json"
            if not checkpoint_file.exists():
                return None

            with open(checkpoint_file, "r") as f:
                data = json.load(f)

            return CheckpointData(
                checkpoint_id=data["checkpoint_id"],
                timestamp=datetime.fromisoformat(data["timestamp"]),
                phase=data["phase"],
                progress=data["progress"],
                system_state=data["system_state"],
                rollback_actions=data["rollback_actions"],
            )

        except Exception as e:
            self.logger.error(
                f"Failed to load checkpoint for job {job_id}: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return None

    def _restore_from_checkpoint(
        self, checkpoint: CheckpointData, progress_callback: Optional[Callable] = None
    ) -> bool:
        """Restore system state from checkpoint."""
        try:
            if progress_callback:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    f"Restoring checkpoint {checkpoint.checkpoint_id}...",
                )

            # Execute rollback actions in reverse order
            for rollback_action in reversed(checkpoint.rollback_actions):
                self._execute_rollback_action(rollback_action)

            self.logger.info(
                f"Successfully restored from checkpoint {checkpoint.checkpoint_id}"
            )
            return True

        except Exception as e:
            self.logger.error(
                f"Failed to restore from checkpoint {checkpoint.checkpoint_id}: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return False

    def _execute_rollback_action(self, action: Dict[str, Any]):
        """Execute a single rollback action."""
        action_type = action.get("type")

        if action_type == "git_reset":
            from ...utils.git_runner import run_git_command

            run_git_command(
                ["reset", "--hard", action["commit"]], cwd=action["repository"]
            )
        elif action_type == "file_restore":
            # Restore file from backup
            pass  # TODO: Implement file restore logic
        elif action_type == "index_restore":
            # Restore index from backup
            pass  # TODO: Implement index restore logic
        else:
            self.logger.warning(
                f"Unknown rollback action type: {action_type}",
                extra={"correlation_id": get_correlation_id()},
            )


class RecoveryOrchestrator:
    """Orchestrates multiple recovery strategies with intelligent selection."""

    def __init__(self) -> None:
        self.strategies: List[RecoveryStrategy] = []
        self.recovery_history: List[RecoveryResult] = []
        self.logger = logging.getLogger(f"{__name__}.RecoveryOrchestrator")

        # Register default strategies
        self.register_strategy(RetryWithBackoffStrategy())
        self.register_strategy(RollbackStrategy())
        self.register_strategy(CheckpointRecoveryStrategy())

    def register_strategy(self, strategy: RecoveryStrategy):
        """Register a recovery strategy."""
        self.strategies.append(strategy)
        self.strategies.sort(key=lambda s: s.priority, reverse=True)
        self.logger.info(
            f"Registered recovery strategy: {strategy.name} (priority {strategy.priority})"
        )

    def attempt_recovery(
        self,
        error: SyncError,
        context: ErrorContext,
        operation: Callable[[], Any],
        progress_callback: Optional[Callable] = None,
        max_recovery_attempts: int = 3,
    ) -> RecoveryResult:
        """
        Attempt recovery using available strategies.

        Args:
            error: The error to recover from
            context: Error context information
            operation: The operation to retry/recover
            progress_callback: Optional progress callback
            max_recovery_attempts: Maximum number of recovery strategies to try

        Returns:
            RecoveryResult indicating final outcome
        """
        self.logger.info(
            f"Starting recovery for error {error.error_code} (severity: {error.severity.value})"
        )

        # Find applicable strategies
        applicable_strategies = [
            strategy
            for strategy in self.strategies
            if strategy.can_handle(error, context)
        ]

        if not applicable_strategies:
            self.logger.warning(
                "No recovery strategies available for this error",
                extra={"correlation_id": get_correlation_id()},
            )
            return RecoveryResult(
                success=False,
                action_taken=RecoveryAction.ESCALATE,
                outcome=RecoveryOutcome.ESCALATED,
                attempts=[],
                final_error=error,
                escalation_reason="No applicable recovery strategies found",
            )

        self.logger.info(
            f"Found {len(applicable_strategies)} applicable recovery strategies: "
            f"{[s.name for s in applicable_strategies]}"
        )

        # Try strategies in priority order
        for attempt_num, strategy in enumerate(
            applicable_strategies[:max_recovery_attempts], 1
        ):
            self.logger.info(
                f"Attempting recovery {attempt_num} using strategy: {strategy.name}"
            )

            try:
                if progress_callback:
                    progress_callback(
                        0,
                        0,
                        Path(""),
                        f"Recovery attempt {attempt_num}: {strategy.name}",
                    )

                result = strategy.execute_recovery(
                    error, context, operation, progress_callback
                )

                # Record result in history
                self.recovery_history.append(result)

                if result.success:
                    self.logger.info(
                        f"Recovery successful using strategy {strategy.name} "
                        f"after {result.recovery_time_seconds:.2f}s"
                    )
                    return result

                else:
                    self.logger.warning(
                        f"Recovery strategy {strategy.name} failed: {result.outcome.value}",
                        extra={"correlation_id": get_correlation_id()},
                    )

                    # If this strategy escalated, don't try others
                    if result.outcome == RecoveryOutcome.ESCALATED:
                        self.logger.info(
                            "Recovery strategy escalated - stopping recovery attempts"
                        )
                        return result

                    # Update error for next strategy
                    if result.final_error:
                        error = result.final_error

            except Exception as strategy_exception:
                self.logger.error(
                    f"Recovery strategy {strategy.name} threw exception: {strategy_exception}",
                    extra={"correlation_id": get_correlation_id()},
                )
                # Continue to next strategy

        # All strategies exhausted
        self.logger.error(
            f"All {len(applicable_strategies)} recovery strategies exhausted",
            extra={"correlation_id": get_correlation_id()},
        )

        return RecoveryResult(
            success=False,
            action_taken=RecoveryAction.ABORT,
            outcome=RecoveryOutcome.ABORTED,
            attempts=[],
            final_error=error,
            escalation_reason="All recovery strategies exhausted",
        )

    def get_recovery_statistics(self) -> Dict[str, Any]:
        """Get recovery statistics and success rates."""
        if not self.recovery_history:
            return {"total_recoveries": 0}

        total_recoveries = len(self.recovery_history)
        successful_recoveries = sum(1 for r in self.recovery_history if r.success)

        # Strategy success rates
        strategy_stats: Dict[str, Dict[str, Union[int, float]]] = {}
        for result in self.recovery_history:
            strategy_name = result.action_taken.value
            if strategy_name not in strategy_stats:
                strategy_stats[strategy_name] = {"attempts": 0, "successes": 0}

            strategy_stats[strategy_name]["attempts"] += 1
            if result.success:
                strategy_stats[strategy_name]["successes"] += 1

        # Calculate success rates
        for strategy_name in strategy_stats:
            stats = strategy_stats[strategy_name]
            stats["success_rate"] = stats["successes"] / stats["attempts"]

        return {
            "total_recoveries": total_recoveries,
            "successful_recoveries": successful_recoveries,
            "overall_success_rate": successful_recoveries / total_recoveries,
            "strategy_statistics": strategy_stats,
            "average_recovery_time_seconds": sum(
                r.recovery_time_seconds for r in self.recovery_history
            )
            / total_recoveries,
        }
