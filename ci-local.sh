#!/bin/bash

# Local CI script that emulates GitHub Actions workflow
# Runs all checks and builds without publishing

set -e  # Exit on any error

echo "🚀 Starting local CI/CD pipeline..."
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

# 4. Type check with mypy (strict mode like GitHub Actions)
print_step "Running mypy type checking"
if mypy src/; then
    print_success "MyPy type checking passed"
else
    print_error "MyPy type checking failed"
    exit 1
fi

# 5. Run tests with coverage
print_step "Running tests with coverage"
if pytest tests/ --cov=src/code_indexer --cov-report=xml --cov-report=term; then
    print_success "All tests passed"
else
    print_error "Tests failed"
    exit 1
fi

# 6. Build package
print_step "Building package"
pip install build twine
if python -m build; then
    print_success "Package built successfully"
else
    print_error "Package build failed"
    exit 1
fi

# 7. Check package
print_step "Checking package integrity"
if twine check dist/*; then
    print_success "Package check passed"
else
    print_error "Package check failed"
    exit 1
fi

# 8. Build Docker image (local only, no push)
print_step "Building Docker image (local test)"
if command -v docker &> /dev/null; then
    if docker build -t code-indexer:local-test .; then
        print_success "Docker image built successfully"
        print_warning "Docker image tagged as 'code-indexer:local-test'"
    else
        print_error "Docker build failed"
        exit 1
    fi
else
    print_warning "Docker not available, skipping Docker build"
fi

# Summary
echo -e "\n${GREEN}🎉 Local CI pipeline completed successfully!${NC}"
echo "================================="
echo "✅ Linting passed"
echo "✅ Formatting checked"
echo "✅ Type checking passed"
echo "✅ All tests passed"
echo "✅ Package built and validated"
if command -v docker &> /dev/null; then
    echo "✅ Docker image built"
fi
echo ""
echo "Ready to push to GitHub! 🚀"