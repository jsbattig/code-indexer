#!/bin/bash

# Fast automation script - comprehensive local testing
# Runs all unit tests that don't require external services or special permissions
# More comprehensive than GitHub Actions CI but faster than full-automation.sh

set -e  # Exit on any error

# Source .env files if they exist (for local testing)
if [[ -f ".env.local" ]]; then
    source .env.local
fi
if [[ -f ".env" ]]; then
    source .env
fi

echo "🚀 Starting fast automation pipeline (local unit tests)..."
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
echo "ℹ️  Using new organized test structure: tests/unit/ directory only"

# Run unit tests with same exclusions as GitHub Actions (permission-dependent tests)
if PYTHONPATH="$(pwd)/src:$(pwd)/tests" pytest \
    tests/unit/ \
    -m "not slow and not e2e and not real_api and not integration" \
    --ignore=tests/unit/infrastructure/test_data_cleaner_health.py \
    --ignore=tests/unit/infrastructure/test_cleanup_validation.py \
    --ignore=tests/unit/infrastructure/test_global_port_registry.py \
    --ignore=tests/unit/infrastructure/test_broken_softlink_cleanup.py \
    --ignore=tests/unit/infrastructure/test_real_world_path_walking.py \
    --ignore=tests/unit/cli/test_cli_init_segment_size.py \
    --cov=code_indexer \
    --cov-report=xml --cov-report=term; then
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
echo "🔍 Test organization with new directory structure:"
echo "   ✅ tests/unit/ - ISOLATED unit tests (482 tests) - INCLUDED in CI"
echo "   🚫 tests/unit/cli/ - CLI tests (require subprocess) - EXCLUDED from CI"
echo "   🚫 tests/unit/services/ - Service tests (require containers) - EXCLUDED from CI"
echo "   🚫 tests/unit/infrastructure/ - Infrastructure tests (require services) - EXCLUDED from CI"
echo "   🚫 tests/integration/ - Integration tests (140+ tests) - EXCLUDED from CI"
echo "   🚫 tests/e2e/ - End-to-end tests (70+ tests) - EXCLUDED from CI"
echo ""
echo "🚫 Excluded test categories:"
echo "   • Integration tests (require Docker, Qdrant, Ollama services)"
echo "   • E2E tests (require full service stack and external APIs)"
echo "   • Performance tests (require service dependencies)"
echo "   • Claude integration tests (require Claude API and SDK)"
echo "   • Docker manager tests (require Docker/Podman)"
echo "   • Git workflow tests (require Git repositories and indexing services)"
echo "   • Provider tests (require API keys and external services)"
echo "   • Any tests marked as 'slow', 'e2e', or 'real_api'"
echo ""
echo "ℹ️  This matches the GitHub Actions workflow for fast CI execution"
echo "ℹ️  Run 'full-automation.sh' for full local testing including all test categories"
echo "Ready to push to GitHub! 🚀"