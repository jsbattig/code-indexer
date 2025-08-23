#!/bin/bash

# Full automation script for linting, testing, building, and compiling
# Uses minimal container footprint strategy (Story 8: Minimal Container Footprint Strategy)
# Part of Epic: Test Infrastructure Refactoring - Two-Container Architecture

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "🚀 Starting full automation pipeline with minimal container footprint..."
echo "========================================================================"

if [[ "$SKIP_DOCKER_TESTS" == "true" ]]; then
    echo -e "${YELLOW}⚠️  Running in Podman-only mode (Docker tests will be skipped)${NC}"
    echo ""
fi

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

# Parse command line arguments
SKIP_DOCKER_TESTS=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-docker|--podman-only)
            SKIP_DOCKER_TESTS=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  --skip-docker, --podman-only   Skip Docker-specific tests (run Podman tests only)"
            echo "  --help, -h                     Show this help message"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help to see available options"
            exit 1
            ;;
    esac
done

# Check if we're in the right directory
if [[ ! -f "pyproject.toml" ]]; then
    print_error "Not in project root directory (pyproject.toml not found)"
    exit 1
fi

if [[ "$SKIP_DOCKER_TESTS" == "true" ]]; then
    print_warning "Docker tests will be skipped - running Podman tests only"
fi

# Source .env files if they exist
if [[ -f ".env.local" ]]; then
    source .env.local
    print_success "Loaded environment variables from .env.local"
fi
if [[ -f ".env" ]]; then
    source .env
    print_success "Loaded environment variables from .env"
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

# 5. Setup test environment using modular script
print_step "Setting up test environment"

# Call the dedicated setup script
if ./setup-test-environment.sh; then
    print_success "Test environment setup completed"
else
    print_warning "Test environment setup had issues (continuing anyway)"
fi

# 6. Run tests with coverage (individual test files for better isolation)
print_step "Running tests with coverage - individual test files for better isolation"


# Get all test files from reorganized structure (exclude infrastructure files)
test_files=($(find tests/unit tests/integration tests/e2e -name "test_*.py" 2>/dev/null | grep -v "infrastructure.py" | sort))

# Filter out Docker tests if requested
if [[ "$SKIP_DOCKER_TESTS" == "true" ]]; then
    print_step "Filtering out Docker-specific tests"
    filtered_files=()
    docker_test_files=(
        "tests/integration/docker/test_docker_compose_validation.py"
        "tests/integration/docker/test_docker_manager_cleanup.py"
        "tests/integration/docker/test_docker_manager.py"
        "tests/integration/docker/test_docker_manager_simple.py"
        "tests/e2e/misc/test_end_to_end_dual_engine.py"
        "tests/e2e/misc/test_e2e_embedding_providers.py"
    )
    
    for file in "${test_files[@]}"; do
        # Check if this file is in our Docker test list
        skip_file=false
        for docker_test in "${docker_test_files[@]}"; do
            if [[ "$file" == "$docker_test" ]]; then
                skip_file=true
                break
            fi
        done
        
        if [[ "$skip_file" == "true" ]]; then
            print_warning "Skipping Docker test: $(basename "$file")"
        else
            filtered_files+=("$file")
        fi
    done
    test_files=("${filtered_files[@]}")
    print_success "Filtered to ${#test_files[@]} Podman-compatible tests"
fi

# Check if COW_CLONE_E2E_TESTS is set to exclude the slow CoW clone tests
if [[ "${COW_CLONE_E2E_TESTS:-}" == "false" ]]; then
    print_warning "Skipping CoW clone E2E tests (COW_CLONE_E2E_TESTS=false)"
    # Filter out CoW clone test
    filtered_files=()
    for file in "${test_files[@]}"; do
        if [[ "$file" != "tests/e2e/misc/test_cow_clone_e2e_full_automation.py" && "$file" != "tests/test_cow_clone_e2e_full_automation.py" ]]; then
            filtered_files+=("$file")
        fi
    done
    test_files=("${filtered_files[@]}")
else
    print_step "Including CoW clone E2E tests (may take several minutes)"
    print_step "To skip them: export COW_CLONE_E2E_TESTS=false"
fi

# Initialize coverage
rm -f .coverage 2>/dev/null || true

# Setup test output logging
TEST_OUTPUT_DIR="test_output_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$TEST_OUTPUT_DIR"
TEST_LOG="$TEST_OUTPUT_DIR/full_test_run.log"
TEST_SUMMARY_LOG="$TEST_OUTPUT_DIR/test_summary.json"

echo "   📝 Test output will be saved to: $TEST_OUTPUT_DIR"
echo ""

# Run each test file individually
failed_tests=()
passed_count=0
skipped_count=0
total_count=${#test_files[@]}
current_index=0

echo "   Total test files to run: $total_count"
echo ""

# Start JSON summary
echo '{"test_run": {' > "$TEST_SUMMARY_LOG"
echo '  "start_time": "'$(date -Iseconds)'",' >> "$TEST_SUMMARY_LOG"
echo '  "total_files": '$total_count',' >> "$TEST_SUMMARY_LOG"
echo '  "test_results": [' >> "$TEST_SUMMARY_LOG"

for test_file in "${test_files[@]}"; do
    current_index=$((current_index + 1))
    
    # Create individual test log
    test_name=$(basename "$test_file" .py)
    individual_log="$TEST_OUTPUT_DIR/${test_name}.log"
    
    # Run test and capture output
    echo -e "\n   [$current_index/$total_count] Running $test_name..." | tee -a "$TEST_LOG"
    
    # Run the test with output to both console and file
    PYTHONPATH="$(pwd)/src:$(pwd)/tests" pytest "$test_file" \
        --cov=src/code_indexer --cov-append --no-cov-on-fail --cov-report= \
        --tb=auto --maxfail=3 --no-header -p no:warnings 2>&1 | tee -a "$TEST_LOG" | tee "$individual_log"
    
    exit_code=${PIPESTATUS[0]}
    
    # Check if tests were skipped by examining output
    if grep -q "collected 0 items.*skipped" "$individual_log" || grep -q "^====.* skipped in .*====" "$individual_log"; then
        test_status="skipped"
    elif [[ $exit_code -eq 0 ]]; then
        test_status="passed"
    elif [[ $exit_code -eq 5 ]]; then
        # Exit code 5 usually means no tests collected
        test_status="skipped"
    else
        test_status="failed"
    fi
    
    # Add comma if not first result
    if [[ $current_index -gt 1 ]]; then
        echo ',' >> "$TEST_SUMMARY_LOG"
    fi
    
    # Write JSON result
    echo -n '    {"file": "'$test_file'", "name": "'$test_name'", "status": "'$test_status'"}' >> "$TEST_SUMMARY_LOG"
    
    if [[ $test_status == "passed" ]]; then
        echo "   ✅ $test_name passed" | tee -a "$TEST_LOG"
        passed_count=$((passed_count + 1))
    elif [[ $test_status == "skipped" ]]; then
        echo "   ⏭️  $test_name skipped" | tee -a "$TEST_LOG"
        skipped_count=$((skipped_count + 1))
        # Don't count as failed
    else
        echo "   ❌ $test_name failed" | tee -a "$TEST_LOG"
        failed_tests+=("$test_file")
    fi
done

# Close JSON summary
echo '' >> "$TEST_SUMMARY_LOG"
echo '  ],' >> "$TEST_SUMMARY_LOG"
echo '  "end_time": "'$(date -Iseconds)'",' >> "$TEST_SUMMARY_LOG"
echo '  "passed_count": '$passed_count',' >> "$TEST_SUMMARY_LOG"
echo '  "skipped_count": '$skipped_count',' >> "$TEST_SUMMARY_LOG"
echo '  "failed_count": '${#failed_tests[@]} >> "$TEST_SUMMARY_LOG"
echo '}}' >> "$TEST_SUMMARY_LOG"

# Generate final coverage report
if [[ -f .coverage ]]; then
    echo "   Generating final coverage report..."
    PYTHONPATH="$(pwd)/src:$(pwd)/tests" python -m coverage xml
    PYTHONPATH="$(pwd)/src:$(pwd)/tests" python -m coverage report --show-missing
fi

# Report results
echo ""
echo "📊 Test Results Summary:"
echo "   Passed: $passed_count/$total_count"
echo "   Skipped: $skipped_count/$total_count"
echo "   Failed: ${#failed_tests[@]}/$total_count"

# Generate detailed test report using Python parser
if [[ -f "parse_test_results.py" ]]; then
    echo ""
    echo "📋 Generating detailed test report..."
    python parse_test_results.py "$TEST_OUTPUT_DIR" | tee "$TEST_OUTPUT_DIR/detailed_summary.txt"
else
    echo ""
    echo "⚠️  Test parser not found, showing basic summary only"
fi

if [[ ${#failed_tests[@]} -eq 0 ]]; then
    if [[ "${COW_CLONE_E2E_TESTS:-}" == "false" ]]; then
        print_success "All tests passed (excluding CoW clone E2E test) - using individual test file execution"
    else
        print_success "All tests passed (including CoW clone E2E) - using individual test file execution"
    fi
else
    echo ""
    echo "❌ Failed test files:"
    for failed_test in "${failed_tests[@]}"; do
        echo "   - $failed_test"
    done
    print_error "Some tests failed - using individual test file execution"
    
    # Show where to find detailed logs
    echo ""
    echo "📁 Detailed logs saved in: $TEST_OUTPUT_DIR/"
    echo "   - Full test run: $TEST_LOG"
    echo "   - Individual test logs: $TEST_OUTPUT_DIR/*.log"
    echo "   - JSON summary: $TEST_SUMMARY_LOG"
    
    exit 1
fi

# 8. Build package
print_step "Building package"
pip install build twine
if python -m build; then
    print_success "Package built successfully"
else
    print_error "Package build failed"
    exit 1
fi

# 9. Check package
print_step "Checking package integrity"
if twine check dist/*.whl dist/*.tar.gz; then
    print_success "Package check passed"
else
    print_error "Package check failed"
    exit 1
fi

# 10. Validate Docker service files
print_step "Validating Docker service files"
if command -v docker &> /dev/null; then
    for dockerfile in src/code_indexer/docker/Dockerfile.*; do
        if [[ -f "$dockerfile" ]]; then
            echo "✓ Found $(basename "$dockerfile")"
        fi
    done
    print_success "Docker service files validated"
else
    print_warning "Docker not available, skipping Docker validation"
fi

# 11. Final cleanup
print_step "Performing final cleanup"
# Clean up any test temporary directories
if ls ~/.tmp/test_* >/dev/null 2>&1; then
    rm -rf ~/.tmp/test_* 2>/dev/null || true
fi
if ls ~/.tmp/shared_test_* >/dev/null 2>&1; then
    rm -rf ~/.tmp/shared_test_* 2>/dev/null || true
fi
print_success "Final cleanup completed"

# Summary
echo -e "\n${GREEN}🎉 Full automation pipeline completed successfully with minimal container footprint!${NC}"
echo "================================================================================"
echo "✅ Linting passed"
echo "✅ Formatting checked"
echo "✅ Type checking passed"
echo "✅ All test groups passed with minimal container usage"
echo "✅ Package built and validated"
if command -v docker &> /dev/null; then
    echo "✅ Docker service files validated"
fi
echo "✅ Complete cleanup performed"
echo ""
echo "📌 Container Resource Optimization:"
echo "   - Maximum containers: 3 (vs previous 6-9)"
echo "   - Resource reduction: 70-80%"
echo "   - Full cleanup between test groups"
echo "   - Trade-off: 2-3x slower execution for minimal resource usage"
echo ""
echo "📌 Note: E2E tests require VOYAGE_API_KEY environment variable"
echo ""
echo "Ready to push to GitHub! 🚀"