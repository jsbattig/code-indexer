"""
Index Health Checker for CIDX Server - Story 9 Implementation.

Specialized health checking for embedding quality, corruption detection,
and performance analysis. Following CLAUDE.md Foundation #1: NO MOCKS -
real health checking with actual data.
"""

import logging
import time
import numpy as np
from datetime import datetime

from .models import HealthCheckResult
from .exceptions import IndexCorruptionError
from ...config import Config
from ...storage.filesystem_vector_store import FilesystemVectorStore

logger = logging.getLogger(__name__)


class IndexHealthChecker:
    """
    Specialized health checker for embedding quality and corruption detection.

    Performs detailed analysis of embedding vectors, metadata integrity,
    and query performance to ensure index health and quality.
    """

    def __init__(self, config: Config, vector_store_client: FilesystemVectorStore):
        """
        Initialize IndexHealthChecker.

        Args:
            config: CIDX configuration
            vector_store_client: Vector store client for database operations
        """
        self.config = config
        self.vector_store_client = vector_store_client

        # Health check configuration
        self.sample_size = getattr(config, "validation_sample_size", 100)
        self.performance_sample_queries = getattr(
            config, "validation_performance_queries", 5
        )
        self.expected_dimensions = getattr(
            config.voyage_ai, "embedding_dimensions", 1024
        )

        # Quality thresholds
        self.dimension_consistency_threshold = 0.95
        self.vector_quality_threshold = 0.8
        self.metadata_completeness_threshold = 0.9
        self.performance_threshold_ms = 100

        logger.info("IndexHealthChecker initialized")

    def check_embedding_dimensions(self) -> HealthCheckResult:
        """
        Check embedding dimension consistency across the index.

        Returns:
            HealthCheckResult with dimension consistency analysis
        """
        try:
            logger.info("Checking embedding dimensions consistency")

            # Get sample of embeddings from vector store
            sample_embeddings = self.vector_store_client.sample_vectors(
                self.sample_size
            )

            if not sample_embeddings:
                logger.warning("No embeddings found in index for dimension checking")
                return HealthCheckResult(
                    is_healthy=False,
                    dimension_consistency_score=0.0,
                    expected_dimensions=self.expected_dimensions,
                    actual_dimensions=[],
                    dimension_violations=[],
                )

            # Analyze dimensions
            actual_dimensions = []
            dimension_violations = []
            correct_dimensions = 0

            for embedding in sample_embeddings:
                vector = embedding.get("vector", [])
                file_path = embedding.get("payload", {}).get("file_path", "unknown")

                actual_dim = len(vector) if vector else 0
                actual_dimensions.append(actual_dim)

                if actual_dim == self.expected_dimensions:
                    correct_dimensions += 1
                else:
                    dimension_violations.append(
                        {
                            "file_path": file_path,
                            "expected_dimensions": self.expected_dimensions,
                            "actual_dimensions": actual_dim,
                            "embedding_id": embedding.get("id"),
                        }
                    )

            # Calculate consistency score
            total_embeddings = len(sample_embeddings)
            consistency_score = (
                correct_dimensions / total_embeddings if total_embeddings > 0 else 0.0
            )

            # Determine health status
            is_healthy = consistency_score >= self.dimension_consistency_threshold

            logger.info(
                f"Dimension consistency check completed: "
                f"{consistency_score:.2f} score, {len(dimension_violations)} violations"
            )

            return HealthCheckResult(
                is_healthy=is_healthy,
                dimension_consistency_score=consistency_score,
                expected_dimensions=self.expected_dimensions,
                actual_dimensions=actual_dimensions,
                dimension_violations=dimension_violations,
            )

        except Exception as e:
            logger.error(f"Embedding dimension check failed: {e}", exc_info=True)
            raise IndexCorruptionError(
                f"Failed to check embedding dimensions: {str(e)}",
                corruption_type="dimension_check_failed",
            )

    def check_vector_quality(self) -> HealthCheckResult:
        """
        Analyze vector quality for corruption, zeros, NaNs, and variance.

        Returns:
            HealthCheckResult with vector quality analysis
        """
        try:
            logger.info("Analyzing vector quality for corruption detection")

            # Get sample of embeddings from Filesystem
            sample_embeddings = self.vector_store_client.sample_vectors(
                self.sample_size
            )

            if not sample_embeddings:
                logger.warning("No embeddings found for vector quality analysis")
                return HealthCheckResult(
                    is_healthy=False,
                    quality_score=0.0,
                    zero_vector_count=0,
                    nan_vector_count=0,
                    variance_score=0.0,
                    corrupt_files=[],
                )

            # Analyze vector quality
            zero_vector_count = 0
            nan_vector_count = 0
            corrupt_files = []
            variances = []

            for embedding in sample_embeddings:
                vector = embedding.get("vector", [])
                file_path = embedding.get("payload", {}).get("file_path", "unknown")

                if not vector:
                    corrupt_files.append(file_path)
                    continue

                # Convert to numpy array for analysis
                try:
                    vec_array = np.array(vector, dtype=np.float32)

                    # Check for zero vectors
                    if np.allclose(vec_array, 0.0):
                        zero_vector_count += 1
                        corrupt_files.append(file_path)
                        continue

                    # Check for NaN values
                    if np.any(np.isnan(vec_array)):
                        nan_vector_count += 1
                        corrupt_files.append(file_path)
                        continue

                    # Calculate variance for quality assessment
                    variance = float(np.var(vec_array))
                    variances.append(variance)

                    # Check for suspiciously low variance (constant or near-constant vectors)
                    if variance < 1e-6:
                        corrupt_files.append(file_path)

                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to analyze vector for {file_path}: {e}")
                    corrupt_files.append(file_path)

            # Calculate quality metrics
            total_embeddings = len(sample_embeddings)
            healthy_vectors = (
                total_embeddings
                - zero_vector_count
                - nan_vector_count
                - len(set(corrupt_files))
            )
            quality_score = (
                healthy_vectors / total_embeddings if total_embeddings > 0 else 0.0
            )

            # Calculate average variance (indicator of meaningful embeddings)
            variance_score = np.mean(variances) if variances else 0.0

            # Normalize variance score (typical good variance is 0.1-0.5)
            normalized_variance_score = (
                min(1.0, variance_score / 0.3) if variance_score > 0 else 0.0
            )

            # Overall quality combines vector health and variance
            overall_quality = (quality_score + normalized_variance_score) / 2.0

            # Determine health status
            is_healthy = bool(overall_quality >= self.vector_quality_threshold)

            logger.info(
                f"Vector quality check completed: {overall_quality:.2f} score, "
                f"{zero_vector_count} zero vectors, {nan_vector_count} NaN vectors"
            )

            return HealthCheckResult(
                is_healthy=is_healthy,
                quality_score=overall_quality,
                zero_vector_count=zero_vector_count,
                nan_vector_count=nan_vector_count,
                variance_score=normalized_variance_score,
                corrupt_files=list(set(corrupt_files)),  # Remove duplicates
            )

        except Exception as e:
            logger.error(f"Vector quality check failed: {e}", exc_info=True)
            raise IndexCorruptionError(
                f"Failed to analyze vector quality: {str(e)}",
                corruption_type="vector_quality_check_failed",
            )

    def check_metadata_integrity(self) -> HealthCheckResult:
        """
        Check metadata integrity and completeness in index entries.

        Returns:
            HealthCheckResult with metadata integrity analysis
        """
        try:
            logger.info("Checking metadata integrity")

            # Get sample of embeddings with metadata
            sample_embeddings = self.vector_store_client.sample_vectors(
                self.sample_size
            )

            if not sample_embeddings:
                logger.warning("No embeddings found for metadata integrity check")
                return HealthCheckResult(
                    is_healthy=False,
                    completeness_score=0.0,
                    missing_metadata_count=0,
                    invalid_metadata_count=0,
                    metadata_errors=[],
                )

            # Required metadata fields
            required_fields = ["file_path", "language", "chunk_index", "indexed_at"]

            # Analyze metadata integrity
            missing_metadata_count = 0
            invalid_metadata_count = 0
            metadata_errors = []
            complete_metadata_count = 0

            for embedding in sample_embeddings:
                payload = embedding.get("payload", {})
                embedding_id = embedding.get("id", "unknown")

                # Check for completely missing payload
                if not payload:
                    missing_metadata_count += 1
                    metadata_errors.append(
                        {
                            "embedding_id": embedding_id,
                            "error": "missing_payload",
                            "description": "Completely missing metadata payload",
                        }
                    )
                    continue

                # Check required fields
                missing_required = []
                invalid_fields = []

                for field in required_fields:
                    if field not in payload:
                        missing_required.append(field)
                    elif payload[field] is None or (
                        isinstance(payload[field], str) and not payload[field].strip()
                    ):
                        invalid_fields.append(field)

                # Validate specific field formats
                if "indexed_at" in payload:
                    try:
                        # Try to parse the timestamp
                        if isinstance(payload["indexed_at"], str):
                            datetime.fromisoformat(
                                payload["indexed_at"].replace("Z", "+00:00")
                            )
                    except (ValueError, TypeError):
                        invalid_fields.append("indexed_at")

                if "chunk_index" in payload:
                    try:
                        # Validate that chunk_index can be converted to int
                        chunk_idx = payload["chunk_index"]
                        if chunk_idx is None:
                            invalid_fields.append("chunk_index")
                        elif isinstance(chunk_idx, (int, float)):
                            # Numeric values are valid (including 0)
                            pass
                        elif isinstance(chunk_idx, str):
                            # String values must be convertible to int
                            if chunk_idx.strip() == "":
                                invalid_fields.append("chunk_index")
                            else:
                                int(chunk_idx)  # Try to convert to int
                        else:
                            # Other types are invalid
                            invalid_fields.append("chunk_index")
                    except (ValueError, TypeError):
                        invalid_fields.append("chunk_index")

                # Record errors
                if missing_required:
                    missing_metadata_count += 1
                    metadata_errors.append(
                        {
                            "embedding_id": embedding_id,
                            "file_path": payload.get("file_path", "unknown"),
                            "error": "missing_required_fields",
                            "missing_fields": missing_required,
                        }
                    )

                if invalid_fields:
                    invalid_metadata_count += 1
                    metadata_errors.append(
                        {
                            "embedding_id": embedding_id,
                            "file_path": payload.get("file_path", "unknown"),
                            "error": "invalid_field_values",
                            "invalid_fields": invalid_fields,
                        }
                    )

                # Count complete metadata
                if not missing_required and not invalid_fields:
                    complete_metadata_count += 1

            # Calculate completeness score
            total_embeddings = len(sample_embeddings)
            completeness_score = (
                complete_metadata_count / total_embeddings
                if total_embeddings > 0
                else 0.0
            )

            # Determine health status
            is_healthy = completeness_score >= self.metadata_completeness_threshold

            logger.info(
                f"Metadata integrity check completed: {completeness_score:.2f} completeness, "
                f"{missing_metadata_count} missing, {invalid_metadata_count} invalid"
            )

            return HealthCheckResult(
                is_healthy=is_healthy,
                completeness_score=completeness_score,
                missing_metadata_count=missing_metadata_count,
                invalid_metadata_count=invalid_metadata_count,
                metadata_errors=metadata_errors,
            )

        except Exception as e:
            logger.error(f"Metadata integrity check failed: {e}", exc_info=True)
            raise IndexCorruptionError(
                f"Failed to check metadata integrity: {str(e)}",
                corruption_type="metadata_check_failed",
            )

    def measure_query_performance(self) -> HealthCheckResult:
        """
        Measure query performance to detect degradation.

        Returns:
            HealthCheckResult with performance metrics
        """
        try:
            logger.info("Measuring query performance")

            # Generate test query vectors (random vectors for performance testing)
            query_times = []
            slow_queries = []

            for i in range(self.performance_sample_queries):
                # Create a random query vector with correct dimensions
                query_vector = np.random.normal(
                    0, 0.5, self.expected_dimensions
                ).tolist()

                # Measure query time
                start_time = time.time()
                try:
                    results = self.vector_store_client.search(
                        collection_name=None,  # Let FilesystemVectorStore resolve the collection name
                        query_vector=query_vector,
                        limit=10,
                    )
                    end_time = time.time()

                    query_time_ms = (end_time - start_time) * 1000
                    query_times.append(query_time_ms)

                    # Track slow queries
                    if query_time_ms > self.performance_threshold_ms:
                        slow_queries.append(
                            {
                                "query_id": i,
                                "query_time_ms": query_time_ms,
                                "results_count": len(results) if results else 0,
                            }
                        )

                except Exception as e:
                    logger.warning(f"Query {i} failed: {e}")
                    # Consider failed queries as very slow
                    query_times.append(10000.0)  # 10 second penalty
                    slow_queries.append(
                        {
                            "query_id": i,
                            "query_time_ms": 10000.0,
                            "error_code": 1.0,
                        }  # Error indicator
                    )

            # Calculate performance metrics
            if query_times:
                average_query_time = sum(query_times) / len(query_times)
                slowest_query_time = max(query_times)
            else:
                average_query_time = float("inf")
                slowest_query_time = float("inf")

            # Calculate performance score (inverse relationship with query time)
            if average_query_time <= self.performance_threshold_ms:
                performance_score = 1.0
            elif average_query_time <= self.performance_threshold_ms * 2:
                # Linear decay from 1.0 to 0.5 for times up to 2x threshold
                performance_score = 1.0 - 0.5 * (
                    (average_query_time - self.performance_threshold_ms)
                    / self.performance_threshold_ms
                )
            else:
                # Exponential decay for very slow queries
                performance_score = 0.5 * np.exp(
                    -average_query_time / (self.performance_threshold_ms * 2)
                )

            performance_score = float(max(0.0, min(1.0, performance_score)))

            # Determine if performance is acceptable
            is_performant = bool(performance_score >= 0.7)

            logger.info(
                f"Query performance measurement completed: {average_query_time:.1f}ms average, "
                f"{performance_score:.2f} score"
            )

            return HealthCheckResult(
                is_healthy=is_performant,
                is_performant=is_performant,
                average_query_time_ms=average_query_time,
                slowest_query_time_ms=slowest_query_time,
                performance_score=performance_score,
                slow_queries=slow_queries,
            )

        except Exception as e:
            logger.error(f"Query performance measurement failed: {e}", exc_info=True)
            # Return degraded performance result rather than raising exception
            return HealthCheckResult(
                is_healthy=False,
                is_performant=False,
                average_query_time_ms=float("inf"),
                slowest_query_time_ms=float("inf"),
                performance_score=0.0,
                slow_queries=[{"error": f"Performance measurement failed: {str(e)}"}],
            )

    def collect_index_statistics(self) -> HealthCheckResult:
        """
        Collect comprehensive index statistics.

        Returns:
            HealthCheckResult with detailed index statistics
        """
        try:
            logger.info("Collecting index statistics")

            # Get collection info from Filesystem
            collection_info = self.vector_store_client.get_collection_info()

            # Extract basic statistics
            total_documents = collection_info.get("points_count", 0)
            total_vectors = collection_info.get("vectors_count", 0)
            index_status = collection_info.get("status", "unknown")

            # Extract configuration details
            config_info = collection_info.get("config", {})
            vector_config = config_info.get("params", {}).get("vectors", {})
            vector_dimensions = vector_config.get("size", 0)
            distance_metric = vector_config.get("distance", "unknown")

            # Estimate storage usage (rough approximation)
            # Typical storage: vectors (dimensions * 4 bytes) + metadata overhead
            estimated_vector_storage_mb = (total_vectors * vector_dimensions * 4) / (
                1024 * 1024
            )
            estimated_metadata_storage_mb = (
                total_documents * 0.5 / 1024
            )  # ~0.5KB per document metadata
            storage_usage_mb = (
                estimated_vector_storage_mb + estimated_metadata_storage_mb
            )

            logger.info(
                f"Index statistics collected: {total_documents} documents, {total_vectors} vectors, "
                f"{storage_usage_mb:.1f}MB estimated storage"
            )

            return HealthCheckResult(
                is_healthy=True,  # Statistics collection itself succeeded
                total_documents=total_documents,
                total_vectors=total_vectors,
                index_status=index_status,
                vector_dimensions=vector_dimensions,
                distance_metric=distance_metric,
                storage_usage_mb=storage_usage_mb,
            )

        except Exception as e:
            logger.error(f"Failed to collect index statistics: {e}", exc_info=True)
            # Return empty statistics rather than raising exception
            return HealthCheckResult(
                is_healthy=False,
                total_documents=0,
                total_vectors=0,
                index_status="error",
                vector_dimensions=0,
                distance_metric="unknown",
                storage_usage_mb=0.0,
            )

    def comprehensive_health_check(self) -> HealthCheckResult:
        """
        Run comprehensive health check combining all health checks.

        Returns:
            Combined HealthCheckResult with overall health assessment
        """
        try:
            logger.info("Running comprehensive health check")

            # Run all health checks
            dimension_result = self.check_embedding_dimensions()
            quality_result = self.check_vector_quality()
            metadata_result = self.check_metadata_integrity()
            performance_result = self.measure_query_performance()
            statistics_result = self.collect_index_statistics()

            # Combine results
            critical_issues = []
            warnings = []
            recommendations = []

            # Check for critical issues
            if not dimension_result.is_healthy:
                critical_issues.append(
                    f"Embedding dimension inconsistency: {len(dimension_result.dimension_violations)} violations"
                )
                recommendations.append(
                    "Perform full re-index to fix dimension inconsistencies"
                )

            if (
                quality_result.zero_vector_count > 0
                or quality_result.nan_vector_count > 0
            ):
                critical_issues.append(
                    f"Vector corruption detected: {quality_result.zero_vector_count} zero vectors, "
                    f"{quality_result.nan_vector_count} NaN vectors"
                )
                recommendations.append(
                    "Full re-index required to fix corrupted embeddings"
                )

            if not metadata_result.is_healthy:
                if (
                    metadata_result.missing_metadata_count
                    > metadata_result.invalid_metadata_count
                ):
                    warnings.append(
                        f"Missing metadata for {metadata_result.missing_metadata_count} entries"
                    )
                    recommendations.append(
                        "Incremental re-index to restore missing metadata"
                    )
                else:
                    warnings.append(
                        f"Invalid metadata for {metadata_result.invalid_metadata_count} entries"
                    )
                    recommendations.append(
                        "Metadata repair or incremental re-index needed"
                    )

            if not performance_result.is_performant:
                warnings.append(
                    f"Query performance degraded: {performance_result.average_query_time_ms:.1f}ms average"
                )
                recommendations.append(
                    "Consider index optimization or performance tuning"
                )

            # Calculate overall health score
            component_scores = [
                dimension_result.dimension_consistency_score,
                quality_result.quality_score,
                metadata_result.completeness_score,
                performance_result.performance_score,
            ]

            # Weight critical issues more heavily
            if critical_issues:
                overall_health_score = min(
                    0.3, sum(component_scores) / len(component_scores)
                )
            else:
                overall_health_score = sum(component_scores) / len(component_scores)

            # Determine overall health status
            is_healthy = overall_health_score >= 0.8 and len(critical_issues) == 0

            # Check for severe corruption that warrants exception
            if overall_health_score < 0.2 or len(critical_issues) >= 3:
                raise IndexCorruptionError(
                    "Severe index corruption detected - immediate action required",
                    corruption_type="comprehensive_health_failure",
                )

            logger.info(
                f"Comprehensive health check completed: {overall_health_score:.2f} health score, "
                f"{len(critical_issues)} critical issues, {len(warnings)} warnings"
            )

            # Combine all results into comprehensive result
            return HealthCheckResult(
                is_healthy=is_healthy,
                overall_health_score=overall_health_score,
                critical_issues=critical_issues,
                warnings=warnings,
                recommendations=recommendations,
                # Dimension results
                dimension_consistency_score=dimension_result.dimension_consistency_score,
                expected_dimensions=dimension_result.expected_dimensions,
                actual_dimensions=dimension_result.actual_dimensions,
                dimension_violations=dimension_result.dimension_violations,
                # Quality results
                quality_score=quality_result.quality_score,
                zero_vector_count=quality_result.zero_vector_count,
                nan_vector_count=quality_result.nan_vector_count,
                variance_score=quality_result.variance_score,
                corrupt_files=quality_result.corrupt_files,
                # Metadata results
                completeness_score=metadata_result.completeness_score,
                missing_metadata_count=metadata_result.missing_metadata_count,
                invalid_metadata_count=metadata_result.invalid_metadata_count,
                metadata_errors=metadata_result.metadata_errors,
                # Performance results
                is_performant=performance_result.is_performant,
                average_query_time_ms=performance_result.average_query_time_ms,
                slowest_query_time_ms=performance_result.slowest_query_time_ms,
                performance_score=performance_result.performance_score,
                slow_queries=performance_result.slow_queries,
                # Statistics results
                total_documents=statistics_result.total_documents,
                total_vectors=statistics_result.total_vectors,
                index_status=statistics_result.index_status,
                vector_dimensions=statistics_result.vector_dimensions,
                distance_metric=statistics_result.distance_metric,
                storage_usage_mb=statistics_result.storage_usage_mb,
            )

        except IndexCorruptionError:
            raise  # Re-raise corruption errors
        except Exception as e:
            logger.error(f"Comprehensive health check failed: {e}", exc_info=True)
            raise IndexCorruptionError(
                f"Health check system failure: {str(e)}",
                corruption_type="health_check_system_failure",
            )
