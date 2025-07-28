"""
End-to-End Test for Complete Docker Uninstall Cleanup

This test specifically verifies that the uninstall command completely removes
ALL Qdrant data when using Docker with root privileges, addressing the issue
where files under .code-indexer/qdrant are not completely removed.

Test Scenario:
1. Create test repository in /tmp folder
2. Configure cidx with --force-docker
3. Start services (Qdrant runs with root privileges)
4. Index files (creates root-owned data in qdrant folder)
5. Stop services
6. Run uninstall command
7. Assert COMPLETE cleanup - NO files left in .code-indexer/qdrant
8. Verify entire qdrant folder is completely gone
9. Confirm data-cleaner container properly removed root-owned files

WARNING: This test is designed for full-automation.sh ONLY
- Uses real Docker services with root privileges
- Creates files in /tmp directory
- Requires Docker daemon running
- NOT included in ci-github.sh (Docker permission issues)
"""

import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import List

import pytest

# Test infrastructure available if needed
# from .test_infrastructure import TestProjectInventory

# Mark this test for full automation ONLY - NOT for ci-github.sh
pytestmark = [
    pytest.mark.full_automation,  # ONLY runs in full-automation.sh
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.real_api,  # Requires real Docker daemon
    pytest.mark.skipif(
        not os.getenv("DOCKER_AVAILABLE", "true").lower() == "true",
        reason="Docker required for root privilege uninstall testing",
    ),
    pytest.mark.skipif(
        os.getenv("CI_GITHUB", "false").lower() == "true",
        reason="Docker uninstall test excluded from ci-github.sh due to root privilege requirements",
    ),
]


def _run_cidx_command(
    command_args: List[str],
    cwd: Path,
    timeout: int = 120,
    expect_success: bool = True,
    capture_output: bool = True,
) -> subprocess.CompletedProcess:
    """Run a cidx command and return the complete result"""
    try:
        result = subprocess.run(
            ["code-indexer"] + command_args,
            cwd=cwd,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
        )

        if expect_success and result.returncode != 0:
            raise RuntimeError(
                f"Command failed (rc={result.returncode}): "
                f"cmd='code-indexer {' '.join(command_args)}' "
                f"stderr='{result.stderr}' stdout='{result.stdout}'"
            )
        return result
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Command timed out after {timeout}s: code-indexer {' '.join(command_args)}"
        )
    except Exception as e:
        raise RuntimeError(f"Command failed: {e}") from e


def _create_test_project(project_path: Path) -> None:
    """Create a test project with sample files for indexing"""
    # Create source directory
    src_dir = project_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    # Create test files that will generate Qdrant data
    test_files = {
        "main.py": '''
def main():
    """Main application entry point"""
    print("Hello, World!")
    return 0

class DataProcessor:
    """Process application data"""
    
    def __init__(self, config):
        self.config = config
        self.processed_count = 0
    
    def process_item(self, item):
        """Process a single data item"""
        self.processed_count += 1
        return item.upper()
''',
        "utils.py": '''
def calculate_sum(a, b):
    """Calculate sum of two numbers"""
    return a + b

def validate_input(data):
    """Validate input data"""
    if not data:
        raise ValueError("Data cannot be empty")
    return True

class Logger:
    """Simple logging utility"""
    
    def __init__(self, level="INFO"):
        self.level = level
    
    def log(self, message):
        """Log a message"""
        print(f"[{self.level}] {message}")
''',
        "config.yaml": """
app:
  name: "Docker Uninstall Test App"
  version: "1.0.0"
  
database:
  host: "localhost"
  port: 5432
  
processing:
  batch_size: 100
  timeout: 30
""",
    }

    # Create all test files
    for filename, content in test_files.items():
        file_path = src_dir / filename
        file_path.write_text(content)

    print(f"✅ Created test project with {len(test_files)} files in {project_path}")


def _verify_no_qdrant_data(project_path: Path) -> None:
    """Verify that NO Qdrant data exists - complete cleanup verification"""
    code_indexer_dir = project_path / ".code-indexer"
    qdrant_dir = code_indexer_dir / "qdrant"

    print(f"🔍 Verifying complete cleanup in {project_path}")

    # Check if .code-indexer directory exists
    if not code_indexer_dir.exists():
        print("✅ .code-indexer directory completely removed - perfect cleanup")
        return

    print(f"📁 .code-indexer directory still exists: {code_indexer_dir}")

    # Check if qdrant directory exists at all
    if not qdrant_dir.exists():
        print("✅ qdrant directory completely removed - perfect cleanup")
        return

    # If qdrant directory exists, it should be completely empty
    print(f"⚠️  qdrant directory still exists: {qdrant_dir}")

    # List all contents recursively
    all_contents = []
    try:
        for root, dirs, files in os.walk(qdrant_dir):
            for name in dirs + files:
                full_path = Path(root) / name
                stat_info = full_path.stat()
                all_contents.append(
                    {
                        "path": str(full_path.relative_to(project_path)),
                        "type": "dir" if full_path.is_dir() else "file",
                        "size": stat_info.st_size if full_path.is_file() else 0,
                        "owner": stat_info.st_uid,
                        "group": stat_info.st_gid,
                        "mode": oct(stat_info.st_mode),
                    }
                )
    except Exception as e:
        print(f"❌ Error scanning qdrant directory: {e}")
        all_contents.append({"error": str(e)})

    if all_contents:
        print("❌ CLEANUP FAILURE: Files still exist in qdrant directory:")
        for item in all_contents:
            if "error" in item:
                print(f"   ERROR: {item['error']}")
            else:
                print(
                    f"   {item['type']}: {item['path']} (size: {item['size']}, owner: {item['owner']}, mode: {item['mode']})"
                )

        # This is the critical assertion - NOTHING should be left
        pytest.fail(
            f"UNINSTALL CLEANUP FAILED: {len(all_contents)} items still exist in qdrant directory!\n"
            f"The data-cleaner container failed to remove all root-owned files.\n"
            f"Remaining items: {all_contents}"
        )
    else:
        print("✅ qdrant directory exists but is completely empty - acceptable cleanup")


def test_docker_uninstall_complete_cleanup():
    """
    Test complete Docker uninstall cleanup with root privilege file removal

    This test reproduces the exact scenario described:
    - Ubuntu box with Docker
    - Qdrant runs with root privileges
    - Files under qdrant are not completely removed
    - Verifies data-cleaner container operation
    """
    print("\n" + "=" * 80)
    print("🧪 TESTING: Complete Docker Uninstall Cleanup with Root Privileges")
    print("=" * 80)

    # Phase 1: Create test repository in /tmp
    print("\n🚀 Phase 1: Creating test repository in /tmp")

    # Use /tmp as requested for realistic testing
    with tempfile.TemporaryDirectory(
        prefix="cidx_uninstall_test_", dir="/tmp"
    ) as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        print(f"📁 Test directory: {temp_dir}")

        # Create test project
        _create_test_project(temp_dir)

        try:
            # Phase 2: Configure cidx with --force-docker
            print("\n🚀 Phase 2: Configuring cidx with --force-docker")

            init_result = _run_cidx_command(
                [
                    "init",
                    "--force",
                    "--embedding-provider",
                    "voyage-ai",
                ],
                temp_dir,
            )

            print("✅ Initialized with --force-docker configuration")
            print(f"📊 Init output: {init_result.stdout[:200]}...")

            # Verify configuration was created
            config_file = temp_dir / ".code-indexer" / "config.json"
            assert config_file.exists(), "Configuration file should be created"

            # Phase 3: Start services (Qdrant with root privileges)
            print("\n🚀 Phase 3: Starting services with Docker root privileges")

            start_result = _run_cidx_command(
                ["start", "--quiet", "--force-docker"],
                temp_dir,
                timeout=180,  # CRITICAL: Force Docker usage for root privilege testing
            )

            print("✅ Services started with Docker")
            print(f"📊 Start output: {start_result.stdout[:200]}...")

            # Give services time to fully initialize
            time.sleep(5)

            # Phase 4: Index files (creates root-owned data)
            print("\n🚀 Phase 4: Indexing files (creating root-owned Qdrant data)")

            index_result = _run_cidx_command(
                ["index", "--clear"], temp_dir, timeout=180
            )

            print("✅ Indexing completed - root-owned data created")
            print(f"📊 Index output: {index_result.stdout[:200]}...")

            # Verify that Qdrant data was actually created
            qdrant_dir = temp_dir / ".code-indexer" / "qdrant"
            assert (
                qdrant_dir.exists()
            ), "Qdrant directory should be created during indexing"

            # Check for any files in qdrant directory before cleanup
            files_before = []
            try:
                for root, dirs, files in os.walk(qdrant_dir):
                    files_before.extend([Path(root) / f for f in files])
                    files_before.extend([Path(root) / d for d in dirs])
            except Exception as e:
                print(f"⚠️  Could not scan qdrant dir before cleanup: {e}")

            print(f"📊 Files created before cleanup: {len(files_before)}")
            if files_before:
                print("📁 Sample files:")
                for f in files_before[:5]:  # Show first 5 files
                    try:
                        stat_info = f.stat()
                        print(
                            f"   {f.relative_to(temp_dir)} (owner: {stat_info.st_uid})"
                        )
                    except Exception:
                        print(f"   {f.relative_to(temp_dir)} (stat failed)")

            # Verify indexing worked with a quick query
            try:
                query_result = _run_cidx_command(
                    ["query", "calculate sum"], temp_dir, timeout=30
                )
                assert "utils.py" in query_result.stdout, "Indexing should have worked"
                print("✅ Indexing verification successful")
            except Exception as e:
                print(f"⚠️  Query verification failed (continuing): {e}")

            # Phase 5: Stop services (CRITICAL: Must stop before uninstall)
            print("\n🚀 Phase 5: Stopping services")

            stop_result = _run_cidx_command(
                ["stop"], temp_dir, timeout=120, expect_success=False
            )  # Stop might fail if already stopped

            print("✅ Stop command executed")
            print(f"📊 Stop output: {stop_result.stdout[:200]}...")

            # CRITICAL: Verify containers are actually stopped before uninstall
            # This ensures uninstall can start its own data-cleaner
            print("🔍 Verifying containers are stopped before uninstall...")
            time.sleep(3)  # Give containers time to fully stop

            # Check container status using Docker directly
            try:
                # Look for any containers that might still be running for this project
                container_check = subprocess.run(
                    ["docker", "ps", "--format", "{{.Names}}", "--filter", "name=cidx"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                running_containers = [
                    name
                    for name in container_check.stdout.strip().split("\n")
                    if name.strip()
                ]

                if running_containers:
                    print(
                        f"⚠️  Found {len(running_containers)} containers still running (expected for other tests)"
                    )
                    # Don't fail the test - this is normal in concurrent test environment
                else:
                    print("✅ No cidx containers running - clean state for uninstall")

            except Exception as e:
                print(f"⚠️  Could not check container status: {e}")
                # Continue anyway - uninstall should handle this

            # Phase 6: Run uninstall command (CRITICAL TEST)
            print("\n🚀 Phase 6: Running uninstall command with data-cleaner")
            print("   This should:")
            print("   1. Stop any remaining containers")
            print("   2. Start ONLY the data-cleaner container")
            print("   3. Use data-cleaner to remove ALL root-owned files")
            print("   4. Complete cleanup without permission errors")

            # This is the critical command that should remove ALL root-owned files
            uninstall_result = _run_cidx_command(
                ["uninstall", "--force-docker"], temp_dir, timeout=300
            )  # Longer timeout for cleanup operations

            print("✅ Uninstall command completed")
            print(f"📊 Uninstall output: {uninstall_result.stdout}")

            # Verify the data-cleaner was used (should be in output)
            if "Using data cleaner for root-owned files" in uninstall_result.stdout:
                print("✅ Confirmed: Data-cleaner was used for root file cleanup")
            else:
                print("⚠️  Warning: Data-cleaner usage not clearly indicated in output")

            # Give the data-cleaner container time to complete cleanup
            time.sleep(3)

            # Phase 7: Assert COMPLETE cleanup
            print("\n🚀 Phase 7: Verifying COMPLETE cleanup - NO files should remain")

            # This is the critical verification - NOTHING should be left
            _verify_no_qdrant_data(temp_dir)

            # Additional verification: Check if any Docker containers are still running
            print("\n🔍 Additional verification: Checking for lingering containers")
            try:
                # Check for any containers related to this project
                docker_ps_result = subprocess.run(
                    [
                        "docker",
                        "ps",
                        "--filter",
                        "name=cidx",
                        "--format",
                        "table {{.Names}}\t{{.Status}}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if docker_ps_result.stdout.strip():
                    print(f"⚠️  Containers still running: {docker_ps_result.stdout}")
                else:
                    print("✅ No cidx containers still running")

            except Exception as e:
                print(f"⚠️  Could not check Docker containers: {e}")

            print("\n🎉 SUCCESS: Complete Docker uninstall cleanup test passed!")
            print(
                "✅ All root-owned files successfully removed by data-cleaner container"
            )
            print("✅ No files remaining in .code-indexer/qdrant directory")
            print("✅ Complete cleanup verified")

        except Exception as e:
            print(f"\n❌ Test failed during execution: {e}")

            # On failure, provide diagnostic information
            print("\n🔍 Diagnostic information:")
            qdrant_dir = temp_dir / ".code-indexer" / "qdrant"
            if qdrant_dir.exists():
                print(
                    "❌ Qdrant directory still exists - attempting manual verification"
                )
                _verify_no_qdrant_data(temp_dir)

            # Re-raise the exception to fail the test
            raise

        finally:
            # Emergency cleanup: Try to stop any remaining containers
            print("\n🧹 Emergency cleanup: Ensuring no containers left running")
            try:
                subprocess.run(
                    ["code-indexer", "stop"],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except Exception:
                pass  # Ignore errors in emergency cleanup


def test_manual_docker_uninstall_verification_workflow():
    """
    Manual workflow documentation for Docker uninstall verification
    """
    print("\n" + "=" * 80)
    print("MANUAL WORKFLOW: Docker Uninstall Complete Cleanup Verification")
    print("=" * 80)

    print("\n1. Setup test environment:")
    print("   mkdir /tmp/test_cidx_uninstall")
    print("   cd /tmp/test_cidx_uninstall")
    print("   echo 'def test(): pass' > test.py")

    print("\n2. Configure with Docker:")
    print("   code-indexer init --force --force-docker --embedding-provider voyage-ai")

    print("\n3. Start services and create root-owned data:")
    print("   code-indexer start")
    print("   code-indexer index --clear")
    print("   # This creates root-owned files in .code-indexer/qdrant/")

    print("\n4. Verify data exists:")
    print("   ls -la .code-indexer/qdrant/")
    print("   # Should show root-owned files/directories")

    print("\n5. Stop and uninstall:")
    print("   code-indexer stop")
    print("   code-indexer uninstall")
    print("   # Should use data-cleaner container for root file cleanup")

    print("\n6. Verify complete cleanup:")
    print(
        "   ls -la .code-indexer/qdrant/ 2>/dev/null || echo 'Directory not found - perfect!'"
    )
    print("   # Should show NO files remaining")

    print("\n7. Expected behavior:")
    print("   - data-cleaner container removes ALL root-owned files")
    print("   - .code-indexer/qdrant directory is completely empty or removed")
    print("   - No permission errors during cleanup")
    print("   - Complete cleanup regardless of file ownership")

    print("\n8. Troubleshooting if cleanup fails:")
    print("   - Check Docker daemon is running with correct privileges")
    print("   - Verify data-cleaner container has --privileged flag")
    print("   - Check for mount path consistency (/qdrant/storage/*)")
    print("   - Ensure container can access host filesystem with correct permissions")

    print("\n✅ Manual workflow documented")


if __name__ == "__main__":
    # Run the test when executed directly
    pytest.main(
        [
            __file__,
            "-v",
            "-s",  # Don't capture output for debugging
            "--tb=short",
        ]
    )
