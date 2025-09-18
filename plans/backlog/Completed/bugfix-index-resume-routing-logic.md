# Bug Fix: Index Resume Routing Logic

## Bug Summary
**Issue**: When a user cancels an index operation (Ctrl+C) and runs `cidx index` again (without `--reconcile`), the system restarts indexing from scratch instead of resuming from where it left off.

**Root Cause**: Logic flow bug in `_do_incremental_index()` that ignores interrupted operations and only checks for timestamp-based resume, which fails for interrupted operations.

**Severity**: High - Impacts user productivity and wastes computational resources

## Problem Analysis

### **Current Broken Flow:**
```
cidx index (after interruption)
↓
smart_indexer.index() 
↓
_do_incremental_index()  ← 🚨 Wrong path for interrupted operations
↓ 
get_resume_timestamp() returns 0.0 (no timestamp for interrupted ops)
↓
"No previous index found, performing full index" ← 🚨 Restarts from scratch
```

### **Working Flow (with --reconcile):**
```
cidx index --reconcile (after interruption)  
↓
smart_indexer.index()
↓
_do_reconcile_with_database() ← ✅ Bypasses broken incremental logic
```

### **Missing Logic:**
The main `index()` method correctly checks for interrupted operations, but `_do_incremental_index()` does not:

**Working Check in `index()` method:**
```python
# Check for interrupted operations first - highest priority
if (not force_full and self.progressive_metadata.can_resume_interrupted_operation()):
    return self._do_resume_interrupted(...)  # ✅ Works correctly
```

**Missing Check in `_do_incremental_index()` method:**
```python
def _do_incremental_index(self, ...):
    # 🚨 MISSING: Check for interrupted operations
    resume_timestamp = self.progressive_metadata.get_resume_timestamp(...)
    if resume_timestamp == 0.0:  # Always 0.0 for interrupted ops
        return self._do_full_index(...)  # 🚨 Restarts from scratch
```

## Technical Fix Specification

### **File to Modify:**
`src/code_indexer/services/smart_indexer.py`

### **Method to Fix:**
`_do_incremental_index()` at approximately line 669

### **Exact Fix Implementation:**

#### **Current Code (Broken):**
```python
def _do_incremental_index(
    self,
    batch_size: int,
    progress_callback: Optional[Callable],
    git_status: Dict[str, Any],
    provider_name: str,
    model_name: str,
    safety_buffer_seconds: int,
    quiet: bool = False,
    vector_thread_count: Optional[int] = None,
) -> ProcessingStats:
    """Perform incremental indexing."""
    # Get resume timestamp with safety buffer
    resume_timestamp = self.progressive_metadata.get_resume_timestamp(
        safety_buffer_seconds
    )
    if resume_timestamp == 0.0:
        # No previous index found, do full index
        if progress_callback:
            progress_callback(
                0,
                0,
                Path(""),
                info="No previous index found, performing full index",
            )
        return self._do_full_index(
            batch_size,
            progress_callback,
            git_status,
            provider_name,
            model_name,
            quiet,
        )
    # ... rest of method
```

#### **Fixed Code:**
```python
def _do_incremental_index(
    self,
    batch_size: int,
    progress_callback: Optional[Callable],
    git_status: Dict[str, Any],
    provider_name: str,
    model_name: str,
    safety_buffer_seconds: int,
    quiet: bool = False,
    vector_thread_count: Optional[int] = None,
) -> ProcessingStats:
    """Perform incremental indexing."""
    
    # 🔧 FIX: Check for interrupted operation first (before timestamp check)
    if self.progressive_metadata.can_resume_interrupted_operation():
        if progress_callback:
            # Get preview stats for feedback
            metadata_stats = self.progressive_metadata.get_stats()
            completed = metadata_stats.get("files_processed", 0)
            total = metadata_stats.get("total_files_to_index", 0)
            remaining = metadata_stats.get("remaining_files", 0)
            chunks_so_far = metadata_stats.get("chunks_indexed", 0)
            
            progress_callback(
                0,
                0,
                Path(""),
                info=f"🔄 Resuming interrupted operation: {completed}/{total} files completed ({chunks_so_far} chunks), {remaining} files remaining",
            )
        return self._do_resume_interrupted(
            batch_size,
            progress_callback,
            git_status,
            provider_name,
            model_name,
            quiet,
            vector_thread_count,
        )
    
    # Get resume timestamp with safety buffer (for completed operations)
    resume_timestamp = self.progressive_metadata.get_resume_timestamp(
        safety_buffer_seconds
    )
    if resume_timestamp == 0.0:
        # No previous index found, do full index
        if progress_callback:
            progress_callback(
                0,
                0,
                Path(""),
                info="No previous index found, performing full index",
            )
        return self._do_full_index(
            batch_size,
            progress_callback,
            git_status,
            provider_name,
            model_name,
            quiet,
        )
    # ... rest of method unchanged
```

### **Method Dependencies:**
The fix uses existing methods that are already working correctly:
- `progressive_metadata.can_resume_interrupted_operation()` ✅ Working
- `_do_resume_interrupted()` ✅ Working  
- `progressive_metadata.get_stats()` ✅ Working

## Expected Behavior After Fix

### **Scenario 1: User Cancels and Resumes**
```
1. User runs: cidx index
2. Progress: [████████░░] 80% complete (800/1000 files)
3. User hits Ctrl+C  
4. Status: "in_progress", files_processed=800, current_file_index=800
5. User runs: cidx index  
6. Expected: "🔄 Resuming interrupted operation: 800/1000 files completed (15,234 chunks), 200 files remaining"
7. Continues from file #801
```

### **Scenario 2: Completed Operation (No Change)**
```
1. Previous operation completed successfully
2. User runs: cidx index
3. Expected: Uses timestamp-based incremental indexing (existing behavior)
```

### **Scenario 3: No Previous Operation (No Change)**  
```
1. Fresh project, no metadata
2. User runs: cidx index
3. Expected: "No previous index found, performing full index" (existing behavior)
```

## Testing Strategy

### **Test Cases to Verify:**

#### **Test 1: Interrupted Operation Resume**
1. Start indexing operation with large file set
2. Interrupt after 50% completion (simulate Ctrl+C by manipulating metadata)
3. Run `cidx index` again
4. **Expected**: Should resume from interruption point, not restart

#### **Test 2: Completed Operation (Regression Test)**
1. Complete full indexing operation
2. Run `cidx index` again  
3. **Expected**: Should use timestamp-based incremental indexing

#### **Test 3: Fresh Project (Regression Test)**
1. New project with no metadata
2. Run `cidx index`
3. **Expected**: Should perform full index from scratch

#### **Test 4: Different Resume Flags**
1. Interrupt indexing operation
2. Test both `cidx index` and `cidx index --reconcile`
3. **Expected**: Both should resume correctly (not just --reconcile)

### **Validation Script:**
```python
def test_interrupt_resume_fix():
    # Simulate interrupted state
    metadata.start_indexing("voyage-ai", "voyage-code-3", git_status)
    metadata.set_files_to_index([Path("file1.py"), Path("file2.py"), Path("file3.py")])
    metadata.mark_file_completed("file1.py", chunks_count=10)
    # Leave status as "in_progress" (interrupted)
    
    # Create new indexer instance (fresh process)
    indexer = SmartIndexer(...)
    
    # This should resume, not restart
    result = indexer.index(force_full=False, reconcile_with_database=False)
    
    # Verify it resumed correctly
    assert "Resuming interrupted operation" in captured_output
    assert not "performing full index" in captured_output
```

## Risk Assessment

### **Risk Level: Low**
- **Isolated change**: Only affects routing logic within one method
- **Uses existing code**: No new functionality, just better routing
- **Backward compatible**: Doesn't change API or external behavior
- **Well-tested code paths**: Uses `_do_resume_interrupted()` which already works

### **Rollback Plan:**
If issues arise, simply revert the added interrupted operation check and restore original logic.

## Implementation Notes

### **Why This Fix is Minimal and Safe:**
1. **No API changes**: External interface remains identical
2. **Uses proven code**: `_do_resume_interrupted()` already works correctly in main flow
3. **Simple routing fix**: Just adds missing check that exists elsewhere
4. **Preserves all existing behavior**: Timestamp-based resume still works for completed operations

### **Alternative Solutions Considered:**

#### **Option A: Fix `get_resume_timestamp()` Logic**
- **Rejected**: More complex, affects other code paths
- **Risk**: Could break timestamp-based incremental indexing

#### **Option B: Always Route Through Main Index Flow**
- **Rejected**: Major refactoring required
- **Risk**: Could introduce other routing issues  

#### **Option C: Add Flag to Force Resume Mode**
- **Rejected**: Adds complexity to user interface
- **User Impact**: Requires users to remember special flags

### **Chosen Solution: Add Interrupted Check (Minimal Risk)**
- ✅ **Simple**: Single check added to existing method
- ✅ **Safe**: Uses proven working code paths
- ✅ **No user impact**: Transparent fix
- ✅ **Consistent**: Makes `_do_incremental_index()` match main flow logic

## Definition of Done

### **Code Changes:**
- [ ] Add interrupted operation check to `_do_incremental_index()` method
- [ ] Update progress message to show resumption status  
- [ ] Ensure proper routing to `_do_resume_interrupted()`

### **Testing:**
- [ ] Write test for interrupted operation resume via `cidx index`
- [ ] Verify existing timestamp-based incremental indexing still works
- [ ] Verify fresh project full indexing still works
- [ ] Run full test suite to ensure no regressions

### **Validation:**
- [ ] Manual testing: Cancel and resume operations
- [ ] Verify both `cidx index` and `cidx index --reconcile` work  
- [ ] Confirm user sees proper "Resuming interrupted operation" message
- [ ] Ensure operation continues from correct file position

This fix addresses the core routing logic bug that sends interrupted operations down the wrong code path, ensuring users can resume interrupted indexing operations regardless of which flags they use.