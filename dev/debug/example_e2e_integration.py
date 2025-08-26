#!/usr/bin/env python3
"""
Example showing how to integrate the new collection tracking into e2e tests.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))

from tests.test_suite_setup import (
    register_test_collection,
    create_test_collection_context,
    with_collection_tracking,
)


def example_manual_registration():
    """Example of manually registering collections in e2e tests."""
    
    # When your test creates a collection, register it:
    collection_name = "my_e2e_test_collection_abc123"
    
    # Register the collection for cleanup
    register_test_collection(collection_name)
    
    print(f"✅ Registered collection: {collection_name}")
    
    # Your test code would continue here...
    # The collection will be cleaned up automatically during suite teardown


def example_context_manager_usage():
    """Example of using the context manager for automatic collection naming."""
    
    # Use context manager for automatic unique naming and registration
    with create_test_collection_context("my_e2e_test") as collection_name:
        print(f"✅ Using collection: {collection_name}")
        
        # Your test code would use this collection_name
        # Collection is automatically registered for cleanup
        
        # Simulate some test operations
        print("   - Creating test data...")
        print("   - Running test scenarios...")
        print("   - Validating results...")


@with_collection_tracking("fixed_collection_name")
def example_decorator_usage():
    """Example of using the decorator for fixed collection names."""
    
    # This function will automatically register "fixed_collection_name" for cleanup
    print("✅ Using decorator with fixed collection name")
    
    # Your test code would continue here...
    # The collection will be cleaned up automatically during suite teardown


def example_integration_patterns():
    """Examples of how to integrate with different test patterns."""
    
    print("🔧 Pattern 1: Manual registration (for existing code)")
    example_manual_registration()
    
    print("\n🔧 Pattern 2: Context manager (for new code)")
    example_context_manager_usage()
    
    print("\n🔧 Pattern 3: Decorator (for simple cases)")
    example_decorator_usage()
    
    print("\n✨ All patterns demonstrated!")


if __name__ == "__main__":
    example_integration_patterns()