# Story: Data Structure Modification

## 📖 User Story

As a system developer, I want to modify the VectorTask and VectorResult data structures to support chunk arrays instead of single chunks so that the foundation for batch processing is established in the core threading infrastructure.

## 🎯 Business Value

After this story completion, the VectorCalculationManager will have the data structure foundation needed for batch processing, enabling subsequent stories to implement the actual batch processing logic without further structural changes.

## 📍 Implementation Target

**File**: `/src/code_indexer/services/vector_calculation_manager.py`  
**Lines**: 31-48 (VectorTask and VectorResult dataclasses)

## ✅ Acceptance Criteria

### Scenario: VectorTask supports chunk arrays
```gherkin
Given the existing VectorTask dataclass with single chunk_text field
When I modify the VectorTask structure to support multiple chunks
Then the VectorTask should have chunk_texts field as List[str]
And the VectorTask should maintain all existing metadata fields
And the task_id should represent the batch operation identifier
And the created_at timestamp should track batch creation time

Given a VectorTask created with multiple chunks
When the task contains chunk array ["chunk1", "chunk2", "chunk3"]
Then the chunk_texts field should contain exactly those three strings
And the order of chunks should be preserved exactly as provided
And the metadata should support batch processing context information
```

### Scenario: VectorResult returns embedding arrays
```gherkin
Given the existing VectorResult dataclass with single embedding field
When I modify the VectorResult to support batch processing results
Then the VectorResult should have embeddings field as List[List[float]]
And each embedding should correspond to input chunks in same order
And the processing_time should reflect total batch processing duration
And error handling should apply to entire batch as single unit

Given a batch processing result with 3 chunks processed
When the VectorResult contains embeddings for all chunks
Then the embeddings field should contain exactly 3 embedding vectors
And embeddings[0] should correspond to chunk_texts[0] from input
And embeddings[1] should correspond to chunk_texts[1] from input
And embeddings[2] should correspond to chunk_texts[2] from input
And the task_id should match the original batch task identifier
```

### Scenario: Metadata preservation for batch operations
```gherkin
Given a VectorTask with complex batch metadata
When the task includes file path, chunk indices, and processing context
Then all metadata should be preserved through batch processing
And metadata should support tracking multiple chunks within single task
And batch-specific metadata should include chunk count information
And processing statistics should correctly account for batch operations

Given batch processing statistics tracking
When multiple chunks are processed in single batch task
Then statistics should count embeddings generated, not tasks completed
And processing_time should reflect entire batch duration
And error counts should treat batch failure as single failure event
```

## 🔧 Technical Implementation Details

### Data Structure Changes

**VectorTask Modifications:**
```pseudocode
@dataclass
class VectorTask:
    task_id: str
    chunk_texts: List[str]  # Changed from chunk_text: str
    metadata: Dict[str, Any]
    created_at: float
    batch_size: int  # New field for tracking
```

**VectorResult Modifications:**
```pseudocode
@dataclass  
class VectorResult:
    task_id: str
    embeddings: List[List[float]]  # Changed from embedding: List[float]
    metadata: Dict[str, Any]
    processing_time: float
    batch_size: int  # New field for tracking
    error: Optional[str] = None
```

### Compatibility Considerations
- **Breaking Change**: This temporarily breaks existing single-chunk usage
- **Restoration Plan**: Feature 2 will restore compatibility via wrapper methods
- **Testing Strategy**: Unit tests must be updated to use chunk arrays

## 🧪 Testing Requirements

### Unit Tests
- [ ] VectorTask creation with chunk arrays
- [ ] VectorResult creation with embedding arrays  
- [ ] Metadata preservation through data structure changes
- [ ] Order preservation for chunks and embeddings
- [ ] Batch size tracking accuracy

### Integration Tests
- [ ] Data structure compatibility with threading infrastructure
- [ ] Statistics tracking with modified structures
- [ ] Error handling with batch-oriented data

## ⚠️ Known Breaking Changes

### Temporary Breakage (Restored in Feature 2)
- [ ] Existing `submit_task()` calls will fail (single chunk → array expected)
- [ ] Current `_calculate_vector()` method incompatible with new structures  
- [ ] Unit tests requiring updates for new data structure format

### Migration Path
1. **This Story**: Modify data structures (breaks current usage)
2. **Next Story**: Update processing methods to use new structures
3. **Feature 2**: Add compatibility wrappers to restore single-chunk APIs

## 📋 Definition of Done

- [ ] VectorTask supports chunk_texts array field
- [ ] VectorResult supports embeddings array field
- [ ] All metadata fields preserved and enhanced for batch context
- [ ] Data structure changes maintain thread safety
- [ ] Unit tests updated and passing for new structures
- [ ] Code review completed and approved
- [ ] Documentation updated for data structure changes

---

**Story Status**: ⏳ Ready for Implementation  
**Estimated Effort**: 2-3 hours
**Risk Level**: 🟡 Medium (Breaking changes)  
**Dependencies**: None  
**Blocks**: 02_Story_BatchProcessingMethod