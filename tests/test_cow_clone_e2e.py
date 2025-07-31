"""
End-to-end test for CoW (Copy-on-Write) clone functionality.

This test verifies that when a repo is CoW cloned, the new copy:
1. Uses its own local Qdrant database
2. Can index new files independently
3. Maintains proper isolation from the original repo
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


def run_cli_command(command_args, cwd, timeout=60):
    """Run a CLI command and return the result."""
    result = subprocess.run(
        command_args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
    return result


def detect_filesystem_type() -> str:
    """Detect if we're on a filesystem that supports CoW operations."""
    try:
        # Check if we're on btrfs, zfs, or other CoW-capable filesystem
        result = subprocess.run(
            ["df", "--output=fstype", "/tmp"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            fstype = result.stdout.strip().split("\n")[-1]
            return fstype.lower()
    except Exception:
        pass

    # Fallback: detect distro for filesystem assumptions
    try:
        with open("/etc/os-release", "r") as f:
            os_info = f.read().lower()
            if "rocky" in os_info or "rhel" in os_info or "centos" in os_info:
                return "rocky"
            elif "ubuntu" in os_info or "debian" in os_info:
                return "ubuntu"
    except Exception:
        pass

    return "unknown"


def perform_cow_clone(source_path: Path, target_path: Path, fs_type: str) -> bool:
    """
    Perform CoW clone based on filesystem type.

    Args:
        source_path: Source directory to clone
        target_path: Target directory for clone
        fs_type: Filesystem type detected

    Returns:
        True if CoW clone succeeded, False if fallback to regular copy
    """
    print(f"🔍 Detected filesystem: {fs_type}")

    # Try CoW-specific operations based on filesystem
    if fs_type in ["btrfs"]:
        try:
            # btrfs subvolume snapshot for true CoW
            subprocess.run(
                ["btrfs", "subvolume", "snapshot", str(source_path), str(target_path)],
                check=True,
                timeout=30,
            )
            print(f"✅ btrfs CoW snapshot created: {target_path}")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("⚠️  btrfs snapshot failed, falling back to cp --reflink")

    if fs_type in ["zfs"]:
        try:
            # ZFS clone (requires dataset setup, complex for test)
            print("⚠️  ZFS detected but clone requires dataset setup, using reflink")
        except Exception:
            pass

    # Try cp --reflink for CoW on supported filesystems
    try:
        subprocess.run(
            ["cp", "--reflink=auto", "-r", str(source_path), str(target_path)],
            check=True,
            timeout=60,
        )
        print(f"✅ CoW reflink copy created: {target_path}")
        return True
    except subprocess.CalledProcessError:
        print("⚠️  --reflink failed, falling back to regular copy")

    # Fallback to regular recursive copy
    try:
        shutil.copytree(source_path, target_path, dirs_exist_ok=False)
        print(f"✅ Regular copy created (CoW not supported): {target_path}")
        return False  # Not actually CoW, but copy succeeded
    except Exception as e:
        print(f"❌ All copy methods failed: {e}")
        raise


@pytest.mark.e2e
@pytest.mark.timeout(300)  # 5 minute timeout
def test_cow_clone_independent_indexing():
    """Test that CoW cloned repos maintain independent Qdrant databases."""

    print("\n🧪 Starting CoW clone independence test")

    # Test requires VoyageAI API key
    if not os.getenv("VOYAGE_API_KEY"):
        pytest.skip("VOYAGE_API_KEY environment variable not set")

    test_base_dir = None
    original_repo = None
    cow_cloned_repo = None

    try:
        # Step 1: Create test environment
        print("\n=== Step 1: Setting up test environment ===")
        test_base_dir = Path(tempfile.mkdtemp(prefix="cow_test_"))
        print(f"📁 Test directory: {test_base_dir}")

        # Step 2: Clone the test repository
        print("\n=== Step 2: Cloning test repository ===")
        original_repo = test_base_dir / "original_tries"

        subprocess.run(
            [
                "git",
                "clone",
                "https://github.com/jsbattig/tries.git",
                str(original_repo),
            ],
            check=True,
            timeout=60,
        )
        print(f"✅ Repository cloned to: {original_repo}")

        # Step 3: Initialize and index original repo
        print("\n=== Step 3: Initializing original repository ===")

        # Initialize with VoyageAI
        run_cli_command(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=original_repo,
            timeout=30,
        )
        print("✅ Original repo initialized with VoyageAI")

        # Start services
        start_result = subprocess.run(
            ["code-indexer", "start"],
            cwd=original_repo,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if start_result.returncode != 0:
            print(f"⚠️  Start command output: {start_result.stdout}")
            print(f"⚠️  Start command errors: {start_result.stderr}")
            # Services might already be running, continue

        # Index the original repository (larger timeout for external repo)
        run_cli_command(["code-indexer", "index"], cwd=original_repo, timeout=300)
        print("✅ Original repo indexed")

        # Verify original indexing worked
        query_result = run_cli_command(
            ["code-indexer", "query", "trie data structure", "--quiet"],
            cwd=original_repo,
            timeout=30,
        )

        if not query_result.stdout.strip():
            pytest.fail("Original repo indexing failed - no search results")
        print("✅ Original repo search verified")

        # Step 4: Perform CoW clone
        print("\n=== Step 4: Performing CoW clone ===")

        fs_type = detect_filesystem_type()
        cow_cloned_repo = test_base_dir / "cow_cloned_tries"

        is_true_cow = perform_cow_clone(original_repo, cow_cloned_repo, fs_type)

        # Verify clone exists and has expected structure
        assert cow_cloned_repo.exists(), "CoW clone directory should exist"
        assert (
            cow_cloned_repo / ".code-indexer"
        ).exists(), "CoW clone should have .code-indexer directory"
        assert (
            cow_cloned_repo / ".code-indexer" / "config.json"
        ).exists(), "CoW clone should have config.json"

        # Check if Qdrant collection was copied
        qdrant_collection_dir = cow_cloned_repo / ".code-indexer" / "qdrant_collection"
        if qdrant_collection_dir.exists():
            print("✅ Qdrant collection directory found in CoW clone")
        else:
            print(
                "⚠️  No Qdrant collection directory in clone (will be created on index)"
            )

        # Step 5: Create unique file in CoW clone
        print("\n=== Step 5: Creating unique file in CoW clone ===")

        unique_content = """
{ UNIQUE_COW_TEST_CONTENT - This content only exists in the CoW clone }
{ Testing CoW clone independence with special marker: COW_CLONE_MARKER_12345 }

unit CoWTestUnit;

interface

type
  TCoWTestClass = class
  private
    cowTestIdentifier: string;
  public
    constructor Create;
    procedure PerformCoWTest;
  end;

implementation

constructor TCoWTestClass.Create;
begin
  cowTestIdentifier := 'COW_UNIQUE_IDENTIFIER_ABCDEF';
end;

procedure TCoWTestClass.PerformCoWTest;
begin
  WriteLn('This method only exists in CoW clone: COW_METHOD_SIGNATURE');
  { Unique test content for verification }
end;

end.
        """

        # Create the file with .pas extension to match the repository's file types
        unique_file = cow_cloned_repo / "CoWTestFile.pas"
        unique_file.write_text(unique_content)
        print(f"✅ Created unique file: {unique_file}")

        # Step 6: Fix configuration in CoW clone (MANDATORY for independence)
        print("\n=== Step 6: Fixing configuration in CoW clone ===")

        # Run fix-config to ensure clone gets its own containers and ports
        print(f"🔧 Running fix-config in: {cow_cloned_repo}")
        fix_result = run_cli_command(
            ["code-indexer", "fix-config", "--force", "--verbose"],
            cwd=cow_cloned_repo,
            timeout=60,
        )

        # Show fix-config output to verify it worked
        print("📋 Fix-config output:")
        print(fix_result.stdout)
        if fix_result.stderr:
            print("⚠️ Fix-config errors:")
            print(fix_result.stderr)
        print("✅ CoW clone configuration fixed for independence")

        # Step 7: Start services in CoW clone and index
        print("\n=== Step 7: Starting services in CoW clone ===")

        # The CoW clone should now use its own isolated containers and database
        start_result = subprocess.run(
            ["code-indexer", "start"],
            cwd=cow_cloned_repo,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if start_result.returncode != 0:
            print(f"⚠️  CoW start output: {start_result.stdout}")
            print(f"⚠️  CoW start errors: {start_result.stderr}")
            # Continue - services might be running

        print("✅ Services started in CoW clone")

        # Index the CoW clone (should pick up the new file)
        run_cli_command(["code-indexer", "index"], cwd=cow_cloned_repo, timeout=300)
        print("✅ CoW clone indexed (including new file)")

        # Step 8: Query for unique content
        print("\n=== Step 8: Testing CoW clone independence ===")

        # First check if the unique file was included in indexing
        status_result = run_cli_command(
            ["code-indexer", "status"], cwd=cow_cloned_repo, timeout=30
        )
        print(f"📊 Indexing status: {status_result.stdout}")

        # Query for content that only exists in the CoW clone
        cow_query_result = run_cli_command(
            ["code-indexer", "query", "COW_UNIQUE_IDENTIFIER_ABCDEF", "--quiet"],
            cwd=cow_cloned_repo,
            timeout=30,
        )

        print(f"🔍 CoW query result: {cow_query_result.stdout[:200]}...")

        # Try a broader search for the file name
        file_query_result = run_cli_command(
            ["code-indexer", "query", "CoWTestFile", "--quiet"],
            cwd=cow_cloned_repo,
            timeout=30,
        )

        print(f"🔍 File name query result: {file_query_result.stdout[:200]}...")

        # Step 9: Verify results
        print("\n=== Step 9: Verifying independence ===")

        # The CoW clone should find the unique content
        cow_results = cow_query_result.stdout.strip()
        file_results = file_query_result.stdout.strip()

        # Check if either the unique identifier or the file name was found
        if (
            "COW_UNIQUE_IDENTIFIER_ABCDEF" in cow_results
            or "CoWTestFile" in file_results
        ):
            print("✅ CoW clone found unique content - independence verified!")
            unique_content_found = True
        else:
            print("⚠️  Unique content not found in search results")
            print(
                f"Looking for 'COW_UNIQUE_IDENTIFIER_ABCDEF' in: {cow_results[:100]}..."
            )
            print(f"Looking for 'CoWTestFile' in: {file_results[:100]}...")
            unique_content_found = False

        # For the test to pass, we need to find the unique content
        assert (
            unique_content_found
        ), "CoW clone should find unique content (either identifier or filename)"

        print("✅ CoW clone found unique content - independence verified!")

        # Verify original repo does NOT have the unique content
        try:
            original_query_result = run_cli_command(
                ["code-indexer", "query", "COW_UNIQUE_IDENTIFIER_ABCDEF", "--quiet"],
                cwd=original_repo,
                timeout=30,
            )

            original_results = original_query_result.stdout.strip()
            # Original should not find the content (it doesn't exist there)
            if "COW_UNIQUE_IDENTIFIER_ABCDEF" in original_results:
                pytest.fail("Original repo should NOT find CoW-specific content")

            print("✅ Original repo correctly isolated from CoW changes")

        except subprocess.CalledProcessError:
            # No results is expected for original repo
            print("✅ Original repo has no results for CoW content (as expected)")

        print(f"\n🎉 CoW clone test completed successfully! (CoW: {is_true_cow})")

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        raise

    finally:
        # Step 10: Cleanup
        print("\n=== Step 10: Cleanup ===")

        cleanup_dirs = []
        if cow_cloned_repo and cow_cloned_repo.exists():
            cleanup_dirs.append(cow_cloned_repo)
        if original_repo and original_repo.exists():
            cleanup_dirs.append(original_repo)

        # Stop services in both directories
        for repo_dir in cleanup_dirs:
            try:
                print(f"🛑 Stopping services in {repo_dir.name}")
                subprocess.run(
                    ["code-indexer", "stop"],
                    cwd=repo_dir,
                    capture_output=True,
                    timeout=30,
                )
            except Exception as e:
                print(f"⚠️  Could not stop services in {repo_dir.name}: {e}")

        # Remove test directory
        if test_base_dir and test_base_dir.exists():
            try:
                print(f"🗑️  Removing test directory: {test_base_dir}")
                shutil.rmtree(test_base_dir, ignore_errors=True)
                print("✅ Cleanup completed")
            except Exception as e:
                print(f"⚠️  Cleanup error: {e}")


if __name__ == "__main__":
    # Run the test directly
    test_cow_clone_independent_indexing()
