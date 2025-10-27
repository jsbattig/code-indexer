#!/bin/bash

# Server-focused fast automation script - tests CIDX server functionality
# Runs server unit tests that don't require external services or special permissions
# Separated from main fast-automation.sh to focus on server components

set -e  # Exit on any error

# Source .env files if they exist (for local testing)
if [[ -f ".env.local" ]]; then
    source .env.local
fi
if [[ -f ".env" ]]; then
    source .env
fi

echo "🖥️  Starting server-focused fast automation pipeline..."
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

# Check Python version
print_step "Checking Python version"
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d " " -f 2)
echo "Using Python $PYTHON_VERSION"
print_success "Python version checked"

# 1. Install dependencies
print_step "Installing dependencies"
python3 -m pip install -e ".[dev]"
print_success "Dependencies installed"

# 2. Lint server code with ruff
print_step "Running ruff linter on server code"
if ruff check src/code_indexer/server/ tests/unit/server/; then
    print_success "Server ruff linting passed"
else
    print_error "Server ruff linting failed"
    exit 1
fi

# 3. Check server code formatting with black
print_step "Checking server code formatting with black"
if black --check src/code_indexer/server/ tests/unit/server/; then
    print_success "Server black formatting check passed"
else
    print_error "Server black formatting check failed"
    print_warning "Run 'black src/code_indexer/server/ tests/unit/server/' to fix formatting"
    exit 1
fi

# 4. Type check server code with mypy
print_step "Running mypy type checking on server code"
if mypy src/code_indexer/server/ --ignore-missing-imports; then
    print_success "Server MyPy type checking passed"
else
    print_error "Server MyPy type checking failed"
    exit 1
fi

# 5. Run server unit tests only
print_step "Running server unit tests"
echo "ℹ️  Testing CIDX server functionality including:"
echo "   • API endpoints and authentication"
echo "   • Repository management"
echo "   • Job management and sync orchestration"
echo "   • Validation and error handling"
echo "   • Branch operations"

# Run server-specific unit tests
if PYTHONPATH="$(pwd)/src:$(pwd)/tests" pytest \
    tests/unit/server/ \
    -m "not slow and not e2e and not real_api and not integration" \
    --cov=code_indexer.server \
    --cov-report=xml --cov-report=term-missing; then
    print_success "Server unit tests passed"
else
    print_error "Server unit tests failed"
    exit 1
fi

# Summary
echo -e "\n${GREEN}🎉 Server-focused automation completed successfully!${NC}"
echo "==========================================="
echo "✅ Server linting passed"
echo "✅ Server formatting checked"
echo "✅ Server type checking passed"
echo "✅ Server unit tests passed"
echo ""
echo "🖥️  Server test coverage:"
echo "   ✅ tests/unit/server/ - Server API and core functionality"
echo "   ✅ Authentication and authorization tests"
echo "   ✅ Repository management tests"
echo "   ✅ Job management and orchestration tests"
echo "   ✅ Validation and error handling tests"
echo ""
echo "ℹ️  This complements fast-automation.sh (CLI tests) for complete coverage"
echo "Ready for server deployment! 🚀"