"""
Auto-Recovery Engine for CIDX Server - Story 9 Implementation.

Automated recovery system that triggers appropriate actions based on
validation failures. Following CLAUDE.md Foundation #1: Real recovery
with actual indexing operations, not mocked actions.
"""

from code_indexer.server.middleware.correlation import get_correlation_id

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Dict

from .models import (
    ValidationResult,
    RecoveryAction,
    RecoveryResult,
    RecoveryType,
    RecoveryPriority,
)
from .exceptions import RecoveryFailedError
from ...config import Config

logger = logging.getLogger(__name__)


class AutoRecoveryEngine:
    """
    Automated recovery engine for index validation failures.

    Analyzes validation results and executes appropriate recovery actions
    including incremental indexing, full re-indexing, and optimization.
    """

    def __init__(self, config: Config):
        """
        Initialize AutoRecoveryEngine.

        Args:
            config: CIDX configuration for recovery operations
        """
        self.config = config

        # Recovery configuration - check for nested auto_recovery config first
        auto_recovery_config = getattr(config, "auto_recovery", None)
        if auto_recovery_config is not None:
            # Use the structured configuration
            self.max_recovery_attempts = auto_recovery_config.max_recovery_attempts
            self.recovery_timeout_minutes = (
                auto_recovery_config.recovery_timeout_minutes
            )
            self.backup_before_full_recovery = (
                auto_recovery_config.backup_before_full_recovery
            )
            self.allow_automatic_full_recovery = (
                auto_recovery_config.allow_automatic_full_recovery
            )
            self.enabled = auto_recovery_config.enabled
        else:
            # Fallback to flat configuration attributes
            self.max_recovery_attempts = getattr(
                config, "auto_recovery_max_attempts", 3
            )
            self.recovery_timeout_minutes = getattr(
                config, "auto_recovery_timeout_minutes", 60
            )
            self.backup_before_full_recovery = getattr(
                config, "auto_recovery_backup_enabled", True
            )
            self.allow_automatic_full_recovery = getattr(
                config, "auto_recovery_allow_full", True
            )
            self.enabled = getattr(config, "auto_recovery_enabled", True)

        # Recovery thresholds
        self.critical_health_threshold = 0.3
        self.poor_health_threshold = 0.6
        self.performance_threshold = 0.7

        # Recovery tracking
        self.recovery_attempts: Dict[str, int] = {}
        self.last_recovery_time: Optional[datetime] = None

        logger.info(f"AutoRecoveryEngine initialized (enabled: {self.enabled})", extra={"correlation_id": get_correlation_id()})

    def decide_recovery_action(
        self, validation_result: ValidationResult
    ) -> RecoveryAction:
        """
        Decide what recovery action should be taken based on validation results.

        Args:
            validation_result: ValidationResult to analyze

        Returns:
            RecoveryAction describing the recommended recovery
        """
        try:
            if not self.enabled:
                return RecoveryAction(
                    recovery_type=RecoveryType.NONE.value,
                    is_required=False,
                    priority=RecoveryPriority.LOW.value,
                    description="Auto-recovery is disabled",
                    estimated_duration_minutes=0,
                )

            # If validation passed with good health, no recovery needed
            if (
                validation_result.is_valid
                and validation_result.overall_health_score >= 0.8
            ):
                return RecoveryAction(
                    recovery_type=RecoveryType.NONE.value,
                    is_required=False,
                    priority=RecoveryPriority.LOW.value,
                    description="Index is healthy - no recovery needed",
                    estimated_duration_minutes=0,
                )

            # Analyze errors for decision making
            critical_errors = [
                e for e in validation_result.validation_errors if e.is_critical
            ]
            error_types = set(
                error.error_type for error in validation_result.validation_errors
            )

            health_score = validation_result.overall_health_score

            # Critical issues require full recovery
            if (
                health_score < self.critical_health_threshold
                or len(critical_errors) > 0
                or validation_result.corruption_detected
                or "INDEX_CORRUPTION" in error_types
                or "METADATA_CORRUPTION" in error_types
            ):

                return self._create_full_recovery_action(
                    validation_result, critical_errors
                )

            # Performance issues may need optimization
            elif (
                validation_result.performance_score < self.performance_threshold
                and "PERFORMANCE_DEGRADATION" in error_types
            ):

                return self._create_optimization_recovery_action(validation_result)

            # Multiple moderate issues may warrant full recovery
            elif (
                health_score < self.poor_health_threshold
                and len(validation_result.validation_errors) >= 3
            ):

                return self._create_full_recovery_action(validation_result, [])

            # Minor completeness or consistency issues can use incremental recovery
            elif (
                "MISSING_FILES" in error_types
                or "OUTDATED_INDEX_ENTRIES" in error_types
                or "METADATA_INCONSISTENT" in error_types
            ):

                return self._create_incremental_recovery_action(validation_result)

            # Default to incremental recovery for other issues
            elif validation_result.validation_errors:
                return self._create_incremental_recovery_action(validation_result)

            else:
                # No specific issues identified
                return RecoveryAction(
                    recovery_type=RecoveryType.NONE.value,
                    is_required=False,
                    priority=RecoveryPriority.LOW.value,
                    description="No specific recovery action identified",
                    estimated_duration_minutes=0,
                )

        except Exception as e:
            logger.error(f"Failed to decide recovery action: {e}", extra={"correlation_id": get_correlation_id()})
            return RecoveryAction(
                recovery_type=RecoveryType.NONE.value,
                is_required=False,
                priority=RecoveryPriority.LOW.value,
                description=f"Recovery decision failed: {str(e)}",
                estimated_duration_minutes=0,
            )

    def execute_recovery(
        self,
        recovery_action: RecoveryAction,
        progress_callback: Optional[Callable[[int, int, Path, str], None]] = None,
    ) -> RecoveryResult:
        """
        Execute the specified recovery action.

        Args:
            recovery_action: RecoveryAction to execute
            progress_callback: Optional progress callback

        Returns:
            RecoveryResult with execution details

        Raises:
            RecoveryFailedError: If recovery execution fails
        """
        start_time = datetime.now(timezone.utc)

        try:
            logger.info(f"Starting recovery action: {recovery_action.recovery_type}", extra={"correlation_id": get_correlation_id()})

            if recovery_action.recovery_type == RecoveryType.NONE.value:
                return RecoveryResult(
                    success=True,
                    recovery_type=recovery_action.recovery_type,
                    duration_seconds=0.0,
                    started_at=start_time,
                    completed_at=start_time,
                )

            # Execute pre-recovery steps
            backup_path = None
            if recovery_action.pre_recovery_steps:
                backup_path = self._execute_pre_recovery_steps(
                    recovery_action.pre_recovery_steps, progress_callback
                )

            # Execute main recovery based on type
            if recovery_action.recovery_type == RecoveryType.INCREMENTAL.value:
                result = self._execute_incremental_recovery(
                    recovery_action, progress_callback
                )
            elif recovery_action.recovery_type == RecoveryType.FULL.value:
                result = self._execute_full_recovery(recovery_action, progress_callback)
            elif recovery_action.recovery_type == RecoveryType.OPTIMIZATION.value:
                result = self._execute_optimization_recovery(
                    recovery_action, progress_callback
                )
            else:
                raise RecoveryFailedError(
                    f"Unknown recovery type: {recovery_action.recovery_type}",
                    recovery_action.recovery_type,
                )

            # Update result with backup information
            if backup_path:
                result.backup_created = True
                result.backup_path = backup_path

            # Complete timing
            end_time = datetime.now(timezone.utc)
            result.completed_at = end_time
            result.duration_seconds = (end_time - start_time).total_seconds()

            # Update recovery tracking
            self.last_recovery_time = end_time

            logger.info(
                f"Recovery completed successfully: {recovery_action.recovery_type} "
                f"in {result.duration_seconds:.1f} seconds"
            , extra={"correlation_id": get_correlation_id()})

            return result

        except RecoveryFailedError:
            # Re-raise recovery failures for upstream handling
            raise
        except Exception as e:
            end_time = datetime.now(timezone.utc)
            logger.error(f"Recovery execution failed: {e}", exc_info=True, extra={"correlation_id": get_correlation_id()})

            # Return failed result for other exceptions
            return RecoveryResult(
                success=False,
                recovery_type=recovery_action.recovery_type,
                duration_seconds=(end_time - start_time).total_seconds(),
                started_at=start_time,
                completed_at=end_time,
                error_message=str(e),
            )

    def _create_full_recovery_action(
        self, validation_result: ValidationResult, critical_errors: list
    ) -> RecoveryAction:
        """Create a full recovery action for critical issues."""
        affected_files = []
        for error in validation_result.validation_errors:
            affected_files.extend(error.affected_files)

        description = "Full re-index required due to "
        if critical_errors:
            description += f"{len(critical_errors)} critical errors"
        elif validation_result.corruption_detected:
            description += "index corruption"
        else:
            description += "poor overall health"

        pre_recovery_steps = []
        if self.backup_before_full_recovery:
            pre_recovery_steps.append("create_backup")

        # Estimate duration based on repository size
        estimated_minutes = self._estimate_full_recovery_duration()

        return RecoveryAction(
            recovery_type=RecoveryType.FULL.value,
            is_required=True,
            priority=(
                RecoveryPriority.CRITICAL.value
                if critical_errors
                else RecoveryPriority.HIGH.value
            ),
            description=description,
            estimated_duration_minutes=estimated_minutes,
            affected_files=list(set(affected_files)),
            pre_recovery_steps=pre_recovery_steps,
            post_recovery_verification=["validate_comprehensive"],
        )

    def _create_incremental_recovery_action(
        self, validation_result: ValidationResult
    ) -> RecoveryAction:
        """Create an incremental recovery action for minor issues."""
        affected_files = []
        for error in validation_result.validation_errors:
            affected_files.extend(error.affected_files)

        # Add missing and outdated files
        affected_files.extend(validation_result.missing_files)
        affected_files.extend(validation_result.outdated_files)

        issue_count = len(validation_result.validation_errors)
        description = f"Incremental indexing to address {issue_count} validation issues"

        # Estimate duration based on affected files
        estimated_minutes = max(5, len(set(affected_files)) // 10)  # Rough estimate

        return RecoveryAction(
            recovery_type=RecoveryType.INCREMENTAL.value,
            is_required=True,
            priority=RecoveryPriority.MEDIUM.value,
            description=description,
            estimated_duration_minutes=estimated_minutes,
            affected_files=list(set(affected_files)),
            pre_recovery_steps=[],
            post_recovery_verification=[
                "validate_completeness",
                "validate_consistency",
            ],
        )

    def _create_optimization_recovery_action(
        self, validation_result: ValidationResult
    ) -> RecoveryAction:
        """Create an optimization recovery action for performance issues."""
        description = f"Index optimization to optimize performance through compaction and tuning (current score: {validation_result.performance_score:.2f})"

        return RecoveryAction(
            recovery_type=RecoveryType.OPTIMIZATION.value,
            is_required=True,
            priority=RecoveryPriority.MEDIUM.value,
            description=description,
            estimated_duration_minutes=15,
            affected_files=[],
            pre_recovery_steps=[],
            post_recovery_verification=["validate_performance"],
        )

    def _execute_pre_recovery_steps(
        self, steps: list, progress_callback: Optional[Callable]
    ) -> Optional[str]:
        """Execute pre-recovery steps like backup creation."""
        backup_path = None

        for step in steps:
            if step == "create_backup":
                if progress_callback:
                    progress_callback(
                        0, 0, Path(""), "Creating backup before recovery..."
                    )

                backup_path = self._create_backup()

                if progress_callback:
                    progress_callback(
                        0, 0, Path(""), f"Backup created at {backup_path}"
                    )

        return backup_path

    def _execute_incremental_recovery(
        self, recovery_action: RecoveryAction, progress_callback: Optional[Callable]
    ) -> RecoveryResult:
        """Execute incremental recovery using SmartIndexer."""
        try:
            if progress_callback:
                progress_callback(
                    0, 0, Path(""), "Starting incremental indexing recovery..."
                )

            # Get SmartIndexer instance
            smart_indexer = self._get_smart_indexer()

            # Execute incremental indexing
            stats = smart_indexer.smart_index(
                force_full=False,
                reconcile_with_database=False,
                progress_callback=progress_callback,
            )

            if stats and not getattr(stats, "cancelled", False):
                return RecoveryResult(
                    success=True,
                    recovery_type=recovery_action.recovery_type,
                    duration_seconds=0.0,  # Will be updated by caller
                    files_processed=getattr(stats, "files_processed", 0),
                    chunks_created=getattr(stats, "chunks_created", 0),
                )
            else:
                raise RecoveryFailedError(
                    "Incremental indexing was cancelled or failed",
                    recovery_action.recovery_type,
                )

        except Exception as e:
            raise RecoveryFailedError(
                f"Incremental recovery failed: {str(e)}",
                recovery_action.recovery_type,
                e,
            )

    def _execute_full_recovery(
        self, recovery_action: RecoveryAction, progress_callback: Optional[Callable]
    ) -> RecoveryResult:
        """Execute full recovery using SmartIndexer."""
        try:
            if progress_callback:
                progress_callback(
                    0, 0, Path(""), "Starting full re-indexing recovery..."
                )

            # Get SmartIndexer instance
            smart_indexer = self._get_smart_indexer()

            # Clear the collection first
            vector_store_client = self._get_vector_store_client()
            embedding_provider = self._get_embedding_provider()
            collection_name = vector_store_client.resolve_collection_name(
                self.config, embedding_provider
            )
            vector_store_client.clear_collection(collection_name)

            if progress_callback:
                progress_callback(
                    0, 0, Path(""), "Collection cleared, starting full indexing..."
                )

            # Execute full indexing
            stats = smart_indexer.smart_index(
                force_full=True,
                reconcile_with_database=False,
                progress_callback=progress_callback,
            )

            if stats and not getattr(stats, "cancelled", False):
                return RecoveryResult(
                    success=True,
                    recovery_type=recovery_action.recovery_type,
                    duration_seconds=0.0,  # Will be updated by caller
                    files_processed=getattr(stats, "files_processed", 0),
                    chunks_created=getattr(stats, "chunks_created", 0),
                )
            else:
                raise RecoveryFailedError(
                    "Full indexing was cancelled or failed",
                    recovery_action.recovery_type,
                )

        except Exception as e:
            raise RecoveryFailedError(
                f"Full recovery failed: {str(e)}", recovery_action.recovery_type, e
            )

    def _execute_optimization_recovery(
        self, recovery_action: RecoveryAction, progress_callback: Optional[Callable]
    ) -> RecoveryResult:
        """Execute optimization recovery on vector store collection."""
        try:
            if progress_callback:
                progress_callback(0, 0, Path(""), "Starting index optimization...")

            # Get vector store client
            vector_store_client = self._get_vector_store_client()
            embedding_provider = self._get_embedding_provider()

            # Optimize the collection
            collection_name = vector_store_client.resolve_collection_name(
                self.config, embedding_provider
            )
            success = vector_store_client.optimize_collection(collection_name)

            if not success:
                raise RecoveryFailedError(
                    "Index optimization failed", recovery_action.recovery_type
                )

            if progress_callback:
                progress_callback(0, 0, Path(""), "Index optimization completed")

            return RecoveryResult(
                success=True,
                recovery_type=recovery_action.recovery_type,
                duration_seconds=0.0,  # Will be updated by caller
                optimization_performed=True,
            )

        except Exception as e:
            raise RecoveryFailedError(
                f"Optimization recovery failed: {str(e)}",
                recovery_action.recovery_type,
                e,
            )

    def _create_backup(self) -> str:
        """Create a backup before recovery operations."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = Path.home() / ".tmp" / "cidx_recovery_backups"
            backup_dir.mkdir(parents=True, exist_ok=True)

            backup_path = backup_dir / f"index_backup_{timestamp}"

            # Create backup of .code-indexer directory
            source_dir = Path(self.config.codebase_dir) / ".code-indexer"
            if source_dir.exists():
                shutil.copytree(source_dir, backup_path)
                logger.info(f"Created backup at {backup_path}", extra={"correlation_id": get_correlation_id()})
                return str(backup_path)
            else:
                logger.warning("No .code-indexer directory found to backup", extra={"correlation_id": get_correlation_id()})
                return str(backup_path)

        except Exception as e:
            logger.error(f"Failed to create backup: {e}", extra={"correlation_id": get_correlation_id()})
            raise RecoveryFailedError(f"Backup creation failed: {str(e)}", "backup")

    def _get_smart_indexer(self):
        """Get SmartIndexer instance for recovery operations."""
        try:
            from ...services.smart_indexer import SmartIndexer
            from ...services.embedding_factory import EmbeddingProviderFactory
            from pathlib import Path
            from ...storage.filesystem_vector_store import FilesystemVectorStore

            # Initialize required services (Story #505 - FilesystemVectorStore)
            embedding_provider = EmbeddingProviderFactory.create(self.config)

            # Initialize vector store
            index_dir = Path(self.config.codebase_dir) / ".code-indexer" / "index"
            vector_store_client = FilesystemVectorStore(
                base_path=index_dir, project_root=Path(self.config.codebase_dir)
            )

            # Create SmartIndexer
            metadata_path = (
                Path(self.config.codebase_dir) / ".code-indexer" / "metadata.json"
            )
            smart_indexer = SmartIndexer(
                config=self.config,
                embedding_provider=embedding_provider,
                vector_store_client=vector_store_client,
                metadata_path=metadata_path,
            )

            return smart_indexer

        except Exception as e:
            logger.error(f"Failed to create SmartIndexer: {e}", extra={"correlation_id": get_correlation_id()})
            raise RecoveryFailedError(
                f"SmartIndexer creation failed: {str(e)}", "initialization"
            )

    def _get_embedding_provider(self):
        """Get embedding provider instance for recovery operations."""
        try:
            from ...services.embedding_factory import EmbeddingProviderFactory

            return EmbeddingProviderFactory.create(self.config)
        except Exception as e:
            logger.error(f"Failed to create embedding provider: {e}", extra={"correlation_id": get_correlation_id()})
            raise RecoveryFailedError(
                f"Embedding provider creation failed: {str(e)}", "initialization"
            )

    def _get_vector_store_client(self):
        """Get vector store client instance for recovery operations."""
        try:
            from pathlib import Path
            from ...storage.filesystem_vector_store import FilesystemVectorStore

            index_dir = Path(self.config.codebase_dir) / ".code-indexer" / "index"
            return FilesystemVectorStore(
                base_path=index_dir, project_root=Path(self.config.codebase_dir)
            )

        except Exception as e:
            logger.error(f"Failed to create vector store client: {e}", extra={"correlation_id": get_correlation_id()})
            raise RecoveryFailedError(
                f"Vector store client creation failed: {str(e)}", "initialization"
            )

    def _estimate_full_recovery_duration(self) -> int:
        """Estimate duration for full recovery in minutes."""
        try:
            # Rough estimation based on repository size
            repo_path = Path(self.config.codebase_dir)
            if not repo_path.exists():
                return 30  # Default estimate

            # Count files (rough estimate)
            file_count = 0
            try:
                for _ in repo_path.rglob("*"):
                    file_count += 1
                    if file_count > 10000:  # Avoid counting too long
                        break
            except Exception:
                file_count = 1000  # Default estimate

            # Very rough estimation: 1 minute per 100 files, minimum 35 minutes for full recovery
            estimated_minutes = max(35, file_count // 100)

            # Cap at reasonable maximum
            return min(estimated_minutes, 120)

        except Exception as e:
            logger.warning(f"Failed to estimate recovery duration: {e}", extra={"correlation_id": get_correlation_id()})
            return 30  # Default estimate
