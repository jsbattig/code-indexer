# Story 3.1: Incremental Indexing

## Story Description

As a CIDX system optimizer, I need to perform incremental semantic indexing on only the files that changed during sync, so that re-indexing completes quickly while maintaining search accuracy and minimizing resource usage.

## Technical Specification

### Incremental Update Strategy

```pseudocode
class IncrementalIndexer:
    def processChanges(changeSet: ChangeSet, index: SemanticIndex):
        # Phase 1: Remove obsolete entries
        for file in changeSet.deleted:
            index.removeEmbeddings(file)
            index.removeDependencies(file)

        # Phase 2: Update modified files
        for file in changeSet.modified:
            oldEmbeddings = index.getEmbeddings(file)
            newEmbeddings = generateEmbeddings(file)
            index.updateEmbeddings(file, newEmbeddings)
            trackDependencies(file)

        # Phase 3: Add new files
        for file in changeSet.added:
            embeddings = generateEmbeddings(file)
            index.addEmbeddings(file, embeddings)
            establishDependencies(file)

        # Phase 4: Update affected dependencies
        affected = calculateAffectedFiles(changeSet)
        updateDependentEmbeddings(affected)

class DependencyTracker:
    imports: Map<FilePath, Set<FilePath>>
    exports: Map<FilePath, Set<FilePath>>
    references: Map<Symbol, Set<FilePath>>

    def calculateAffected(changed: Set<FilePath>) -> Set<FilePath>
    def updateDependencyGraph(file: FilePath) -> void
```

## Acceptance Criteria

### Changed File Detection
```gherkin
Given a sync operation detected file changes
When incremental indexing begins
Then the system should:
  - Load the complete change set
  - Filter files by supported languages
  - Identify files needing re-indexing
  - Skip unchanged files entirely
And process only necessary files
```

### Selective Embedding Updates
```gherkin
Given modified files need re-indexing
When generating new embeddings
Then the system should:
  - Remove old embeddings from vector DB
  - Generate new embeddings for content
  - Preserve file metadata and history
  - Update embeddings atomically
And maintain index consistency
```

### Dependency Tracking
```gherkin
Given a file has been modified
When checking for dependencies
Then the system should:
  - Identify files importing this file
  - Find files this file imports
  - Track symbol references
  - Mark dependent files for update
And update the dependency graph
```

### Index Consistency
```gherkin
Given incremental updates are applied
When validating index state
Then the system should ensure:
  - No orphaned embeddings exist
  - All file references are valid
  - Dependency graph is complete
  - Search results remain accurate
And report any inconsistencies
```

### Performance Optimization
```gherkin
Given a large number of changes
When processing incrementally
Then the system should:
  - Batch embedding operations
  - Use parallel processing
  - Cache frequently accessed data
  - Minimize database round trips
And complete within performance targets
```

## Completion Checklist

- [ ] Changed file detection
  - [ ] Parse change set from git
  - [ ] Filter by file types
  - [ ] Build processing queue
  - [ ] Skip ignored patterns
- [ ] Selective embedding updates
  - [ ] Remove old embeddings
  - [ ] Generate new embeddings
  - [ ] Atomic updates to vector DB
  - [ ] Preserve metadata
- [ ] Dependency tracking
  - [ ] Parse import statements
  - [ ] Build dependency graph
  - [ ] Identify affected files
  - [ ] Update graph incrementally
- [ ] Index consistency
  - [ ] Validate after updates
  - [ ] Check referential integrity
  - [ ] Verify search quality
  - [ ] Report metrics

## Test Scenarios

### Happy Path
1. Single file change → Update one file → Index consistent
2. Multiple changes → Batch processing → All updated
3. With dependencies → Dependencies updated → Graph accurate
4. Large changeset → Parallel processing → Completes quickly

### Error Cases
1. Embedding fails → Retry with backoff → Eventually succeeds
2. Vector DB down → Queue changes → Process when available
3. Corrupt file → Skip with warning → Continue processing
4. Memory pressure → Switch to streaming → Completes slowly

### Edge Cases
1. File renamed → Update references → Links preserved
2. Circular dependencies → Detect cycle → Process once
3. Binary file changed → Skip embedding → Log as skipped
4. Massive file → Chunk processing → Handle gracefully

## Performance Requirements

- Process 100 changed files: <10 seconds
- Process 1000 changed files: <60 seconds
- Memory usage: <500MB for typical operation
- Parallel threads: min(CPU_cores, 8)
- Batch size: 50 files per batch

## Dependency Analysis

### Import Pattern Detection
```pseudocode
Language-specific patterns:
- Python: import X, from X import Y
- JavaScript: import X from 'Y', require('X')
- Java: import com.example.X
- Go: import "package/path"
- C++: #include "header.h"
```

### Dependency Impact Levels
| Level | Description | Action |
|-------|-------------|--------|
| Direct | File directly imports changed file | Must re-index |
| Transitive | Imports file that imports changed | Consider re-index |
| Symbol | References exported symbol | Check if symbol changed |
| None | No dependency relationship | No action needed |

## Incremental Update Metrics

```yaml
metrics:
  performance:
    files_per_second: 10
    embeddings_per_second: 100
    batch_efficiency: 0.85
  quality:
    search_accuracy_maintained: 0.99
    index_consistency: 1.0
    dependency_accuracy: 0.95
  resource:
    memory_usage_mb: 200-500
    cpu_utilization: 0.6-0.8
    io_operations: minimized
```

## Definition of Done

- [ ] Incremental indexing processes only changed files
- [ ] Embeddings updated atomically in vector DB
- [ ] Dependency graph maintained accurately
- [ ] Index consistency validated after updates
- [ ] Performance targets achieved
- [ ] Parallel processing implemented
- [ ] Error handling with retry logic
- [ ] Unit tests >90% coverage
- [ ] Integration tests with real repositories
- [ ] Metrics collection implemented