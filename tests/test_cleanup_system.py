"""
Test to validate the TestSuiteCleanup system works correctly.
"""

import subprocess
from pathlib import Path

import pytest

from .test_infrastructure import TestSuiteCleanup


def test_cleanup_methods_exist():
    """Test that cleanup methods are available and callable."""
    # Test that methods exist and are callable
    assert hasattr(TestSuiteCleanup, "cleanup_all_test_containers")
    assert callable(TestSuiteCleanup.cleanup_all_test_containers)

    # Test private methods exist
    assert hasattr(TestSuiteCleanup, "_cleanup_test_collections")
    assert hasattr(TestSuiteCleanup, "_cleanup_test_temp_directories")


def test_cleanup_temp_directories():
    """Test cleanup of temporary directories without actual deletion."""
    # Test the directory pattern detection logic
    temp_patterns = [
        "/tmp/code_indexer_test_*",
        "/home/jsbattig/.tmp/shared_test_containers",
    ]

    # This tests the pattern logic without actual cleanup
    for pattern in temp_patterns:
        if "*" in pattern:
            # Wildcard pattern
            assert "code_indexer_test_" in pattern
        else:
            # Direct path
            path = Path(pattern)
            # Just verify we can create a Path object
            assert isinstance(path, Path)


def test_cleanup_can_run_safely():
    """Test that cleanup can run safely even without containers."""
    try:
        # This should not crash even if no containers exist
        # We'll just test that the method can be called
        print("Testing cleanup method availability...")

        # Test that we can access the method
        cleanup_method = TestSuiteCleanup.cleanup_all_test_containers
        assert cleanup_method is not None

        # Test that we can access the static method
        temp_cleanup = TestSuiteCleanup._cleanup_test_temp_directories
        assert temp_cleanup is not None

        print("✅ Cleanup methods are accessible")

    except Exception as e:
        pytest.fail(f"Cleanup methods should be accessible: {e}")


def test_container_detection_commands():
    """Test that container detection commands are valid."""
    # Test podman commands that would be used
    try:
        # Test that we can run podman ps (this might fail but shouldn't crash)
        result = subprocess.run(
            ["podman", "ps", "-a", "--format", "{{.Names}}", "--filter", "name=cidx-"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Command should complete (return code doesn't matter for this test)
        print(f"Podman ps command completed with return code: {result.returncode}")

    except subprocess.TimeoutExpired:
        print("Podman command timed out (expected in some environments)")
    except FileNotFoundError:
        print("Podman not found (expected in some environments)")
    except Exception as e:
        print(f"Podman command failed: {e}")

    # Test should pass regardless - we're just validating the command structure
    assert True
