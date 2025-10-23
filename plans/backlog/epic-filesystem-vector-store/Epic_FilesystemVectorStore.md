# Epic: Filesystem-Based Vector Database Backend

**Epic ID:** EPIC-FS-VEC-001
**Created:** 2025-01-23
**Status:** Backlog
**Priority:** High
**Target Release:** TBD

## Executive Summary

Replace the container-based Qdrant vector database with a zero-dependency filesystem-based vector storage system that enables git-trackable semantic search indexes stored alongside code. This eliminates container infrastructure requirements (Docker/Podman), reduces RAM overhead, and simplifies deployment while maintaining query performance within acceptable bounds (<1s for 40K vectors).

**User Requirement Citation:** *"I don't want to run ANY containers, zero. I want to store my index, side by side, with my code, and I want it to go inside git, as the code. I don't want the overhead and complexity of qdrant and the data cleaner, and I don't want the ram overhead of every qdrant database."*

## Business Value

### Problems Solved
1. **Container Dependency Elimination:** No Docker/Podman requirement reduces setup complexity
2. **Version Control Integration:** Vector indexes become git-trackable alongside code
3. **Resource Efficiency:** Eliminates RAM overhead of running Qdrant instances
4. **Simplified Deployment:** No container orchestration or port management needed
5. **Local-First Architecture:** All data lives with the code repository

### Target Users
- Developers working in container-restricted environments
- Teams wanting version-controlled semantic search indexes
- Projects prioritizing minimal infrastructure dependencies
- Individual developers seeking simplified local setup

## Technical Architecture

### Path-as-Vector Quantization System

**User Insight Citation:** *"can't you lay, on disk, json files that represent the metadata related to the vector, and the entire path IS the vector?"*

**Core Innovation:** Use filesystem paths as quantized vector representations, leveraging OS filesystem indexing for initial filtering before exact ranking in RAM.

**Quantization Pipeline:**
```
1536-dim vector → Random Projection → 64-dim → 2-bit Quantization → 32 hex chars → Directory Path
```

**Storage Structure:**
```
.code-indexer/vectors/{collection_name}/
├── projection_matrix.json       # Deterministic projection matrix
├── a3/                          # First level (depth factor determines split)
│   ├── b7/                      # Second level
│   │   ├── 2f/                  # Third level
│   │   │   └── c9d8e4f1...json # Vector metadata + full 1536-dim vector
```

### JSON Storage Format

**User Requirement Citation:** *"no chunk data is stored in the json objects, but relative references to the files that contain the chunks"*

```json
{
  "file_path": "src/module/file.py",
  "start_line": 42,
  "end_line": 87,
  "start_offset": 1234,
  "end_offset": 2567,
  "chunk_hash": "abc123...",
  "vector": [0.123, -0.456, ...],  // Full 1536-dim vector
  "metadata": {
    "file_hash": "def456...",
    "indexed_at": "2025-01-23T10:00:00Z",
    "embedding_model": "voyage-code-3",
    "branch": "main"
  }
}
```

### Search Algorithm

**User Clarification Citation:** *"can't you fetch and sort in RAM by rank? It's OK to fetch all, sort and return"*

1. **Query Quantization:** Convert query vector to filesystem path
2. **Neighbor Discovery:** Use glob patterns to find exact + neighbor buckets
3. **Batch Loading:** Load all matching JSON files into RAM
4. **Exact Ranking:** Compute cosine similarity with full 1536-dim vectors
5. **Filter Application:** Apply metadata filters in memory
6. **Result Return:** Sort by similarity, return top-k results

### Backend Abstraction Layer

**User Requirement Citation:** *"abstract the qdrant db provider behind an abstraction layer, and create a similar one for our new db, and drop it in based on a --flag on init commands"*

```python
class VectorStoreBackend(ABC):
    """Abstract interface for vector storage backends"""
    def initialize(self) -> bool
    def start(self) -> bool
    def stop(self) -> bool
    def get_status(self) -> Dict
    def cleanup(self, remove_data: bool) -> bool
    def get_vector_store_client(self) -> Union[QdrantClient, FilesystemVectorStore]
    def health_check(self) -> bool
    def get_service_info(self) -> Dict
```

## Success Metrics

### Performance Targets
- **Query Latency:** <1s for 40K vectors (User: *"~1s is fine"*)
- **Indexing Speed:** Comparable to current Qdrant implementation
- **Storage Efficiency:** JSON files 1-10 per directory (optimal from POC)

### Functional Requirements
- **Zero Containers:** No Docker/Podman dependencies
- **Git Integration:** Full index stored in `.code-indexer/vectors/`
- **API Compatibility:** Drop-in replacement for QdrantClient
- **Multi-Provider Support:** Works with VoyageAI and Ollama embeddings

## Implementation Approach

### Phase 1: Proof of Concept (Story 0)
**User Requirement Citation:** *"I want you to add one user story, story zero... doing a proof of concept... fine tune with this the approach"*

- Validate filesystem performance at scale
- Determine optimal directory depth factor
- Measure query latency and over-fetch ratios
- Go/No-Go decision based on 40K vector performance

### Phase 2: Core Implementation
- Implement FilesystemVectorStore with QdrantClient interface
- Create backend abstraction layer
- Migrate CLI commands to use abstraction

### Phase 3: Integration & Testing
- Comprehensive test coverage
- Performance benchmarking
- Documentation updates

## Risk Assessment

### Technical Risks
1. **Query Performance Degradation**
   - Mitigation: POC validation before full implementation
   - Acceptance: User accepts ~1s latency

2. **Large Repository Scalability**
   - Mitigation: Depth factor tuning from POC
   - Primary target: 40K vectors

3. **Git Repository Bloat**
   - Mitigation: JSON compression, .gitignore option
   - User accepts this trade-off for version control benefits

### Operational Risks
1. **Migration Path**
   - User Decision: *"I don't want any migration tools, to use this new system, we will destroy, re-init and reindex"*
   - Clean slate approach eliminates migration complexity

## Stories Overview

**Epic Structure:** 9 user-value stories (S00-S08) focused on end-to-end testable functionality via `cidx` CLI.

| ID | Story | Priority | Estimated Effort | Implementation Order |
|----|-------|----------|------------------|---------------------|
| S00 | Proof of Concept - Path Quantization Performance Analysis | Critical | 3-5 days | 1 |
| S01 | Initialize Filesystem Backend for Container-Free Indexing | High | 3-5 days | 2 |
| S02 | Index Code to Filesystem Without Containers | High | 8-12 days | 3 |
| S03 | Search Indexed Code from Filesystem | High | 5-7 days | 4 |
| S04 | Monitor Filesystem Index Status and Health | Medium | 2-3 days | 5 |
| S05 | Manage Collections and Clean Up Filesystem Index | High | 3-4 days | 6 |
| S06 | Seamless Start and Stop Operations | High | 2-3 days | 7 |
| S07 | Multi-Provider Support with Filesystem Backend | Medium | 2-3 days | 8 |
| S08 | Switch Between Qdrant and Filesystem Backends | High | 2-3 days | 9 |

**Total Estimated Effort:** 30-44 days

## Dependencies

### Technical Dependencies
- Python filesystem operations
- NumPy for vector operations
- JSON serialization
- Glob pattern matching

### No External Dependencies
- No Docker/Podman
- No Qdrant
- No network services
- No container orchestration

## Constraints

### Design Constraints
- Must maintain QdrantClient interface compatibility
- Must support existing embedding providers
- Must work with current CLI command structure
- Must achieve <1s query time for 40K vectors

### Operational Constraints
- No migration tools (fresh re-index required)
- No incremental updates from Qdrant
- Stateless CLI operations (no RAM caching between calls)

## Open Questions

1. **Optimal Depth Factor:** To be determined from POC (2, 3, 4, 6, or 8)
2. **Compression Strategy:** JSON compression vs raw storage trade-offs
3. **Concurrent Access:** File locking strategy for parallel operations

## Acceptance Criteria

1. ✅ Zero containers required for operation
2. ✅ Vector index stored in `.code-indexer/vectors/`
3. ✅ Git-trackable JSON files
4. ✅ Query performance <1s for 40K vectors
5. ✅ Drop-in replacement via `--vector-store filesystem` flag
6. ✅ All existing CLI commands work transparently
7. ✅ Support for VoyageAI and Ollama providers
8. ✅ No chunk text duplication in storage

## Implementation Notes

### Key Design Decisions

1. **Filesystem is Default Backend**
   - **User Requirement:** *"make sure we specify that if the user doesn't specify the db storage subsystem, we default to filesystem, only if the user asks for qdrant, we use qdrant"*
   - `cidx init` → Filesystem backend (NO containers)
   - `cidx init --vector-store qdrant` → Qdrant backend (WITH containers)
   - New users get zero-dependency experience by default
   - Existing projects unaffected (config already specifies provider)

2. **No Chunk Text Storage:** Only store references (file_path, line ranges)

3. **Deterministic Projection:** Reusable projection matrix for consistency

4. **No Fallback to Qdrant:** User: *"no. if we use this, we use this"*

5. **Clean Migration Path:** Destroy, reinit, reindex (no complex migration)

### Performance Optimization Opportunities
1. Parallel JSON file loading
2. Memory-mapped file access
3. Batch vector operations
4. Directory structure caching

## Related Documentation

- Current Qdrant implementation: `/src/code_indexer/services/qdrant.py`
- CLI integration points: `/src/code_indexer/cli.py`
- Configuration system: `/src/code_indexer/config.py`

## Story Details

### Story 0: Proof of Concept - Path Quantization Performance Analysis
**File:** `00_Story_POCPathQuantization.md`

Validate filesystem performance at scale before full implementation. Determine optimal directory depth factor, measure query latency, and confirm <1s performance target for 40K vectors. Go/No-Go decision based on results.

### Story 1: Initialize Filesystem Backend for Container-Free Indexing
**File:** `01_Story_InitializeFilesystemBackend.md`

Create backend abstraction layer supporting both Qdrant and filesystem backends. Implement `cidx init --vector-store filesystem` to initialize container-free vector storage. Backend selection via CLI flag enables drop-in replacement architecture.

### Story 2: Index Code to Filesystem Without Containers
**File:** `02_Story_IndexCodeToFilesystem.md`

Implement complete indexing pipeline: vector quantization (1536→64 dimensions), path-based storage, JSON file creation with file references (no chunk text), and projection matrix management. Supports all embedding providers with proper dimension handling.

### Story 3: Search Indexed Code from Filesystem
**File:** `03_Story_SearchIndexedCode.md`

Implement semantic search with quantized path lookup + exact ranking in RAM. Support accuracy modes (fast/balanced/high), score thresholds, and metadata filtering. Target <1s query latency for 40K vectors.

### Story 4: Monitor Filesystem Index Status and Health
**File:** `04_Story_MonitorIndexStatus.md`

Provide health monitoring, validation, and status reporting for filesystem backend. List indexed files, validate vector dimensions, sample vectors for debugging, and report storage metrics.

### Story 5: Manage Collections and Clean Up Filesystem Index
**File:** `05_Story_ManageCollections.md`

Implement collection management operations: clean collections, delete collections, list collections with metadata. Includes safety confirmations and git-aware cleanup recommendations.

### Story 6: Seamless Start and Stop Operations
**File:** `06_Story_StartStopOperations.md`

Make start/stop operations work transparently for both backends. Filesystem backend returns instant success (no services to start/stop), maintaining consistent CLI interface with Qdrant.

### Story 7: Multi-Provider Support with Filesystem Backend
**File:** `07_Story_MultiProviderSupport.md`

Support multiple embedding providers (VoyageAI, Ollama) with correct vector dimensions. Dynamic projection matrix creation based on provider, proper collection naming, and dimension validation.

### Story 8: Switch Between Qdrant and Filesystem Backends
**File:** `08_Story_SwitchBackends.md`

Enable backend switching via clean-slate approach (destroy, reinit, reindex). No migration tools per user requirement. Includes safety confirmations, git history guidance, and backend comparison documentation.