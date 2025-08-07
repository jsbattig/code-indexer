# Fix Deletion Problem Plan

## Executive Summary

The code indexer has critical gaps in file deletion handling that violate the branch-aware architecture and cause data loss. This plan addresses three main issues:

1. **Watch mode hard-deletes files across ALL branches** (data loss risk)
2. **Reconcile never detects files deleted from filesystem** (stale data accumulation)
3. **Standard indexing skips deletion detection** (incomplete database state)

## Current State Analysis

### Deletion Detection & Handling Matrix

| Scenario | Git-Aware | Non Git-Aware | Status | Impact |
|----------|-----------|---------------|---------|--------|
| **Watch mode deletion** | ❌ Hard delete ALL branches | ✅ Hard delete | **CRITICAL BUG** | Data loss |
| **Git branch switching** | ✅ Branch-aware hide | N/A | **WORKING** | Correct |
| **Reconcile deleted files** | ❌ Never detected | ❌ Never detected | **BROKEN** | Stale data |
| **Standard indexing** | ❌ Never detected | ❌ Never detected | **BROKEN** | Stale data |

### Architecture Problem

**Two-Strategy System:**
- **Git-aware projects**: Should use soft delete (`_hide_file_in_branch`) 
- **Non git-aware projects**: Should use hard delete (`delete_by_filter`)

**Current Implementation:**
- **Watch mode**: Always hard deletes (wrong for git-aware)
- **Other modes**: Never detect deletions (wrong for both)

## Test Coverage Analysis

### Existing Tests (Relevant)
- ✅ `test_branch_topology_e2e.py` - Branch cleanup functionality
- ✅ `test_git_aware_watch_handler.py` - Watch deletion events (unit)
- ✅ `test_git_aware_watch_e2e.py` - Watch deletion (e2e, limited)
- ✅ `test_reconcile_e2e.py` - Reconcile functionality (no deletion tests)

### Major Test Gaps
- ❌ No tests for `_hide_file_in_branch` functionality  
- ❌ No multi-branch deletion scenarios
- ❌ No reconcile with deleted files
- ❌ No watch mode Qdrant state verification
- ❌ No SmartIndexer deletion unit tests

## Implementation Plan

### Phase 1: Test-Driven Development Setup

#### 1.1 Create Failing Tests for Watch Mode Bug
**Priority: CRITICAL**

Create comprehensive tests that demonstrate the current bug:

```python
# tests/test_watch_mode_deletion_bug.py
def test_watch_mode_preserves_files_in_other_branches():
    """FAILING: Watch mode should not delete files from other branches"""
    # Create file in main branch
    # Switch to feature branch, delete file
    # Verify file still exists in main branch search results
    # Currently FAILS because watch mode hard-deletes across all branches

def test_watch_mode_uses_branch_aware_deletion():
    """FAILING: Watch mode should use _hide_file_in_branch"""
    # Monitor watch mode deletion calls
    # Verify _hide_file_in_branch is called instead of delete_by_filter
    # Currently FAILS because watch mode bypasses branch-aware deletion
```

#### 1.2 Create Failing Tests for Reconcile Bug
**Priority: HIGH**

```python
# tests/test_reconcile_deletion_bug.py
def test_reconcile_detects_deleted_files():
    """FAILING: Reconcile should detect files deleted from filesystem"""
    # Index files, delete from filesystem, run reconcile
    # Verify reconcile detects and handles deleted files
    # Currently FAILS because reconcile only processes existing files

def test_reconcile_handles_deleted_files_per_project_type():
    """FAILING: Reconcile should handle deletions based on project type"""
    # Test both git-aware and non git-aware projects
    # Verify correct deletion strategy used
    # Currently FAILS because reconcile doesn't detect deletions
```

#### 1.3 Create Comprehensive Deletion Tests
**Priority: HIGH**

```python
# tests/test_branch_aware_deletion.py
def test_hide_file_in_branch_functionality():
    """Test _hide_file_in_branch works correctly"""
    # These tests currently don't exist
    
def test_multi_branch_deletion_isolation():
    """Test file deletion in one branch doesn't affect others"""
    # Critical for branch-aware architecture
    
def test_deletion_strategy_selection():
    """Test correct deletion strategy based on project type"""
    # Ensures git-aware vs non git-aware handling
```

### Phase 2: Fix Critical Watch Mode Bug

#### 2.1 Modify GitAwareWatchHandler
**File: `src/code_indexer/services/git_aware_watch_handler.py`**

**Current problematic code:**
```python
# In process_pending_changes() method
if change_type == "deleted":
    # Currently calls SmartIndexer.process_files_incrementally()
    # which does hard delete via delete_by_filter()
```

**Fix approach:**
```python
# New logic needed:
if change_type == "deleted":
    if self.is_git_aware_project():
        # Use branch-aware soft delete
        current_branch = self.get_current_branch()
        self.smart_indexer.branch_aware_indexer._hide_file_in_branch(
            file_path, current_branch, collection_name
        )
    else:
        # Use hard delete for non git-aware projects
        self.smart_indexer.process_files_incrementally([file_path])
```

#### 2.2 Add Branch Context to Watch Handler
**Enhancements needed:**
- Add `get_current_branch()` method to watch handler
- Add `is_git_aware_project()` detection
- Add proper error handling for branch-aware operations

#### 2.3 Update SmartIndexer Integration
**File: `src/code_indexer/services/smart_indexer.py`**

Add new method for branch-aware deletion:
```python
def delete_file_branch_aware(self, file_path: str, branch: str, collection_name: str):
    """Delete file using branch-aware strategy"""
    if self.is_git_aware():
        self.branch_aware_indexer._hide_file_in_branch(file_path, branch, collection_name)
    else:
        # Use existing hard delete logic
        self.qdrant_client.delete_by_filter(
            {"must": [{"key": "path", "match": {"value": file_path}}]}
        )
```

### Phase 3: Fix Reconcile Deletion Detection

#### 3.1 Enhance Reconcile Logic
**File: `src/code_indexer/services/smart_indexer.py`**

**Current reconcile logic (lines 586-888):**
- Only processes files that exist on disk
- Never detects files that exist in database but deleted from filesystem

**Enhancement needed:**
```python
def _do_reconcile_with_database_and_deletions(self, ...):
    # Existing reconcile logic for modified/missing files
    existing_reconcile_result = self._do_reconcile_with_database(...)
    
    # NEW: Detect deleted files
    deleted_files = self._detect_deleted_files(collection_name)
    
    # Handle deletions based on project type
    for file_path in deleted_files:
        if self.is_git_aware():
            current_branch = self.git_topology_service.get_current_branch()
            self.branch_aware_indexer._hide_file_in_branch(
                file_path, current_branch, collection_name
            )
        else:
            self.qdrant_client.delete_by_filter(
                {"must": [{"key": "path", "match": {"value": file_path}}]}
            )
```

#### 3.2 Implement Deleted File Detection
```python
def _detect_deleted_files(self, collection_name: str) -> List[str]:
    """Find files that exist in database but not on filesystem"""
    # Query all indexed files from database
    all_indexed_files = self._get_all_indexed_files(collection_name)
    
    # Get all files that should be indexed from filesystem
    existing_files = set(self.file_finder.find_files())
    
    # Find files in database but not on filesystem
    deleted_files = []
    for db_file in all_indexed_files:
        if db_file not in existing_files:
            deleted_files.append(db_file)
    
    return deleted_files
```

### Phase 4: Add Deletion Detection to Standard Indexing

#### 4.1 Optional Deletion Detection
Add `--detect-deletions` flag to `cidx index` command:

```python
# In cli.py
@click.option("--detect-deletions", is_flag=True, help="Detect and handle deleted files")
def index(ctx, clear, reconcile, detect_deletions, ...):
    stats = smart_indexer.smart_index(
        detect_deletions=detect_deletions,
        ...
    )
```

#### 4.2 Integrate with SmartIndexer
Modify `smart_index()` method to optionally detect deletions:

```python
def smart_index(self, detect_deletions: bool = False, ...):
    # Existing indexing logic
    
    # NEW: Optional deletion detection
    if detect_deletions:
        deleted_files = self._detect_deleted_files(collection_name)
        self._handle_deleted_files(deleted_files, collection_name)
```

### Phase 5: Testing and Validation

#### 5.1 Run All Tests
```bash
# Run unit tests
pytest tests/test_*deletion*.py -v

# Run integration tests  
pytest tests/test_*_e2e.py -k deletion -v

# Run watch mode tests
pytest tests/test_git_aware_watch*.py -v

# Run reconcile tests
pytest tests/test_reconcile*.py -v
```

#### 5.2 Manual Validation Scenarios

**Scenario 1: Watch Mode Multi-Branch**
1. Create file in `main` branch, index it
2. Switch to `feature` branch, index it  
3. Delete file in `feature` branch while watching
4. Verify file still searchable in `main` branch
5. Verify file not searchable in `feature` branch

**Scenario 2: Reconcile with Deletions**
1. Index project completely
2. Delete files from filesystem
3. Run `cidx index --reconcile --detect-deletions`
4. Verify deleted files are handled correctly
5. Verify existing files remain untouched

**Scenario 3: Non Git-Aware Project**
1. Initialize non git-aware project
2. Index files
3. Delete files from filesystem
4. Run reconcile with deletion detection
5. Verify hard deletion removes files completely

### Phase 6: Performance and Optimization

#### 6.1 Optimize Deletion Detection
- Implement efficient database queries for deleted file detection
- Add caching for repeated deletion checks
- Optimize batch deletion operations

#### 6.2 Add Metrics and Logging
```python
# Add to deletion operations
logger.info(f"Deleted {len(deleted_files)} files using {deletion_strategy}")
stats.files_deleted = len(deleted_files)
stats.deletion_strategy = deletion_strategy
```

### Phase 7: Documentation and Cleanup

#### 7.1 Update README
- Document deletion behavior for git-aware vs non git-aware projects
- Add examples of deletion detection usage
- Document `--detect-deletions` flag

#### 7.2 Update Help Text
```bash
cidx index --help
# Should show:
#   --detect-deletions    Detect and handle files deleted from filesystem
```

#### 7.3 Add Migration Guide
For existing users who may have stale data:
```bash
# Clean up stale data
cidx index --reconcile --detect-deletions
```

## Implementation Timeline

### Week 1: Critical Bug Fix
- ✅ Create failing tests for watch mode bug
- ✅ Fix watch mode to use branch-aware deletion
- ✅ Validate fix with comprehensive tests

### Week 2: Reconcile Enhancement  
- ✅ Create failing tests for reconcile bug
- ✅ Implement deleted file detection
- ✅ Add deletion handling to reconcile logic

### Week 3: Standard Indexing & Testing
- ✅ Add optional deletion detection to standard indexing
- ✅ Complete comprehensive test suite
- ✅ Performance optimization

### Week 4: Documentation & Validation
- ✅ Update documentation
- ✅ Manual validation scenarios
- ✅ Migration guide for existing users

## Risk Mitigation

### Data Loss Prevention
- Always test deletion logic with backup data
- Implement deletion confirmation in CLI
- Add rollback mechanisms where possible

### Backward Compatibility
- Make deletion detection optional by default
- Maintain existing behavior unless explicitly requested
- Provide migration path for existing installations

### Performance Considerations
- Limit deletion detection to reasonable batch sizes
- Implement timeout mechanisms for large projects
- Add progress reporting for deletion operations

## Success Criteria

1. **Watch mode preserves branch isolation** - Files deleted in one branch remain visible in others
2. **Reconcile detects deleted files** - Stale database entries are cleaned up
3. **Correct deletion strategy per project type** - Git-aware uses soft delete, non git-aware uses hard delete
4. **Zero data loss** - No unintended file removal across branches
5. **Performance maintained** - Deletion detection doesn't significantly impact indexing speed
6. **Comprehensive test coverage** - All deletion scenarios covered by automated tests

## Monitoring and Maintenance

### Metrics to Track
- Number of files deleted per operation
- Deletion strategy used (soft vs hard)
- Performance impact of deletion detection
- Error rates in deletion operations

### Ongoing Maintenance
- Regular testing of multi-branch deletion scenarios
- Performance monitoring of deletion operations
- User feedback on deletion behavior
- Continuous improvement of deletion detection accuracy

This plan ensures that the code indexer's deletion handling is architecturally sound, preserves data integrity, and provides users with predictable behavior across all project types.