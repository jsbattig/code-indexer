"""
Re-indexing Decision Engine for CIDX Server - Story 8 Implementation.

Analyzes repository changes and index metrics to intelligently determine
when full re-indexing is needed instead of incremental indexing.
"""

import logging
from typing import Optional, List, TypedDict

from code_indexer.server.middleware.correlation import get_correlation_id
from .reindexing_config import ReindexingConfig
from .reindexing_models import (
    ReindexingDecision,
    ChangeSet,
    IndexMetrics,
    ReindexingContext,
)


class ChangeImpact(TypedDict):
    """Type definition for change impact analysis results."""

    severity: str
    affected_areas: List[str]
    risk_factors: List[str]
    recommendations: List[str]


# Configure logging
logger = logging.getLogger(__name__)


class ReindexingDecisionEngine:
    """
    Intelligent decision engine for determining when full re-indexing is needed.

    Analyzes multiple factors including:
    - Change percentage thresholds
    - Configuration file modifications
    - Structural repository changes
    - Index quality metrics
    - Age-based triggers
    - Corruption detection
    - User requests
    """

    def __init__(self, config: Optional[ReindexingConfig] = None):
        """
        Initialize ReindexingDecisionEngine.

        Args:
            config: Configuration for thresholds and behavior (uses defaults if None)
        """
        self.config = config or ReindexingConfig()
        logger.info("ReindexingDecisionEngine initialized with config: %s", self.config)

    @classmethod
    def from_config(cls, cidx_config) -> "ReindexingDecisionEngine":
        """Create decision engine from CIDX configuration."""
        reindexing_config = ReindexingConfig.from_cidx_config(cidx_config)
        return cls(config=reindexing_config)

    def should_full_reindex(
        self,
        change_set: ChangeSet,
        metrics: IndexMetrics,
        context: Optional[ReindexingContext] = None,
        force_full_reindex: bool = False,
    ) -> ReindexingDecision:
        """
        Analyze whether full re-indexing should be performed.

        Args:
            change_set: Repository changes to analyze
            metrics: Current index quality metrics
            context: Additional context for decision making
            force_full_reindex: User-requested forced full re-index

        Returns:
            ReindexingDecision with analysis results and recommendation
        """
        logger.info(
            "Analyzing re-indexing decision: %d changes (%.1f%%), "
            "accuracy %.2f, age %d days",
            change_set.change_count,
            change_set.percentage_changed * 100,
            metrics.search_accuracy,
            metrics.index_age_days,
        )

        decision = ReindexingDecision(
            should_reindex=False,
            change_percentage=change_set.percentage_changed,
            search_accuracy=metrics.search_accuracy,
            index_age_days=metrics.index_age_days,
        )

        # Apply decision rules in priority order
        self._analyze_user_request(decision, force_full_reindex)
        self._analyze_corruption(decision, metrics)
        self._analyze_config_changes(decision, change_set)
        self._analyze_change_percentage(decision, change_set)
        self._analyze_structural_changes(decision, change_set)
        self._analyze_search_quality(decision, metrics)
        self._analyze_index_age(decision, metrics)

        # Set final recommendation details
        self._finalize_decision(decision, change_set, metrics, context)

        logger.info(
            "Re-indexing decision: %s (triggers: %s)",
            "FULL" if decision.should_reindex else "INCREMENTAL",
            ", ".join(decision.trigger_reasons) if decision.trigger_reasons else "none",
        )

        return decision

    def _analyze_user_request(
        self, decision: ReindexingDecision, force_full: bool
    ) -> None:
        """Analyze user-requested full re-index."""
        if force_full:
            decision.should_reindex = True
            decision.add_trigger_reason("user_requested")
            decision.confidence_score = 1.0
            logger.debug("User requested full re-index")

    def _analyze_corruption(
        self, decision: ReindexingDecision, metrics: IndexMetrics
    ) -> None:
        """Analyze index corruption detection."""
        if not self.config.enable_corruption_detection:
            return

        if metrics.corruption_detected:
            decision.should_reindex = True
            decision.add_trigger_reason("corruption_detected")
            decision.confidence_score = 1.0
            logger.warning(
                "Index corruption detected - full re-index required",
                extra={"correlation_id": get_correlation_id()},
            )

    def _analyze_config_changes(
        self, decision: ReindexingDecision, change_set: ChangeSet
    ) -> None:
        """Analyze configuration file changes."""
        if not self.config.enable_config_change_detection:
            return

        # Check if any changed files are configuration files
        config_files_changed = []
        all_changed_files = (
            change_set.files_changed + change_set.files_added + change_set.files_deleted
        )

        for file_path in all_changed_files:
            if self.config.is_config_file(file_path):
                config_files_changed.append(file_path)

        if config_files_changed or change_set.has_config_changes:
            decision.should_reindex = True
            decision.add_trigger_reason("config_changes")
            decision.confidence_score = 0.95
            logger.info(
                "Configuration changes detected: %s",
                (
                    ", ".join(config_files_changed)
                    if config_files_changed
                    else "structural config changes"
                ),
            )

    def _analyze_change_percentage(
        self, decision: ReindexingDecision, change_set: ChangeSet
    ) -> None:
        """Analyze change percentage threshold."""
        if change_set.percentage_changed > self.config.change_percentage_threshold:
            decision.should_reindex = True
            decision.add_trigger_reason("change_percentage")

            # Higher confidence for larger change percentages
            excess_ratio = (
                change_set.percentage_changed - self.config.change_percentage_threshold
            ) / 0.7
            decision.confidence_score = max(
                decision.confidence_score, 0.8 + min(0.2, excess_ratio * 0.2)
            )

            logger.info(
                "Change percentage %.1f%% exceeds threshold %.1f%%",
                change_set.percentage_changed * 100,
                self.config.change_percentage_threshold * 100,
            )

    def _analyze_structural_changes(
        self, decision: ReindexingDecision, change_set: ChangeSet
    ) -> None:
        """Analyze structural repository changes."""
        if not self.config.enable_structural_change_detection:
            return

        # Check explicit structural change flag
        if change_set.has_structural_changes:
            decision.should_reindex = True
            decision.add_trigger_reason("structural_changes")
            decision.confidence_score = max(decision.confidence_score, 0.85)
            logger.info("Structural changes detected (explicit flag)")

        # Check directory changes
        dir_changes = len(change_set.directories_added) + len(
            change_set.directories_removed
        )
        if dir_changes >= self.config.structural_change_threshold:
            decision.should_reindex = True
            decision.add_trigger_reason("structural_changes")
            decision.confidence_score = max(decision.confidence_score, 0.8)
            logger.info(
                "Structural changes detected: %d directory changes", dir_changes
            )

        # Check file moves
        if len(change_set.file_moves) >= self.config.max_file_moves_threshold:
            decision.should_reindex = True
            decision.add_trigger_reason("structural_changes")
            decision.confidence_score = max(decision.confidence_score, 0.75)
            logger.info(
                "Structural changes detected: %d file moves", len(change_set.file_moves)
            )

        # Check structural indicator files
        all_changed_files = (
            change_set.files_changed + change_set.files_added + change_set.files_deleted
        )

        structural_files_changed = [
            f for f in all_changed_files if self.config.is_structural_indicator(f)
        ]

        if structural_files_changed:
            decision.should_reindex = True
            decision.add_trigger_reason("structural_changes")
            decision.confidence_score = max(decision.confidence_score, 0.8)
            logger.info(
                "Structural indicator files changed: %s",
                ", ".join(structural_files_changed),
            )

    def _analyze_search_quality(
        self, decision: ReindexingDecision, metrics: IndexMetrics
    ) -> None:
        """Analyze search quality degradation."""
        if metrics.search_accuracy < self.config.accuracy_threshold:
            decision.should_reindex = True
            decision.add_trigger_reason("search_accuracy")

            # Lower accuracy = higher confidence in need for re-index
            accuracy_deficit = self.config.accuracy_threshold - metrics.search_accuracy
            decision.confidence_score = max(
                decision.confidence_score, 0.7 + min(0.3, accuracy_deficit * 1.5)
            )

            logger.info(
                "Search accuracy %.2f below threshold %.2f",
                metrics.search_accuracy,
                self.config.accuracy_threshold,
            )

    def _analyze_index_age(
        self, decision: ReindexingDecision, metrics: IndexMetrics
    ) -> None:
        """Analyze index age for periodic re-indexing."""
        if not self.config.enable_periodic_reindex:
            return

        if metrics.index_age_days > self.config.max_index_age_days:
            decision.should_reindex = True
            decision.add_trigger_reason("index_age")

            # Confidence increases with age
            age_excess = metrics.index_age_days - self.config.max_index_age_days
            decision.confidence_score = max(
                decision.confidence_score,
                0.6
                + min(
                    0.4, (age_excess / 30) * 0.4
                ),  # Max confidence after 30 extra days
            )

            logger.info(
                "Index age %d days exceeds threshold %d days",
                metrics.index_age_days,
                self.config.max_index_age_days,
            )

    def _finalize_decision(
        self,
        decision: ReindexingDecision,
        change_set: ChangeSet,
        metrics: IndexMetrics,
        context: Optional[ReindexingContext],
    ) -> None:
        """Finalize decision with strategy and time estimates."""
        if not decision.should_reindex:
            decision.recommended_strategy = "incremental"
            decision.estimated_time_minutes = 0
            return

        # Determine recommended strategy
        if context:
            decision.recommended_strategy = context.recommended_strategy
        else:
            # Default strategy based on change characteristics
            if "corruption_detected" in decision.trigger_reasons:
                decision.recommended_strategy = "in_place"  # Need immediate fix
            elif change_set.change_count > 1000:  # Large changes
                decision.recommended_strategy = "blue_green"
            else:
                decision.recommended_strategy = "in_place"

        # Estimate time
        decision.estimated_time_minutes = self.config.estimate_reindex_time_minutes(
            total_files=change_set.total_files,
            repository_size_mb=(
                context.repository_size_mb if context else 100.0
            ),  # Default estimate
        )

        # Ensure confidence score is set
        if decision.confidence_score == 1.0 and len(decision.trigger_reasons) > 1:
            # Multiple triggers reduce individual confidence but increase overall confidence
            decision.confidence_score = min(
                1.0, 0.7 + (len(decision.trigger_reasons) * 0.1)
            )

    def get_trigger_explanations(self) -> dict:
        """Get human-readable explanations for each trigger type."""
        return {
            "user_requested": "User explicitly requested full re-indexing",
            "corruption_detected": "Index corruption detected - full rebuild required",
            "config_changes": "Configuration files changed - may affect indexing behavior",
            "change_percentage": f"Changes exceed {self.config.change_percentage_threshold*100:.0f}% threshold",
            "structural_changes": "Major repository structure changes detected",
            "search_accuracy": f"Search accuracy below {self.config.accuracy_threshold*100:.0f}% threshold",
            "index_age": f"Index older than {self.config.max_index_age_days} days",
        }

    def analyze_change_impact(self, change_set: ChangeSet) -> ChangeImpact:
        """Analyze the potential impact of changes on search quality."""
        affected_areas: List[str] = []
        risk_factors: List[str] = []
        recommendations: List[str] = []

        impact: ChangeImpact = {
            "severity": "low",
            "affected_areas": affected_areas,
            "risk_factors": risk_factors,
            "recommendations": recommendations,
        }

        # Analyze severity
        if change_set.percentage_changed > 0.5:
            impact["severity"] = "high"
        elif change_set.percentage_changed > 0.2:
            impact["severity"] = "medium"

        # Identify affected areas
        if change_set.has_config_changes:
            impact["affected_areas"].append("indexing_configuration")

        if change_set.has_structural_changes:
            impact["affected_areas"].append("repository_structure")

        if change_set.has_schema_changes:
            impact["affected_areas"].append("data_schema")

        # Identify risk factors
        if len(change_set.files_deleted) > 0:
            impact["risk_factors"].append(
                f"{len(change_set.files_deleted)} files deleted"
            )

        if len(change_set.directories_removed) > 0:
            impact["risk_factors"].append(
                f"{len(change_set.directories_removed)} directories removed"
            )

        if len(change_set.file_moves) > 5:
            impact["risk_factors"].append(f"{len(change_set.file_moves)} files moved")

        # Generate recommendations
        if impact["severity"] == "high":
            impact["recommendations"].append(
                "Consider full re-indexing for optimal search quality"
            )

        if "indexing_configuration" in impact["affected_areas"]:
            impact["recommendations"].append(
                "Configuration changes may require full re-index"
            )

        if not impact["recommendations"]:
            impact["recommendations"].append(
                "Incremental indexing should be sufficient"
            )

        return impact
