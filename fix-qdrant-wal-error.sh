#!/bin/bash

# Fix for Qdrant WAL (Write-Ahead Log) error in test infrastructure
# This cleans up corrupted or locked Qdrant data

echo "🔧 Fixing Qdrant WAL error in test infrastructure..."
echo "=================================================="

# Shared test directory
SHARED_TEST_DIR="$HOME/.tmp/shared_test_containers"
SHARED_TEST_DIR_DOCKER="$HOME/.tmp/shared_test_containers_docker"

# Function to clean Qdrant data
clean_qdrant_data() {
    local dir=$1
    echo "Cleaning Qdrant data in: $dir"
    
    if [ -d "$dir/.code-indexer/qdrant" ]; then
        echo "  Found Qdrant directory, cleaning..."
        
        # Stop any containers using this directory
        echo "  Stopping any running containers..."
        cd "$dir" 2>/dev/null && code-indexer stop 2>/dev/null || true
        
        # Remove Qdrant data directory
        echo "  Removing Qdrant data..."
        rm -rf "$dir/.code-indexer/qdrant/storage" 2>/dev/null || true
        rm -rf "$dir/.code-indexer/qdrant/snapshots" 2>/dev/null || true
        rm -rf "$dir/.code-indexer/qdrant/log" 2>/dev/null || true
        rm -rf "$dir/.code-indexer/qdrant/wal" 2>/dev/null || true
        
        # Remove any lock files
        find "$dir/.code-indexer/qdrant" -name "*.lock" -type f -delete 2>/dev/null || true
        
        echo "  ✅ Cleaned Qdrant data"
    else
        echo "  No Qdrant directory found"
    fi
}

# Clean both podman and docker shared directories
if [ -d "$SHARED_TEST_DIR" ]; then
    echo ""
    echo "🧹 Cleaning Podman shared test directory..."
    clean_qdrant_data "$SHARED_TEST_DIR"
fi

if [ -d "$SHARED_TEST_DIR_DOCKER" ]; then
    echo ""
    echo "🧹 Cleaning Docker shared test directory..."
    clean_qdrant_data "$SHARED_TEST_DIR_DOCKER"
fi

# Also check for any Qdrant containers that might be stuck
echo ""
echo "🐳 Checking for stuck Qdrant containers..."

# For Podman
if command -v podman &> /dev/null; then
    echo "  Checking Podman containers..."
    stuck_containers=$(podman ps -a --filter "name=qdrant" --filter "status=exited" -q 2>/dev/null || true)
    if [ ! -z "$stuck_containers" ]; then
        echo "  Found stuck Qdrant containers, removing..."
        podman rm -f $stuck_containers 2>/dev/null || true
    fi
fi

# For Docker
if command -v docker &> /dev/null; then
    echo "  Checking Docker containers..."
    stuck_containers=$(docker ps -a --filter "name=qdrant" --filter "status=exited" -q 2>/dev/null || true)
    if [ ! -z "$stuck_containers" ]; then
        echo "  Found stuck Qdrant containers, removing..."
        docker rm -f $stuck_containers 2>/dev/null || true
    fi
fi

echo ""
echo "🔍 Checking disk space..."
df -h "$HOME/.tmp" | grep -E "Filesystem|tmp"

echo ""
echo "✅ Cleanup complete!"
echo ""
echo "Next steps:"
echo "1. Try running your tests again"
echo "2. If the error persists, check disk space: df -h"
echo "3. Consider rebooting if filesystem issues persist"