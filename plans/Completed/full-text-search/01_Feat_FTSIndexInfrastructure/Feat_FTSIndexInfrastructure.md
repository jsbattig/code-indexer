# Feature: FTS Index Infrastructure

## Summary

Establish the foundational full-text search indexing infrastructure using Tantivy, providing opt-in index creation and real-time maintenance capabilities that run parallel to semantic indexing.

## Problem Statement

CIDX lacks a persistent full-text index, forcing users to rely on grep which re-scans files on every search. We need an efficient, index-backed text search system that maintains itself automatically.

## Success Criteria

1. **Opt-in Activation:** --fts flag enables FTS indexing without affecting default behavior
2. **Parallel Processing:** FTS indexing runs alongside semantic indexing without interference
3. **Real-time Updates:** Watch mode maintains FTS index within 5-50ms of file changes
4. **Storage Efficiency:** Index stored in .code-indexer/tantivy_index/ with <50% overhead
5. **Progress Visibility:** Unified progress reporting for both semantic and FTS indexing

## Scope

### In Scope
- Tantivy index creation with --fts flag
- Parallel indexing via HighThroughputProcessor
- Real-time incremental updates in watch mode
- Background segment merging for optimization
- Progress reporting integration
- Metadata tracking for FTS availability

### Out of Scope
- Query functionality (handled by FTS Query Engine feature)
- API endpoints (handled by Hybrid Search Integration feature)
- Score merging algorithms
- Migration of existing semantic-only indexes

## Technical Design

### Tantivy Schema Definition
```python
schema = {
    "path": "stored, not indexed",  # File path for retrieval
    "content": "text, tokenized",   # Code-aware tokenization
    "content_raw": "stored",        # For exact phrase matching
    "identifiers": "text, simple",  # Function/class names
    "line_start": "u64, indexed",   # Line position tracking
    "line_end": "u64, indexed",     # Line position tracking
    "language": "facet"             # For language filtering
}
```

### Storage Architecture
```
.code-indexer/
├── index/              # Existing semantic vectors
├── tantivy_index/      # New FTS index location
│   ├── meta.json       # Index metadata
│   ├── segments/       # Tantivy segments
│   └── write.lock      # Concurrency control
└── config.json         # Configuration
```

### Integration Points

1. **CLI Commands:**
   - `cidx index --fts` - Build both semantic and FTS indexes
   - `cidx watch --fts` - Monitor and update both indexes

2. **Processing Pipeline:**
   - Hook into FileChunkingManager for file content
   - Extend HighThroughputProcessor for parallel indexing
   - Integrate with RichLiveProgressManager for dual progress

3. **Commit Strategy:**
   - Initial indexing: Batch commits (100-1000 files)
   - Watch mode: Per-file commits (5-50ms latency)
   - Background merging: 10-20 segments → 3-5 optimal

## Stories

| Story # | Title | Priority | Effort |
|---------|-------|----------|--------|
| 01 | Opt-In FTS Index Creation | MVP | Large |
| 02 | Real-Time FTS Index Maintenance | MVP | Medium |

## Dependencies

- Tantivy Python bindings (v0.25.0)
- Existing HighThroughputProcessor
- FileChunkingManager for file content access
- RichLiveProgressManager for progress reporting

## Acceptance Criteria

1. **Index Creation:**
   - `cidx index` without --fts creates semantic index only
   - `cidx index --fts` creates both indexes in parallel
   - Progress bar shows both indexing operations
   - Tantivy index stored in correct location

2. **Watch Mode:**
   - `cidx watch` without --fts updates semantic only
   - `cidx watch --fts` updates both indexes
   - File changes reflected in <100ms
   - Graceful handling of missing FTS index

3. **Performance:**
   - Indexing speed: 10K-50K files/second
   - Memory usage: Fixed 1GB heap
   - Storage overhead: <50% with compression
   - Minimal blocking: 5-50ms for commits

## Conversation References

- **Opt-in Design:** "cidx index builds semantic only (default), cidx index --fts builds both"
- **Storage Location:** ".code-indexer/tantivy_index/ storage parallel to FilesystemVectorStore"
- **Commit Strategy:** "Adaptive (watch=per-file 5-50ms, initial=large batches 100-1000 files)"
- **Integration:** "Hook into existing cidx index --fts and cidx watch --fts commands"