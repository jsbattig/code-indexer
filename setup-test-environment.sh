#!/bin/bash

# Test environment setup script - proper modular approach
# This script handles service startup for test environment

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_step() {
    echo -e "\n${BLUE}➡️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

echo "🚀 Setting up test environment..."
echo "================================"

# Create a shared test services project
print_step "Preparing shared test services"
SHARED_TEST_DIR="$HOME/.tmp/shared_test_services"
mkdir -p "$SHARED_TEST_DIR"

# Create minimal project structure
echo "# Shared test services project" > "$SHARED_TEST_DIR/README.md"
echo "print('Test services project')" > "$SHARED_TEST_DIR/main.py"

# Store current directory
ORIGINAL_DIR=$(pwd)

# Move to test services directory
cd "$SHARED_TEST_DIR"

# Initialize and start services using proper commands
print_step "Starting services using code-indexer commands"

# Initialize if not already done
if [[ ! -f ".code-indexer/config.json" ]]; then
    echo "   Initializing shared test project..."
    if code-indexer init --force --embedding-provider voyage-ai; then
        print_success "Test project initialized"
    else
        print_error "Failed to initialize test project"
        cd "$ORIGINAL_DIR"
        exit 1
    fi
else
    echo "   Test project already initialized"
fi

# Verify config was created
if [[ ! -f ".code-indexer/config.json" ]]; then
    print_error "Configuration file was not created properly"
    cd "$ORIGINAL_DIR"
    exit 1
fi

# Start services using the proper command
echo "   Starting services with code-indexer start..."
if code-indexer start; then
    print_success "Services started successfully"
elif code-indexer status; then
    print_success "Services are already running"
else
    print_warning "Service start had issues, but continuing..."
fi

# Verify services are ready
print_step "Verifying service readiness"
if code-indexer status; then
    print_success "All services are ready for testing"
else
    print_warning "Service status check had issues (continuing anyway)"
fi

# Return to original directory
cd "$ORIGINAL_DIR"

# Clean up test collections using existing services
print_step "Cleaning up test collections"
export FULL_AUTOMATION=1  # Enable test collection cleanup

# Detect the actual Qdrant port from running services
echo "   Detecting Qdrant port from running services..."
QDRANT_PORT=""
for port in 7003 6333 6334 6335 6902 7249 6560; do
    if curl -s "http://localhost:$port/cluster" >/dev/null 2>&1; then
        QDRANT_PORT=$port
        echo "   Found Qdrant running on port $port"
        break
    fi
done

if [[ -z "$QDRANT_PORT" ]]; then
    print_warning "Could not detect Qdrant port, skipping collection cleanup"
else
    # Use a direct cleanup approach that doesn't try to start services
    python -c "
import sys
sys.path.insert(0, '$ORIGINAL_DIR/tests')
sys.path.insert(0, '$ORIGINAL_DIR/src')

from test_suite_setup import cleanup_test_collections
from rich.console import Console

console = Console()
try:
    # Use the detected port
    result = cleanup_test_collections(console=console, qdrant_port=$QDRANT_PORT)
    if 'error' not in result:
        total = result.get('total_deleted', 0)
        if total > 0:
            console.print(f'✅ Cleaned up {total} test collections', style='green')
        else:
            console.print('✅ No test collections to clean up', style='green')
    else:
        console.print(f'⚠️  Collection cleanup: {result[\"error\"]}', style='yellow')
except Exception as e:
    console.print(f'⚠️  Collection cleanup failed: {e}', style='yellow')
    # Non-fatal error
"
fi

if [ $? -eq 0 ]; then
    print_success "Test collection cleanup completed"
else
    print_warning "Test collection cleanup had issues (continuing anyway)"
fi

print_success "Environment setup completed using proper code-indexer commands"