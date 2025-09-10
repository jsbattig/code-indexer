# Story: Batch Processing Method Implementation

## 📖 User Story

As a system developer, I want to refactor the `_calculate_vector()` method to process multiple chunks via the existing `get_embeddings_batch()` API so that the core embedding generation uses efficient batch processing instead of individual chunk processing.

## 🎯 Business Value

After this story completion, the core vector calculation will use VoyageAI's batch processing API, reducing API calls from N (one per chunk) to 1 (one per batch), achieving the fundamental efficiency improvement that enables 10-20x throughput gains.

## 📍 Implementation Target

**File**: `/src/code_indexer/services/vector_calculation_manager.py`  
**Lines**: 201-283 (`_calculate_vector()` method)

## ✅ Acceptance Criteria

### Scenario: Batch processing replaces single chunk processing
```gherkin
Given the existing _calculate_vector method processing single chunks
When I refactor it to process multiple chunks from VectorTask.chunk_texts
Then the method should call embedding_provider.get_embeddings_batch(task.chunk_texts)
And the method should receive embeddings array matching chunk order
And the method should return VectorResult with embeddings array
And processing_time should reflect total batch processing duration

Given a VectorTask containing 5 text chunks
When the batch processing method processes the task
Then exactly 1 API call should be made to get_embeddings_batch()
And the API call should include all 5 chunks in correct order
And the response should contain 5 embeddings in corresponding order
And the VectorResult should contain all 5 embeddings
```

### Scenario: Error handling for batch operations
```gherkin
Given a batch processing request that encounters a retryable error
When the VoyageAI API returns a 429 rate limit error
Then the existing exponential backoff retry logic should apply to entire batch
And the batch should be retried as a complete unit
And server-provided Retry-After headers should be respected for batch
And batch failure should result in single error for all chunks in batch

Given a batch processing request with API connection failure
When the network request fails during batch processing
Then the entire batch should be marked as failed
And appropriate error information should be preserved in VectorResult
And the error should apply to all chunks in the failed batch
And processing_time should reflect time until failure occurred
```

### Scenario: Statistics tracking for batch operations
```gherkin
Given the existing statistics tracking system
When batch tasks are processed with multiple chunks per task
Then statistics should accurately count total embeddings generated
And embeddings_per_second should account for multiple embeddings per API call
And processing_time tracking should reflect batch processing efficiency
And queue_size calculations should remain accurate with batch tasks

Given a batch task processing 10 chunks in single API call
When statistics are updated after batch completion
Then total_tasks_completed should increase by 1 (one batch task)
And total embeddings should increase by 10 (ten chunks processed)
And embeddings_per_second should reflect improved throughput
And average_processing_time should show batch processing efficiency
```

### Scenario: Cancellation handling for batch operations
```gherkin
Given a batch processing task in progress
When the cancellation event is triggered during batch processing
Then the batch task should be cancelled gracefully
And partial results should not be committed to avoid inconsistent state
And appropriate cancellation status should be returned in VectorResult
And the task should be marked as cancelled rather than failed

Given multiple batch tasks queued when cancellation is requested
When cancellation occurs before batch processing begins
Then the unstarted batch tasks should be cancelled immediately
And no API calls should be made for cancelled batch tasks
And cancellation should be reflected in VectorResult.error field
```

## 🔧 Technical Implementation Details

### Method Signature Change
```pseudocode
# Current (single chunk)
def _calculate_vector(self, task: VectorTask) -> VectorResult:
    embedding = self.embedding_provider.get_embedding(task.chunk_text)

# Target (batch processing)  
def _calculate_vector(self, task: VectorTask) -> VectorResult:
    embeddings = self.embedding_provider.get_embeddings_batch(task.chunk_texts)
```

### Key Integration Points
- **Existing Infrastructure**: Use `get_embeddings_batch()` at lines 173-206
- **Error Handling**: Maintain existing retry/backoff patterns for batch operations
- **Statistics**: Update counters to reflect batch processing metrics
- **Cancellation**: Apply existing cancellation checks to batch operations

### Processing Flow
```pseudocode
1. Check cancellation status (existing pattern)
2. Call get_embeddings_batch(task.chunk_texts) (new batch API)
3. Process batch result into embeddings array (new logic)
4. Update statistics for batch operation (modified tracking)
5. Return VectorResult with embeddings array (new structure)
```

## 🧪 Testing Requirements

### Unit Tests
- [ ] Batch processing with multiple chunks
- [ ] Single chunk processing (via array of one item)
- [ ] Error handling and retry logic for batches
- [ ] Cancellation during batch processing
- [ ] Statistics tracking accuracy for batch operations

### Integration Tests  
- [ ] Real VoyageAI API batch processing
- [ ] Thread pool integration with batch tasks
- [ ] Performance improvement validation
- [ ] Error scenarios with actual API failures

## 🎯 Performance Validation

### Expected Improvements
- **API Calls**: N chunks = 1 API call (vs N API calls previously)
- **Network Overhead**: Reduced connection establishment per embedding
- **Rate Limit Efficiency**: Better RPM utilization with batch requests
- **Processing Time**: Lower total processing time due to batch efficiency

### Measurement Points
- [ ] API call count before/after modification
- [ ] Total processing time for equivalent workloads
- [ ] Embeddings per second throughput improvement
- [ ] Rate limit usage efficiency

## ⚠️ Implementation Considerations

### Existing Infrastructure Leverage
- **✅ Available**: `get_embeddings_batch()` fully implemented
- **✅ Tested**: Existing batch processing has error handling and retries  
- **✅ Compatible**: Same return format as individual calls (arrays)

### Threading Safety
- **Thread Pool**: No changes required to ThreadPoolExecutor
- **Worker Threads**: Same execution pattern with batch payloads
- **Statistics Lock**: Existing locking patterns apply to batch updates

## 📋 Definition of Done

- [ ] `_calculate_vector()` method processes chunk arrays via `get_embeddings_batch()`
- [ ] Batch processing maintains all existing error handling patterns
- [ ] Statistics tracking accurately reflects batch operations
- [ ] Cancellation handling works correctly for batch tasks
- [ ] Unit tests pass for batch processing scenarios
- [ ] Integration tests demonstrate API call reduction
- [ ] Performance improvements are measurable and documented
- [ ] Code review completed and approved

---

**Story Status**: ⏳ Ready for Implementation  
**Estimated Effort**: 4-6 hours  
**Risk Level**: 🟡 Medium (Core processing logic changes)  
**Dependencies**: 01_Story_DataStructureModification  
**Blocks**: 03_Story_BatchTaskSubmission, Feature 2 stories