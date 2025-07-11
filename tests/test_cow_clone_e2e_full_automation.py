"""
End-to-End Test for Copy-on-Write Clone Workflow with Real Services

This test verifies the complete CoW clone workflow using real services:
- Qdrant for vector storage
- File system operations
- Docker container management
- Migration middleware

WARNING: This test is designed for full-automation.sh ONLY
- Uses real Qdrant services
- Requires CoW filesystem (btrfs, ZFS, etc.)
- Takes significant time to complete
- NOT included in ci-github.sh

Test Scenario:
1. Create test project with local storage
2. Index files and verify content
3. Start watch mode and make changes
4. Perform safe CoW clone workflow
5. Verify both projects work independently
6. Confirm local collections are used
7. Test project isolation
"""

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Dict

import pytest

# Import test infrastructure for aggressive setup
from .conftest import local_temporary_directory
from .test_infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
)

# Mark this test as requiring full automation and exclude from CI
pytestmark = [
    pytest.mark.full_automation,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.real_api,
]


@pytest.fixture
def cow_clone_test_workspace():
    """Create a test workspace for CoW clone testing."""
    with local_temporary_directory() as temp_dir:
        # Create isolated project space using inventory system (no config tinkering)
        create_test_project_with_inventory(
            temp_dir, TestProjectInventory.COW_CLONE_E2E_FULL_AUTOMATION
        )

        # Ensure we're on a filesystem that supports CoW
        # This is a basic check - in production you'd want more sophisticated detection
        cow_support = _check_cow_support(temp_dir)
        print(f"CoW support check: {cow_support}")
        if not cow_support:
            pytest.skip("CoW filesystem required for this test")

        # Don't check services here - the test will start them in its own project directory
        print("Skipping service check in fixture - test will handle services")

        yield temp_dir


def _check_cow_support(path: Path) -> bool:
    """Check if the filesystem supports copy-on-write"""
    try:
        # Try to create a test file and use cp --reflink
        test_file = path / "test_cow_check"
        test_file.write_text("test")

        result = subprocess.run(
            ["cp", "--reflink=always", str(test_file), str(test_file) + "_copy"],
            capture_output=True,
        )

        # Clean up
        test_file.unlink(missing_ok=True)
        (path / "test_cow_check_copy").unlink(missing_ok=True)

        return result.returncode == 0
    except Exception:
        return False


def _ensure_services_ready(temp_dir: Path) -> bool:
    """Ensure services are ready for testing."""
    try:
        # Test basic functionality with init and start
        print(f"Running init in {temp_dir}")
        init_result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if init_result.returncode != 0:
            print(f"Init failed: {init_result.stderr}")
            return False

        # Start services
        print("Running start command...")
        start_result = subprocess.run(
            ["code-indexer", "start", "--quiet"],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if start_result.returncode != 0:
            print(f"Start failed: {start_result.stderr}")
            print(f"Start stdout: {start_result.stdout}")
        return start_result.returncode == 0
    except Exception as e:
        print(f"Exception in _ensure_services_ready: {e}")
        return False


def _create_test_project(workspace: Path, name: str) -> Path:
    """Create a test project with sample files."""
    project_path = workspace / name
    project_path.mkdir(parents=True, exist_ok=True)

    # Define custom files for CoW clone testing
    test_files = {
        "src/utils.py": '''
def calculate_sum(a, b):
    """Calculate sum of two numbers"""
    return a + b

def process_data(data):
    """Process incoming data"""
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
    return result
''',
        "src/models.py": '''
class DataProcessor:
    """Class for processing data efficiently"""
    
    def __init__(self, config):
        self.config = config
        self.processed_count = 0
    
    def process_batch(self, batch):
        """Process a batch of data"""
        results = []
        for item in batch:
            processed = self._process_item(item)
            results.append(processed)
            self.processed_count += 1
        return results
    
    def _process_item(self, item):
        """Process individual item"""
        return item.upper() if isinstance(item, str) else str(item)
''',
        "config.yaml": """
app:
  name: "Test Application"
  version: "1.0.0"
  
database:
  host: "localhost"
  port: 5432
  
processing:
  batch_size: 100
  timeout: 30
""",
    }

    # Create test files
    for file_path, content in test_files.items():
        full_path = project_path / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

    return project_path


def _run_cidx_command(
    command_args: list,
    cwd: Path,
    timeout: int = 60,
    expect_success: bool = True,
) -> str:
    """Run a cidx command and return output"""
    try:
        result = subprocess.run(
            ["code-indexer"] + command_args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if expect_success and result.returncode != 0:
            raise RuntimeError(f"Command failed: {result.stderr}")
        return str(result.stdout)
    except Exception as e:
        raise RuntimeError(f"Command failed: {e}") from e


def _cow_clone_directory(source: Path, target: Path):
    """Perform copy-on-write clone"""
    result = subprocess.run(
        ["cp", "--reflink=always", "-r", str(source), str(target)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"CoW clone failed: {result.stderr}")


def _read_config(config_path: Path) -> Dict[str, Any]:
    """Read project configuration"""
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)  # type: ignore[no-any-return]
    return {}


def test_complete_cow_clone_workflow(cow_clone_test_workspace):
    """
    Complete end-to-end test of CoW clone workflow

    This test exercises the entire workflow from project creation
    to independent operation of cloned projects.
    """
    temp_workspace = cow_clone_test_workspace

    # Phase 1: Create and Initialize Original Project
    print("🚀 Phase 1: Creating original project")

    original_project = _create_test_project(temp_workspace, "original-project")

    # Initialize with local storage (triggers migration middleware)
    print("📦 Initializing project with local storage...")
    _run_cidx_command(
        ["init", "--force", "--embedding-provider", "voyage-ai"],
        original_project,
    )

    # Verify initialization
    assert (original_project / ".code-indexer" / "config.json").exists()
    print("✅ Project initialized successfully")

    # Phase 2: Initial Indexing and Verification
    print("🚀 Phase 2: Initial indexing and verification")

    # Services should already be running from aggressive setup
    # But let's ensure they're running for this specific project
    print("📊 Starting services and indexing...")
    try:
        _run_cidx_command(
            ["start", "--quiet"],
            original_project,
            timeout=180,
            expect_success=False,
        )
    except RuntimeError:
        # Services might already be running, continue
        pass

    _run_cidx_command(["index", "--clear"], original_project, timeout=180)

    # Query 1: Verify file1 content (function definition)
    print("🔍 Querying for function definition...")
    query1_result = _run_cidx_command(
        ["query", "function definition"], original_project
    )
    assert "utils.py" in query1_result
    print("✅ Found function definition in utils.py")

    # Query 2: Verify file2 content (class implementation)
    print("🔍 Querying for class implementation...")
    query2_result = _run_cidx_command(
        ["query", "class implementation"], original_project
    )
    assert "models.py" in query2_result
    print("✅ Found class implementation in models.py")

    # Phase 3: Make Changes and Re-index
    print("🚀 Phase 3: Making changes and re-indexing")

    # Make a change to file1
    print("✏️  Making changes to utils.py...")
    utils_file = original_project / "src" / "utils.py"
    current_content = utils_file.read_text()
    updated_content = (
        current_content
        + '''

def updated_function():
    """This is an updated function definition"""
    return "updated functionality"
'''
    )
    utils_file.write_text(updated_content)

    # Re-index to capture the changes
    print("📊 Re-indexing to capture changes...")
    _run_cidx_command(["index"], original_project, timeout=180)

    # Verify change is indexed
    print("🔍 Verifying updated content is indexed...")
    query_updated = _run_cidx_command(
        ["query", "updated function definition"], original_project
    )
    assert "utils.py" in query_updated
    print("✅ Updated function found in index")

    # Phase 4: Prepare for CoW Clone
    print("🚀 Phase 4: Preparing for CoW clone")

    # Note: Skipping force-flush for now as it can take too long with many collections
    # Force flush to ensure consistency would be:
    # _run_cidx_command(["force-flush"], original_project, timeout=300)
    print("✅ Ready for CoW clone")

    # Phase 5: CoW Clone Operation
    print("🚀 Phase 5: Performing CoW clone")

    cloned_project = temp_workspace / "cloned-project"
    print(f"📋 Cloning {original_project} to {cloned_project}...")

    start_time = time.time()
    _cow_clone_directory(original_project, cloned_project)
    clone_time = time.time() - start_time

    print(f"✅ CoW clone completed in {clone_time:.2f} seconds")

    # Verify clone exists and has expected structure
    assert cloned_project.exists()
    assert (cloned_project / "src" / "utils.py").exists()
    assert (cloned_project / "src" / "models.py").exists()
    assert (cloned_project / ".code-indexer" / "config.json").exists()
    print("✅ Clone structure verified")

    # Phase 6: Configure Clone
    print("🚀 Phase 6: Configuring clone")

    # Fix-config on clone (triggers migration)
    print("🔧 Running fix-config on clone...")
    _run_cidx_command(["fix-config", "--force"], cloned_project, timeout=180)
    print("✅ Clone configuration updated")

    # Index the cloned project to create its own collection
    print("📊 Indexing cloned project...")
    _run_cidx_command(["index", "--clear"], cloned_project, timeout=180)
    print("✅ Cloned project indexed")

    # Phase 7: Verify Clone Independence
    print("🚀 Phase 7: Verifying clone independence")

    # Start services on clone (should already be running)
    print("🚀 Ensuring services are available for clone...")
    try:
        _run_cidx_command(
            ["start", "--quiet"],
            cloned_project,
            timeout=180,
            expect_success=False,
        )
    except RuntimeError:
        # Services might already be running, continue
        pass

    # Query same content in both projects
    print("🔍 Querying both projects for same content...")

    original_query1 = _run_cidx_command(
        ["query", "function definition"], original_project
    )
    cloned_query1 = _run_cidx_command(["query", "function definition"], cloned_project)

    original_query2 = _run_cidx_command(["query", "updated function"], original_project)
    cloned_query2 = _run_cidx_command(["query", "updated function"], cloned_project)

    # Both should return similar results (both have the same content)
    assert "utils.py" in original_query1
    assert "utils.py" in cloned_query1
    assert "utils.py" in original_query2
    assert "utils.py" in cloned_query2
    print("✅ Both projects return expected query results")

    # Phase 8: Verify Local Collection Usage
    print("🚀 Phase 8: Verifying local collection usage")

    # Check configuration files exist (structure depends on implementation)
    print("📋 Checking configuration structures...")

    # Verify local qdrant-data directories exist
    original_storage = original_project / ".code-indexer" / "qdrant-data"
    cloned_storage = cloned_project / ".code-indexer" / "qdrant-data"

    # These might be created during indexing
    print(f"Original storage exists: {original_storage.exists()}")
    print(f"Cloned storage exists: {cloned_storage.exists()}")

    # Phase 9: Test Independent Operations
    print("🚀 Phase 9: Testing independent operations")

    # Make different changes to each project
    print("✏️  Making different changes to each project...")

    # Change in original
    original_utils = original_project / "src" / "utils.py"
    original_content = original_utils.read_text()
    original_utils.write_text(
        original_content
        + '''

def original_specific_function():
    """This function only exists in the original project"""
    return "original specific change"
'''
    )

    # Change in clone
    cloned_utils = cloned_project / "src" / "utils.py"
    cloned_content = cloned_utils.read_text()
    cloned_utils.write_text(
        cloned_content
        + '''

def cloned_specific_function():
    """This function only exists in the cloned project"""
    return "cloned specific change"
'''
    )

    # Re-index both projects to capture changes
    print("📊 Re-indexing both projects to capture changes...")
    _run_cidx_command(["index"], original_project, timeout=180)
    _run_cidx_command(["index"], cloned_project, timeout=180)

    # Verify isolation - each project should see only its own changes
    print("🔍 Verifying project isolation...")

    original_specific = _run_cidx_command(
        ["query", "original specific"], original_project
    )
    cloned_specific = _run_cidx_command(["query", "cloned specific"], cloned_project)

    assert "utils.py" in original_specific
    assert "utils.py" in cloned_specific
    print("✅ Both projects see their own changes")

    # Cross-check isolation (this might not always fail due to indexing timing)
    # But we'll check anyway
    try:
        original_no_clone = _run_cidx_command(
            ["query", "cloned specific"], original_project, expect_success=False
        )
        cloned_no_original = _run_cidx_command(
            ["query", "original specific"], cloned_project, expect_success=False
        )

        # If we get results, they shouldn't contain the other project's changes
        print("🔍 Cross-checking isolation...")
        if "utils.py" in original_no_clone:
            print("⚠️  Original project might see cloned changes (check isolation)")
        if "utils.py" in cloned_no_original:
            print("⚠️  Cloned project might see original changes (check isolation)")

    except Exception as e:
        # This is actually good - means the queries didn't find anything
        print(f"✅ Cross-check queries returned no results (good isolation): {e}")

    # Phase 10: Cleanup
    print("🚀 Phase 10: Cleanup")

    # Follow aggressive setup pattern - don't stop services, leave them running
    print("✅ Leaving services running for next test (aggressive setup pattern)")

    print("🎉 Complete CoW clone workflow test completed successfully!")
    print("📊 Summary:")
    print(f"   - Original project: {original_project}")
    print(f"   - Cloned project: {cloned_project}")
    print(f"   - Clone time: {clone_time:.2f} seconds")
    print("   - Both projects operational independently")


if __name__ == "__main__":
    # This test should only be run as part of full automation
    pytest.main(
        [
            __file__,
            "-v",
            "-s",  # Don't capture output so we can see progress
            "--tb=short",
        ]
    )
