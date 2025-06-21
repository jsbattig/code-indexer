# Test Performance Optimization Guide

## Problem Statement

Non-unit tests (E2E and integration tests) are taking way too long because they shutdown and startup Docker containers on every test execution. This document provides the solution for **50-70% faster test execution** without sacrificing test functionality.

## Root Cause Analysis

### Current Slow Pattern (60-120s per test):
```python
def tearDown(self):
    # This takes 30-60 seconds PER TEST!
    subprocess.run([
        "code-indexer", "clean", "--remove-data", "--force", "--validate"
    ], timeout=90)
```

**What's happening:**
1. **Container startup**: 30-60s (pulling images, network setup, health checks)
2. **Test execution**: 5-10s (the actual test logic)  
3. **Container shutdown**: 15-30s (cleanup, volume removal, validation)
4. **Repeat for every test**: Multiply by number of tests!

### New Fast Pattern (5-10s per test):
```python
# Session-scoped: Start containers ONCE per test session
@pytest.fixture(scope="session")
def shared_containers():
    start_containers_once()  # 30-60s total for ALL tests
    yield
    stop_containers_once()   # 15s total for ALL tests

# Per-test: Only clean data, keep containers running  
def test_something(shared_containers, clean_test_data):
    # Test runs in 5-10s, containers already running!
    pass  # clean_test_data fixture handles fast cleanup
```

## New CLI Command Structure

We've implemented a cleaner command structure with clear semantics:

### ✅ **New Commands (Use These)**

| Command | Duration | Use Case |
|---------|----------|----------|
| `stop` | 2-5s | Stop containers (keep for restart) |
| `clean-data` | 1-3s | Clear collections only (keep containers) |
| `uninstall` | 30-60s | Complete removal (rarely needed) |

### ❌ **Old Commands (Avoid in Tests)**

| Command | Duration | Problem |
|---------|----------|---------|
| `clean --remove-data` | 30-60s | Too slow for tests |
| `clean --force --validate` | 45-90s | Way too slow for tests |

## Implementation Steps

### Step 1: Use Session-Scoped Containers

```python
# tests/your_test_file.py
from .shared_container_fixture import shared_containers, clean_test_data, fast_cli_command

@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests"
)  
class TestYourFeature:
    
    @pytest.fixture(autouse=True) 
    def setup(self, shared_containers, clean_test_data):
        # Containers already running, just setup test data
        self.setup_test_files()
        yield
        # clean_test_data handles cleanup automatically
        
    def test_something(self, shared_containers):
        # Containers are already running - test is FAST!
        result = fast_cli_command(["index"])
        assert result.returncode == 0
```

### Step 2: Replace Heavy Cleanup with Light Cleanup

**Before (SLOW):**
```python
def tearDown(self):
    subprocess.run([
        "code-indexer", "clean", "--remove-data", "--force", "--validate"  
    ], timeout=90)  # 30-90 seconds!
```

**After (FAST):**
```python  
def tearDown(self, shared_containers):
    fast_cli_command(["clean-data"])  # 1-3 seconds!
    # Containers keep running for next test
```

### Step 3: Update Test Verification

Instead of checking for complete cleanup, verify containers are reusable:

**Before:**
```python
# Verify complete cleanup worked
result = subprocess.run(["docker", "ps", "-a"])
assert "code-indexer" not in result.stdout
```

**After:**  
```python
# Verify containers are ready for reuse
result = fast_cli_command(["status"])
assert "✅ Ready" in result.stdout
```

## Migration Priority

### High Priority (Migrate First)
These tests run in full-automation.sh and are the slowest:

1. `test_end_to_end_complete.py` - Multiple 60s+ tests
2. `test_end_to_end_dual_engine.py` - Parametrized tests (2x slowdown)  
3. `test_integration_multiproject.py` - Multiple project setups
4. `test_branch_topology_e2e.py` - Complex topology tests
5. `test_voyage_ai_e2e.py` - VoyageAI-specific tests

### Medium Priority  
6. `test_schema_migration_e2e.py` - Migration tests
7. `test_reconcile_e2e.py` - Reconciliation tests
8. `test_start_stop_e2e.py` - Lifecycle tests

### Low Priority
- Unit tests (already fast)
- Simple integration tests

## Expected Performance Improvements

| Test Type | Before | After | Improvement |
|-----------|--------|-------|-------------|
| Single E2E test | 60-120s | 10-20s | 70-80% faster |
| Test suite (10 tests) | 10-20 min | 3-5 min | 70% faster |
| full-automation.sh full run | 45-60 min | 15-25 min | 60% faster |

## Verification Steps

### Test the New Commands:
```bash
# Test new fast commands
code-indexer start              # Start containers once
code-indexer clean-data         # Fast data cleanup (2s)
code-indexer clean-data         # Can run repeatedly (1s)
code-indexer stop               # Stop containers (3s)
code-indexer uninstall          # Full cleanup (60s, rarely needed)
```

### Run Optimized Tests:
```bash
# Test the new pattern
python -m pytest tests/test_optimized_example.py -v

# Compare timing with old vs new pattern
time python -m pytest tests/test_end_to_end_complete.py::TestEndToEndComplete::test_single_project_full_cycle -v
```

## Rules for New Tests

1. **Always use `shared_containers` fixture** for E2E tests
2. **Never use `clean --remove-data`** in test cleanup  
3. **Use `clean-data` for fast cleanup** between tests
4. **Only use `uninstall` for end-of-session cleanup**
5. **Verify containers are reusable**, don't verify complete removal

## Troubleshooting

### If containers get stuck:
```bash
code-indexer uninstall          # Nuclear option
code-indexer start              # Fresh start
```

### If tests still slow:
1. Check you're using `shared_containers` fixture
2. Check you're not calling `clean --remove-data` 
3. Check you're using `fast_cli_command()` helper
4. Profile with `time pytest -v test_file.py`

### If containers conflict:
- Use `clean-data --all-projects` to clear all data
- Each test should clean its own data in setup/teardown
- Containers are shared, data should be isolated

The goal is **test isolation without container isolation** - keep containers running, isolate data only.