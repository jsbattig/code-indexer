# Epic: Full-Text Search for CIDX

## Executive Summary

CIDX currently excels at semantic code search but lacks efficient full-text search capabilities. Developers resort to external grep tools that re-scan files on every search, creating performance bottlenecks. This epic introduces an opt-in, index-backed full-text search system using Tantivy, providing fast exact text matching alongside semantic search.

## Problem Statement

**Current State:** CIDX users perform semantic searches but must use external grep for exact text matching, which re-scans files on every search (inefficient for large codebases).

**Desired State:** CIDX provides both semantic AND fast index-backed full-text search with real-time updates, fuzzy matching, and configurable result presentation.

**Impact:** Eliminates performance bottlenecks, provides unified search experience, enables hybrid semantic+text search strategies.

## Success Criteria

1. **Performance:** <5ms query latency for text searches on 40K+ file codebases
2. **Real-time Updates:** Index updates within 5-50ms of file changes in watch mode
3. **Flexibility:** Case sensitivity control, fuzzy matching with configurable edit distance
4. **Integration:** Seamless CLI and Server API support with opt-in --fts flag
5. **Non-Breaking:** All existing functionality preserved, FTS is purely additive

## Features Overview

| Feature | Priority | Description | Stories |
|---------|----------|-------------|---------|
| FTS Index Infrastructure | MVP | Tantivy-based indexing with opt-in activation | 1 |
| FTS Query Engine | MVP | Text search with fuzzy matching and configurable presentation | 2 |
| Hybrid Search Integration | Medium | Combined text+semantic search capability | 2 |

## Technical Architecture Summary

### Core Technology: Tantivy v0.25.0
- **Performance:** 10K-50K docs/sec indexing, <5ms query latency
- **Storage:** .code-indexer/tantivy_index/ (parallel to semantic index)
- **Memory:** Fixed 1GB heap (proven from LanceDB approach)
- **Schema:** path, content (tokenized), content_raw (exact), identifiers, line positions, language

### Integration Points
- **CLI:** --fts flag via Click decorators on index/watch/query commands
- **Processing:** Parallel indexing via HighThroughputProcessor
- **Progress:** Extended RichLiveProgressManager for dual-index reporting
- **Storage:** FilesystemVectorStore pattern adapted for Tantivy segments

### Key Design Decisions
1. **Opt-in by Default:** --fts flag required (no breaking changes)
2. **Fuzzy Matching:** Default edit distance 0 (exact), configurable via --edit-distance
3. **Context Lines:** Default 5 lines, configurable via --snippet-lines
4. **Hybrid Presentation:** Separate sections (text first, then semantic) - no score merging

## Implementation Phases

### Phase 1: MVP Core (Features 1-2)
- FTS index infrastructure with Tantivy
- Basic text search with configurable options
- Real-time maintenance in watch mode
- CLI integration with --fts flag

### Phase 2: Enhanced Integration (Feature 3)
- Hybrid search capability
- Server API extensions
- Documentation and teach-ai updates

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Storage overhead (+30-50%) | Medium | Opt-in design, compression options |
| Memory usage (+100MB) | Low | Fixed 1GB heap, OS page cache |
| Index corruption | High | Atomic writes, segment isolation |
| Performance degradation | Medium | Background merging, adaptive commits |

## Conversation References

- **Problem Definition:** "CIDX has excellent semantic search but lacks efficient full-text search"
- **Opt-in Design:** "cidx index builds semantic only (default), cidx index --fts builds both"
- **Technology Choice:** "Tantivy v0.25.0, 10K-50K docs/sec indexing, <5ms query latency"
- **Hybrid Approach:** "Approach A - Separate Presentation (FTS first, header separator, then semantic)"
- **Storage Location:** ".code-indexer/tantivy_index/ confirmed"

## Dependencies and Prerequisites

- Python 3.8+ (Tantivy compatibility)
- Existing CIDX semantic search infrastructure
- HighThroughputProcessor for parallel processing
- RichLiveProgressManager for progress reporting

## Success Metrics

1. **Query Performance:** <5ms P99 latency for text searches
2. **Index Freshness:** <100ms from file change to searchable
3. **User Adoption:** 50%+ users enabling --fts within 3 months
4. **API Usage:** 30%+ of API searches using FTS or hybrid mode
5. **Storage Efficiency:** <50% overhead with compression enabled