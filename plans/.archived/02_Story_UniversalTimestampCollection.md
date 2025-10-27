# User Story: Universal Timestamp Collection

## 📋 **User Story**

As a **CIDX user (both local and remote modes)**, I want **file modification timestamps collected during indexing for all files regardless of git status**, so that **I can detect when my local files differ from the remote index and understand result staleness**.

## 🎯 **Business Value**

Enables file-level staleness detection by ensuring consistent timestamp collection across all indexing scenarios. Users can make informed decisions about query results when they know local files have changed since remote indexing. Critical foundation for remote mode staleness awareness.

## 📝 **Acceptance Criteria**

### Given: Universal Timestamp Collection During Indexing
**When** I index any repository (git or non-git)  
**Then** the system collects `file_last_modified` timestamp for every file  
**And** uses `file_path.stat().st_mtime` as the timestamp source  
**And** works identically for git and non-git projects  
**And** timestamp collection never fails or blocks indexing process  

### Given: Vector Database Payload Enhancement
**When** I examine indexed file data in the vector database  
**Then** each file record includes `file_last_modified` timestamp  
**And** timestamp is stored as Unix timestamp (float) for consistency  
**And** existing payload structure is preserved (backward compatible)  
**And** timestamp data is queryable and retrievable  

### Given: Enhanced Query Response Model
**When** I receive query results from any endpoint  
**Then** QueryResultItem includes `file_last_modified` field  
**And** includes `indexed_timestamp` showing when file was indexed  
**And** timestamp fields are optional (nullable) for backward compatibility  
**And** response serialization handles timestamp fields correctly  

### Given: FileChunkingManager Integration
**When** I examine the FileChunkingManager implementation  
**Then** timestamp collection is integrated into existing chunking workflow  
**And** collection happens during file processing, not as separate operation  
**And** no performance degradation from timestamp collection  
**And** error handling preserves indexing success even if timestamp fails  

## 🏗️ **Technical Implementation**

### FileChunkingManager Enhancement
```python
class FileChunkingManager:
    def _create_file_chunk(self, file_path: Path, content: str, chunk_index: int) -> FileChunk:
        """Enhanced to always collect file modification timestamp."""
        
        # Always collect file modification timestamp
        try:
            file_last_modified = file_path.stat().st_mtime
        except (OSError, IOError):
            file_last_modified = None  # Don't fail indexing for timestamp issues
            
        # Create chunk with timestamp
        return FileChunk(
            # Existing fields...
            file_last_modified=file_last_modified,
            indexed_timestamp=time.time()  # When this indexing occurred
        )
```

### Vector Database Schema Enhancement
```python
# Enhanced payload structure
file_metadata = {
    # Existing fields preserved...
    "file_last_modified": file_path.stat().st_mtime,  # NEW: Always collected
    "indexed_timestamp": time.time(),                  # NEW: When indexed
    "git_last_modified": git_timestamp,                # Existing: git-specific
    "file_size": file_path.stat().st_size,            # Existing
}
```

### QueryResultItem Model Enhancement
```python
class QueryResultItem(BaseModel):
    # Existing fields...
    content: str
    score: float
    file_path: str
    
    # NEW: Timestamp fields for staleness detection
    file_last_modified: Optional[float] = None    # File mtime when indexed
    indexed_timestamp: Optional[float] = None     # When indexing occurred
    
    # Existing git-specific field (preserved)
    git_last_modified: Optional[str] = None
```

### Backward Compatibility Strategy
```python
def serialize_query_result(chunk_data: Dict[str, Any]) -> QueryResultItem:
    """Safely handle missing timestamp fields in existing data."""
    return QueryResultItem(
        # Existing fields...
        content=chunk_data.get("content"),
        score=chunk_data.get("score"),
        file_path=chunk_data.get("file_path"),
        
        # New fields with safe defaults
        file_last_modified=chunk_data.get("file_last_modified"),
        indexed_timestamp=chunk_data.get("indexed_timestamp"),
        git_last_modified=chunk_data.get("git_last_modified"),
    )
```

## 🧪 **Testing Requirements**

### Unit Tests
- ✅ Timestamp collection for various file types and permissions
- ✅ Error handling when file stat() fails (permissions, deleted files)
- ✅ FileChunk creation with timestamp fields
- ✅ QueryResultItem serialization with new timestamp fields

### Integration Tests
- ✅ End-to-end indexing workflow with timestamp collection
- ✅ Vector database storage and retrieval of timestamp data
- ✅ Query operations returning enhanced timestamp information
- ✅ Backward compatibility with existing indexed data

### Performance Tests
- ✅ Timestamp collection impact on indexing performance (<1% overhead)
- ✅ Query response time with additional timestamp fields
- ✅ Memory usage impact of enhanced payload structure
- ✅ Concurrent indexing operations with timestamp collection

### Compatibility Tests
- ✅ Git project timestamp collection (compare with existing behavior)
- ✅ Non-git project timestamp collection (verify consistency)
- ✅ Mixed repository types in same indexing session
- ✅ Legacy query results without timestamp fields handled gracefully

## ⚙️ **Implementation Pseudocode**

### Enhanced File Processing Algorithm
```
FOR each file in repository:
    content = read_file(file_path)
    
    # ALWAYS collect file modification timestamp (NEW)
    TRY:
        file_mtime = file_path.stat().st_mtime
    EXCEPT (permissions, not found):
        file_mtime = NULL  # Don't fail indexing
    
    # Create chunks with timestamp data
    FOR each chunk in split_content(content):
        chunk_metadata = {
            existing_fields...,
            file_last_modified: file_mtime,      # NEW
            indexed_timestamp: current_time()    # NEW
        }
        
        store_in_vector_db(chunk_metadata)
```

### Query Result Enhancement
```
def get_query_results(query: str) -> List[QueryResultItem]:
    raw_results = vector_db.query(query)
    
    enhanced_results = []
    FOR result in raw_results:
        enhanced_result = QueryResultItem(
            content=result.content,
            score=result.score,
            file_path=result.file_path,
            file_last_modified=result.get('file_last_modified'),    # NEW
            indexed_timestamp=result.get('indexed_timestamp'),      # NEW
            git_last_modified=result.get('git_last_modified')       # Existing
        )
        enhanced_results.append(enhanced_result)
    
    return enhanced_results
```

## ⚠️ **Edge Cases and Error Handling**

### File System Access Issues
- Permission denied on file stat() -> set timestamp to None, continue indexing
- File deleted during indexing -> handle gracefully, don't crash process
- Symbolic links -> resolve and get target file timestamp
- Network mounted files -> handle potential latency in stat() calls

### Timestamp Accuracy Considerations
- Timezone handling: store as UTC timestamps for consistency
- File system timestamp precision varies by platform
- Very old files (before Unix epoch) handled appropriately
- Future timestamps (clock skew) detected and logged

### Performance Impact Mitigation
- Timestamp collection integrated into existing file read operations
- Minimal additional system calls (stat() already used for file size)
- Batch timestamp collection where possible
- Error handling prevents timestamp failures from blocking indexing

### Data Migration Strategy
- Existing indexed data without timestamps continues to work
- New indexing operations include timestamp data
- Query responses handle mixed data (some with/without timestamps)
- No forced re-indexing required for timestamp support

## 📊 **Definition of Done**

- ✅ FileChunkingManager enhanced to collect file modification timestamps universally
- ✅ Vector database schema supports timestamp storage without breaking changes
- ✅ QueryResultItem model includes timestamp fields with backward compatibility
- ✅ All existing functionality preserved (no regressions in local mode)
- ✅ Performance impact measured and documented (<1% overhead)
- ✅ Comprehensive test coverage for timestamp collection and retrieval
- ✅ Error handling prevents timestamp issues from blocking indexing
- ✅ Documentation updated to reflect enhanced timestamp capabilities
- ✅ Code review validates implementation correctness and performance
- ✅ Integration testing confirms end-to-end timestamp workflow