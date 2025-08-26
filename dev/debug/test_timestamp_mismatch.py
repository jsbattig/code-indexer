#!/usr/bin/env python3
"""
Debug script to test timestamp mismatch between watch and reconcile.
This tests if the int vs float conversion in FileIdentifier causes re-indexing issues.
"""

import time
from pathlib import Path

def test_timestamp_comparison():
    """Test how different timestamp representations compare."""
    
    # Get a sample file timestamp
    test_file = Path(__file__)
    stat = test_file.stat()
    
    # Get timestamp as float (like BranchAwareIndexer)
    float_timestamp = stat.st_mtime
    
    # Get timestamp as int (like FileIdentifier)
    int_timestamp = int(stat.st_mtime)
    
    print(f"Original float timestamp: {float_timestamp}")
    print(f"Truncated int timestamp: {int_timestamp}")
    print(f"Difference: {float_timestamp - int_timestamp}")
    
    # Test reconcile's comparison logic with 1 second tolerance
    tolerance = 1.0
    
    # Scenario 1: File hasn't changed
    disk_mtime = float_timestamp
    db_timestamp = int_timestamp
    needs_reindex = disk_mtime > db_timestamp + tolerance
    print(f"\nScenario 1 - No change:")
    print(f"  Disk: {disk_mtime}, DB: {db_timestamp}")
    print(f"  Needs reindex? {needs_reindex} (should be False)")
    
    # Scenario 2: File was just modified (fractional seconds difference)
    disk_mtime = float_timestamp + 0.5  # Half second newer
    db_timestamp = int_timestamp
    needs_reindex = disk_mtime > db_timestamp + tolerance
    print(f"\nScenario 2 - Recent change (0.5s):")
    print(f"  Disk: {disk_mtime}, DB: {db_timestamp}")
    print(f"  Needs reindex? {needs_reindex} (should be False due to tolerance)")
    
    # Scenario 3: File was modified more than 1 second ago
    disk_mtime = float_timestamp + 1.5  # 1.5 seconds newer
    db_timestamp = int_timestamp
    needs_reindex = disk_mtime > db_timestamp + tolerance
    print(f"\nScenario 3 - Older change (1.5s):")
    print(f"  Disk: {disk_mtime}, DB: {db_timestamp}")
    print(f"  Needs reindex? {needs_reindex} (should be True)")
    
    # The problem case: float timestamp in DB, float on disk
    print("\n" + "="*50)
    print("POTENTIAL ISSUE - Both timestamps are floats:")
    db_timestamp = float_timestamp  # DB has float (from BranchAwareIndexer)
    disk_mtime = float_timestamp    # Disk has same float
    needs_reindex = disk_mtime > db_timestamp + tolerance
    print(f"  Disk: {disk_mtime}, DB: {db_timestamp}")
    print(f"  Needs reindex? {needs_reindex} (should be False)")
    
    # But if there's any tiny difference due to float precision...
    db_timestamp = float_timestamp
    disk_mtime = float_timestamp + 0.0000001  # Tiny float precision difference
    needs_reindex = disk_mtime > db_timestamp + tolerance
    print(f"\nWith tiny float difference:")
    print(f"  Disk: {disk_mtime}, DB: {db_timestamp}")
    print(f"  Needs reindex? {needs_reindex} (should be False)")

if __name__ == "__main__":
    test_timestamp_comparison()