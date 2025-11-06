"""
Temporal Progressive Metadata - Track indexing progress for resume capability.
"""

import json
from pathlib import Path
from typing import Set


class TemporalProgressiveMetadata:
    """Track progressive state for temporal indexing resume capability."""

    def __init__(self, temporal_dir: Path):
        """Initialize progressive metadata tracker."""
        self.temporal_dir = temporal_dir
        self.progress_path = temporal_dir / "temporal_progress.json"

    def save_completed(self, commit_hash: str) -> None:
        """Mark a commit as completed."""
        # Load existing data
        data = self._load()

        # Initialize completed_commits if not exists
        if "completed_commits" not in data:
            data["completed_commits"] = []

        # Add commit
        data["completed_commits"].append(commit_hash)
        data["status"] = "in_progress"

        # Save
        with open(self.progress_path, 'w') as f:
            json.dump(data, f, indent=2)

    def load_completed(self) -> Set[str]:
        """Load set of completed commit hashes."""
        data = self._load()
        return set(data.get("completed_commits", []))

    def clear(self) -> None:
        """Clear progress tracking."""
        if self.progress_path.exists():
            self.progress_path.unlink()

    def _load(self):
        """Load progress data from file."""
        if not self.progress_path.exists():
            return {}

        try:
            with open(self.progress_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}