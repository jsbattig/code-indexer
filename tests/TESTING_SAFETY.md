# Testing Safety Guide

## Production Safety Measures

The organized test infrastructure in this repository is designed to avoid conflicts with production container setups while supporting both Docker and Podman engines. Here are the safety measures implemented:

## Test Categorization and Safety

### Automatic Test Categorization

Tests are automatically categorized by container requirements using the `TestCategorizer` system:

- **Shared-Safe Tests** (`@pytest.mark.shared_safe`) - Data-only operations that can use either container set
- **Docker-Only Tests** (`@pytest.mark.docker_only`) - Require Docker-specific features  
- **Podman-Only Tests** (`@pytest.mark.podman_only`) - Require Podman-specific features or rootless containers
- **Destructive Tests** (`@pytest.mark.destructive`) - Manipulate containers directly, require isolation

### Container Isolation Patterns

Tests follow specific patterns based on their category:

#### Shared-Safe Test Pattern
```python
@pytest.mark.shared_safe
@pytest.mark.e2e
def test_semantic_search_workflow(self):
    """Tests that only perform data operations."""
    # Uses existing containers, no lifecycle management
    # Safe to run in parallel with other shared-safe tests
```

#### Destructive Test Pattern  
```python
@pytest.mark.destructive
@pytest.mark.integration
def test_container_lifecycle(self):
    """Tests that manipulate containers directly."""
    # Requires container isolation
    # Cannot run in parallel with other container tests
```

### 1. Test-Specific Container Names

**Test containers**: Legacy references only, container usage has been removed

### 2. Test-Specific Networks

**Test networks**: Legacy references only, container usage has been removed

### 3. Environment Variable Protection

Tests use environment variables for test mode activation.

## How to Run Tests Safely

### Running Tests by Category
```bash
# Run only shared-safe tests (can run in parallel)
pytest -m shared_safe -v

# Run only Docker-specific tests  
pytest -m docker_only -v

# Run only non-destructive tests
pytest -m "not destructive" -v

# Run organized test directories
pytest tests/unit/ -v                    # Fast unit tests
pytest tests/integration/ -v             # Integration tests  
pytest tests/e2e/ -v                     # End-to-end tests
```

### Running Individual Tests
```bash
# Run specific test files with automatic categorization
python -m pytest tests/e2e/git_workflows/test_git_pull_incremental_e2e.py -v
python -m pytest tests/integration/docker/test_container_manager_integration.py -v
```

### Manual Cleanup (if needed)
```bash
# Clean test data directories
rm -rf /tmp/code-indexer-test-*
rm -rf ~/.code-indexer-test-*
```

## Verification Commands

### Check for Test Data
```bash
# Check for test directories
ls -la /tmp/ | grep code-indexer-test
ls -la ~/.code-indexer-test-* 2>/dev/null
```

## Production Safety Checklist

✅ Tests use isolated data directories
✅ Tests only run in explicit test mode
✅ Automatic cleanup removes all test resources
✅ No interference with production data directories

## Emergency Procedures

If you suspect test data is interfering with production:

1. **Remove all test directories immediately**:
   ```bash
   rm -rf /tmp/code-indexer-test-*
   rm -rf ~/.code-indexer-test-*
   ```

2. **Verify production data is intact**:
   ```bash
   ls -la ~/.code-indexer/
   ```

## Contact

If you encounter any production conflicts or safety concerns, please file an issue with:
- Test data listing: `ls -la /tmp/code-indexer-test-* && ls -la ~/.code-indexer-test-*`
- Production data status: `ls -la ~/.code-indexer/`