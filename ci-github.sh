#!/bin/bash

# GitHub CI script that emulates GitHub Actions workflow
# Runs the same checks as GitHub Actions but locally (without publishing)

set -e  # Exit on any error

echo "🚀 Starting GitHub CI pipeline (local)..."
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
PYTHON_VERSION=$(python --version 2>&1 | cut -d " " -f 2)
echo "Using Python $PYTHON_VERSION"
print_success "Python version checked"

# 1. Install dependencies (same as GitHub Actions)
print_step "Installing dependencies"
python -m pip install --upgrade pip
pip install -e ".[dev]"
print_success "Dependencies installed"

# 2. Lint with ruff (same as GitHub Actions)
print_step "Running ruff linter"
if ruff check src/ tests/; then
    print_success "Ruff linting passed"
else
    print_error "Ruff linting failed"
    exit 1
fi

# 3. Check formatting with black (same as GitHub Actions)
print_step "Checking code formatting with black"
if black --check src/ tests/; then
    print_success "Black formatting check passed"
else
    print_error "Black formatting check failed"
    print_warning "Run 'black src/ tests/' to fix formatting"
    exit 1
fi

# 4. Type check with mypy (same as GitHub Actions)
print_step "Running mypy type checking"
if mypy src/ --ignore-missing-imports; then
    print_success "MyPy type checking passed"
else
    print_error "MyPy type checking failed"
    exit 1
fi

# 5. Run unit tests only (same as GitHub Actions - no E2E/integration tests)
print_step "Running unit tests only (excluding E2E/integration tests)"
echo "ℹ️  This matches GitHub Actions - only unit tests that don't require external services"

# Run the exact same test command as GitHub Actions
if pytest tests/ \
    --ignore=tests/test_e2e_embedding_providers.py \
    --ignore=tests/test_start_stop_e2e.py \
    --ignore=tests/test_end_to_end_complete.py \
    --ignore=tests/test_end_to_end_dual_engine.py \
    --ignore=tests/test_integration_multiproject.py \
    --ignore=tests/test_docker_manager.py \
    --ignore=tests/test_docker_manager_cleanup.py \
    --ignore=tests/test_docker_manager_simple.py \
    --ignore=tests/test_clean_command.py \
    --ignore=tests/test_health_checker.py \
    --ignore=tests/test_cleanup_validation.py \
    --ignore=tests/test_data_cleaner_health.py \
    --ignore=tests/test_timeout_config.py \
    --ignore=tests/test_service_readiness.py \
    --ignore=tests/test_claude_e2e.py \
    --ignore=tests/test_reconcile_e2e.py \
    -m "not slow and not e2e and not real_api" \
    --cov=src/code_indexer --cov-report=xml --cov-report=term; then
    print_success "Unit tests passed"
else
    print_error "Unit tests failed"
    exit 1
fi

# Note: GitHub Actions also has version checking and publishing steps
# but those are only relevant for actual GitHub runs

# Summary
echo -e "\n${GREEN}🎉 GitHub CI pipeline (local) completed successfully!${NC}"
echo "==========================================="
echo "✅ Linting passed"
echo "✅ Formatting checked"
echo "✅ Type checking passed"
echo "✅ Unit tests passed (E2E/integration tests excluded)"
echo ""
echo "🔍 Tests excluded (same as GitHub Actions):"
echo "   • E2E embedding provider tests"
echo "   • Start/stop E2E tests"
echo "   • End-to-end complete tests"
echo "   • Dual engine tests"
echo "   • Integration multiproject tests"
echo "   • Docker manager tests"
echo "   • Service health/cleanup tests"
echo "   • Claude E2E tests (require Claude SDK and services)"
echo "   • Reconcile E2E tests (require indexing services)"
echo "   • Any tests marked as 'slow', 'e2e', or 'real_api'"
echo ""
echo "ℹ️  This matches the GitHub Actions workflow for fast CI execution"
echo "ℹ️  Run 'ci-local.sh' for full local testing including E2E tests"
echo "Ready to push to GitHub! 🚀"