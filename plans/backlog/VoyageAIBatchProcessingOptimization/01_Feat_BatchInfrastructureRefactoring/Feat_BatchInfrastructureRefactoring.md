# Feature: Batch Infrastructure Refactoring

## 🎯 Feature Intent

Refactor the core VectorCalculationManager infrastructure to support batch processing of chunk arrays instead of individual chunks, enabling efficient utilization of the already-implemented `get_embeddings_batch()` VoyageAI API.

## 📊 Feature Value

- **Foundation**: Enables batch processing capability in the core threading infrastructure
- **Performance**: Prepares system for 100x API call reduction
- **Architecture**: Maintains existing thread pool patterns while supporting arrays
- **Safety**: Internal changes with no external API impact during this feature

## 🏗️ Technical Architecture

### Current State
```
VectorTask { chunk_text: str }
    ↓
_calculate_vector(task)
    ↓  
embedding_provider.get_embedding(task.chunk_text)
    ↓
VectorResult { embedding: List[float] }
```

### Target State
```
VectorTask { chunk_texts: List[str] }
    ↓
_calculate_vector_batch(task)
    ↓
embedding_provider.get_embeddings_batch(task.chunk_texts)
    ↓  
VectorResult { embeddings: List[List[float]] }
```

## 🔧 Key Components

### Data Structure Extensions
- **VectorTask**: Extend to support chunk arrays with backward compatibility
- **VectorResult**: Extend to return embedding arrays with metadata preservation
- **Statistics Tracking**: Update to handle batch operations correctly

### Processing Method Refactoring
- **Batch Processing Core**: Replace single-chunk processing with batch processing
- **Error Handling**: Maintain existing retry/backoff patterns for batches
- **Threading Safety**: Preserve current thread pool architecture

### Integration Points
- **Existing Infrastructure**: Leverage `get_embeddings_batch()` (lines 173-206)
- **Thread Pool**: No changes to ThreadPoolExecutor or worker management
- **Cancellation**: Maintain existing cancellation patterns for batch operations

## 📋 Story Implementation Tracking

- [ ] **01_Story_DataStructureModification**
- [ ] **02_Story_BatchProcessingMethod** 
- [ ] **03_Story_BatchTaskSubmission**

## 🎯 Success Criteria

### Technical Validation
- [ ] VectorTask and VectorResult support chunk arrays
- [ ] Batch processing method integrates with existing `get_embeddings_batch()`
- [ ] Statistics tracking accurately reflects batch operations
- [ ] Thread pool architecture remains unchanged

### Quality Assurance
- [ ] Unit tests pass for data structure modifications
- [ ] Batch processing handles errors and cancellation correctly
- [ ] Performance metrics show expected improvements
- [ ] No breaking changes to internal API contracts

## ⚠️ Implementation Risks

### Managed Risks
- **Breaking Changes**: Internal APIs temporarily broken until Feature 2 restores compatibility
- **Batch Failures**: Entire batch fails if any chunk fails (mitigated in Feature 2)
- **Memory Usage**: Slight increase due to array processing (~128KB max)

### Risk Mitigation
- **Incremental Testing**: Each story independently testable
- **Error Handling**: Maintain existing patterns adapted to batch context
- **Performance Monitoring**: Track memory and processing time impacts

## 🔍 Dependencies

### Prerequisites
- ✅ `get_embeddings_batch()` already implemented in VoyageAI service
- ✅ Current threading infrastructure stable and tested
- ✅ Existing error handling and retry patterns established

### Successor Requirements
- **Feature 2**: Depends on completion of all batch infrastructure
- **Feature 3**: Requires both infrastructure and compatibility layers

---

**Feature Status**: ⏳ Ready for Implementation  
**Implementation Order**: 1st (Foundation)  
**Risk Level**: 🟡 Medium (Internal breaking changes)  
**Next Step**: Begin with 01_Story_DataStructureModification