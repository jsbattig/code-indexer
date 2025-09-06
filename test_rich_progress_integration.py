#!/usr/bin/env python3
"""Manual test to verify Rich Progress Display integration."""

import sys
import subprocess
import shutil
from pathlib import Path

def create_test_files(test_dir: Path, count: int = 50):
    """Create test Python files for indexing."""
    for i in range(count):
        file_path = test_dir / f"test_file_{i:03d}.py"
        content = f'''"""Test file {i} for Rich Progress Display testing."""

def function_{i}():
    """Function {i} with some documentation."""
    # Some comment about the implementation
    result = {i} * 42
    for j in range(10):
        result += j * {i}
    return result

class TestClass_{i}:
    """Test class {i} with methods."""
    
    def __init__(self):
        self.value = {i}
    
    def method_a(self):
        """Method A implementation."""
        return self.value * 2
    
    def method_b(self, param):
        """Method B implementation."""
        return self.value + param

# Additional code to make the file larger
data = [{{"id": {i}, "name": "item_{i}"}} for x in range(100)]
'''
        file_path.write_text(content)
    print(f"✅ Created {count} test files in {test_dir}")

def run_indexing_test():
    """Run cidx index and capture output to verify Rich Progress Display."""
    # Create temporary test directory
    test_dir = Path.home() / ".tmp" / "rich_progress_test"
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"🔧 Test directory: {test_dir}")
    
    # Create test files
    create_test_files(test_dir, 50)
    
    # Change to test directory
    import os
    os.chdir(test_dir)
    
    # Initialize cidx
    print("\n📦 Initializing cidx...")
    init_result = subprocess.run(
        ["cidx", "init", "--embedding-provider", "ollama"],
        capture_output=True,
        text=True
    )
    
    if init_result.returncode != 0:
        print(f"❌ Failed to initialize: {init_result.stderr}")
        return False
    
    print("✅ Initialization complete")
    
    # Run indexing with real-time output
    print("\n🚀 Running indexing (watch for multi-threaded display)...")
    print("=" * 60)
    
    # Run without capturing to see real-time output
    index_result = subprocess.run(
        ["cidx", "index", "-p", "8"],
        text=True
    )
    
    print("=" * 60)
    
    if index_result.returncode != 0:
        print("❌ Indexing failed")
        return False
    
    print("\n✅ Indexing completed successfully")
    
    # Check status
    print("\n📊 Checking status...")
    status_result = subprocess.run(
        ["cidx", "status"],
        capture_output=True,
        text=True
    )
    
    print(status_result.stdout)
    
    # Cleanup
    print("\n🧹 Cleaning up...")
    subprocess.run(["cidx", "stop"], capture_output=True)
    shutil.rmtree(test_dir)
    
    return True

if __name__ == "__main__":
    print("🎯 Rich Progress Display Integration Test")
    print("This test will create files and run indexing to verify the multi-threaded display")
    print("-" * 60)
    
    success = run_indexing_test()
    
    if success:
        print("\n✅ Test completed successfully")
        print("\n🔍 Expected behavior:")
        print("  - Multiple file lines showing concurrent processing")
        print("  - Each line shows: ├─ filename (size, time) status")
        print("  - Bottom progress bar with aggregate metrics")
        print("  - Files/sec, KB/sec, and thread count metrics")
    else:
        print("\n❌ Test failed")
        sys.exit(1)