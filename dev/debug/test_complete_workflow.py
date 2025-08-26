#!/usr/bin/env python3
"""
Test the complete collection tracking and cleanup workflow.
"""

import sys
from pathlib import Path
import tempfile

# Add tests to path
sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))

from test_suite_setup import (
    register_test_collection,
    get_tracked_test_collections,
    clear_tracked_test_collections,
    cleanup_test_collections,
)
from test_infrastructure import auto_register_project_collections

def test_complete_workflow():
    """Test the complete workflow from registration to cleanup."""
    print("🧪 Testing complete collection tracking workflow...")
    
    # Step 1: Clear any existing tracking
    print("\n1️⃣ Clearing existing tracked collections...")
    clear_tracked_test_collections()
    initial_tracked = get_tracked_test_collections()
    print(f"   Initial tracked collections: {len(initial_tracked)}")
    
    # Step 2: Manual registration (simulating existing tests)
    print("\n2️⃣ Manual registration (simulating existing test patterns)...")
    manual_collections = [
        "test_clear_bug_collection",
        "deletion_test_collection", 
        "stuck_indexing_test",
        "test_e2e_collection",
        "test_e2e_integration"
    ]
    for collection in manual_collections:
        register_test_collection(collection)
    
    tracked_after_manual = get_tracked_test_collections()
    print(f"   Tracked after manual registration: {len(tracked_after_manual)}")
    print(f"   Collections: {sorted(tracked_after_manual)}")
    
    # Step 3: Auto-registration (simulating e2e test infrastructure)
    print("\n3️⃣ Auto-registration (simulating e2e test infrastructure)...")
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)
        auto_collections = auto_register_project_collections(project_dir)
        print(f"   Auto-registered {len(auto_collections)} collections:")
        for collection in auto_collections:
            print(f"   - {collection}")
    
    # Step 4: Check total tracked collections
    print("\n4️⃣ Total tracked collections...")
    all_tracked = get_tracked_test_collections()
    print(f"   Total tracked collections: {len(all_tracked)}")
    print(f"   All collections:")
    for collection in sorted(all_tracked):
        print(f"   - {collection}")
    
    # Step 5: Test dry-run cleanup
    print("\n5️⃣ Testing dry-run cleanup...")
    dry_run_result = cleanup_test_collections(dry_run=True)
    print(f"   Would delete {dry_run_result.get('total_would_delete', 0)} collections")
    print(f"   Collections to delete: {sorted(dry_run_result.get('would_delete', []))}")
    
    # Step 6: Test actual cleanup (will fail as Qdrant not running, but should clear file)
    print("\n6️⃣ Testing cleanup (expecting Qdrant not accessible)...")
    cleanup_result = cleanup_test_collections(dry_run=False)
    if "error" in cleanup_result and "Qdrant not accessible" in cleanup_result["error"]:
        print("   ✅ Cleanup correctly detected no Qdrant")
    else:
        print(f"   ⚠️  Unexpected cleanup result: {cleanup_result}")
    
    # Step 7: Verify tracking file is cleared
    print("\n7️⃣ Verifying tracking file state...")
    final_tracked = get_tracked_test_collections()
    print(f"   Final tracked collections: {len(final_tracked)}")
    
    if len(final_tracked) == 0:
        print("   ✅ Tracking file correctly cleared")
    else:
        print(f"   ⚠️  Tracking file not cleared: {final_tracked}")
    
    print("\n🎉 Complete workflow test finished!")

if __name__ == "__main__":
    test_complete_workflow()