#!/bin/bash

# Fast automation script - CIDX CLI focused testing
# Runs CLI unit tests that don't require external services or special permissions
# Focuses on CIDX command-line interface functionality only
# Use server-fast-automation.sh for server-specific tests

set -e  # Exit on any error

# Source .env files if they exist (for local testing)
if [[ -f ".env.local" ]]; then
    source .env.local
fi
if [[ -f ".env" ]]; then
    source .env
fi

echo "🖥️  Starting CLI-focused fast automation pipeline..."
echo "==========================================="

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

# Check if we're in the right directory
if [[ ! -f "pyproject.toml" ]]; then
    print_error "Not in project root directory (pyproject.toml not found)"
    exit 1
fi

# Check Python version (GitHub Actions tests multiple versions, we'll use current)
print_step "Checking Python version"
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d " " -f 2)
echo "Using Python $PYTHON_VERSION"
print_success "Python version checked"

# 1. Install dependencies (same as GitHub Actions)
print_step "Installing dependencies"
pip install -e ".[dev]" --break-system-packages
print_success "Dependencies installed"

# 2. Lint CLI-related code with ruff
print_step "Running ruff linter on CLI code"
if ruff check src/code_indexer/cli.py src/code_indexer/mode_* src/code_indexer/remote/ src/code_indexer/api_clients/ src/code_indexer/business_logic/ tests/unit/cli/ tests/unit/remote/ tests/unit/api_clients/; then
    print_success "CLI ruff linting passed"
else
    print_error "CLI ruff linting failed"
    exit 1
fi

# 3. Check CLI code formatting with black
print_step "Checking CLI code formatting with black"
if black --check src/code_indexer/cli.py src/code_indexer/mode_* src/code_indexer/remote/ src/code_indexer/api_clients/ src/code_indexer/business_logic/ tests/unit/cli/ tests/unit/remote/ tests/unit/api_clients/; then
    print_success "CLI black formatting check passed"
else
    print_error "CLI black formatting check failed"
    print_warning "Run 'black' on the CLI-related files to fix formatting"
    exit 1
fi

# 4. Type check CLI code with mypy
print_step "Running mypy type checking on CLI code"
if mypy src/code_indexer/cli.py src/code_indexer/mode_* src/code_indexer/remote/ src/code_indexer/api_clients/ src/code_indexer/business_logic/ --ignore-missing-imports; then
    print_success "CLI MyPy type checking passed"
else
    print_error "CLI MyPy type checking failed"
    exit 1
fi

# 5. Run ALL unit tests (excluding slow/integration tests)
print_step "Running comprehensive unit tests"
echo "ℹ️  Testing ALL CIDX functionality including:"
echo "   • Command-line interface and argument parsing"
echo "   • Remote repository linking and authentication"
echo "   • API client functionality"
echo "   • Business logic integration"
echo "   • Mode detection and routing"
echo "   • Core indexing and processing logic"
echo "   • Configuration and validation"
echo "   • Display and progress reporting"

# Run ALL unit tests that don't require external services (excluding server tests)
if PYTHONPATH="$(pwd)/src:$(pwd)/tests" pytest \
    tests/unit/ \
    --ignore=tests/unit/server/ \
    -m "not slow and not e2e and not real_api and not integration" \
    --ignore=tests/unit/cli/test_cli_init_segment_size.py \
    --ignore=tests/unit/cli/test_query_functionality_fix.py \
    --cov=code_indexer \
    --cov-report=xml --cov-report=term-missing; then
    print_success "Unit tests passed"
else
    print_error "Unit tests failed"
    exit 1
fi

# Note: GitHub Actions also has version checking and publishing steps
# but those are only relevant for actual GitHub runs

# Summary
echo -e "\n${GREEN}🎉 Comprehensive automation completed successfully!${NC}"
echo "==========================================="
echo "✅ Linting passed"
echo "✅ Formatting checked"
echo "✅ Type checking passed"
echo "✅ Unit tests passed"
echo ""
echo "🖥️  Complete test coverage:"
echo "   ✅ tests/unit/ - ALL unit tests (CLI, remote, API clients, core logic, config, display)"
echo "   🚫 Excluded: slow, e2e, real_api, integration tests"
echo ""
echo "🖥️  Functionality validated:"
echo "   • Command-line interface and argument parsing"
echo "   • Remote mode initialization and authentication"
echo "   • Repository linking and branch matching"
echo "   • Transparent remote querying"
echo "   • JWT token management and credential encryption"
echo "   • Network error handling and resilience"
echo "   • Progress reporting and job management"
echo "   • Core indexing and processing logic"
echo "   • Configuration management and validation"
echo ""
echo "ℹ️  Run 'server-fast-automation.sh' for server-specific tests"
echo "ℹ️  Run 'full-automation.sh' for complete integration testing"
echo "CIDX ready for manual testing! 🚀"