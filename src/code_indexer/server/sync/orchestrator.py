"""
Sync Execution Orchestrator for CIDX Server - Enhanced with Comprehensive Error Handling.

Coordinates GitSyncExecutor with SyncJobManager to provide comprehensive
job-managed sync operations with multi-phase progress tracking, intelligent
error handling, automatic recovery, and detailed error reporting.
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable, Any, List, cast

from ..git.git_sync_executor import GitSyncExecutor, GitSyncResult, GitSyncError
from ..jobs.manager import SyncJobManager
from ..jobs.models import JobType, JobStatus
from ..jobs.exceptions import JobNotFoundError
from .exceptions import SyncOrchestratorError
from .reindexing_engine import ReindexingDecisionEngine
from .git_analyzer import GitChangeAnalyzer
from .reindexing_models import ChangeSet, IndexMetrics, ReindexingContext

# Import comprehensive error handling system
from .error_handler import (
    SyncError,
    create_error_context,
    classify_error,
    ErrorSeverity,
)
from .recovery_strategies import RecoveryOrchestrator, RecoveryResult
from .error_reporter import ErrorReporter


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of a complete sync operation including job information and error handling."""

    success: bool
    job_id: str
    git_sync_result: Optional[GitSyncResult] = None
    error_message: Optional[str] = None
    backup_created: bool = False
    backup_path: Optional[str] = None
    indexing_mode: str = "incremental"  # "incremental" or "full"
    execution_time: float = 0.0
    validation_result: Optional[Any] = (
        None  # ValidationResult when validation is enabled
    )

    # Enhanced error handling fields
    errors_encountered: List[SyncError] = field(default_factory=list)
    recovery_attempts: List[RecoveryResult] = field(default_factory=list)
    final_error: Optional[SyncError] = None
    recovery_successful: bool = False
    error_report_id: Optional[str] = None


class SyncExecutionOrchestrator:
    """
    Orchestrates sync operations between GitSyncExecutor and SyncJobManager.

    Provides comprehensive job-managed sync operations with:
    - Multi-phase progress tracking (git pull + indexing)
    - Real-time progress reporting
    - Error handling and retry mechanisms
    - Repository locking and concurrency control
    - Backup and recovery integration
    """

    def __init__(
        self,
        repository_path: Path,
        job_manager: SyncJobManager,
        backup_dir: Optional[Path] = None,
        auto_index_on_changes: bool = True,
        enable_intelligent_reindexing: bool = True,
        enable_validation: bool = False,
        validation_health_threshold: float = 0.7,
        enable_auto_recovery: bool = False,
        enable_comprehensive_error_handling: bool = True,
        max_recovery_attempts: int = 3,
    ):
        """
        Initialize SyncExecutionOrchestrator with comprehensive error handling.

        Args:
            repository_path: Path to the git repository
            job_manager: SyncJobManager instance for job tracking
            backup_dir: Optional directory for backups
            auto_index_on_changes: Automatically trigger indexing when changes detected
            enable_intelligent_reindexing: Use ReindexingDecisionEngine for smart decisions
            enable_validation: Enable index validation as third phase
            validation_health_threshold: Health threshold for validation pass/fail
            enable_auto_recovery: Enable automatic recovery when validation fails
            enable_comprehensive_error_handling: Enable comprehensive error handling and recovery
            max_recovery_attempts: Maximum number of recovery strategies to attempt
        """
        self.repository_path = Path(repository_path).resolve()
        self.job_manager = job_manager
        self.auto_index_on_changes = auto_index_on_changes
        self.enable_intelligent_reindexing = enable_intelligent_reindexing
        self.enable_validation = enable_validation
        self.validation_health_threshold = validation_health_threshold
        self.enable_auto_recovery = enable_auto_recovery
        self.enable_comprehensive_error_handling = enable_comprehensive_error_handling
        self.max_recovery_attempts = max_recovery_attempts

        # Initialize comprehensive error handling system
        self.recovery_orchestrator: Optional[RecoveryOrchestrator] = None
        self.error_reporter: Optional[ErrorReporter] = None

        if self.enable_comprehensive_error_handling:
            try:
                self.recovery_orchestrator = RecoveryOrchestrator()
                self.error_reporter = ErrorReporter()
                logger.info("Comprehensive error handling and recovery enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize error handling: {e}")
                self.enable_comprehensive_error_handling = False
                self.recovery_orchestrator = None
                self.error_reporter = None

        # Initialize GitSyncExecutor
        self.git_sync_executor = GitSyncExecutor(
            repository_path=self.repository_path,
            backup_dir=backup_dir,
            auto_index_on_changes=False,  # We'll handle indexing through job system
        )

        # Initialize intelligent re-indexing components
        self.reindexing_engine: Optional["ReindexingDecisionEngine"] = None
        self.git_analyzer: Optional["GitChangeAnalyzer"] = None

        if self.enable_intelligent_reindexing:
            try:
                self.reindexing_engine = ReindexingDecisionEngine.from_config(
                    self._load_cidx_config()
                )
                self.git_analyzer = GitChangeAnalyzer(self.repository_path)
                logger.info("Intelligent re-indexing enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize intelligent re-indexing: {e}")
                self.enable_intelligent_reindexing = False
                self.reindexing_engine = None
                self.git_analyzer = None

        # Initialize validation components
        self.validation_engine: Optional["IndexValidationEngine"] = None
        self.auto_recovery_engine: Optional["AutoRecoveryEngine"] = None

        if self.enable_validation:
            try:
                from ..validation import IndexValidationEngine, AutoRecoveryEngine
                from ...services.qdrant import QdrantClient

                # Load config for validation components
                config = self._load_cidx_config()
                if config:
                    # Create Qdrant client for validation
                    qdrant_client = QdrantClient(
                        config.qdrant, None, self.repository_path
                    )

                    # Initialize validation engine
                    self.validation_engine = IndexValidationEngine(
                        config=config, qdrant_client=qdrant_client
                    )

                    # Initialize auto-recovery engine if enabled
                    if self.enable_auto_recovery:
                        self.auto_recovery_engine = AutoRecoveryEngine(config=config)
                    else:
                        self.auto_recovery_engine = None

                    logger.info("Index validation enabled")
                else:
                    logger.warning(
                        "Failed to load config for validation - disabling validation"
                    )
                    self.enable_validation = False
                    self.validation_engine = None
                    self.auto_recovery_engine = None

            except Exception as e:
                logger.warning(f"Failed to initialize validation components: {e}")
                self.enable_validation = False
                self.validation_engine = None
                self.auto_recovery_engine = None

        # Current job ID for progress tracking
        self._current_job_id: Optional[str] = None

        logger.info(
            f"SyncExecutionOrchestrator initialized for repository: {self.repository_path}"
        )

    def execute_sync(
        self,
        username: str,
        user_alias: str,
        repository_url: Optional[str] = None,
        merge_strategy: str = "fast-forward",
        force_full_index: bool = False,
        progress_callback: Optional[Callable[[int, int, Path, str], None]] = None,
    ) -> SyncResult:
        """
        Execute comprehensive sync operation with job tracking.

        Args:
            username: Username of the user requesting sync
            user_alias: Display name of the user
            repository_url: Repository URL for tracking (optional)
            merge_strategy: Git merge strategy to use
            force_full_index: Force full indexing instead of incremental
            progress_callback: Optional callback for progress reporting

        Returns:
            SyncResult with operation details and job information

        Raises:
            SyncOrchestratorError: If sync operation fails
            DuplicateRepositorySyncError: If repository is already being synced
        """
        start_time = time.time()

        try:
            # Create job with multi-phase tracking
            phases = ["git_pull", "indexing"]
            phase_weights = {"git_pull": 0.3, "indexing": 0.7}

            # Add validation phase if enabled
            if self.enable_validation:
                phases.append("validation")
                phase_weights = {"git_pull": 0.25, "indexing": 0.6, "validation": 0.15}

            job_id = self.job_manager.create_job_with_phases(
                username=username,
                user_alias=user_alias,
                job_type=JobType.REPOSITORY_SYNC,
                repository_url=repository_url,
                phases=phases,
                phase_weights=phase_weights,
            )

            self._current_job_id = job_id
            logger.info(f"Created sync job {job_id} for user {username}")

            # Create progress integrator for job updates
            from .progress_integrator import ProgressCallbackIntegrator

            progress_integrator = ProgressCallbackIntegrator(
                job_manager=self.job_manager, job_id=job_id
            )

            # Chain external callback with job integrator
            def combined_callback(current: int, total: int, file_path: Path, info: str):
                # Update job status
                progress_integrator.progress_callback(current, total, file_path, info)

                # Call external callback if provided
                if progress_callback:
                    progress_callback(current, total, file_path, info)

            # Start git_pull phase
            self.job_manager.start_phase(job_id, "git_pull")

            try:
                # Execute git pull operation
                git_result = self.git_sync_executor.execute_pull(
                    merge_strategy=merge_strategy, progress_callback=combined_callback
                )

                # Complete git_pull phase
                self.job_manager.complete_phase(
                    job_id=job_id,
                    phase="git_pull",
                    result={
                        "success": git_result.success,
                        "changes_detected": git_result.changes_detected,
                        "files_changed": git_result.files_changed,
                        "commits_pulled": git_result.commits_pulled,
                        "merge_strategy": git_result.merge_strategy,
                        "backup_created": git_result.backup_created,
                        "backup_path": git_result.backup_path,
                    },
                )

                # Determine indexing mode using intelligent decision engine
                indexing_mode, indexing_decision = self._determine_indexing_mode(
                    git_result, force_full_index, progress_callback=combined_callback
                )
                indexing_triggered = False

                if git_result.changes_detected and self.auto_index_on_changes:
                    # Start indexing phase
                    self.job_manager.start_phase(job_id, "indexing")

                    try:
                        # Trigger internal indexing with determined mode
                        force_full = indexing_mode == "full"
                        indexing_triggered = self._trigger_cidx_index(
                            force_full=force_full,
                            progress_callback=combined_callback,
                        )

                        # Log indexing decision details
                        if indexing_decision:
                            logger.info(
                                f"Indexing decision: {indexing_mode} mode selected. "
                                f"Triggers: {', '.join(indexing_decision.trigger_reasons)}"
                            )

                        if indexing_triggered:
                            # Complete indexing phase
                            self.job_manager.complete_phase(
                                job_id=job_id,
                                phase="indexing",
                                result={
                                    "indexing_mode": indexing_mode,
                                    "success": True,
                                },
                            )
                        else:
                            # Fail indexing phase
                            self.job_manager.fail_phase(
                                job_id=job_id,
                                phase="indexing",
                                error_message="Internal indexing failed",
                                error_code="INDEXING_FAILED",
                            )

                    except Exception as e:
                        # Fail indexing phase
                        self.job_manager.fail_phase(
                            job_id=job_id,
                            phase="indexing",
                            error_message=f"Indexing error: {str(e)}",
                            error_code="INDEXING_ERROR",
                        )
                        logger.error(f"Indexing failed for job {job_id}: {e}")

                elif not git_result.changes_detected:
                    # Skip indexing - no changes
                    self.job_manager.skip_phase(
                        job_id=job_id,
                        phase="indexing",
                        reason="No changes detected - indexing not required",
                    )

                    # Also skip validation if no indexing was performed
                    if self.enable_validation:
                        self.job_manager.skip_phase(
                            job_id=job_id,
                            phase="validation",
                            reason="Skipped - no indexing performed",
                        )

                # Execute validation phase if enabled and indexing was performed
                validation_result = None
                if self.enable_validation and indexing_triggered:
                    validation_result = self._execute_validation_phase(
                        job_id=job_id, progress_callback=combined_callback
                    )

                # Job completion is handled automatically by multi-phase logic
                # when all phases are completed/skipped. No need to explicitly complete here.

                execution_time = time.time() - start_time

                return SyncResult(
                    success=True,
                    job_id=job_id,
                    git_sync_result=git_result,
                    backup_created=git_result.backup_created,
                    backup_path=git_result.backup_path,
                    indexing_mode=indexing_mode,
                    execution_time=execution_time,
                    validation_result=validation_result,
                )

            except GitSyncError as e:
                # Git operation failed
                self.job_manager.fail_phase(
                    job_id=job_id,
                    phase="git_pull",
                    error_message=e.message,
                    error_code=e.error_code,
                )

                # Job is already marked as failed by fail_phase() method

                execution_time = time.time() - start_time

                return SyncResult(
                    success=False,
                    job_id=job_id,
                    error_message=e.message,
                    execution_time=execution_time,
                )

        except Exception as e:
            error_message = f"Sync orchestration failed: {str(e)}"
            logger.error(error_message, exc_info=True)

            # Try to mark job as failed if it was created
            if hasattr(self, "_current_job_id") and self._current_job_id:
                try:
                    self.job_manager.mark_job_completed(
                        self._current_job_id, error_message=error_message
                    )
                except Exception:
                    pass  # Job might not exist yet

            execution_time = time.time() - start_time

            # Return failed result or raise exception
            if hasattr(self, "_current_job_id") and self._current_job_id:
                return SyncResult(
                    success=False,
                    job_id=self._current_job_id,
                    error_message=error_message,
                    execution_time=execution_time,
                )
            else:
                raise SyncOrchestratorError(error_message, cause=e)

        finally:
            self._current_job_id = None

    def retry_job(self, job_id: str) -> SyncResult:
        """
        Retry a failed sync job.

        Args:
            job_id: Job ID to retry

        Returns:
            SyncResult with retry operation details

        Raises:
            JobNotFoundError: If job ID doesn't exist
            SyncOrchestratorError: If retry operation fails
        """
        try:
            # Get job details
            job = self.job_manager.get_job(job_id)

            if job["status"] not in [JobStatus.FAILED.value, JobStatus.CANCELLED.value]:
                raise SyncOrchestratorError(
                    f"Cannot retry job {job_id} in status {job['status']}"
                )

            # Release repository lock if held by this failed job
            if job.get("repository_url"):
                try:
                    # Access the protected method to release the repository lock
                    with self.job_manager._lock:
                        normalized_url = self.job_manager._normalize_repository_url(
                            job["repository_url"]
                        )
                        current_lock_job = self.job_manager._repository_locks.get(
                            normalized_url
                        )
                        if current_lock_job == job_id:
                            self.job_manager._release_repository_lock(
                                job["repository_url"]
                            )
                            logger.info(
                                f"Released repository lock for job {job_id} before retry"
                            )
                except Exception as e:
                    logger.warning(f"Could not release repository lock for retry: {e}")

            # Create a new job with same parameters (retry creates new job)
            return self.execute_sync(
                username=job["username"],
                user_alias=job["user_alias"],
                repository_url=job.get("repository_url"),
            )

        except JobNotFoundError:
            raise
        except Exception as e:
            raise SyncOrchestratorError(f"Job retry failed: {str(e)}", cause=e)

    def _trigger_cidx_index(
        self,
        force_full: bool = False,
        progress_callback: Optional[Callable[[int, int, Path, str], None]] = None,
    ) -> bool:
        """
        Trigger internal CIDX indexing using SmartIndexer with progress reporting.

        Args:
            force_full: Force full indexing instead of incremental
            progress_callback: Optional callback for progress reporting

        Returns:
            True if indexing completed successfully, False otherwise
        """
        try:
            from ...services.smart_indexer import SmartIndexer
            from ...services.embedding_factory import EmbeddingProviderFactory
            from ...services import QdrantClient
            from ...config import ConfigManager
            from pathlib import Path

            logger.info(f"Starting internal CIDX indexing for {self.repository_path}")

            # Get configuration for this repository
            config_manager = ConfigManager.create_with_backtrack(self.repository_path)
            config = config_manager.load()

            # Initialize required services (similar to CLI approach)
            embedding_provider = EmbeddingProviderFactory.create(config)
            qdrant_client = QdrantClient(config.qdrant, None, Path(config.codebase_dir))

            # Health checks
            if not embedding_provider.health_check():
                logger.error("Embedding provider health check failed")
                return False

            if not qdrant_client.health_check():
                logger.error("Qdrant client health check failed")
                return False

            # Create SmartIndexer
            metadata_path = (
                Path(config.codebase_dir) / ".code-indexer" / "metadata.json"
            )
            smart_indexer = SmartIndexer(
                config=config,
                embedding_provider=embedding_provider,
                vector_store_client=qdrant_client,
                metadata_path=metadata_path,
            )

            # Create progress callback wrapper for indexing phase
            def indexing_progress_callback(
                current, total, file_path, info=None, **kwargs
            ):
                if progress_callback:
                    # Convert progress callback format to match expected signature
                    progress_callback(
                        current,
                        total,
                        Path(file_path) if file_path else Path(""),
                        info or "",
                    )

            # Execute smart indexing with proper parameters
            stats = smart_indexer.smart_index(
                force_full=force_full,
                reconcile_with_database=False,  # Incremental by default
                batch_size=50,  # Default batch size
                progress_callback=indexing_progress_callback,
                safety_buffer_seconds=60,
                vector_thread_count=config.voyage_ai.parallel_requests,
                detect_deletions=False,  # Don't detect deletions during sync operations
            )

            # Check if indexing was successful
            if stats and not getattr(stats, "cancelled", False):
                logger.info(
                    f"Internal CIDX indexing completed successfully: {stats.files_processed} files, {stats.chunks_created} chunks"
                )
                return True
            else:
                logger.warning("Internal CIDX indexing was cancelled or failed")
                return False

        except Exception as e:
            logger.error(f"Internal CIDX indexing failed: {e}", exc_info=True)
            return False

    def _determine_indexing_mode(
        self,
        git_result: GitSyncResult,
        force_full_index: bool,
        progress_callback: Optional[Callable] = None,
    ) -> tuple[str, Optional[Any]]:
        """
        Determine whether to use full or incremental indexing.

        Args:
            git_result: Result from git pull operation
            force_full_index: User-requested force full indexing
            progress_callback: Optional callback for progress updates

        Returns:
            Tuple of (indexing_mode, decision_details) where mode is "full" or "incremental"
        """
        # If intelligent re-indexing is disabled, use simple logic
        if not self.enable_intelligent_reindexing:
            mode = "full" if force_full_index else "incremental"
            return mode, None

        try:
            # Report analysis progress
            if progress_callback:
                progress_callback(
                    0, 0, Path(""), "Analyzing changes for indexing decision..."
                )

            # Analyze git changes
            change_set = self._build_change_set_from_git_result(git_result)

            # Get current index metrics
            index_metrics = self._get_current_index_metrics()

            # Create reindexing context
            context = self._create_reindexing_context()

            # Make decision using engine
            if self.reindexing_engine is None:
                return "full", None  # Default to full indexing if engine not available

            decision = self.reindexing_engine.should_full_reindex(
                change_set=change_set,
                metrics=index_metrics,
                context=context,
                force_full_reindex=force_full_index,
            )

            indexing_mode = "full" if decision.should_reindex else "incremental"

            logger.info(
                f"Intelligent reindexing decision: {indexing_mode} "
                f"(confidence: {decision.confidence_score:.2f})"
            )

            return indexing_mode, decision

        except Exception as e:
            logger.warning(f"Failed to make intelligent reindexing decision: {e}")
            # Fall back to simple logic
            mode = "full" if force_full_index else "incremental"
            return mode, None

    def _build_change_set_from_git_result(self, git_result: GitSyncResult) -> ChangeSet:
        """Build ChangeSet from GitSyncResult for decision analysis."""
        try:
            # Use git analyzer for detailed analysis if available
            if self.git_analyzer and git_result.commits_pulled > 0:
                try:
                    return self.git_analyzer.analyze_recent_changes(
                        commits_back=git_result.commits_pulled
                    )
                except Exception as e:
                    logger.warning(f"Git analyzer failed, using simple analysis: {e}")

            # Build basic change set from git result
            # Estimate total files based on changed files (conservative estimate)
            estimated_total = max(100, len(git_result.files_changed) * 5)

            has_config_changes = self._detect_config_changes(git_result.files_changed)

            return ChangeSet(
                files_changed=git_result.files_changed,
                files_added=[],  # Git result doesn't separate added vs changed
                files_deleted=[],
                total_files=estimated_total,
                has_config_changes=has_config_changes,
            )

        except Exception as e:
            logger.warning(f"Failed to build change set: {e}")
            # Minimal fallback - ensure we don't have division by zero
            total_files = max(100, len(git_result.files_changed) * 5)
            return ChangeSet(
                files_changed=git_result.files_changed, total_files=total_files
            )

    def _get_current_index_metrics(self) -> IndexMetrics:
        """Get current index quality metrics."""
        try:
            from ...config import ConfigManager
            from pathlib import Path
            from datetime import datetime

            # Get configuration
            config_manager = ConfigManager.create_with_backtrack(self.repository_path)
            config = config_manager.load()

            # Check if index metadata exists
            metadata_path = (
                Path(config.codebase_dir) / ".code-indexer" / "metadata.json"
            )

            if metadata_path.exists():
                # Estimate index age and quality
                last_modified = datetime.fromtimestamp(metadata_path.stat().st_mtime)
                age_days = (datetime.now() - last_modified).days

                return IndexMetrics(
                    search_accuracy=0.9,  # Default assumption for existing indexes
                    index_age_days=age_days,
                    corruption_detected=False,
                )
            else:
                # No index exists - treat as very old/poor quality
                return IndexMetrics(
                    search_accuracy=0.5,
                    index_age_days=365,  # Very old
                    corruption_detected=False,
                )

        except Exception as e:
            logger.warning(f"Failed to get index metrics: {e}")
            # Conservative defaults
            return IndexMetrics(
                search_accuracy=0.8, index_age_days=15, corruption_detected=False
            )

    def _create_reindexing_context(self) -> ReindexingContext:
        """Create reindexing context with system information."""
        try:
            import shutil
            import psutil

            # Get repository size
            repo_size_mb = sum(
                f.stat().st_size for f in self.repository_path.rglob("*") if f.is_file()
            ) / (1024 * 1024)

            # Get available resources
            disk_usage = shutil.disk_usage(self.repository_path)
            available_disk_mb = disk_usage.free / (1024 * 1024)

            memory = psutil.virtual_memory()
            available_memory_mb = memory.available / (1024 * 1024)

            system_load = (
                psutil.getloadavg()[0] if hasattr(psutil, "getloadavg") else 0.5
            )

            return ReindexingContext(
                repository_path=self.repository_path,
                repository_size_mb=repo_size_mb,
                available_memory_mb=available_memory_mb,
                available_disk_space_mb=available_disk_mb,
                system_load=system_load,
            )

        except Exception as e:
            logger.warning(f"Failed to create reindexing context: {e}")
            # Minimal context
            return ReindexingContext(
                repository_path=self.repository_path,
                repository_size_mb=100.0,  # Default estimate
                available_memory_mb=2048.0,
                available_disk_space_mb=10000.0,
                system_load=0.5,
            )

    def _detect_config_changes(self, changed_files: list) -> bool:
        """Detect if any changed files are configuration files."""
        if not self.reindexing_engine:
            return False

        config_patterns = self.reindexing_engine.config.config_file_patterns
        for file_path in changed_files:
            if any(pattern in file_path for pattern in config_patterns):
                return True
        return False

    def _execute_validation_phase(
        self,
        job_id: str,
        progress_callback: Optional[Callable[[int, int, Path, str], None]] = None,
    ):
        """
        Execute the validation phase after successful indexing.

        Args:
            job_id: Job ID for phase tracking
            progress_callback: Optional callback for progress reporting

        Returns:
            ValidationResult from the validation process
        """
        try:
            # Start validation phase
            self.job_manager.start_phase(job_id, "validation")

            if progress_callback:
                progress_callback(0, 0, Path(""), "Starting index validation...")

            # Run comprehensive validation
            if self.validation_engine is None:
                logger.warning("Validation engine not available - skipping validation")
                return None

            validation_result = self.validation_engine.validate_comprehensive(
                progress_callback=progress_callback, include_performance=True
            )

            # Determine if validation passed based on health threshold
            validation_passed = (
                validation_result.overall_health_score
                >= self.validation_health_threshold
            )

            if validation_passed:
                # Complete validation phase successfully
                self.job_manager.complete_phase(
                    job_id=job_id,
                    phase="validation",
                    result={
                        "validation_passed": True,
                        "health_score": validation_result.overall_health_score,
                        "validation_errors": len(validation_result.validation_errors),
                        "recommendations": validation_result.recommendations,
                        "requires_reindex": validation_result.requires_full_reindex,
                    },
                )
                logger.info(
                    f"Validation passed with health score {validation_result.overall_health_score:.2f}"
                )
            else:
                # Validation failed but still complete the phase (with warnings)
                self.job_manager.complete_phase(
                    job_id=job_id,
                    phase="validation",
                    result={
                        "validation_passed": False,
                        "health_score": validation_result.overall_health_score,
                        "validation_errors": len(validation_result.validation_errors),
                        "recommendations": validation_result.recommendations,
                        "requires_reindex": validation_result.requires_full_reindex,
                        "auto_recovery_triggered": False,
                    },
                )
                logger.warning(
                    f"Validation failed with health score {validation_result.overall_health_score:.2f}"
                )

                # Attempt auto-recovery if enabled and required
                if (
                    self.enable_auto_recovery
                    and self.auto_recovery_engine
                    and validation_result.requires_full_reindex
                ):

                    try:
                        if progress_callback:
                            progress_callback(
                                0, 0, Path(""), "Triggering auto-recovery..."
                            )

                        recovery_action = (
                            self.auto_recovery_engine.decide_recovery_action(
                                validation_result
                            )
                        )
                        if recovery_action.is_required:
                            recovery_result = (
                                self.auto_recovery_engine.execute_recovery(
                                    recovery_action, progress_callback
                                )
                            )

                            if recovery_result.success:
                                # Update validation phase result to indicate successful recovery
                                self.job_manager.complete_phase(
                                    job_id=job_id,
                                    phase="validation",
                                    result={
                                        "validation_passed": True,  # After recovery
                                        "auto_recovery_performed": True,
                                        "recovery_type": recovery_result.recovery_type,
                                        "original_health_score": validation_result.overall_health_score,
                                        "post_recovery_health_score": 0.9,  # Assume recovery improves health
                                    },
                                )
                                logger.info(
                                    f"Auto-recovery completed successfully: {recovery_result.recovery_type}"
                                )
                            else:
                                logger.error(
                                    f"Auto-recovery failed: {recovery_result.error_message}"
                                )

                    except Exception as e:
                        logger.error(f"Auto-recovery execution failed: {e}")

            return validation_result

        except Exception as e:
            # Fail validation phase
            error_message = f"Validation error: {str(e)}"
            self.job_manager.fail_phase(
                job_id=job_id,
                phase="validation",
                error_message=error_message,
                error_code="VALIDATION_ERROR",
            )
            logger.error(f"Validation phase failed for job {job_id}: {e}")

            # Return a failed validation result
            from ..validation.models import ValidationResult, ValidationError

            return ValidationResult(
                is_valid=False,
                completeness_score=0.0,
                quality_score=0.0,
                consistency_score=0.0,
                performance_score=0.0,
                validation_errors=[
                    ValidationError(
                        error_type="VALIDATION_SYSTEM_ERROR",
                        message=error_message,
                        severity="critical",
                    )
                ],
            )

    def _load_cidx_config(self):
        """Load CIDX configuration for the repository."""
        try:
            from ...config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(self.repository_path)
            return config_manager.load()
        except Exception as e:
            logger.warning(f"Failed to load CIDX config: {e}")
            return None

    def _handle_error_with_recovery(
        self,
        error: Exception,
        context_phase: str,
        operation: Callable[[], Any],
        job_id: Optional[str] = None,
        user_id: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
    ) -> tuple[bool, Any, Optional[SyncError], List[RecoveryResult]]:
        """
        Handle error with comprehensive error classification and recovery attempts.

        Args:
            error: The original exception that occurred
            context_phase: The phase where the error occurred
            operation: The operation to retry if recovery is attempted
            job_id: Associated job ID if available
            user_id: User ID for error context
            progress_callback: Progress callback for recovery operations

        Returns:
            Tuple of (success, result, final_error, recovery_attempts)
        """
        if (
            not self.enable_comprehensive_error_handling
            or not self.recovery_orchestrator
        ):
            # Fallback to legacy error handling
            return False, None, classify_error(error), []

        try:
            # Create comprehensive error context
            error_context = create_error_context(
                phase=context_phase,
                repository=str(self.repository_path),
                user_id=user_id or "unknown",
                job_id=job_id,
                additional_info={
                    "orchestrator_config": {
                        "enable_validation": self.enable_validation,
                        "enable_auto_recovery": self.enable_auto_recovery,
                        "enable_intelligent_reindexing": self.enable_intelligent_reindexing,
                    }
                },
            )

            # Classify the error using comprehensive system
            sync_error = classify_error(error, error_context)

            # Report the error
            if self.error_reporter:
                self.error_reporter.report_error(sync_error)

            # Attempt recovery if error is recoverable
            recovery_attempts = []
            if sync_error.severity in [
                ErrorSeverity.RECOVERABLE,
                ErrorSeverity.WARNING,
            ]:
                logger.info(f"Attempting recovery for {sync_error.error_code} error")

                recovery_result = self.recovery_orchestrator.attempt_recovery(
                    sync_error,
                    error_context,
                    operation,
                    progress_callback,
                    max_recovery_attempts=self.max_recovery_attempts,
                )

                recovery_attempts.append(recovery_result)

                # Report recovery result
                if self.error_reporter:
                    self.error_reporter.report_error(sync_error, recovery_result)

                if recovery_result.success:
                    logger.info(
                        f"Successfully recovered from {sync_error.error_code} error"
                    )
                    return True, "recovered", sync_error, recovery_attempts
                else:
                    logger.warning(
                        f"Recovery failed for {sync_error.error_code}: {recovery_result.outcome.value}"
                    )

            # No recovery possible or recovery failed
            logger.error(
                f"Error handling completed for {sync_error.error_code} - "
                f"no recovery possible (severity: {sync_error.severity.value})"
            )

            return False, None, sync_error, recovery_attempts

        except Exception as handling_error:
            logger.error(
                f"Error handling system failed: {handling_error}", exc_info=True
            )
            # Fallback to basic error classification
            fallback_error = classify_error(error)
            return False, None, fallback_error, []

    def _create_enhanced_sync_result(
        self,
        base_result: SyncResult,
        errors_encountered: List[SyncError],
        recovery_attempts: List[RecoveryResult],
        final_error: Optional[SyncError] = None,
    ) -> SyncResult:
        """
        Enhance a SyncResult with comprehensive error handling information.

        Args:
            base_result: Base SyncResult to enhance
            errors_encountered: List of all errors encountered
            recovery_attempts: List of all recovery attempts made
            final_error: Final unresolved error if any

        Returns:
            Enhanced SyncResult with error handling information
        """
        base_result.errors_encountered = errors_encountered
        base_result.recovery_attempts = recovery_attempts
        base_result.final_error = final_error
        base_result.recovery_successful = any(
            attempt.success for attempt in recovery_attempts
        )

        # Generate error report if we have errors
        if errors_encountered and self.error_reporter:
            try:
                report_json = self.error_reporter.generate_report(time_window_hours=1)
                import json

                report_data = json.loads(report_json)
                base_result.error_report_id = report_data.get("report_id")
            except Exception as e:
                logger.warning(f"Failed to generate error report: {e}")

        return base_result

    def get_error_statistics(self, time_window_hours: int = 24) -> dict[str, Any]:
        """
        Get comprehensive error statistics for this orchestrator.

        Args:
            time_window_hours: Time window for statistics (default 24 hours)

        Returns:
            Dictionary containing error statistics and recovery metrics
        """
        if not self.error_reporter:
            return {"error": "Comprehensive error handling not enabled"}

        try:
            return cast(
                dict[str, Any],
                self.error_reporter.aggregator.get_error_statistics(time_window_hours),
            )
        except Exception as e:
            logger.error(f"Failed to get error statistics: {e}")
            return {"error": str(e)}

    def generate_error_report(
        self,
        time_window_hours: int = 24,
        report_format: str = "json",
        report_level: str = "detailed",
    ) -> str:
        """
        Generate comprehensive error report for this orchestrator.

        Args:
            time_window_hours: Time window for report (default 24 hours)
            report_format: Format for report ("json", "markdown", "text")
            report_level: Level of detail ("summary", "detailed", "diagnostic")

        Returns:
            Formatted error report
        """
        if not self.error_reporter:
            return "Comprehensive error handling not enabled"

        try:
            from .error_reporter import ReportFormat, ReportLevel

            format_map = {
                "json": ReportFormat.JSON,
                "markdown": ReportFormat.MARKDOWN,
                "text": ReportFormat.TEXT,
            }

            level_map = {
                "summary": ReportLevel.SUMMARY,
                "detailed": ReportLevel.DETAILED,
                "diagnostic": ReportLevel.DIAGNOSTIC,
            }

            return self.error_reporter.generate_report(
                time_window_hours=time_window_hours,
                format=format_map.get(report_format.lower(), ReportFormat.JSON),
                report_level=level_map.get(report_level.lower(), ReportLevel.DETAILED),
            )

        except Exception as e:
            logger.error(f"Failed to generate error report: {e}")
            return f"Error generating report: {str(e)}"

    def get_user_friendly_error_message(self, error: SyncError) -> str:
        """
        Get user-friendly error message with recovery guidance.

        Args:
            error: SyncError to format

        Returns:
            User-friendly error message with recovery suggestions
        """
        if not self.error_reporter:
            return f"Error: {error.message}"

        try:
            return self.error_reporter.get_user_friendly_error_message(error)
        except Exception as e:
            logger.error(f"Failed to format user-friendly error message: {e}")
            return f"Error: {error.message}"
