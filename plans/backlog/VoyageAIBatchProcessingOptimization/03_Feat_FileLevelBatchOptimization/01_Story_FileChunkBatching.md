# Story: File Chunk Batching Implementation

## 📖 User Story

As a performance-conscious user, I want files with multiple chunks to be processed as single batch operations so that indexing throughput is dramatically improved through optimal API utilization while maintaining complete file processing functionality.

## 🎯 Business Value

After this story completion, files with many chunks will process 10-50x faster due to single batch API calls instead of multiple individual calls, providing the primary performance benefit that justifies this entire epic while maintaining all existing functionality.

## 📍 Implementation Target

**File**: `/src/code_indexer/services/file_chunking_manager.py`  
**Lines**: 320-380 (`_process_file_clean_lifecycle()` method - chunk submission and processing section)

## ✅ Acceptance Criteria

### Scenario: Single batch submission replaces individual chunk processing
```gherkin
Given the existing file processing that submits chunks individually
When I refactor _process_file_clean_lifecycle() to use batch processing
Then all chunks from a file should be collected into a single array
And a single batch VectorTask should be submitted to VectorCalculationManager
And the batch should contain all chunks with appropriate file metadata
And file processing should wait for single batch result instead of N individual results

Given a file that generates 25 chunks during processing
When the file processing reaches the vectorization step
Then exactly 1 call to submit_batch_task() should be made
And the batch should contain all 25 chunks in correct order
And exactly 1 API call should be made to VoyageAI (instead of 25)
And the batch result should contain 25 embeddings matching the chunk order
```

### Scenario: Qdrant point creation from batch results
```gherkin
Given a completed batch task with embeddings for all file chunks
When the batch result is processed to create Qdrant points
Then each embedding should be paired with its corresponding chunk data
And Qdrant points should be created with correct metadata for each chunk
And all points should maintain proper chunk index and file relationships
And point creation should preserve all existing metadata patterns

Given batch processing result with 10 chunks and 10 embeddings
When Qdrant points are created from the batch result
Then exactly 10 points should be created with correct embeddings
And point[0] should correspond to chunk[0] with embedding[0]
And point[1] should correspond to chunk[1] with embedding[1]
And all points should contain correct file path, chunk indices, and project metadata
And point IDs should be generated consistently with existing patterns
```

### Scenario: File atomicity and error handling
```gherkin
Given batch processing failure for a file with multiple chunks
When the VoyageAI batch API call fails for the entire file
Then no Qdrant points should be created for any chunks in the file
And the entire file should be marked as failed (atomic failure)
And error information should be preserved for the complete file failure
And other files being processed in parallel should be unaffected

Given a file processing batch that encounters cancellation
When cancellation is requested during batch processing
Then the batch should be cancelled gracefully without partial results
And no Qdrant points should be written for the cancelled file
And file processing should be marked as cancelled rather than failed
And cancellation should not affect other concurrent file processing
```

### Scenario: Order preservation and metadata consistency  
```gherkin
Given file chunks generated in specific order during file processing
When chunks are submitted as batch for vectorization
Then chunk order should be preserved exactly in the batch submission
And embedding results should maintain the same order as input chunks
And Qdrant point creation should respect original chunk ordering
And chunk indices should match original file chunking sequence

Given file metadata including project ID, file hash, and git information
When batch processing is performed for the file
Then all metadata should be preserved for each chunk in the batch
And each Qdrant point should contain complete metadata information
And batch processing should not lose or corrupt any file-level metadata
And git-aware metadata should be consistent across all chunks in the file
```

## 🔧 Technical Implementation Details

### Batch Collection and Submission
```pseudocode
# Current individual processing (REMOVE)
for chunk in file_chunks:
    future = vector_manager.submit_task(chunk["text"], metadata)
    futures.append(future)

# New batch processing (IMPLEMENT)
chunk_texts = [chunk["text"] for chunk in file_chunks]
batch_future = vector_manager.submit_batch_task(chunk_texts, file_metadata)
batch_result = batch_future.result(timeout=VECTOR_PROCESSING_TIMEOUT)
```

### Result Processing Modification
```pseudocode
# Process batch result to create Qdrant points
for i, (chunk, embedding) in enumerate(zip(file_chunks, batch_result.embeddings)):
    qdrant_point = self._create_qdrant_point(
        chunk=chunk,
        embedding=embedding,
        metadata=file_metadata,
        file_path=file_path
    )
    file_points.append(qdrant_point)
```

### Error Handling Integration
- **Batch Failures**: Entire file fails if batch processing fails
- **Timeout Handling**: Apply existing timeout to batch operation
- **Cancellation**: Check cancellation status before and during batch processing
- **Recovery**: Maintain existing error reporting and statistics patterns

## 🧪 Testing Requirements

### Performance Validation
- [ ] API call count measurement (N chunks → 1 API call)
- [ ] Processing time improvement validation (10-50x faster)
- [ ] Memory usage impact assessment for batch processing
- [ ] Rate limit efficiency improvement measurement

### Functional Testing
- [ ] File processing accuracy with batch operations
- [ ] Qdrant point creation with correct chunk-to-embedding mapping
- [ ] Metadata preservation through batch processing
- [ ] Error handling for batch failures

### Edge Cases
- [ ] Single chunk files (batch of 1 item)
- [ ] Very large files approaching VoyageAI batch limits
- [ ] Empty files or files with no processable chunks
- [ ] Files with special characters or encoding issues

### Integration Testing
- [ ] Multiple files processing in parallel with batching
- [ ] File atomicity - no partial file processing
- [ ] Cancellation during batch processing
- [ ] Progress reporting accuracy with batch operations

## 🎯 Performance Expectations

### Throughput Improvements
| File Size | Chunks | Current API Calls | Batch API Calls | Improvement |
|-----------|---------|------------------|----------------|-------------|
| Small | 5-10 | 5-10 | 1 | 5-10x |
| Medium | 20-50 | 20-50 | 1 | 20-50x |
| Large | 100+ | 100+ | 1 | 100x+ |

### System Impact
- **Network Efficiency**: Reduced connection overhead per file
- **Rate Limits**: Better RPM utilization with fewer requests
- **User Experience**: Dramatically faster indexing for large codebases
- **Resource Usage**: Minimal memory increase (~128KB max per batch)

## ⚠️ Implementation Considerations

### Existing Integration Points
- **Chunk Generation**: No changes to chunking logic (already works)
- **Metadata Creation**: Use existing `_create_qdrant_point()` method
- **Error Reporting**: Maintain existing file-level error reporting patterns
- **Statistics**: Update file processing statistics accurately

### File Processing Flow Changes
- **Before**: Chunk → Submit Individual → Wait N Results → Create N Points
- **After**: Chunks → Submit Batch → Wait 1 Result → Create N Points
- **Preserved**: File atomicity, error isolation, progress reporting patterns

### Batch Size Considerations
- **VoyageAI Limit**: Maximum 1000 texts per batch (very large files)
- **Typical Files**: Most files well below 1000 chunks
- **Large Files**: May need chunking strategy for extremely large files (future enhancement)

## 📋 Definition of Done

- [ ] File processing collects all chunks into single array before vectorization
- [ ] Single `submit_batch_task()` call replaces individual chunk submissions
- [ ] Batch results processed correctly to create all Qdrant points
- [ ] Chunk-to-embedding order preservation maintained accurately
- [ ] File atomicity preserved (all chunks succeed or entire file fails)
- [ ] API call count reduced to 1 per file regardless of chunk count
- [ ] All existing metadata and file processing functionality preserved
- [ ] Error handling works correctly for batch operations
- [ ] Performance improvement measurable and significant (10x+ for multi-chunk files)
- [ ] Unit and integration tests pass for batch processing workflow
- [ ] Code review completed and approved

---

**Story Status**: ⏳ Ready for Implementation  
**Estimated Effort**: 6-8 hours  
**Risk Level**: 🟡 Medium (Core file processing changes)  
**Dependencies**: Features 1 and 2 completion (batch infrastructure and compatibility)  
**Expected Impact**: 🚀 Primary performance benefit of entire epic  
**Critical Success Factor**: API call reduction and throughput improvement