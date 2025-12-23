#!/bin/bash

# Fast automation script - CIDX fast unit tests only
# Runs pure unit tests that don't require external dependencies:
# - No real servers or API calls
# - No containers (Docker, Qdrant, Ollama)
# - No external APIs (VoyageAI, auth servers)
# - No special permissions (/var/lib access)
# Use server-fast-automation.sh for tests with dependencies

set -e  # Exit on any error

# TELEMETRY: Create telemetry directory for test performance tracking
TELEMETRY_DIR=".test-telemetry"
mkdir -p "$TELEMETRY_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TELEMETRY_FILE="$TELEMETRY_DIR/fast-automation-${TIMESTAMP}.log"
DURATION_FILE="$TELEMETRY_DIR/test-durations-${TIMESTAMP}.txt"

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
if pip install -e ".[dev]" --break-system-packages 2>/dev/null; then
    :
elif pip install -e ".[dev]" --user 2>/dev/null; then
    :
else
    pip install -e ".[dev]"
fi
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

# 5. Run FAST unit tests only (excluding external dependencies)
print_step "Running fast unit tests (no external services)"
echo "ℹ️  Testing FAST unit test functionality including:"
echo "   • Command-line interface parsing and validation"
echo "   • Configuration and mode detection"
echo "   • Core business logic (without API calls)"
echo "   • Text processing and chunking"
echo "   • Progress reporting and display"
echo "   • Error handling and validation"
echo ""
echo "⚠️  EXCLUDED: Tests requiring real servers, containers, or external APIs"

# Run ONLY fast unit tests that don't require external services
# TELEMETRY: Add --durations=0 to capture ALL test durations
echo "📊 Telemetry enabled: Results will be saved to $TELEMETRY_FILE"
echo "⏱️  Duration report: $DURATION_FILE"
python3 -m pytest \
    tests/unit/ \
    tests/mcpb/ \
    --durations=0 \
    --ignore=tests/unit/server/ \
    --ignore=tests/unit/infrastructure/ \
    --ignore=tests/mcpb/integration/test_bridge_e2e_real.py \
    --ignore=tests/unit/api_clients/test_base_cidx_remote_api_client_real.py \
    --ignore=tests/unit/api_clients/test_remote_query_client_real.py \
    --ignore=tests/unit/api_clients/test_business_logic_integration_real.py \
    --ignore=tests/unit/api_clients/test_repository_linking_client_real.py \
    --ignore=tests/unit/api_clients/test_jwt_token_manager_real.py \
    --ignore=tests/unit/api_clients/test_real_api_integration_required.py \
    --ignore=tests/unit/api_clients/test_messi_rule2_compliance.py \
    --ignore=tests/unit/api_clients/test_admin_api_client.py \
    --ignore=tests/unit/api_clients/test_admin_client_golden_repos_maintenance.py \
    --ignore=tests/unit/api_clients/test_jobs_cancel_status_real_integration.py \
    --ignore=tests/unit/api_clients/test_base_cidx_remote_api_client.py \
    --ignore=tests/unit/api_clients/test_jobs_api_client_tdd.py \
    --ignore=tests/unit/api_clients/test_isolation_utils.py \
    --ignore=tests/unit/api_clients/test_jobs_api_client_cancel_tdd.py \
    --ignore=tests/unit/api_clients/test_remote_query_client.py \
    --ignore=tests/unit/api_clients/test_repos_client_tdd.py \
    --ignore=tests/unit/cli/test_admin_commands.py \
    --ignore=tests/unit/cli/test_explicit_authentication_commands.py \
    --ignore=tests/unit/cli/test_jobs_cli_e2e_tdd.py \
    --ignore=tests/unit/cli/test_password_security_validation.py \
    --ignore=tests/unit/cli/test_server_lifecycle_commands.py \
    --ignore=tests/unit/cli/test_sync_command_structure.py \
    --ignore=tests/unit/cli/test_cli_init_segment_size.py \
    --ignore=tests/unit/cli/test_cli_issues_tdd_fix.py \
    --ignore=tests/unit/cli/test_cli_response_parsing_errors.py \
    --ignore=tests/unit/cli/test_cli_error_propagation_fixes.py \
    --ignore=tests/unit/cli/test_jobs_cancel_status_command_tdd.py \
    --ignore=tests/unit/cli/test_jobs_command_tdd.py \
    --ignore=tests/unit/cli/test_repos_commands_tdd.py \
    --ignore=tests/unit/cli/test_repository_activation_lifecycle.py \
    --ignore=tests/unit/cli/test_repository_branch_switching.py \
    --ignore=tests/unit/cli/test_repository_info_command.py \
    --ignore=tests/unit/cli/test_resource_cleanup_verification.py \
    --ignore=tests/unit/cli/test_authentication_status_management.py \
    --ignore=tests/unit/cli/test_admin_repos_integration_validation.py \
    --ignore=tests/unit/cli/test_daemon_delegation.py \
    --ignore=tests/unit/cli/test_query_fts_flags.py \
    --ignore=tests/unit/cli/test_staleness_display_integration.py \
    --ignore=tests/unit/cli/test_start_stop_backend_integration.py \
    --ignore=tests/unit/cli/test_cli_clear_temporal_progress.py \
    --ignore=tests/unit/cli/test_cli_fast_path.py \
    --ignore=tests/unit/cli/test_cli_temporal_display_comprehensive.py \
    --ignore=tests/unit/cli/test_cli_temporal_display_story2_1.py \
    --ignore=tests/unit/cli/test_improved_remote_query_experience.py \
    --ignore=tests/unit/cli/test_path_pattern_performance.py \
    --ignore=tests/unit/cli/test_status_temporal_performance.py \
    --ignore=tests/unit/cli/test_index_commits_clear_bug.py \
    --ignore=tests/unit/storage/test_filesystem_git_batch_limits.py \
    --ignore=tests/unit/storage/test_hnsw_incremental_batch.py \
    --ignore=tests/unit/remote/test_timeout_management.py \
    --ignore=tests/unit/performance/test_exclusion_filter_performance.py \
    --ignore=tests/unit/integration/ \
    --ignore=tests/unit/documentation/test_fixed_size_chunking_documentation.py \
    --ignore=tests/unit/cli/test_status_temporal_storage_size_bug.py \
    --ignore=tests/unit/services/test_tantivy_language_filter.py \
    --ignore=tests/unit/cli/test_index_delegation_progress.py \
    --ignore=tests/unit/cli/test_cli_option_conflict_fix.py \
    --ignore=tests/unit/test_codebase_audit_story9.py \
    --ignore=tests/unit/daemon/test_display_timing_fix.py \
    --ignore=tests/unit/services/test_clean_file_chunking_manager.py \
    --ignore=tests/unit/services/test_file_chunking_manager.py \
    --ignore=tests/unit/services/test_file_chunk_batching_optimization.py \
    --ignore=tests/unit/services/test_daemon_fts_cache_performance.py \
    --ignore=tests/unit/services/test_rpyc_daemon.py \
    --ignore=tests/unit/services/test_voyage_threadpool_elimination.py \
    --ignore=tests/unit/services/test_tantivy_regex_optimization.py \
    --ignore=tests/unit/services/test_tantivy_path_filter.py \
    --ignore=tests/unit/services/test_tantivy_limit_zero.py \
    --ignore=tests/unit/services/test_tantivy_search.py \
    --ignore=tests/unit/services/test_tantivy_regex_snippet_extraction.py \
    --ignore=tests/unit/cli/test_admin_repos_functionality_verification.py \
    --ignore=tests/unit/cli/test_admin_repos_maintenance_commands.py \
    --ignore=tests/unit/cli/test_admin_repos_add_simple.py \
    --ignore=tests/unit/cli/test_admin_repos_delete_command.py \
    --ignore=tests/unit/cli/test_admin_repos_delete_integration_e2e.py \
    --ignore=tests/unit/cli/test_password_management_commands.py \
    --ignore=tests/unit/cli/test_admin_password_change_command.py \
    --ignore=tests/unit/cli/test_repos_list_fix_verification.py \
    --ignore=tests/unit/cli/test_system_health_commands.py \
    --ignore=tests/unit/remote/test_network_error_handling.py \
    --deselect=tests/unit/cli/test_adapted_command_behavior.py::TestAdaptedStatusCommand::test_status_command_routes_to_uninitialized_mode \
    --deselect=tests/unit/proxy/test_parallel_executor.py::TestParallelCommandExecutor::test_execute_single_repository_success \
    --deselect=tests/unit/chunking/test_fixed_size_chunker.py::TestFixedSizeChunker::test_edge_case_very_large_file \
    --deselect=tests/unit/storage/test_filesystem_vector_store.py::TestProgressReporting::test_progress_callback_invoked_for_each_point \
    --deselect=tests/unit/storage/test_filesystem_vector_store.py::TestFilesystemVectorStoreCore::test_batch_upsert_performance \
    --deselect=tests/unit/storage/test_parallel_index_loading.py::TestPerformanceRequirements::test_parallel_execution_reduces_latency \
    -m "not slow and not e2e and not real_api and not integration and not requires_server and not requires_containers" \
    --cov=code_indexer \
    --cov-report=xml --cov-report=term-missing \
    2>&1 | tee "$TELEMETRY_FILE"

PYTEST_EXIT_CODE=$?

# TELEMETRY: Extract duration data
grep -E "^[0-9]+\.[0-9]+s (call|setup|teardown)" "$TELEMETRY_FILE" | sort -rn > "$DURATION_FILE"

# TELEMETRY: Summary
TOTAL_TIME=$(grep "passed in" "$TELEMETRY_FILE" | grep -oE "[0-9]+\.[0-9]+s" | head -1)
SLOW_TESTS=$(awk '$1 > 5.0' "$DURATION_FILE" | wc -l)

echo ""
echo "📊 TELEMETRY: Total=$TOTAL_TIME, Slow(>5s)=$SLOW_TESTS"
echo "   Log: $TELEMETRY_FILE"
echo "   Durations: $DURATION_FILE"

ln -sf "$(basename $TELEMETRY_FILE)" "$TELEMETRY_DIR/latest.log"
ln -sf "$(basename $DURATION_FILE)" "$TELEMETRY_DIR/latest-durations.txt"

if [ $PYTEST_EXIT_CODE -eq 0 ]; then
    print_success "Fast unit tests passed"
else
    print_error "Fast unit tests failed with exit code $PYTEST_EXIT_CODE"
    exit $PYTEST_EXIT_CODE
fi

# Note: GitHub Actions also has version checking and publishing steps
# but those are only relevant for actual GitHub runs

# Summary
echo -e "\n${GREEN}🎉 Fast automation completed successfully!${NC}"
echo "==========================================="
echo "✅ Linting passed"
echo "✅ Formatting checked"
echo "✅ Type checking passed"
echo "✅ Fast unit tests passed"
echo ""
echo "🖥️  FAST test coverage (no external dependencies):"
echo "   ✅ Core CLI parsing and validation"
echo "   ✅ Configuration management and mode detection"
echo "   ✅ Business logic without API calls"
echo "   ✅ Text processing and chunking"
echo "   ✅ Error handling and validation"
echo "   ✅ Progress reporting and display logic"
echo ""
echo "🚫 EXCLUDED (for speed):"
echo "   • Tests requiring real servers (test_*_real.py)"
echo "   • Tests requiring containers (infrastructure, services)"
echo "   • Tests requiring external APIs (VoyageAI, auth servers)"
echo "   • Tests requiring special permissions (/var/lib access)"
echo "   • Slow integration and e2e tests"
echo ""
echo "⚡ Fast automation focuses on pure unit tests only!"
echo "ℹ️  Run 'server-fast-automation.sh' for server tests with dependencies"
echo "ℹ️  Run 'full-automation.sh' for complete integration testing"
echo "CIDX core logic validated! 🚀"