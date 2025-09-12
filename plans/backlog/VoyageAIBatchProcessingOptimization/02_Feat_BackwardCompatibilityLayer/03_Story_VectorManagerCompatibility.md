# Story: Vector Manager Compatibility Layer

## 📖 User Story

As a system developer, I want the existing `submit_task()` method in VectorCalculationManager to work identically to before so that all current file processing code continues unchanged while internally benefiting from batch processing infrastructure.

## 🎯 Business Value  

After this story completion, all existing code that submits individual chunks for processing will work exactly as before, completing the compatibility layer that enables Feature 3's file-level batch optimization without breaking any current functionality.

## 📍 Implementation Target

**File**: `/src/code_indexer/services/vector_calculation_manager.py`  
**Lines**: ~160 (existing `submit_task()` method)

## ✅ Acceptance Criteria

### Scenario: submit_task() preserves identical behavior
```gherkin
Given the existing submit_task() method for single chunk processing
When I refactor it to use batch processing internally
Then it should wrap the single chunk in array for submit_batch_task()
And extract single result from batch response
And return the same VectorResult format as before
And maintain identical Future interface and callback patterns

Given a single chunk text and metadata for task submission
When submit_task() is called with individual chunk parameters
Then internally submit_batch_task() should be called with [chunk_text] array
And the returned Future should resolve to VectorResult with single embedding
And result.embedding should be List[float] format as before (not array of arrays)
And all metadata should be preserved through single-chunk processing
```

### Scenario: Future interface and behavior preservation
```gherkin
Given existing code using Future objects from submit_task()
When the task is processed through batch infrastructure
Then Future.result() should return identical VectorResult structure as before
And Future.done() should indicate completion identically to original
And Future.cancel() should work exactly as before for single tasks
And timeout behavior should be identical to original implementation

Given multiple single tasks submitted concurrently
When each task calls submit_task() with individual chunks
Then each should get separate Future objects as before
And each Future should resolve independently
And thread pool management should remain unchanged
And cancellation should work per-task exactly as before
```

### Scenario: Error handling and statistics preservation
```gherkin
Given submit_task() encountering processing errors
When underlying batch processing fails for single-chunk batch
Then same error types should be propagated to calling code
And VectorResult.error field should contain same error information as before
And error recovery behavior should be identical to original implementation
And statistics tracking should account for single-task submissions correctly

Given statistics tracking for single task submissions
When tasks are submitted and processed as single-item batches
Then total_tasks_submitted should increment by 1 per submit_task() call
And total_tasks_completed should increment by 1 per completed task
And embeddings_per_second should reflect single embeddings generated
And queue_size should track individual task submissions accurately
```

### Scenario: Thread pool integration unchanged
```gherkin
Given the existing ThreadPoolExecutor integration
When single tasks are processed as single-item batches
Then thread pool worker utilization should remain the same
And task queuing behavior should be identical to before
And thread count limits should be respected exactly as before
And shutdown behavior should work identically for single tasks

Given cancellation requests during single task processing
When cancellation_event is triggered during single-item batch processing
Then single tasks should be cancelled exactly as before
And partial results should not be returned on cancellation
And cancellation status should be reflected in VectorResult.error field
And cancellation should not affect other concurrent tasks
```

## 🔧 Technical Implementation Details

### Wrapper Implementation Pattern
```pseudocode
def submit_task(
    self,
    chunk_text: str, 
    metadata: Dict[str, Any]
) -> Future[VectorResult]:
    """Submit single chunk task (now using batch processing internally)."""
    # Convert single chunk to array
    chunk_texts = [chunk_text]
    
    # Use batch processing for single item
    batch_future = self.submit_batch_task(chunk_texts, metadata)
    
    # Create wrapper future that extracts single result
    single_future = Future()
    
    def extract_single_result():
        try:
            batch_result = batch_future.result()
            # Extract single embedding from batch result
            single_result = VectorResult(
                task_id=batch_result.task_id,
                embedding=batch_result.embeddings[0],  # First (only) embedding
                metadata=batch_result.metadata,
                processing_time=batch_result.processing_time,
                error=batch_result.error
            )
            single_future.set_result(single_result)
        except Exception as e:
            single_future.set_exception(e)
    
    # Process extraction in background
    threading.Thread(target=extract_single_result, daemon=True).start()
    
    return single_future
```

### Result Mapping Logic
- **Embedding Extraction**: `batch_result.embeddings[0]` → `single_result.embedding`
- **Metadata Preservation**: All metadata fields passed through unchanged
- **Error Handling**: Same error types and messages as original
- **Statistics Mapping**: Single task counts as one task, one embedding

### Compatibility Requirements
- **Method Signature**: Exact same parameters and return type
- **Future Behavior**: Identical Future interface and timing
- **Result Structure**: Same VectorResult fields and types
- **Error Propagation**: Same exception types and messages

## 🧪 Testing Requirements

### Regression Testing
- [ ] All existing unit tests for submit_task() pass unchanged
- [ ] Future interface behavior identical to original
- [ ] Error scenarios produce same error types and messages
- [ ] Thread pool integration works exactly as before

### Compatibility Validation  
- [ ] Method signature remains identical
- [ ] VectorResult structure unchanged (single embedding, not array)
- [ ] Statistics tracking accuracy for single task submissions
- [ ] Cancellation behavior preserved exactly

### Integration Testing
- [ ] File processing code works unchanged
- [ ] Concurrent task submissions work identically
- [ ] Thread pool resource management unchanged
- [ ] Performance characteristics maintained or improved

## ⚠️ Implementation Considerations

### Single-Item Batch Processing
- **Array Wrapping**: Single chunk becomes `[chunk]` for batch processing
- **Result Extraction**: Extract first element from embeddings array
- **Error Translation**: Convert batch errors to single-task errors
- **Performance**: Minimal overhead from batch wrapper for single items

### Future Interface Preservation
- **Threading**: May need background thread to extract single result from batch
- **Timing**: Result availability timing should match original closely
- **Cancellation**: Single task cancellation should work identically
- **Exception Handling**: Same exception propagation patterns

### Statistics Accuracy
- **Task Counting**: Each submit_task() call counts as one task
- **Embedding Counting**: Each task generates one embedding
- **Queue Tracking**: Queue size reflects individual task submissions
- **Processing Time**: Single task processing time from batch processing time

## 📋 Definition of Done

- [ ] `submit_task()` method uses batch processing infrastructure internally  
- [ ] Method signature and Future return type remain identical to original
- [ ] VectorResult contains single embedding (List[float]) not array of arrays
- [ ] All error handling produces same error types and messages as before
- [ ] Statistics tracking correctly accounts for single-task submissions
- [ ] Thread pool integration and resource management unchanged
- [ ] All existing unit tests pass without modification
- [ ] Future interface behavior identical to original implementation
- [ ] Performance maintained or improved for single task submissions
- [ ] Code review completed and approved

---

**Story Status**: ⏳ Ready for Implementation  
**Estimated Effort**: 4-5 hours  
**Risk Level**: 🟡 Medium (Future interface complexity)  
**Dependencies**: Feature 1 completion, 01_Story_SingleEmbeddingWrapper  
**Blocks**: Feature 3 file-level batch optimization  
**Critical Path**: File processing compatibility for Feature 3 integration