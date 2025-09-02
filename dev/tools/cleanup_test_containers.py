#!/usr/bin/env python3
"""
Cleanup script for dual-engine test containers.
This script removes any leftover containers from dual-engine testing.
"""

import subprocess
import os


def cleanup_dual_engine_containers():
    """Clean up all dual-engine test containers and networks"""
    print("🧹 Cleaning up dual-engine test containers and networks...")

    # Set dual-engine test mode
    os.environ["CODE_INDEXER_DUAL_ENGINE_TEST_MODE"] = "true"

    # Stop and remove containers for both engines with dual-engine naming
    for engine in ["podman", "docker"]:
        for service in ["ollama", "qdrant"]:
            # Use dual-engine container names
            container_name = f"code-indexer-{service}-{engine}"
            try:
                # Stop container
                result_stop = subprocess.run(
                    [engine, "stop", container_name],
                    capture_output=True,
                    timeout=30,
                )
                # Remove container
                result_rm = subprocess.run(
                    [engine, "rm", container_name],
                    capture_output=True,
                    timeout=30,
                )
                if result_stop.returncode == 0 or result_rm.returncode == 0:
                    print(f"✅ Cleaned up {container_name}")
            except Exception as e:
                print(f"⚠️  Could not clean up {container_name}: {e}")

        # Remove networks with dual-engine naming
        network_name = f"code-indexer-global-{engine}"
        try:
            subprocess.run(
                [engine, "network", "rm", network_name],
                capture_output=True,
                timeout=30,
            )
            print(f"✅ Cleaned up network {network_name}")
        except Exception as e:
            print(f"⚠️  Could not clean up network {network_name}: {e}")

    # Also clean up any legacy containers with old naming
    for engine in ["podman", "docker"]:
        for container_name in ["code-indexer-ollama", "code-indexer-qdrant"]:
            try:
                subprocess.run(
                    [engine, "stop", container_name], capture_output=True, timeout=30
                )
                subprocess.run(
                    [engine, "rm", container_name], capture_output=True, timeout=30
                )
                print(f"✅ Cleaned up legacy {container_name}")
            except Exception:
                pass

        # Clean up legacy network
        try:
            subprocess.run(
                [engine, "network", "rm", "code-indexer-global"],
                capture_output=True,
                timeout=30,
            )
            print("✅ Cleaned up legacy network code-indexer-global")
        except Exception:
            pass

    print("🧹 Cleanup completed!")


if __name__ == "__main__":
    cleanup_dual_engine_containers()
