"""
Individual file progress line tracker for Rich Progress Display Feature 3.

Manages file processing status lines with format:
├─ filename (size, elapsed) status_label

Status labels:
- "vectorizing..." (during processing)
- "complete" (finished, displayed for exactly 3 seconds before removal)
"""

import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from rich.console import Console


class FileLineTracker:
    """Individual file progress line tracker.

    Manages file processing status lines with format:
    ├─ filename (size, elapsed) status_label

    Status labels:
    - "vectorizing..." (during processing)
    - "complete" (finished, displayed for exactly 3 seconds before removal)
    """

    def __init__(self, console: Console = None):
        self.console = console or Console()
        self.active_files: Dict[str, Dict[str, Any]] = {}

    def start_file_processing(self, file_path: Path, file_size: int) -> None:
        """Start tracking processing for a file."""
        file_key = str(file_path)
        current_time = time.time()

        self.active_files[file_key] = {
            "path": file_path,
            "size": file_size,
            "start_time": current_time,
            "status": "processing",
            "completion_time": None,
        }

    def update_file_status(self, file_path: Path, status: str) -> str:
        """Update file status and return formatted line."""
        file_key = str(file_path)
        current_time = time.time()

        # Auto-start if not already tracking
        if file_key not in self.active_files:
            self.start_file_processing(file_path, 0)  # Default size 0 for unknown files

        file_info = self.active_files[file_key]
        file_info["status"] = status

        # Format the line
        filename = file_path.name
        size_str = self.format_file_size(file_info["size"])
        elapsed_str = self.format_elapsed_time(current_time - file_info["start_time"])

        status_label = "vectorizing..." if status == "vectorizing" else status

        return f"├─ {filename} ({size_str}, {elapsed_str}) {status_label}"

    def complete_file_processing(self, file_path: Path) -> None:
        """Mark file as complete and schedule removal."""
        file_key = str(file_path)
        current_time = time.time()

        if file_key in self.active_files:
            self.active_files[file_key]["status"] = "complete"
            self.active_files[file_key]["completion_time"] = current_time

    def get_active_file_lines(self, current_time: Optional[float] = None) -> List[str]:
        """Get all currently active file lines."""
        if current_time is None:
            current_time = time.time()

        active_lines = []
        files_to_remove = []

        for file_key, file_info in self.active_files.items():
            # Check if completed files should be removed (after 3 seconds)
            if (
                file_info["status"] == "complete"
                and file_info["completion_time"]
                and current_time - file_info["completion_time"] >= 3.0
            ):
                files_to_remove.append(file_key)
                continue

            # Generate line for active files
            filename = file_info["path"].name
            size_str = self.format_file_size(file_info["size"])
            elapsed_str = self.format_elapsed_time(
                current_time - file_info["start_time"]
            )

            if file_info["status"] == "complete":
                status_label = "complete"
            else:
                status_label = "vectorizing..."

            line = f"├─ {filename} ({size_str}, {elapsed_str}) {status_label}"
            active_lines.append(line)

        # Remove expired completed files
        for file_key in files_to_remove:
            del self.active_files[file_key]

        return active_lines

    def format_file_size(self, size_bytes: int) -> str:
        """Format file size in human-readable KB format."""
        size_kb = size_bytes / 1024.0
        return f"{size_kb:.1f} KB"

    def format_elapsed_time(self, elapsed_seconds: float) -> str:
        """Format elapsed processing time."""
        # Round to nearest second, with minimum of 1s
        rounded_seconds = max(1, round(elapsed_seconds))
        return f"{rounded_seconds}s"
