# Story: Metadata Compatibility Wrapper Implementation

## 📖 User Story

As a system developer, I want the existing `get_embedding_with_metadata()` functionality to work identically to before so that all metadata-dependent operations continue unchanged while leveraging internal batch processing efficiency.

## 🎯 Business Value

After this story completion, all code that relies on embedding metadata (tokens used, model info, provider details) will work exactly as before, maintaining system functionality while benefiting from batch processing optimizations.

## 📍 Implementation Target

**File**: `/src/code_indexer/services/voyage_ai.py`  
**Lines**: 208-225 (`get_embedding_with_metadata()` method)

## ✅ Acceptance Criteria

### Scenario: get_embedding_with_metadata() preserves exact behavior
```gherkin
Given the existing get_embedding_with_metadata() method
When I refactor it to use batch processing internally
Then it should call get_embeddings_batch_with_metadata([text], model)
And extract the first result from the batch response
And return the same EmbeddingResult format as before
And preserve all metadata fields (model, tokens_used, provider)

Given a single text chunk for metadata processing
When get_embedding_with_metadata() processes the text
Then the returned EmbeddingResult should contain identical fields as before
And embedding field should be List[float] as originally returned
And model field should show correct VoyageAI model name
And tokens_used field should contain accurate token count for the single text
And provider field should remain "voyage-ai" exactly as before
```

### Scenario: Metadata accuracy and consistency  
```gherkin
Given get_embedding_with_metadata() processing various text inputs
When processing texts of different lengths and complexity
Then token count should be accurate for each individual text
And model information should be consistent with VoyageAI response
And provider metadata should remain identical to original implementation
And all metadata should reflect single-text processing accurately

Given batch processing metadata extraction for single item
When the underlying batch API returns metadata for single-item batch
Then total_tokens_used from batch should equal tokens_used for single result
And model information should be extracted correctly from batch response
And provider should be set to "voyage-ai" consistently
And no batch-specific metadata should leak to single-item result
```

### Scenario: Error handling with metadata preservation
```gherkin
Given get_embedding_with_metadata() encountering VoyageAI errors
When the underlying batch processing fails with API errors
Then same error types should be raised as original implementation
And error messages should be identical to previous single-request behavior
And no metadata should be returned when errors occur
And error recovery should match original implementation exactly

Given authentication failures during metadata processing
When invalid API key causes batch processing to fail
Then ValueError should be raised with same message as before
And no partial metadata should be returned on authentication failure
And error handling should be indistinguishable from original behavior

Given rate limiting during metadata processing
When 429 errors occur during underlying batch processing
Then RuntimeError should be raised with same rate limit message
And retry behavior should be identical to original implementation
And metadata processing should resume after successful retry
```

### Scenario: Integration with dependent systems
```gherkin
Given systems that depend on EmbeddingResult metadata
When these systems call get_embedding_with_metadata()
Then all dependent code should continue working unchanged
And metadata fields should be available in same format as before
And data processing pipelines should work identically
And no changes should be required in consuming code

Given logging and monitoring systems using embedding metadata
When metadata is collected for operational metrics
Then token usage tracking should remain accurate
And model usage statistics should be preserved
And provider information should be consistently available
And operational dashboards should show identical information
```

## 🔧 Technical Implementation Details

### Wrapper Implementation Pattern
```pseudocode
def get_embedding_with_metadata(self, text: str, model: Optional[str] = None) -> EmbeddingResult:
    """Generate embedding with metadata (now using batch processing)."""
    # Convert single text to array
    texts = [text]
    
    # Use existing batch metadata processing
    batch_result = self.get_embeddings_batch_with_metadata(texts, model)
    
    # Extract single result from batch
    if not batch_result.embeddings or len(batch_result.embeddings) == 0:
        raise ValueError("No embedding returned from VoyageAI")
    
    # Create single EmbeddingResult from batch result
    return EmbeddingResult(
        embedding=batch_result.embeddings[0],
        model=batch_result.model,
        tokens_used=batch_result.total_tokens_used,  # For single item, total = individual
        provider=batch_result.provider,
    )
```

### Metadata Extraction Logic
- **Token Mapping**: `total_tokens_used` from batch maps to `tokens_used` for single item
- **Model Preservation**: Model name extracted from batch response unchanged
- **Provider Consistency**: Provider field remains "voyage-ai" exactly as before
- **Error Handling**: Same error types and messages for metadata failures

### Compatibility Requirements
- **Return Type**: Must return `EmbeddingResult` exactly as before
- **Field Names**: All field names identical to original structure
- **Field Types**: All field types and formats preserved
- **Optional Fields**: Optional fields handled identically to original

## 🧪 Testing Requirements

### Regression Testing
- [ ] All existing unit tests for get_embedding_with_metadata() pass
- [ ] Metadata fields contain same values as original implementation
- [ ] Error scenarios produce identical error types and messages
- [ ] Token counting accuracy maintained for single texts

### Metadata Validation
- [ ] EmbeddingResult structure unchanged
- [ ] Embedding field contains correct vector data
- [ ] Model field shows accurate VoyageAI model name
- [ ] Tokens_used field shows accurate count for processed text
- [ ] Provider field consistently shows "voyage-ai"

### Integration Testing
- [ ] Systems dependent on metadata continue working unchanged
- [ ] Operational monitoring and logging systems unaffected
- [ ] Token usage tracking remains accurate
- [ ] Model usage statistics preserved

## ⚠️ Implementation Considerations

### Batch-to-Single Metadata Mapping
- **Token Aggregation**: Single item batch has same token count as individual
- **Model Consistency**: Model information should be identical
- **Provider Preservation**: No changes to provider identification
- **Metadata Completeness**: All original metadata fields preserved

### Error Handling Precision
- **Same Exceptions**: Exact error types as original (ValueError, RuntimeError)
- **Same Messages**: Identical error message content and format
- **No Batch Leakage**: No indication of internal batch processing in errors
- **Recovery Behavior**: Identical retry and recovery patterns

## 📋 Definition of Done

- [ ] `get_embedding_with_metadata()` uses batch processing internally
- [ ] Method returns identical EmbeddingResult structure as before
- [ ] All metadata fields accurate and preserved (model, tokens_used, provider)
- [ ] Error handling produces same error types and messages as original
- [ ] All existing unit tests pass without modification
- [ ] Integration with metadata-dependent systems unchanged
- [ ] Token counting and model information accuracy validated
- [ ] Code review completed and approved

---

**Story Status**: ⏳ Ready for Implementation  
**Estimated Effort**: 2-3 hours  
**Risk Level**: 🟢 Low (Straightforward metadata mapping)  
**Dependencies**: Feature 1 completion, 01_Story_SingleEmbeddingWrapper  
**Blocks**: Systems dependent on embedding metadata  
**Critical Path**: Operational monitoring and token usage tracking