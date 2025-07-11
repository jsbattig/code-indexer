"""
Helper functions for ensuring CoW-compatible test environments.

This module provides utilities to ensure tests run with the proper
Copy-on-Write architecture and don't get blocked by legacy containers.
"""

import logging
from code_indexer.services.docker_manager import DockerManager

logger = logging.getLogger(__name__)


def ensure_clean_cow_environment(force: bool = True) -> bool:
    """
    Ensure test environment has no legacy containers.

    This function removes any existing legacy containers to ensure
    tests start with a clean slate and don't get blocked by legacy detection.

    Args:
        force: Whether to force container removal

    Returns:
        True if environment is clean, False otherwise
    """
    try:
        # Use DockerManager to detect and remove any existing containers
        docker_manager = DockerManager(project_name="test_shared")

        # Remove all containers and volumes to ensure clean state
        success = docker_manager.remove_containers(remove_volumes=True)

        if success:
            logger.info("✅ Cleaned legacy containers for test environment")
        else:
            logger.warning("⚠️  Failed to clean legacy containers")

        return bool(success)

    except Exception as e:
        logger.error(f"❌ Error cleaning test environment: {e}")
        return False


def check_cow_compatibility() -> bool:
    """
    Check if current environment is CoW-compatible.

    Returns:
        True if environment is ready for CoW tests
    """
    try:
        from code_indexer.services.legacy_detector import legacy_detector
        import asyncio

        # Run legacy detection
        is_legacy = asyncio.run(legacy_detector.check_legacy_container())

        if is_legacy:
            logger.warning("⚠️  Legacy containers detected in test environment")
            return False
        else:
            logger.info("✅ Test environment is CoW-compatible")
            return True

    except Exception as e:
        logger.error(f"❌ Error checking CoW compatibility: {e}")
        return False


def setup_cow_test_environment() -> bool:
    """
    Complete setup for CoW-compatible test environment.

    This combines cleaning and validation to ensure tests can run.

    Returns:
        True if environment is ready
    """
    logger.info("🔧 Setting up CoW test environment...")

    # First clean any existing legacy containers
    if not ensure_clean_cow_environment():
        logger.error("❌ Failed to clean test environment")
        return False

    # Then verify compatibility
    if not check_cow_compatibility():
        logger.error("❌ Test environment is not CoW-compatible after cleanup")
        return False

    logger.info("✅ CoW test environment ready")
    return True
