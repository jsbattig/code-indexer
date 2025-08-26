# Clean Index Cancellation Fix Plan

## Problem Summary

**Issue**: Indexing operations take too long to respond to cancellation (Ctrl-C), sometimes continuing to process for minutes after interruption.

**Root Cause**: The `as_completed()` loop in `HighThroughputProcessor` processes ALL queued futures regardless of cancellation requests, with cancellation checks only occurring during progress callback intervals.

## Critical Database Consistency Issue Discovered

During investigation, a **critical database consistency problem** was identified:

### Current Batch Processing Risk

**Problem**: When cancellation occurs mid-processing, some files may have **partial chunks** indexed in the database while other chunks from the same file are never processed, creating inconsistent database state.

**Scenario**: 
1. File `large_file.py` gets chunked into 10 chunks
2. Chunks 1-5 are processed and stored in Qdrant
3. User cancels operation  
4. Chunks 6-10 are never processed
5. **Database now contains incomplete representation of the file**

**Impact**: 
- Incomplete search results for partially indexed files
- Inconsistent file-level metadata (file marked as "processed" but missing chunks)
- Progressive metadata corruption (file counts don't match actual indexed chunks)

## Comprehensive Solution Plan

### Phase 1: Immediate Cancellation Response

#### 1.1 Add Event-Based Cancellation to VectorCalculationManager
**File**: `src/code_indexer/services/vector_calculation_manager.py`

**Changes**:
- Add `threading.Event` for cancellation signaling
- Modify worker threads to check cancellation flag periodically
- Add `request_cancellation()` method
- Update `submit_chunk()` to respect cancellation state

**Implementation**:
```python
class VectorCalculationManager:
    def __init__(self, ...):
        self.cancellation_event = threading.Event()
        
    def request_cancellation(self):
        self.cancellation_event.set()
        
    def _calculate_embedding_worker(self, task: VectorTask) -> VectorResult:
        # Check cancellation before processing
        if self.cancellation_event.is_set():
            return VectorResult(task_id=task.task_id, error="Cancelled")
```

#### 1.2 Add Immediate Cancellation Flag to HighThroughputProcessor  
**File**: `src/code_indexer/services/high_throughput_processor.py`

**Changes**:
- Add `self.cancelled = False` flag
- Add `request_cancellation()` method  
- Check cancellation flag in EVERY `as_completed()` iteration
- Break out of processing immediately on cancellation

**Implementation**:
```python
class HighThroughputProcessor:
    def __init__(self, ...):
        self.cancelled = False
        
    def request_cancellation(self):
        self.cancelled = True
        
    def process_files_high_throughput(self, ...):
        # In as_completed() loop:
        for future in as_completed(chunk_futures):
            if self.cancelled:  # Check EVERY iteration
                break
```

#### 1.3 Update Progress Callback for Immediate Response
**File**: `src/code_indexer/cli.py` (progress_callback function)

**Changes**:
- Set cancellation flag immediately when "INTERRUPT" is returned
- Pass cancellation signal to HighThroughputProcessor
- Remove dependency on periodic progress updates for cancellation

### Phase 2: Database Consistency Protection

#### 2.1 File-Level Transaction Management

**Strategy**: Ensure files are indexed atomically - either ALL chunks of a file are indexed, or NONE are.

**Implementation Approach**:
1. **Batch by File**: Group chunk futures by source file
2. **File-Level Validation**: Only commit chunks to Qdrant when ALL chunks for a file complete successfully
3. **Cancellation-Safe Commit**: On cancellation, commit only files that are 100% complete

**File**: `src/code_indexer/services/high_throughput_processor.py`

**Changes**:
```python
# Track chunks by file
file_chunks: Dict[Path, List[ChunkTask]] = {}
file_completion_status: Dict[Path, bool] = {}

# In as_completed() loop:
for future in as_completed(chunk_futures):
    if self.cancelled:
        break
        
    # Process result
    chunk_task = vector_result.metadata["chunk_task"]
    current_file = chunk_task.file_path
    
    # Track completion per file
    if current_file not in file_completion_status:
        file_completion_status[current_file] = True
        
    # Only add to batch if file is complete AND not cancelled
    if self._is_file_complete(current_file) and not self.cancelled:
        batch_points.extend(file_chunks[current_file])
```

#### 2.2 Progressive Metadata Cleanup on Cancellation

**File**: `src/code_indexer/services/progressive_metadata.py`

**Changes**:
- Add `handle_cancellation()` method
- Track in-progress files separately from completed files  
- On cancellation, remove incomplete files from `completed_files` list
- Update file counts to reflect only actually completed files

**Implementation**:
```python
def handle_cancellation(self, completed_files: List[Path]):
    """Update metadata after cancellation to reflect only completed files."""
    self.metadata["status"] = "cancelled" 
    self.metadata["completed_files"] = [str(f) for f in completed_files]
    self.metadata["files_processed"] = len(completed_files)
    # Remove incomplete files from processing queue
    self._save_metadata()
```

#### 2.3 Qdrant Batch Safety

**Analysis**: Current `upsert_points()` in `qdrant.py:489` is not transactional - if batch fails partway through, some points may be committed.

**Solution**: 
1. Use smaller batch sizes during cancellation-prone operations
2. Add batch validation before commit
3. Consider using Qdrant's atomic operations where available

### Phase 3: Enhanced Cancellation UX

#### 3.1 Immediate Feedback on Cancellation
**File**: `src/code_indexer/cli.py` (GracefulInterruptHandler)

**Changes**:
- Show "Cancelling..." message immediately
- Display progress on cleanup/rollback operations
- Show final summary of what was successfully indexed

#### 3.2 Cancellation Timeout Protection
**Implementation**: Add timeout mechanism - if cancellation cleanup takes too long, force exit.

```python
def _signal_handler(self, signum, frame):
    self.interrupted = True
    # Start cleanup timeout
    threading.Timer(30.0, self._force_exit).start()
    
def _force_exit(self):
    if self.interrupted:
        os._exit(1)  # Force exit if cleanup takes too long
```

### Phase 4: Testing & Validation

#### 4.1 Cancellation Response Time Test
**File**: `tests/test_fast_cancellation.py`

**Test**: Verify cancellation responds within 1-3 seconds regardless of queue size.

```python
def test_cancellation_response_time():
    # Submit large number of tasks
    # Cancel after 2 seconds
    # Verify response within 3 seconds total
    # Verify no orphaned chunks in database
```

#### 4.2 Database Consistency Test  
**File**: `tests/test_cancellation_consistency.py`

**Test**: Verify no partial files exist in database after cancellation.

```python
def test_no_orphaned_chunks_after_cancellation():
    # Index files with known chunk counts
    # Cancel mid-processing
    # Verify each file in DB has complete chunk set
    # Verify progressive metadata matches actual DB state
```

#### 4.3 Resumability Test
**File**: `tests/test_cancellation_resume.py`

**Test**: Verify clean resumption after cancellation.

```python
def test_resume_after_cancellation():
    # Cancel indexing operation
    # Restart indexing
    # Verify no duplicate processing
    # Verify completion is correct
```

## Implementation Priority

### Critical Path (Must Fix):
1. **Database Consistency** (Phase 2.1-2.2) - Prevents data corruption
2. **Immediate Cancellation** (Phase 1.1-1.3) - Core user experience

### Important (Should Fix):
3. **Enhanced UX** (Phase 3) - Better user feedback  
4. **Testing** (Phase 4) - Regression prevention

### Nice to Have:
- Cancellation metrics/analytics
- Advanced rollback strategies
- Partial resume capabilities

## Expected Results

**Before Fix**:
- Cancellation takes 30-120+ seconds
- Risk of partial file chunks in database
- Poor user experience

**After Fix**:
- Cancellation responds within 1-3 seconds  
- Database maintains file-level consistency
- Clean resumption after cancellation
- Better user feedback during cancellation

## Risk Assessment

**Low Risk**:
- Thread pool cancellation (well-tested pattern)
- Progress callback modifications (isolated)

**Medium Risk**:  
- File-level batching changes (affects core indexing logic)
- Progressive metadata changes (affects resumability)

**High Risk**:
- Database transaction modifications (could break existing functionality)

**Mitigation**: Comprehensive testing, feature flags for new behavior, rollback plan.

## Rollback Plan

If implementation causes issues:
1. Revert to original `as_completed()` loop
2. Keep simple cancellation flag but remove file-level batching
3. Add warning about potential partial indexing during cancellation
4. Document known limitation for future fix

## Testing Strategy

1. **Unit Tests**: Individual component cancellation behavior
2. **Integration Tests**: End-to-end cancellation scenarios  
3. **Performance Tests**: Verify no throughput regression
4. **Stress Tests**: Large queue cancellation scenarios
5. **Consistency Tests**: Database state validation

## Notes

- This plan addresses both the immediate UX issue (slow cancellation) and the underlying data integrity issue (partial file indexing)
- File-level atomicity is crucial for maintaining search quality
- The solution maintains backward compatibility with existing progressive metadata format
- Implementation should be feature-flagged to allow rollback if issues arise