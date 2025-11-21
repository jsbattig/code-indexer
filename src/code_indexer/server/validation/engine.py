"""
Index Validation Engine for CIDX Server - Story 9 Implementation.

Comprehensive index validation including completeness, quality, consistency,
and performance checking. Following CLAUDE.md Foundation #1: NO MOCKS -
real validation with actual data and systems.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional, Callable

from .models import (
    ValidationResult,
    ValidationError,
    ValidationErrorType,
    ValidationSeverity,
)
from .exceptions import ValidationFailedError, IndexCorruptionError
from .health_checker import IndexHealthChecker
from ...config import Config
from ...indexing.file_finder import FileFinder
from ...storage.filesystem_vector_store import FilesystemVectorStore

logger = logging.getLogger(__name__)


class IndexValidationEngine:
    """
    Comprehensive index validation engine.

    Validates index completeness, quality, consistency, and performance
    against the repository state and expected standards.
    """

    def __init__(
        self,
        config: Config,
        vector_store_client: FilesystemVectorStore,
        health_checker: Optional[IndexHealthChecker] = None,
    ):
        """
        Initialize IndexValidationEngine.

        Args:
            config: CIDX configuration
            vector_store_client: Vector store client for index operations
            health_checker: Optional health checker (will create if not provided)
        """
        self.config = config
        self.vector_store_client = vector_store_client
        self.repository_path = Path(config.codebase_dir)

        # Initialize health checker
        self.health_checker = health_checker or IndexHealthChecker(
            config=config, vector_store_client=vector_store_client
        )

        # File finder for repository scanning
        self.file_finder = FileFinder(self.config)

        # Validation thresholds
        self.health_threshold = getattr(config, "validation_health_threshold", 0.7)
        self.completeness_threshold = getattr(
            config, "validation_completeness_threshold", 0.8
        )
        self.quality_threshold = getattr(config, "validation_quality_threshold", 0.75)

        logger.info(f"IndexValidationEngine initialized for {self.repository_path}")

    def validate_completeness(
        self, progress_callback: Optional[Callable] = None
    ) -> ValidationResult:
        """
        Validate index completeness by comparing indexed files vs repository files.

        Args:
            progress_callback: Optional callback for progress updates

        Returns:
            ValidationResult with completeness analysis
        """
        if progress_callback:
            progress_callback(0, 0, Path(""), "Analyzing repository files...")

        try:
            # Get all indexable files from repository
            repository_files = self._get_repository_indexable_files()

            if progress_callback:
                progress_callback(
                    0, 0, Path(""), "Retrieving indexed files from database..."
                )

            # Get all indexed files from Filesystem
            indexed_files = self._get_indexed_files()

            if progress_callback:
                progress_callback(
                    0, 0, Path(""), "Comparing repository vs indexed files..."
                )

            # Compare files
            missing_files = list(set(repository_files) - set(indexed_files))
            extra_indexed_files = list(set(indexed_files) - set(repository_files))

            # Calculate completeness score
            total_expected = len(repository_files)
            correctly_indexed = len(repository_files) - len(missing_files)

            # Base score: coverage of repository files
            if total_expected > 0:
                base_score = correctly_indexed / total_expected
            else:
                base_score = 1.0  # Perfect if no files expected

            # Apply penalty for extra indexed files (stale entries)
            if extra_indexed_files and total_expected > 0:
                # Penalty proportional to extra files vs expected files
                penalty_factor = len(extra_indexed_files) / (
                    total_expected + len(extra_indexed_files)
                )
                completeness_score = base_score * (1.0 - penalty_factor)
            else:
                completeness_score = base_score

            # Ensure score is between 0 and 1
            completeness_score = float(max(0.0, min(1.0, completeness_score)))

            # Generate validation errors
            validation_errors = []
            if missing_files:
                validation_errors.append(
                    ValidationError(
                        error_type=ValidationErrorType.MISSING_FILES.value,
                        message=f"{len(missing_files)} files missing from index",
                        affected_files=missing_files[:10],  # Limit for readability
                        severity=(
                            ValidationSeverity.WARNING.value
                            if len(missing_files) < 50
                            else ValidationSeverity.CRITICAL.value
                        ),
                        metadata={"total_missing": len(missing_files)},
                    )
                )

            if extra_indexed_files:
                validation_errors.append(
                    ValidationError(
                        error_type=ValidationErrorType.EXTRA_INDEXED_FILES.value,
                        message=f"{len(extra_indexed_files)} extra files in index (stale entries)",
                        affected_files=extra_indexed_files[
                            :10
                        ],  # Limit for readability
                        severity=ValidationSeverity.WARNING.value,
                        metadata={"total_extra": len(extra_indexed_files)},
                    )
                )

            # Determine if validation passes
            is_valid = bool(
                completeness_score >= self.completeness_threshold
                and len(validation_errors) == 0
            )

            if progress_callback:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    f"Completeness validation completed: {completeness_score:.2f}",
                )

            return ValidationResult(
                is_valid=is_valid,
                completeness_score=completeness_score,
                quality_score=1.0,  # Not evaluated in this method
                consistency_score=1.0,  # Not evaluated in this method
                performance_score=1.0,  # Not evaluated in this method
                validation_errors=validation_errors,
                missing_files=missing_files,
                extra_indexed_files=extra_indexed_files,
                validation_metadata={
                    "total_repository_files": len(repository_files),
                    "total_indexed_files": len(indexed_files),
                    "correctly_indexed_files": correctly_indexed,
                    "validation_type": "completeness",
                },
            )

        except Exception as e:
            logger.error(f"Completeness validation failed: {e}", exc_info=True)
            raise ValidationFailedError(f"Completeness validation error: {str(e)}")

    def validate_quality(
        self, progress_callback: Optional[Callable] = None
    ) -> ValidationResult:
        """
        Validate index quality by checking embedding integrity and metadata consistency.

        Args:
            progress_callback: Optional callback for progress updates

        Returns:
            ValidationResult with quality analysis
        """
        if progress_callback:
            progress_callback(0, 0, Path(""), "Checking embedding dimensions...")

        try:
            # Check embedding dimensions
            dimension_result = self.health_checker.check_embedding_dimensions()

            if progress_callback:
                progress_callback(0, 0, Path(""), "Analyzing vector quality...")

            # Check vector quality
            vector_result = self.health_checker.check_vector_quality()

            if progress_callback:
                progress_callback(0, 0, Path(""), "Validating metadata integrity...")

            # Check metadata integrity
            metadata_result = self.health_checker.check_metadata_integrity()

            # Combine results into overall quality score
            quality_components = [
                dimension_result.dimension_consistency_score,
                vector_result.quality_score,
                metadata_result.completeness_score,
            ]
            quality_score = float(sum(quality_components) / len(quality_components))

            # Generate validation errors based on health check results
            validation_errors = []

            # Dimension consistency errors
            if not dimension_result.is_healthy:
                validation_errors.append(
                    ValidationError(
                        error_type=ValidationErrorType.INDEX_CORRUPTION.value,
                        message=f"Embedding dimension inconsistency detected: {len(dimension_result.dimension_violations)} violations",
                        affected_files=[
                            v.get("file_path", "unknown")
                            for v in dimension_result.dimension_violations
                        ],
                        severity=ValidationSeverity.CRITICAL.value,
                        metadata={
                            "expected_dimensions": dimension_result.expected_dimensions,
                            "violations": len(dimension_result.dimension_violations),
                        },
                    )
                )

            # Vector quality errors
            if not vector_result.is_healthy:
                severity = (
                    ValidationSeverity.CRITICAL.value
                    if vector_result.quality_score < 0.3
                    else ValidationSeverity.WARNING.value
                )
                validation_errors.append(
                    ValidationError(
                        error_type=ValidationErrorType.QUALITY_DEGRADATION.value,
                        message=f"Vector quality issues: {vector_result.zero_vector_count} zero vectors, {vector_result.nan_vector_count} NaN vectors",
                        affected_files=vector_result.corrupt_files,
                        severity=severity,
                        metadata={
                            "zero_vectors": vector_result.zero_vector_count,
                            "nan_vectors": vector_result.nan_vector_count,
                            "variance_score": vector_result.variance_score,
                        },
                    )
                )

            # Metadata integrity errors
            if not metadata_result.is_healthy:
                validation_errors.append(
                    ValidationError(
                        error_type=ValidationErrorType.METADATA_INCONSISTENT.value,
                        message=f"Metadata integrity issues: {metadata_result.missing_metadata_count} missing, {metadata_result.invalid_metadata_count} invalid",
                        affected_files=[],
                        severity=ValidationSeverity.WARNING.value,
                        metadata={
                            "missing_metadata": metadata_result.missing_metadata_count,
                            "invalid_metadata": metadata_result.invalid_metadata_count,
                        },
                    )
                )

            # Check for critical corruption that should raise exception
            corruption_detected = bool(
                dimension_result.dimension_consistency_score < 0.5
                or vector_result.quality_score < 0.2
                or vector_result.zero_vector_count > 0
                or vector_result.nan_vector_count > 0
            )

            if corruption_detected and quality_score < 0.3:
                corrupt_files = list(
                    set(
                        [
                            v.get("file_path", "unknown")
                            for v in dimension_result.dimension_violations
                        ]
                        + vector_result.corrupt_files
                    )
                )
                raise IndexCorruptionError(
                    "Severe index corruption detected - immediate action required",
                    corrupt_files=corrupt_files,
                    corruption_type="embedding_corruption",
                )

            # Determine if validation passes
            is_valid = bool(
                quality_score >= self.quality_threshold and not corruption_detected
            )

            if progress_callback:
                progress_callback(
                    0, 0, Path(""), f"Quality validation completed: {quality_score:.2f}"
                )

            return ValidationResult(
                is_valid=is_valid,
                completeness_score=1.0,  # Not evaluated in this method
                quality_score=quality_score,
                consistency_score=1.0,  # Not evaluated in this method
                performance_score=1.0,  # Not evaluated in this method
                validation_errors=validation_errors,
                corruption_detected=corruption_detected,
                validation_metadata={
                    "dimension_consistency": dimension_result.dimension_consistency_score,
                    "vector_quality": vector_result.quality_score,
                    "metadata_completeness": metadata_result.completeness_score,
                    "validation_type": "quality",
                },
            )

        except IndexCorruptionError:
            raise  # Re-raise corruption errors
        except Exception as e:
            logger.error(f"Quality validation failed: {e}", exc_info=True)
            raise ValidationFailedError(f"Quality validation error: {str(e)}")

    def validate_consistency(
        self, progress_callback: Optional[Callable] = None
    ) -> ValidationResult:
        """
        Validate index consistency by checking timestamps and file state consistency.

        Args:
            progress_callback: Optional callback for progress updates

        Returns:
            ValidationResult with consistency analysis
        """
        if progress_callback:
            progress_callback(0, 0, Path(""), "Retrieving index timestamps...")

        try:
            # Get file timestamps from index
            indexed_timestamps = self._get_file_index_timestamps()

            if progress_callback:
                progress_callback(
                    0, 0, Path(""), "Comparing with file system timestamps..."
                )

            # Compare with actual file modification times
            outdated_files = []
            total_files_checked = 0

            for file_path, indexed_time in indexed_timestamps.items():
                full_path = self.repository_path / file_path

                if full_path.exists():
                    file_mtime = datetime.fromtimestamp(
                        full_path.stat().st_mtime, tz=timezone.utc
                    )

                    # Allow for some timestamp tolerance (5 seconds) to handle filesystem precision
                    if (
                        file_mtime > indexed_time
                        and (file_mtime - indexed_time).total_seconds() > 5
                    ):
                        outdated_files.append(file_path)

                    total_files_checked += 1

            # Calculate consistency score
            consistency_score = 1.0
            if total_files_checked > 0:
                consistent_files = total_files_checked - len(outdated_files)
                consistency_score = float(consistent_files / total_files_checked)

            # Generate validation errors
            validation_errors = []
            if outdated_files:
                severity = (
                    ValidationSeverity.WARNING.value
                    if len(outdated_files) < 20
                    else ValidationSeverity.CRITICAL.value
                )
                validation_errors.append(
                    ValidationError(
                        error_type=ValidationErrorType.OUTDATED_INDEX_ENTRIES.value,
                        message=f"{len(outdated_files)} files have been modified since indexing",
                        affected_files=outdated_files[:10],  # Limit for readability
                        severity=severity,
                        metadata={"total_outdated": len(outdated_files)},
                    )
                )

            # Determine if validation passes
            consistency_threshold = 0.9  # High threshold for consistency
            is_valid = bool(consistency_score >= consistency_threshold)

            if progress_callback:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    f"Consistency validation completed: {consistency_score:.2f}",
                )

            return ValidationResult(
                is_valid=is_valid,
                completeness_score=1.0,  # Not evaluated in this method
                quality_score=1.0,  # Not evaluated in this method
                consistency_score=consistency_score,
                performance_score=1.0,  # Not evaluated in this method
                validation_errors=validation_errors,
                outdated_files=outdated_files,
                validation_metadata={
                    "total_files_checked": total_files_checked,
                    "outdated_files_count": len(outdated_files),
                    "validation_type": "consistency",
                },
            )

        except Exception as e:
            logger.error(f"Consistency validation failed: {e}", exc_info=True)
            raise ValidationFailedError(f"Consistency validation error: {str(e)}")

    def validate_comprehensive(
        self,
        progress_callback: Optional[Callable] = None,
        include_performance: bool = True,
    ) -> ValidationResult:
        """
        Run comprehensive validation including all validation types.

        Args:
            progress_callback: Optional callback for progress updates
            include_performance: Whether to include performance validation

        Returns:
            Combined ValidationResult with all validation outcomes
        """
        start_time = datetime.now(timezone.utc)

        try:
            if progress_callback:
                progress_callback(
                    0, 0, Path(""), "Starting comprehensive index validation..."
                )

            # Run completeness validation
            if progress_callback:
                progress_callback(1, 4, Path(""), "Validating index completeness...")

            completeness_result = self.validate_completeness(progress_callback)

            # Run quality validation
            if progress_callback:
                progress_callback(2, 4, Path(""), "Validating index quality...")

            quality_result = self.validate_quality(progress_callback)

            # Run consistency validation
            if progress_callback:
                progress_callback(3, 4, Path(""), "Validating index consistency...")

            consistency_result = self.validate_consistency(progress_callback)

            # Run performance validation if requested
            performance_score = 1.0
            performance_errors = []

            if include_performance:
                if progress_callback:
                    progress_callback(4, 4, Path(""), "Measuring index performance...")

                performance_result = self.health_checker.measure_query_performance()
                performance_score = performance_result.performance_score

                if not performance_result.is_performant:
                    performance_errors.append(
                        ValidationError(
                            error_type=ValidationErrorType.PERFORMANCE_DEGRADATION.value,
                            message=f"Query performance below threshold: {performance_result.average_query_time_ms:.1f}ms average",
                            affected_files=[],
                            severity=ValidationSeverity.WARNING.value,
                            metadata={
                                "average_query_time": performance_result.average_query_time_ms,
                                "slowest_query_time": performance_result.slowest_query_time_ms,
                                "slow_queries_count": len(
                                    performance_result.slow_queries
                                ),
                            },
                        )
                    )

            # Combine all results
            all_errors = (
                completeness_result.validation_errors
                + quality_result.validation_errors
                + consistency_result.validation_errors
                + performance_errors
            )

            # Calculate overall validity
            component_scores = [
                completeness_result.completeness_score,
                quality_result.quality_score,
                consistency_result.consistency_score,
                performance_score,
            ]
            overall_score = sum(component_scores) / len(component_scores)
            is_valid = bool(
                overall_score >= self.health_threshold
                and len([e for e in all_errors if e.is_critical]) == 0
            )

            # Generate recommendations based on validation results
            recommendations = self._generate_recommendations(
                completeness_result,
                quality_result,
                consistency_result,
                performance_score,
                all_errors,
            )

            # Determine if full re-index is required
            requires_full_reindex = (
                overall_score < 0.5
                or quality_result.corruption_detected
                or len([e for e in all_errors if e.is_critical]) > 0
                or completeness_result.completeness_score < 0.6
            )

            end_time = datetime.now(timezone.utc)
            validation_duration = end_time - start_time

            if progress_callback:
                progress_callback(
                    4,
                    4,
                    Path(""),
                    f"Comprehensive validation completed: {overall_score:.2f} health score",
                )

            # Combine metadata from all validations
            combined_metadata = {
                "validation_type": "comprehensive",
                "validation_duration_seconds": validation_duration.total_seconds(),
                "component_scores": {
                    "completeness": completeness_result.completeness_score,
                    "quality": quality_result.quality_score,
                    "consistency": consistency_result.consistency_score,
                    "performance": performance_score,
                },
            }
            combined_metadata.update(completeness_result.validation_metadata)
            combined_metadata.update(quality_result.validation_metadata)
            combined_metadata.update(consistency_result.validation_metadata)

            return ValidationResult(
                is_valid=is_valid,
                completeness_score=completeness_result.completeness_score,
                quality_score=quality_result.quality_score,
                consistency_score=consistency_result.consistency_score,
                performance_score=performance_score,
                validation_errors=all_errors,
                recommendations=recommendations,
                missing_files=completeness_result.missing_files,
                extra_indexed_files=completeness_result.extra_indexed_files,
                corruption_detected=quality_result.corruption_detected,
                outdated_files=consistency_result.outdated_files,
                requires_full_reindex=requires_full_reindex,
                validation_timestamp=start_time,
                validation_duration=end_time,
                validation_metadata=combined_metadata,
            )

        except Exception as e:
            logger.error(f"Comprehensive validation failed: {e}", exc_info=True)
            raise ValidationFailedError(f"Comprehensive validation error: {str(e)}")

    def _get_repository_indexable_files(self) -> List[str]:
        """Get all indexable files from the repository using FileFinder."""
        try:
            # Use FileFinder to get all indexable files
            # FileFinder uses the config's codebase_dir, which should be our repository path
            all_files = []
            for file_path in self.file_finder.find_files():
                # Convert to relative path from repository root
                relative_path = file_path.relative_to(self.repository_path)
                all_files.append(str(relative_path))

            return all_files

        except Exception as e:
            logger.error(f"Failed to get repository indexable files: {e}")
            return []

    def _get_indexed_files(self) -> List[str]:
        """Get all indexed files from Filesystem database."""
        try:
            # This would typically query Filesystem for all indexed file paths
            # For now, we'll mock this since we need the Filesystem client implementation
            return self.vector_store_client.get_all_indexed_files()

        except Exception as e:
            logger.error(f"Failed to get indexed files from database: {e}")
            return []

    def _get_file_index_timestamps(self) -> Dict[str, datetime]:
        """Get file index timestamps from Filesystem database."""
        try:
            return self.vector_store_client.get_file_index_timestamps()

        except Exception as e:
            logger.error(f"Failed to get file index timestamps: {e}")
            return {}

    def _generate_recommendations(
        self,
        completeness_result: ValidationResult,
        quality_result: ValidationResult,
        consistency_result: ValidationResult,
        performance_score: float,
        all_errors: List[ValidationError],
    ) -> List[str]:
        """Generate actionable recommendations based on validation results."""
        recommendations = []

        # Completeness recommendations
        if completeness_result.missing_files:
            if len(completeness_result.missing_files) < 50:
                recommendations.append(
                    f"Run incremental indexing to add {len(completeness_result.missing_files)} missing files to the index"
                )
            else:
                recommendations.append(
                    f"Consider full re-indexing due to large number of missing files ({len(completeness_result.missing_files)})"
                )

        if completeness_result.extra_indexed_files:
            recommendations.append(
                f"Clean up {len(completeness_result.extra_indexed_files)} stale index entries for deleted/moved files"
            )

        # Quality recommendations
        if quality_result.corruption_detected:
            recommendations.append(
                "Perform full re-index immediately due to detected index corruption"
            )
        elif quality_result.quality_score < 0.8:
            recommendations.append(
                "Consider re-indexing affected files to improve embedding quality"
            )

        # Consistency recommendations
        if consistency_result.outdated_files:
            if len(consistency_result.outdated_files) < 20:
                recommendations.append(
                    f"Update index for {len(consistency_result.outdated_files)} modified files using incremental indexing"
                )
            else:
                recommendations.append(
                    f"Perform full re-index due to many outdated files ({len(consistency_result.outdated_files)})"
                )

        # Performance recommendations
        if performance_score < 0.7:
            recommendations.append(
                "Optimize index performance through collection compaction or re-indexing"
            )

        # Critical error recommendations
        critical_errors = [e for e in all_errors if e.is_critical]
        if critical_errors:
            recommendations.insert(
                0,
                f"Address {len(critical_errors)} critical validation errors immediately",
            )

        return recommendations
