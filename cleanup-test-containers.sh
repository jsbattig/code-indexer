#!/bin/bash

echo "🧹 Cleaning up test containers..."

# Stop all cidx containers
echo "Stopping cidx containers..."
docker ps -a --filter "name=cidx-" --format "{{.Names}}" | while read container; do
    echo "  Stopping $container"
    docker stop "$container" 2>/dev/null || true
done

# Remove all cidx containers
echo "Removing cidx containers..."
docker ps -a --filter "name=cidx-" --format "{{.Names}}" | while read container; do
    echo "  Removing $container"
    docker rm -f "$container" 2>/dev/null || true
done

# Also try with podman
if command -v podman >/dev/null 2>&1; then
    echo "Cleaning up podman containers..."
    podman ps -a --filter "name=cidx-" --format "{{.Names}}" | while read container; do
        echo "  Stopping and removing $container"
        podman rm -f "$container" 2>/dev/null || true
    done
fi

# Clean up test directories
echo "Cleaning up test directories..."
rm -rf ~/.tmp/shared_test_containers 2>/dev/null || true
rm -rf ~/.tmp/shared_test_containers_docker 2>/dev/null || true
rm -rf ~/.tmp/code_indexer_test_* 2>/dev/null || true
rm -rf ~/.tmp/isolated_test_* 2>/dev/null || true
rm -rf ~/.tmp/isolated_test_docker_* 2>/dev/null || true
rm -rf /tmp/code_indexer_test_* 2>/dev/null || true

echo "✅ Cleanup complete"