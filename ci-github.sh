#!/bin/bash

# GitHub CI script that emulates GitHub Actions workflow
# Runs the same checks as GitHub Actions but locally (without publishing)

set -e  # Exit on any error

# Source .env files if they exist (for local testing)
if [[ -f ".env.local" ]]; then
    source .env.local
fi
if [[ -f ".env" ]]; then
    source .env
fi

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
if PYTHONPATH="$(pwd)/src:$(pwd)/tests" pytest tests/ \
    -m "not e2e" \
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
    --ignore=tests/test_voyage_ai_e2e.py \
    --ignore=tests/test_cow_workflow_e2e.py \
    --ignore=tests/test_docker_compose_validation.py \
    --ignore=tests/test_idempotent_setup.py \
    --ignore=tests/test_idempotent_start.py \
    --ignore=tests/test_branch_topology_e2e.py \
    --ignore=tests/test_optimized_example.py \
    --ignore=tests/test_comprehensive_git_workflow.py \
    --ignore=tests/test_claude_plan_e2e.py \
    --ignore=tests/test_dry_run_claude_prompt.py \
    --ignore=tests/test_dry_run_integration.py \
    --ignore=tests/test_filter_e2e_failing.py \
    --ignore=tests/test_rag_first_claude_service_bug.py \
    --ignore=tests/test_claude_response_formatting_regression.py \
    --ignore=tests/test_real_claude_response_formatting.py \
    --ignore=tests/test_claude_result_formatting.py \
    --ignore=tests/test_git_aware_watch_e2e.py \
    --ignore=tests/test_indexing_consistency_e2e.py \
    --ignore=tests/test_timestamp_comparison_e2e.py \
    --ignore=tests/test_line_number_display_e2e.py \
    --ignore=tests/test_semantic_query_display_e2e.py \
    --ignore=tests/test_semantic_search_capabilities_e2e.py \
    --ignore=tests/test_semantic_chunking_ast_fallback_e2e.py \
    --ignore=tests/test_cancellation_high_throughput_processor.py \
    --ignore=tests/test_schema_migration_e2e.py \
    --ignore=tests/test_concurrent_indexing_prevention.py \
    --ignore=tests/test_resume_and_incremental_bugs.py \
    --ignore=tests/test_actual_file_chunking.py \
    --ignore=tests/test_reproduce_tiny_chunks.py \
    --ignore=tests/test_chunker_docstring_fix.py \
    --ignore=tests/test_prompt_formatting_issues.py \
    --ignore=tests/test_reconcile_deletion_integration.py.disabled \
    --ignore=tests/test_watch_mode_deletion_integration.py.disabled \
    --ignore=tests/test_parallel_voyage_performance.py \
    --ignore=tests/test_branch_transition_logic_fix.py \
    --ignore=tests/test_compare_search_methods.py \
    --ignore=tests/test_debug_branch_isolation.py \
    --ignore=tests/test_search_with_branch_topology_fix.py \
    --ignore=tests/test_cow_clone_e2e_full_automation.py \
    --ignore=tests/test_cow_migration_e2e_full_automation.py \
    --ignore=tests/test_cow_clone_e2e.py \
    --ignore=tests/test_docker_uninstall_complete_cleanup_e2e.py \
    --ignore=tests/test_cli_progress_e2e.py \
    --ignore=tests/test_deletion_handling_e2e.py \
    --ignore=tests/test_git_indexing_consistency_e2e.py \
    --ignore=tests/test_kotlin_semantic_search_e2e.py \
    --ignore=tests/test_reconcile_branch_visibility_bug_e2e.py \
    --ignore=tests/test_reconcile_branch_visibility_e2e.py \
    --ignore=tests/test_reconcile_comprehensive_e2e.py \
    --ignore=tests/test_watch_timestamp_update_e2e.py \
    --ignore=tests/test_working_directory_reconcile_e2e.py \
    --ignore=tests/test_git_pull_incremental_e2e.py \
    --ignore=tests/test_override_cli_integration.py \
    --ignore=tests/test_setup_global_registry_e2e.py \
    --ignore=tests/test_cli_init_segment_size.py \
    --ignore=tests/test_payload_indexes_complete_validation_e2e.py \
    --ignore=tests/test_payload_indexes_comprehensive_e2e.py \
    --ignore=tests/test_payload_index_performance_validation.py \
    --ignore=tests/test_qdrant_config_payload_indexes.py \
    --ignore=tests/test_qdrant_payload_indexes.py \
    --ignore=tests/test_qdrant_segment_size.py \
    --ignore=tests/test_qdrant_service_config_integration.py \
    --ignore=tests/test_filter_e2e_success.py \
    --ignore=tests/test_cow_removal_tdd.py \
    --ignore=tests/test_post_cow_functionality.py \
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
echo "   • Claude CLI dependent tests (require Claude Code installation)"
echo "   • Claude formatting/response tests (require Claude API)"
echo "   • Dry-run Claude integration tests (require Claude CLI)"
echo "   • Reconcile E2E tests (require indexing services)"
echo "   • VoyageAI E2E tests (require Docker and API keys)"
echo "   • Docker Compose validation tests (require Docker)"
echo "   • Idempotent setup tests (require Docker services)"
echo "   • Idempotent start tests (require Docker services)"
echo "   • Branch topology E2E tests (require Git and indexing services)"
echo "   • CoW clone E2E tests (require CoW filesystem and real services)"
echo "   • Optimized example tests (require Docker and VoyageAI API)"
echo "   • Comprehensive git workflow tests (require full service stack)"
echo "   • Git-aware watch E2E tests (require service dependencies)"
echo "   • Indexing consistency/timestamp E2E tests (require services)"
echo "   • Line number display E2E tests (require indexing services)"
echo "   • Concurrent indexing and file chunking tests (require services)"
echo "   • CLI progress E2E tests (require real indexing operations)"
echo "   • Deletion handling E2E tests (require service dependencies)"
echo "   • Reconcile branch visibility E2E tests (require indexing services)"
echo "   • Reconcile comprehensive E2E tests (require full service stack)"
echo "   • Working directory reconcile E2E tests (require indexing services)"
echo "   • Git pull incremental E2E tests (require Git repository and indexing services)"
echo "   • Override CLI integration tests (require /var/lib/code-indexer access)"
echo "   • Setup global registry E2E tests (require sudo and /var/lib/code-indexer access)"
echo "   • CLI init segment size tests (require /var/lib/code-indexer access)"
echo "   • Kotlin semantic search E2E tests (require indexing services)"
echo "   • Watch timestamp update E2E tests (require file system monitoring)"
echo "   • Payload index validation and performance tests (require Qdrant services)"
echo "   • Qdrant service configuration tests (require running Qdrant instances)"
echo "   • Filter E2E success tests (require indexed content)"
echo "   • CoW (Copy-on-Write) removal and functionality tests (require services)"
echo "   • Any tests marked as 'slow', 'e2e', or 'real_api'"
echo ""
echo "ℹ️  This matches the GitHub Actions workflow for fast CI execution"
echo "ℹ️  Run 'full-automation.sh' for full local testing including E2E tests"
echo "Ready to push to GitHub! 🚀"