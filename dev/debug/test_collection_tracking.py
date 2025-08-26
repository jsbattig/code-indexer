#!/usr/bin/env python3
"""
Test script to verify the new collection tracking mechanism.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))

from tests.test_suite_setup import (
    register_test_collection,
    get_tracked_test_collections,
    clear_tracked_test_collections,
    cleanup_test_collections,
    create_test_collection_context,
)
from rich.console import Console

def test_collection_tracking():
    """Test the collection tracking mechanism."""
    console = Console()
    
    # Clear any existing tracking file
    clear_tracked_test_collections()
    
    # Test 1: Register some test collections
    console.print("🧪 Testing collection registration...", style="blue")
    register_test_collection("test_collection_1")
    register_test_collection("test_collection_2")
    register_test_collection("test_collection_3")
    
    # Test 2: Get tracked collections
    tracked = get_tracked_test_collections()
    console.print(f"📋 Tracked collections: {tracked}")
    
    expected = {"test_collection_1", "test_collection_2", "test_collection_3"}
    assert tracked == expected, f"Expected {expected}, got {tracked}"
    
    # Test 3: Test duplicate registration (should not add duplicates)
    register_test_collection("test_collection_1")  # Duplicate
    tracked_after_dup = get_tracked_test_collections()
    assert tracked_after_dup == expected, f"Duplicate registration failed: {tracked_after_dup}"
    
    console.print("✅ Collection registration tests passed", style="green")
    
    # Test 4: Test context manager
    console.print("🧪 Testing context manager...", style="blue")
    with create_test_collection_context("context_test") as collection_name:
        console.print(f"📦 Created collection: {collection_name}")
        assert collection_name.startswith("context_test_"), f"Bad collection name: {collection_name}"
        
        # Check if it was registered
        tracked_with_context = get_tracked_test_collections()
        assert collection_name in tracked_with_context, f"Context collection not tracked: {collection_name}"
    
    console.print("✅ Context manager tests passed", style="green")
    
    # Test 5: Test dry run cleanup
    console.print("🧪 Testing dry run cleanup...", style="blue")
    result = cleanup_test_collections(dry_run=True, console=console)
    
    expected_collections = tracked_with_context
    assert set(result["would_delete"]) == expected_collections, f"Dry run mismatch: {result}"
    
    console.print("✅ Dry run cleanup tests passed", style="green")
    
    # Test 6: Test actual cleanup (but first make sure we're not connected to real Qdrant)
    console.print("🧪 Testing cleanup without Qdrant...", style="blue")
    result = cleanup_test_collections(dry_run=False, console=console)
    
    # Should fail because Qdrant is not accessible, but that's expected
    if "error" in result and "Qdrant not accessible" in result["error"]:
        console.print("✅ Cleanup correctly detected no Qdrant", style="green")
    else:
        console.print("⚠️  Unexpected cleanup result (might be okay if Qdrant is running)", style="yellow")
    
    # Test 7: Test file clearing after cleanup
    console.print("🧪 Testing file clearing...", style="blue")
    clear_tracked_test_collections()
    final_tracked = get_tracked_test_collections()
    assert len(final_tracked) == 0, f"File not cleared: {final_tracked}"
    
    console.print("✅ File clearing tests passed", style="green")
    
    console.print("🎉 All tests passed!", style="bold green")


if __name__ == "__main__":
    test_collection_tracking()