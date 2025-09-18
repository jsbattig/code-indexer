"""
Data models for re-indexing decision engine.

Defines data structures used by the ReindexingDecisionEngine for analyzing
repository changes and determining when full re-indexing is needed.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set


@dataclass
class ReindexingDecision:
    """Result of re-indexing decision analysis."""

    should_reindex: bool
    trigger_reasons: List[str] = field(default_factory=list)
    change_percentage: float = 0.0
    search_accuracy: float = 1.0
    index_age_days: int = 0
    confidence_score: float = 1.0
    recommended_strategy: str = "in_place"  # "in_place", "blue_green", "progressive"
    estimated_time_minutes: int = 0
    analysis_timestamp: Optional[datetime] = None

    def __post_init__(self):
        """Set analysis timestamp if not provided."""
        if self.analysis_timestamp is None:
            self.analysis_timestamp = datetime.now()

    @property
    def primary_trigger(self) -> Optional[str]:
        """Get the primary trigger reason."""
        return self.trigger_reasons[0] if self.trigger_reasons else None

    def add_trigger_reason(self, reason: str) -> None:
        """Add a trigger reason to the decision."""
        if reason not in self.trigger_reasons:
            self.trigger_reasons.append(reason)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "should_reindex": self.should_reindex,
            "trigger_reasons": self.trigger_reasons,
            "change_percentage": self.change_percentage,
            "search_accuracy": self.search_accuracy,
            "index_age_days": self.index_age_days,
            "confidence_score": self.confidence_score,
            "recommended_strategy": self.recommended_strategy,
            "estimated_time_minutes": self.estimated_time_minutes,
            "analysis_timestamp": (
                self.analysis_timestamp.isoformat() if self.analysis_timestamp else None
            ),
            "primary_trigger": self.primary_trigger,
        }


@dataclass
class ChangeSet:
    """Represents a set of repository changes for analysis."""

    files_changed: List[str] = field(default_factory=list)
    files_added: List[str] = field(default_factory=list)
    files_deleted: List[str] = field(default_factory=list)
    total_files: int = 0
    has_structural_changes: bool = False
    has_config_changes: bool = False
    has_schema_changes: bool = False
    directories_added: Set[str] = field(default_factory=set)
    directories_removed: Set[str] = field(default_factory=set)
    file_moves: List[tuple[str, str]] = field(default_factory=list)

    @property
    def percentage_changed(self) -> float:
        """Calculate percentage of files changed."""
        if self.total_files == 0:
            return 0.0
        changed_count = (
            len(self.files_changed) + len(self.files_added) + len(self.files_deleted)
        )
        return changed_count / self.total_files

    @property
    def change_count(self) -> int:
        """Total number of changes."""
        return len(self.files_changed) + len(self.files_added) + len(self.files_deleted)

    @property
    def structural_change_indicators(self) -> int:
        """Count of structural change indicators."""
        indicators = 0
        indicators += len(self.directories_added)
        indicators += len(self.directories_removed)
        indicators += len(self.file_moves)
        if "__init__.py" in " ".join(self.files_added + self.files_deleted):
            indicators += 1
        return indicators

    def is_config_file(self, file_path: str) -> bool:
        """Check if a file is a configuration file."""
        config_files = {
            ".cidx-config",
            ".gitignore",
            "pyproject.toml",
            "setup.py",
            "requirements.txt",
            "Dockerfile",
            "docker-compose.yml",
            "package.json",
            "tsconfig.json",
            "yarn.lock",
            "Pipfile",
            ".env",
            ".env.example",
            "tox.ini",
            "pytest.ini",
        }

        config_patterns = {".cfg", ".ini", ".conf", ".config", ".yml", ".yaml"}

        file_name = Path(file_path).name
        file_suffix = Path(file_path).suffix

        return file_name in config_files or file_suffix in config_patterns


@dataclass
class IndexMetrics:
    """Represents index quality and health metrics."""

    search_accuracy: float
    index_age_days: int
    corruption_detected: bool = False
    document_count: int = 0
    last_updated: Optional[datetime] = None
    query_performance_score: float = 1.0
    storage_size_mb: float = 0.0
    embedding_dimensions: int = 0

    def __post_init__(self):
        """Validate metrics values."""
        if not 0.0 <= self.search_accuracy <= 1.0:
            raise ValueError(
                f"Search accuracy must be between 0.0 and 1.0, got {self.search_accuracy}"
            )

        if self.index_age_days < 0:
            raise ValueError(f"Index age cannot be negative, got {self.index_age_days}")

        if self.document_count < 0:
            raise ValueError(
                f"Document count cannot be negative, got {self.document_count}"
            )

    @property
    def quality_score(self) -> float:
        """Calculate overall quality score (0.0 to 1.0)."""
        if self.corruption_detected:
            return 0.0

        # Combine accuracy and performance scores
        quality = (self.search_accuracy * 0.7) + (self.query_performance_score * 0.3)
        return min(1.0, max(0.0, quality))

    @property
    def is_stale(self, max_age_days: int = 30) -> bool:
        """Check if index is stale based on age threshold."""
        return self.index_age_days > max_age_days

    @property
    def health_status(self) -> str:
        """Get human-readable health status."""
        if self.corruption_detected:
            return "corrupted"
        elif self.quality_score < 0.7:
            return "poor"
        elif self.quality_score < 0.85:
            return "fair"
        else:
            return "excellent"


@dataclass
class ReindexingContext:
    """Context information for re-indexing decisions."""

    repository_path: Path
    repository_size_mb: float = 0.0
    available_memory_mb: float = 0.0
    available_disk_space_mb: float = 0.0
    concurrent_operations: int = 0
    user_requested_full: bool = False
    last_full_reindex: Optional[datetime] = None
    system_load: float = 0.0

    @property
    def has_sufficient_resources(self) -> bool:
        """Check if system has sufficient resources for full re-index."""
        # Basic heuristic: need at least 2x repository size in memory and disk
        memory_ok = self.available_memory_mb > (self.repository_size_mb * 2)
        disk_ok = self.available_disk_space_mb > (self.repository_size_mb * 3)
        load_ok = self.system_load < 0.8

        return memory_ok and disk_ok and load_ok

    @property
    def recommended_strategy(self) -> str:
        """Recommend indexing strategy based on context."""
        if not self.has_sufficient_resources:
            return "progressive"
        elif self.repository_size_mb > 1000:  # >1GB
            return "blue_green"
        else:
            return "in_place"
