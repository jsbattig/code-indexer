# Story: Batch Task Submission API

## 📖 User Story

As a system developer, I want to add a `submit_batch_task()` method to VectorCalculationManager so that external code can submit multiple chunks as a single batch task to the thread pool infrastructure.

## 🎯 Business Value

After this story completion, FileChunkingManager and other components will have a clean API to submit entire chunk arrays for batch processing, completing the infrastructure foundation needed for file-level batch optimization.

## 📍 Implementation Target

**File**: `/src/code_indexer/services/vector_calculation_manager.py`  
**Lines**: ~180 (new method after existing `submit_task()`)

## ✅ Acceptance Criteria

### Scenario: Batch task submission with multiple chunks
```gherkin
Given a VectorCalculationManager with batch processing capability
When I call submit_batch_task() with an array of chunk texts and metadata
Then a single batch VectorTask should be created containing all chunks
And the batch task should be submitted to the existing ThreadPoolExecutor
And a Future should be returned that will contain batch processing results
And the Future should resolve to VectorResult with embeddings for all chunks

Given chunk texts ["chunk1", "chunk2", "chunk3"] and metadata
When I submit them as a batch task
Then the created VectorTask should contain all three chunks in order
And the task_id should uniquely identify the batch operation
And the metadata should be associated with the entire batch
And the Future should eventually return embeddings for all three chunks
```

### Scenario: Batch task integration with thread pool
```gherkin
Given the existing ThreadPoolExecutor infrastructure
When batch tasks are submitted via submit_batch_task()
Then batch tasks should be processed by existing worker threads
And batch tasks should respect the existing thread count limits
And cancellation should work identically for batch tasks
And statistics should track batch tasks appropriately

Given a thread pool with 4 workers processing batch tasks
When multiple batch tasks are submitted concurrently
Then each worker thread can process one batch task at a time
And batch tasks should not interfere with each other
And thread pool shutdown should handle batch tasks correctly
And waiting for completion should work for batch tasks
```

### Scenario: Error handling for batch task submission
```gherkin
Given a VectorCalculationManager not yet started
When I attempt to submit a batch task before thread pool initialization
Then a RuntimeError should be raised indicating manager not started
And the error message should be clear about context manager requirement
And no task should be submitted to a non-existent thread pool

Given batch task submission with empty chunk array
When submit_batch_task() is called with empty chunk_texts list
Then a ValueError should be raised indicating invalid input
And no task should be submitted to the thread pool
And appropriate error message should explain the requirement for non-empty chunks

Given batch task submission during cancellation
When cancellation has been requested before task submission
Then the batch task should be immediately rejected or cancelled
And the Future should indicate cancellation status
And no processing resources should be consumed for cancelled tasks
```

### Scenario: Batch task metadata and tracking
```gherkin
Given batch task submission with complex metadata
When metadata includes file path, processing context, and chunk information
Then all metadata should be preserved through batch task processing
And metadata should be available in the resulting VectorResult
And task_id generation should provide unique identification for batch operations
And created_at timestamp should accurately reflect batch task creation time

Given statistics tracking for batch task operations
When batch tasks are submitted and processed
Then total_tasks_submitted should increment by 1 per batch (not per chunk)
And queue_size should reflect batch tasks awaiting processing
And active_threads should account for threads processing batch tasks
And task completion should be tracked as single batch completion
```

## 🔧 Technical Implementation Details

### Method Signature
```pseudocode
def submit_batch_task(
    self,
    chunk_texts: List[str], 
    metadata: Dict[str, Any]
) -> Future[VectorResult]:
    """
    Submit multiple chunks as single batch task for processing.
    
    Args:
        chunk_texts: Array of text chunks to process together
        metadata: Metadata to associate with entire batch
        
    Returns:
        Future that will contain VectorResult with embeddings array
        
    Raises:
        RuntimeError: If manager not started (context manager required)
        ValueError: If chunk_texts is empty or invalid
    """
```

### Implementation Steps
```pseudocode
1. Validate manager state (started, not cancelled)
2. Validate input parameters (non-empty chunk array)
3. Generate unique task_id for batch operation
4. Create VectorTask with chunk_texts array and metadata
5. Submit batch task to ThreadPoolExecutor
6. Update statistics (tasks_submitted += 1)  
7. Return Future for batch processing result
```

### Integration with Existing Infrastructure
- **Task Queue**: Same ThreadPoolExecutor and worker management
- **Statistics**: Update existing counters for batch task tracking
- **Cancellation**: Use existing cancellation_event for batch tasks
- **Error Handling**: Apply existing patterns to batch task validation

## 🧪 Testing Requirements

### Unit Tests
- [ ] Batch task submission with valid inputs
- [ ] Error handling for invalid inputs (empty arrays, no metadata)
- [ ] Manager state validation (not started, cancelled)
- [ ] Task ID uniqueness and metadata preservation
- [ ] Future resolution with correct VectorResult structure

### Integration Tests
- [ ] Batch task processing through complete workflow
- [ ] Thread pool integration and resource management
- [ ] Cancellation behavior with batch tasks
- [ ] Statistics tracking accuracy
- [ ] Performance characteristics vs individual submissions

### Edge Cases
- [ ] Very large batch submissions (approaching VoyageAI limits)
- [ ] Single chunk batch submission (edge case of array processing)
- [ ] Concurrent batch submissions from multiple threads
- [ ] Memory usage with large batch tasks

## 🔍 API Design Considerations

### Consistency with Existing API
- **Pattern Match**: Similar to existing `submit_task()` method signature
- **Return Type**: Same Future[VectorResult] pattern for consistency
- **Error Handling**: Same exception types and patterns
- **Parameter Validation**: Similar input validation approach

### Future Enhancement Hooks
- **Optional Parameters**: Room for batch-specific options (timeout, priority)
- **Callback Support**: Potential for batch progress callbacks
- **Configuration**: Batch size limits and validation
- **Monitoring**: Batch-specific metrics and logging

## 📋 Definition of Done

- [ ] `submit_batch_task()` method added to VectorCalculationManager
- [ ] Method creates batch VectorTask from chunk array and metadata
- [ ] Batch tasks integrate seamlessly with existing ThreadPoolExecutor
- [ ] Future returns VectorResult with embeddings array for all chunks
- [ ] Error handling covers invalid inputs and manager state issues
- [ ] Statistics tracking correctly accounts for batch task operations
- [ ] Unit tests cover normal operation and error scenarios
- [ ] Integration tests demonstrate end-to-end batch processing
- [ ] Code review completed and approved
- [ ] Documentation updated for new batch submission API

---

**Story Status**: ⏳ Ready for Implementation  
**Estimated Effort**: 3-4 hours  
**Risk Level**: 🟢 Low (Additive API extension)  
**Dependencies**: 01_Story_DataStructureModification, 02_Story_BatchProcessingMethod  
**Blocks**: Feature 2 and 3 stories  
**Next Story**: Feature 2 - Backward compatibility restoration