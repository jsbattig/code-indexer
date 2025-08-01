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

# Check if we need Docker-specific directory (avoid Docker/Podman permission conflicts)
if [[ "$FORCE_DOCKER" == "true" || "$1" == "--force-docker" ]]; then
    SHARED_TEST_DIR="$HOME/.tmp/shared_test_containers_docker"
    echo "   Using Docker-specific test directory to avoid permission conflicts"
else
    SHARED_TEST_DIR="$HOME/.tmp/shared_test_containers"
    echo "   Using Podman test directory (default)"
fi
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

# Initialize if not already done or if config is corrupted
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
    # Check if container names are properly configured
    if ! jq -e '.project_containers.project_hash' .code-indexer/config.json > /dev/null 2>&1; then
        echo "   Configuration incomplete, reinitializing..."
        if code-indexer init --force --embedding-provider voyage-ai; then
            print_success "Test project reinitialized"
        else
            print_error "Failed to reinitialize test project"
            cd "$ORIGINAL_DIR"
            exit 1
        fi
    fi
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

# Clean up test collections using shared cleanup script
print_step "Cleaning up test collections"
"$ORIGINAL_DIR/cleanup-test-collections.sh"

if [ $? -eq 0 ]; then
    print_success "Test collection cleanup completed"
else
    print_warning "Test collection cleanup had issues (continuing anyway)"
fi

print_success "Environment setup completed using proper code-indexer commands"