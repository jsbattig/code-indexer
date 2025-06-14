#!/usr/bin/env python3
"""
Test runner for the code-indexer project.
Runs all unit tests and optionally integration tests.
"""

import sys
import os
import unittest
import argparse

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def discover_unit_tests():
    """Discover and return unit test suite."""
    loader = unittest.TestLoader()

    # Discover all test files except integration tests
    suite = unittest.TestSuite()

    # Add specific test modules
    test_modules = ["test_chunker", "test_config", "test_docker_manager_simple"]

    for module_name in test_modules:
        try:
            module = __import__(module_name)
            module_suite = loader.loadTestsFromModule(module)
            suite.addTest(module_suite)
        except ImportError as e:
            print(f"Warning: Could not import {module_name}: {e}")

    return suite


def run_integration_tests():
    """Run integration tests."""
    try:
        from test_integration_multiproject import run_integration_tests

        return run_integration_tests()
    except ImportError as e:
        print(f"Could not run integration tests: {e}")
        return False


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="Run code-indexer tests")
    parser.add_argument(
        "--integration",
        action="store_true",
        help="Run integration tests (requires Docker)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose test output"
    )

    args = parser.parse_args()

    # Set verbosity
    verbosity = 2 if args.verbose else 1

    print("=" * 60)
    print("Running Code Indexer Tests")
    print("=" * 60)

    # Run unit tests
    print("\n🧪 Running Unit Tests...")
    unit_suite = discover_unit_tests()
    unit_runner = unittest.TextTestRunner(verbosity=verbosity)
    unit_result = unit_runner.run(unit_suite)

    # Print unit test summary
    print("\nUnit Tests Summary:")
    print(f"  Tests run: {unit_result.testsRun}")
    print(f"  Failures: {len(unit_result.failures)}")
    print(f"  Errors: {len(unit_result.errors)}")
    print(f"  Success: {unit_result.wasSuccessful()}")

    # Run integration tests if requested
    integration_success = True
    if args.integration:
        print("\n🔧 Running Integration Tests...")
        os.environ["RUN_INTEGRATION_TESTS"] = "1"
        integration_success = run_integration_tests()
        print(f"Integration Tests Success: {integration_success}")
    else:
        print("\n⏭️  Skipping integration tests (use --integration to run)")

    # Overall summary
    print("\n" + "=" * 60)
    overall_success = unit_result.wasSuccessful() and integration_success
    print(f"Overall Test Result: {'✅ PASS' if overall_success else '❌ FAIL'}")
    print("=" * 60)

    # Exit with appropriate code
    sys.exit(0 if overall_success else 1)


if __name__ == "__main__":
    main()
