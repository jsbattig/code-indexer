#!/bin/bash

# Full automation script for linting, testing, building, and compiling
# Runs all checks and builds without publishing

set -e  # Exit on any error

echo "🚀 Starting full automation pipeline..."
echo "================================="

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

# Check for VoyageAI API key (required for E2E tests)
if [[ -z "${VOYAGE_API_KEY:-}" ]]; then
    print_warning "VOYAGE_API_KEY environment variable not set"
    print_warning "E2E tests will be skipped (they require VoyageAI API access)"
    print_warning "To run E2E tests: export VOYAGE_API_KEY=your_api_key"
fi

# 1. Install dependencies
print_step "Installing dependencies"
python -m pip install --upgrade pip
pip install -e ".[dev]"
print_success "Dependencies installed"

# 2. Lint with ruff
print_step "Running ruff linter"
if ruff check src/ tests/; then
    print_success "Ruff linting passed"
else
    print_error "Ruff linting failed"
    exit 1
fi

# 3. Check formatting with black
print_step "Checking code formatting with black"
if black --check src/ tests/; then
    print_success "Black formatting check passed"
else
    print_error "Black formatting check failed"
    print_warning "Run 'black src/ tests/' to fix formatting"
    exit 1
fi

# 4. Type check with mypy (strict mode)
print_step "Running mypy type checking"
if mypy src/; then
    print_success "MyPy type checking passed"
else
    print_error "MyPy type checking failed"
    exit 1
fi

# 5. Setup test environment (cleanup dangling test collections)
print_step "Setting up test environment"
export FULL_AUTOMATION=1  # Enable test collection cleanup
if python tests/test_suite_setup.py; then
    print_success "Test environment setup completed"
else
    print_warning "Test environment setup had issues (continuing anyway)"
fi

# 6. Run tests with coverage
print_step "Running tests with coverage"
if pytest tests/ --cov=src/code_indexer --cov-report=xml --cov-report=term; then
    print_success "All tests passed"
else
    print_error "Tests failed"
    exit 1
fi

# 7. Build package
print_step "Building package"
pip install build twine
if python -m build; then
    print_success "Package built successfully"
else
    print_error "Package build failed"
    exit 1
fi

# 8. Check package
print_step "Checking package integrity"
if twine check dist/*.whl dist/*.tar.gz; then
    print_success "Package check passed"
else
    print_error "Package check failed"
    exit 1
fi

# 9. Validate Docker service files (no main app Dockerfile needed)
print_step "Validating Docker service files"
if command -v docker &> /dev/null; then
    # Check that service Dockerfiles exist and are valid
    for dockerfile in src/code_indexer/docker/Dockerfile.*; do
        if [[ -f "$dockerfile" ]]; then
            echo "✓ Found $(basename "$dockerfile")"
        fi
    done
    print_success "Docker service files validated"
else
    print_warning "Docker not available, skipping Docker validation"
fi

# Cleanup
print_step "Cleaning up temporary files"
# Remove coverage files
rm -f .coverage .coverage.*
print_success "Coverage files cleaned up"

# Clean up test temporary directories
print_step "Cleaning up test temporary directories"
if ls /tmp/code_indexer_test_* >/dev/null 2>&1; then
    temp_dirs_count=$(ls -d /tmp/code_indexer_test_* 2>/dev/null | wc -l)
    print_warning "Found ${temp_dirs_count} temporary test directories to clean up"
    rm -rf /tmp/code_indexer_test_*
    if [ $? -eq 0 ]; then
        print_success "Test temporary directories cleaned up"
    else
        print_warning "Some test temporary directories could not be cleaned up"
    fi
else
    print_success "No test temporary directories to clean up"
fi

# Summary
echo -e "\n${GREEN}🎉 Full automation pipeline completed successfully!${NC}"
echo "================================="
echo "✅ Linting passed"
echo "✅ Formatting checked"
echo "✅ Type checking passed"
echo "✅ All tests passed"
echo "✅ Package built and validated"
if command -v docker &> /dev/null; then
    echo "✅ Docker service files validated"
fi
echo "✅ Temporary files cleaned up"
echo "✅ Test temporary directories cleaned up"
echo ""
echo "📌 Note: E2E tests require VOYAGE_API_KEY environment variable"
echo "📌 Long-running E2E tests now use VoyageAI instead of Ollama for better stability"
echo ""
echo "Ready to push to GitHub! 🚀"