# Story: Single Embedding Wrapper Implementation

## 📖 User Story

As a CLI user, I want the existing `get_embedding()` functionality to work exactly as before so that query commands and all single-embedding operations continue working unchanged while benefiting from internal batch processing optimizations.

## 🎯 Business Value

After this story completion, all existing single-embedding functionality (especially CLI queries) will work identically to before, but will internally use the efficient batch processing infrastructure, providing performance benefits without any user-visible changes.

## 📍 Implementation Target

**File**: `/src/code_indexer/services/voyage_ai.py`  
**Lines**: 164-171 (`get_embedding()` method)

## ✅ Acceptance Criteria

### Scenario: get_embedding() uses batch processing internally
```gherkin
Given the existing get_embedding() method signature and behavior
When I refactor it to use batch processing internally  
Then it should call get_embeddings_batch([text]) with single-item array
And extract the first (and only) embedding from the batch result
And return the same List[float] format as before
And maintain identical error handling behavior for single requests

Given a single text "def calculate_sum(a, b): return a + b"
When I call get_embedding() with this text
Then internally get_embeddings_batch() should be called with ["def calculate_sum(a, b): return a + b"]
And the result should be identical to previous get_embedding() behavior
And the return type should remain List[float] as before
And processing should complete with same or better performance
```

### Scenario: Error handling preservation for single embedding
```gherkin
Given get_embedding() encountering VoyageAI API errors
When the underlying batch processing encounters a 429 rate limit error
Then the same rate limit error should be propagated to the caller
And error message should be identical to previous single-request errors
And error type should remain the same as original implementation
And retry behavior should be maintained exactly as before

Given get_embedding() with invalid API key
When the batch processing encounters authentication failure
Then ValueError should be raised with identical message to original
And error handling should be indistinguishable from previous behavior
And no indication of internal batch processing should leak to caller

Given get_embedding() with network connectivity issues
When the underlying batch API call fails due to network problems
Then ConnectionError should be raised with same details as before
And error recovery behavior should match original implementation exactly
```

### Scenario: CLI query functionality unchanged
```gherkin
Given the CLI query command using get_embedding() for query processing
When users execute "cidx query 'search terms'" commands
Then query embedding generation should work identically to before
And query performance should be same or better than original
And all CLI functionality should remain completely unchanged
And users should experience no difference in query behavior

Given complex query scenarios with special characters
When CLI processes queries with "áéíóú 中文 🚀" and code snippets
Then get_embedding() should handle all inputs identically to before
And embedding generation should produce same vectors as original
And query results should be identical for same search terms
```

### Scenario: API contract preservation
```gherkin
Given existing code calling get_embedding() method
When the method is refactored to use batch processing internally
Then method signature should remain exactly: get_embedding(text: str, model: Optional[str] = None) -> List[float]
And return type should be identical List[float] format
And optional model parameter should work exactly as before
And method documentation should remain accurate

Given edge cases with empty strings and special inputs
When get_embedding() is called with "", "\\n", or very long texts
Then behavior should be identical to original implementation
And edge case handling should remain exactly the same
And no new edge cases should be introduced by batch processing
```

## 🔧 Technical Implementation Details

### Wrapper Implementation Pattern
```pseudocode
def get_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
    """Generate embedding for given text (now using batch processing)."""
    # Convert single text to array
    texts = [text]
    
    # Use existing batch processing method
    batch_result = self.get_embeddings_batch(texts, model)
    
    # Extract single result from batch
    if not batch_result or len(batch_result) == 0:
        raise ValueError("No embedding returned from VoyageAI")
        
    return batch_result[0]
```

### Error Handling Preservation
- **Same Exceptions**: Maintain exact error types (ValueError, ConnectionError, RuntimeError)
- **Same Messages**: Preserve error message content and format
- **Same Behavior**: Maintain retry patterns and timeout handling
- **No Leakage**: No indication that batch processing is used internally

### Performance Considerations
- **Single-Item Efficiency**: Batch processing single item should be as fast or faster
- **API Call Count**: Same number of API calls (1) for single embedding requests
- **Memory Usage**: Minimal overhead from array wrapping
- **Response Time**: Same or better response time for single requests

## 🧪 Testing Requirements

### Regression Testing
- [ ] All existing unit tests for get_embedding() pass unchanged
- [ ] CLI query functionality works identically to before
- [ ] Error scenarios produce same error types and messages
- [ ] Performance characteristics maintained or improved

### Compatibility Validation
- [ ] Method signature remains identical
- [ ] Return type format unchanged (List[float])
- [ ] Optional parameters work exactly as before
- [ ] Edge cases handled identically to original

### Integration Testing
- [ ] CLI query commands work without changes
- [ ] Embedding quality and consistency validated
- [ ] Network error handling behavior preserved
- [ ] Rate limiting responses handled identically

## ⚠️ Implementation Considerations

### Preserving Original Behavior
- **Exact Error Messages**: Must match original error text precisely
- **Same Performance**: No degradation for single embedding requests  
- **Identical Edge Cases**: Empty string, special characters, very long text
- **Model Parameter**: Optional model selection must work identically

### Batch Processing Integration
- **Internal Only**: Batch processing completely hidden from callers
- **Single Item Arrays**: Always pass [text] to batch method
- **Result Extraction**: Always extract first result from batch response
- **Error Translation**: Convert batch errors to original single-request errors

## 📋 Definition of Done

- [ ] `get_embedding()` method uses `get_embeddings_batch()` internally
- [ ] Method signature and return type remain identical to original
- [ ] All error handling produces same error types and messages as before
- [ ] CLI query functionality works unchanged
- [ ] All existing unit tests pass without modification
- [ ] Performance is same or better than original implementation
- [ ] Edge cases handled identically to original behavior
- [ ] Code review completed and approved
- [ ] Integration testing confirms no regression

---

**Story Status**: ⏳ Ready for Implementation  
**Estimated Effort**: 2-3 hours  
**Risk Level**: 🟢 Low (Simple wrapper implementation)  
**Dependencies**: Feature 1 completion (batch infrastructure available)  
**Blocks**: CLI query regression  
**Critical Path**: CLI functionality preservation