# Story: Remove Container-Related Test Infrastructure

## Story ID
`STORY-TEST-CLEANUP-001`

## Parent Feature
`FEAT-TEST-CLEANUP-001`

## Title
Remove Container-Related Tests and Fixtures

## Status
PLANNED

## Priority
MEDIUM

## Story Points
5

## Assignee
TBD

## Story Summary

As a maintainer of code-indexer, I want to remove all test infrastructure for deprecated functionality so that the test suite is faster, simpler, and focused only on testing the production filesystem backend, reducing maintenance burden and CI/CD execution time.

## Acceptance Criteria

### Required Outcomes
1. **Container Test Removal**
   - [ ] Delete tests/integration/docker/ directory completely
   - [ ] Delete tests/e2e/infrastructure/test_container_manager_e2e.py
   - [ ] Remove any other container-related tests

2. **Qdrant Test Removal**
   - [ ] Delete all test_qdrant_*.py files
   - [ ] Remove Qdrant test fixtures from conftest.py
   - [ ] Clean up Qdrant mock objects

3. **Ollama Test Removal**
   - [ ] Delete all test_ollama*.py files
   - [ ] Remove Ollama test fixtures
   - [ ] Clean up Ollama mock configurations

4. **Fixture Cleanup**
   - [ ] Remove container-related fixtures from conftest.py
   - [ ] Remove Qdrant fixtures from conftest.py
   - [ ] Remove Ollama fixtures from conftest.py
   - [ ] Update shared fixtures to remove deprecated dependencies

5. **Configuration Updates**
   - [ ] Update pytest.ini to remove deprecated markers
   - [ ] Clean up test configuration files
   - [ ] Remove deprecated test settings

6. **Validation**
   - [ ] fast-automation.sh passes with reduced test count
   - [ ] Test execution time reduced by ~30%
   - [ ] No import errors in remaining tests
   - [ ] Coverage report shows no gaps in core functionality

## Technical Details

### Implementation Steps

1. **Test Discovery** (1 hour)
   ```bash
   # Find all container-related tests
   find tests/ -name "*container*.py" -o -name "*docker*.py" -o -name "*podman*.py"

   # Find all Qdrant tests
   find tests/ -name "*qdrant*.py"

   # Find all Ollama tests
   find tests/ -name "*ollama*.py"

   # Count total tests to remove
   find tests/ \( -name "*container*.py" -o -name "*docker*.py" \
                  -o -name "*qdrant*.py" -o -name "*ollama*.py" \) | wc -l
   ```

2. **Remove Test Directories** (30 min)
   ```bash
   # Remove entire test directories
   rm -rf tests/integration/docker/
   rm -rf tests/e2e/infrastructure/

   # Remove if they exist
   rm -rf tests/unit/infrastructure/
   rm -rf tests/integration/qdrant/
   rm -rf tests/integration/ollama/
   ```

3. **Remove Individual Test Files** (1 hour)
   ```bash
   # Remove Qdrant tests
   find tests/ -name "*qdrant*.py" -delete

   # Remove Ollama tests
   find tests/ -name "*ollama*.py" -delete

   # Remove container tests
   find tests/ -name "*container*.py" -delete
   find tests/ -name "*docker*.py" -delete
   ```

4. **Clean Fixtures** (2 hours)
   ```python
   # In tests/conftest.py, remove fixtures like:
   # - qdrant_backend_fixture
   # - ollama_client_fixture
   # - docker_manager_fixture
   # - container_manager_fixture
   # - mock_qdrant_client
   # - mock_ollama_provider

   # Keep only fixtures for:
   # - filesystem_backend
   # - voyageai_provider
   # - test data generation
   # - temporary directories
   ```

5. **Update Test Configuration** (30 min)
   ```ini
   # In pytest.ini, remove markers:
   # - @pytest.mark.container
   # - @pytest.mark.qdrant
   # - @pytest.mark.ollama
   # - @pytest.mark.docker

   # Update test paths if needed
   testpaths = tests/unit tests/integration tests/e2e
   ```

6. **Verify No Broken Imports** (1 hour)
   ```bash
   # Check for any remaining imports of removed modules
   grep -r "from.*docker_manager" tests/
   grep -r "from.*container_manager" tests/
   grep -r "from.*qdrant" tests/
   grep -r "from.*ollama" tests/

   # Fix any found imports
   ```

7. **Measure Performance** (30 min)
   ```bash
   # Before removal (record baseline)
   time ./fast-automation.sh
   # Note: test count and execution time

   # After removal
   time ./fast-automation.sh
   # Compare: should be ~30% faster

   # Generate coverage report
   pytest --cov=src --cov-report=html
   # Verify core functionality coverage maintained
   ```

### Files to Delete

**Directories:**
- tests/integration/docker/ (entire directory)
- tests/e2e/infrastructure/ (if only container tests)
- tests/integration/qdrant/ (if exists)
- tests/integration/ollama/ (if exists)

**Individual Files (patterns):**
- tests/**/test_*qdrant*.py
- tests/**/test_*ollama*.py
- tests/**/test_*container*.py
- tests/**/test_*docker*.py
- tests/**/test_*podman*.py

**Files to Modify:**
- tests/conftest.py (remove deprecated fixtures)
- tests/pytest.ini (remove deprecated markers)
- tests/unit/test_*.py (remove deprecated imports)

### Fixture Removal Examples

```python
# Remove from conftest.py:

# @pytest.fixture
# def qdrant_backend(tmp_path):
#     """Fixture for Qdrant backend."""
#     # DELETE THIS ENTIRE FIXTURE

# @pytest.fixture
# def mock_docker_manager():
#     """Mock Docker manager for testing."""
#     # DELETE THIS ENTIRE FIXTURE

# @pytest.fixture
# def ollama_provider():
#     """Ollama embedding provider fixture."""
#     # DELETE THIS ENTIRE FIXTURE
```

## Test Requirements

### Validation Tests
After removal, verify:
1. Core indexing tests still pass
2. Filesystem backend tests complete
3. VoyageAI provider tests work
4. CLI tests function correctly
5. Server tests run (if applicable)

### Performance Metrics
**Target Improvements:**
- Test count: Reduce by ~135 files
- Execution time: Reduce by ~30%
- Line count: Remove ~6,000 lines

### Manual Testing Checklist
1. [ ] Run `./fast-automation.sh` - passes
2. [ ] Check test count reduction (~135 fewer tests)
3. [ ] Measure execution time (should be ~30% faster)
4. [ ] Run `pytest --collect-only` - no import errors
5. [ ] Generate coverage report - core features covered
6. [ ] Run `./lint.sh` - no import issues
7. [ ] Check CI/CD pipeline - passes faster

## Dependencies

### Blocked By
- Ollama removal (Feature 3)
- Qdrant removal (Feature 1)
- Container removal (Feature 2)

### Blocks
- Documentation updates (need final test structure)

## Definition of Done

1. [ ] All container-related tests deleted
2. [ ] All Qdrant tests deleted
3. [ ] All Ollama tests deleted
4. [ ] Test fixtures cleaned up
5. [ ] pytest configuration updated
6. [ ] fast-automation.sh passes
7. [ ] Test execution ~30% faster
8. [ ] Coverage maintained for core features
9. [ ] No broken imports
10. [ ] Code reviewed and approved

## Notes

### Conversation Context
From conversation: "~150+ tests for deprecated functionality"
Goal is to reduce test burden and execution time.

### Key Benefits
- Faster development feedback loops
- Reduced CI/CD costs
- Simpler test maintenance
- Clearer test focus

### Implementation Tips
- Delete in batches and test frequently
- Use `pytest --collect-only` to find import errors
- Keep a backup of test list before deletion
- Document removed test coverage areas

## Time Tracking

### Estimates
- Analysis: 1 hour
- Implementation: 5 hours
- Validation: 2 hours
- Code Review: 30 minutes
- **Total**: 8.5 hours

### Actual
- Start Date: TBD
- End Date: TBD
- Actual Hours: TBD

## Revision History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2025-11-19 | 1.0 | System | Initial story creation |