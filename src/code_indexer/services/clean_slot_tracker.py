"""
Clean slot-based file tracker with pure integer operations.

DESIGN PRINCIPLES:
1. Slot tracking by integer (not filename) - slots are integers, hold onto slot_id directly
2. Remove filename-to-slot dictionary - eliminate unnecessary complexity
3. Remove ALL thread_id tracking - be completely "thread agnostic"
4. Proper resource management - acquire once, work in try, release once in finally
"""

import queue
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any


class FileStatus(Enum):
    """File processing status enumeration."""

    STARTING = "starting"
    CHUNKING = "chunking"
    VECTORIZING = "vectorizing"
    FINALIZING = "finalizing"
    PROCESSING = "processing"
    COMPLETING = "completing"
    COMPLETE = "complete"


@dataclass
class FileData:
    """Clean file data for slot tracking - no thread_id pollution."""

    filename: str
    file_size: int
    status: FileStatus
    start_time: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)


class CleanSlotTracker:
    """
    Clean slot-based file tracker with integer-only operations.

    ARCHITECTURE:
    - Fixed-size array for O(1) slot access
    - LIFO queue for available slots (stack-like allocation)
    - No filename dictionaries or complex lookups
    - Thread-agnostic design
    - Direct slot_id operations only
    """

    def __init__(self, max_slots: int):
        """Initialize with fixed number of slots."""
        self.max_slots = max_slots

        # Fixed-size status array (the display array)
        self.status_array: List[Optional[FileData]] = [None] * max_slots

        # Concurrent stack for available slot numbers
        self.available_slots: queue.LifoQueue[int] = queue.LifoQueue()
        for i in range(max_slots):
            self.available_slots.put(i)  # Preload 0, 1, 2, ..., max_slots-1

        # Thread safety for array operations
        self._lock = threading.Lock()

    def acquire_slot(self, file_data: FileData) -> int:
        """
        Acquire slot, return integer slot_id.

        Blocks if no slots available (perfect backpressure).
        Returns slot_id to be used in all subsequent operations.
        """
        slot_id = self.available_slots.get()  # Blocks if none available

        with self._lock:
            self.status_array[slot_id] = file_data

        return slot_id

    def update_slot(self, slot_id: int, status: FileStatus):
        """Update slot status by direct integer access."""
        with self._lock:
            file_data = self.status_array[slot_id]
            if file_data is not None:
                file_data.status = status
                file_data.last_updated = time.time()

    def release_slot(self, slot_id: int):
        """Release slot by integer ID, keeping file visible for UX."""
        # CRITICAL UX DECISION: Keep files visible after completion for better user feedback
        # Following user instructions: DO NOT clear completed files from display
        # Files stay visible in COMPLETE state to show user what was processed

        # Return slot to available pool for reuse without clearing display
        self.available_slots.put(slot_id)

    def release_slot_keep_visible(self, slot_id: int):
        """Release slot for reuse but keep file visible in COMPLETE state."""
        # Return slot to available pool for reuse without clearing display
        self.available_slots.put(slot_id)
        # Note: status_array[slot_id] stays as-is to maintain visual feedback

    def get_display_files(self) -> List[FileData]:
        """Simple array scan - show active slots."""
        active_files = []
        with self._lock:
            for slot_data in self.status_array:
                if slot_data is not None:
                    active_files.append(slot_data)
        return active_files

    def get_slot_count(self) -> int:
        """Get number of occupied slots."""
        count = 0
        with self._lock:
            for slot_data in self.status_array:
                if slot_data is not None:
                    count += 1
        return count

    def is_slot_occupied(self, slot_id: int) -> bool:
        """Check if specific slot is occupied."""
        with self._lock:
            return self.status_array[slot_id] is not None

    def get_available_slot_count(self) -> int:
        """Get number of available slots."""
        return self.available_slots.qsize()

    def get_concurrent_files_data(self) -> List[Dict[str, Any]]:
        """Get concurrent files data in dictionary format for compatibility."""
        concurrent_data = []
        with self._lock:
            for i, slot_data in enumerate(self.status_array):
                if slot_data is not None:
                    file_dict = {
                        "slot_id": i,  # Use slot index as slot_id
                        "file_path": slot_data.filename,
                        "file_size": slot_data.file_size,
                        "status": (
                            slot_data.status.value
                            if hasattr(slot_data.status, "value")
                            else str(slot_data.status)
                        ),
                        "estimated_seconds": 1,  # Default estimate for compatibility
                        "start_time": slot_data.start_time,
                        "last_updated": slot_data.last_updated,
                    }
                    concurrent_data.append(file_dict)
        return concurrent_data
