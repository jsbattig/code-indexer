# Story 3.2: Full Re-indexing

## Story Description

As a CIDX system administrator, I need the ability to perform complete re-indexing of repositories when incremental updates are insufficient, ensuring the semantic index is fully rebuilt while minimizing downtime and maintaining service availability.

## Technical Specification

### Full Re-index Triggers

```pseudocode
class ReindexTriggerAnalyzer:
    def shouldFullReindex(changes: ChangeSet, metrics: IndexMetrics) -> bool:
        triggers = [
            changes.percentageChanged > 0.3,        # >30% files changed
            changes.hasStructuralChanges,           # Major refactoring
            metrics.searchAccuracy < 0.8,           # Quality degraded
            metrics.indexAge > 30_days,             # Periodic refresh
            changes.hasSchemaChanges,               # Index format updated
            metrics.corruptionDetected,             # Integrity issues
            userRequestedFullReindex                # Manual trigger
        ]
        return any(triggers)

class FullReindexStrategy:
    BLUE_GREEN    # Zero-downtime with swap
    IN_PLACE      # Direct replacement
    PROGRESSIVE   # Gradual migration
```

### Blue-Green Indexing

```pseudocode
class BlueGreenIndexer:
    def reindex(repo: Repository, currentIndex: Index):
        # Create new index alongside existing
        newIndex = createShadowIndex()

        # Build new index while old serves queries
        buildCompleteIndex(repo, newIndex)

        # Validate new index
        if validateIndex(newIndex):
            # Atomic swap
            swapIndexes(currentIndex, newIndex)
            # Cleanup old index after grace period
            scheduleCleanup(currentIndex, delay=1_hour)
        else:
            rollback(newIndex)
```

## Acceptance Criteria

### Trigger Conditions
```gherkin
Given repository changes have been analyzed
When evaluating re-index triggers
Then the system should check:
  - Percentage of files changed (>30%)
  - Structural refactoring detected
  - Search quality metrics degraded
  - Index age exceeds threshold
  - Manual re-index requested
And trigger full re-index if conditions met
```

### Efficient Processing
```gherkin
Given full re-index is triggered
When processing the repository
Then the system should:
  - Scan all repository files
  - Filter by supported languages
  - Process in optimized batches
  - Use parallel processing
  - Report progress continuously
And complete within time limits
```

### Progress Tracking
```gherkin
Given full re-index is running
When progress updates occur
Then the system should report:
  - Files processed / total files
  - Current processing rate
  - Estimated time remaining
  - Memory and CPU usage
  - Current processing phase
And update every 1 second
```

### Zero-Downtime Updates
```gherkin
Given blue-green indexing is enabled
When performing full re-index
Then the system should:
  - Create shadow index
  - Build new index in background
  - Keep old index serving queries
  - Atomically swap when ready
  - Maintain service availability
And ensure zero query downtime
```

### Validation & Rollback
```gherkin
Given new index has been built
When validating before swap
Then the system should verify:
  - Document count matches expected
  - Sample queries return results
  - Embedding dimensions correct
  - No corruption detected
And rollback if validation fails
```

## Completion Checklist

- [ ] Trigger conditions
  - [ ] Change percentage calculation
  - [ ] Structural change detection
  - [ ] Quality metric monitoring
  - [ ] Age-based triggers
  - [ ] Manual trigger API
- [ ] Efficient processing
  - [ ] File scanning optimization
  - [ ] Batch processing logic
  - [ ] Parallel execution
  - [ ] Memory management
  - [ ] Progress reporting
- [ ] Progress tracking
  - [ ] Real-time metrics
  - [ ] Rate calculation
  - [ ] Time estimation
  - [ ] Resource monitoring
- [ ] Zero-downtime updates
  - [ ] Blue-green implementation
  - [ ] Shadow index creation
  - [ ] Atomic swap mechanism
  - [ ] Grace period cleanup

## Test Scenarios

### Happy Path
1. Trigger met → Full re-index → New index ready → Swap → Success
2. Large repo → Batched processing → Progress shown → Completes
3. Blue-green → Shadow built → Validated → Swapped → No downtime
4. Progressive → Chunks migrated → Verified → Complete migration

### Error Cases
1. Out of memory → Switch to streaming → Continues slowly
2. Embedding service down → Retry with backoff → Eventually completes
3. Validation fails → Automatic rollback → Old index preserved
4. Disk full → Cleanup and retry → Completes with space

### Edge Cases
1. Empty repository → Handle gracefully → Empty index created
2. Huge repository (>100k files) → Chunked approach → Completes
3. Binary-only repo → Skip all files → Empty index with metadata
4. Concurrent modifications → Lock repository → Process snapshot

## Performance Requirements

- Small repo (<1k files): <1 minute
- Medium repo (1k-10k files): <5 minutes
- Large repo (10k-50k files): <15 minutes
- Huge repo (>50k files): <30 minutes
- Memory usage: <1GB typical, <2GB maximum
- CPU utilization: 60-80% during processing

## Re-indexing Strategies

### Blue-Green (Recommended)
```
Advantages:
- Zero downtime
- Safe rollback
- A/B testing possible

Disadvantages:
- 2x storage temporarily
- Complex implementation
```

### In-Place
```
Advantages:
- Simple implementation
- Minimal storage

Disadvantages:
- Service disruption
- No rollback option
```

### Progressive
```
Advantages:
- Gradual migration
- Resource spreading

Disadvantages:
- Complex consistency
- Longer total time
```

## Progress Reporting Format

```json
{
  "phase": "SCANNING | PROCESSING | VALIDATING | SWAPPING",
  "progress": {
    "filesProcessed": 1234,
    "totalFiles": 5000,
    "percentage": 24.68,
    "rate": 45.2,  // files per second
    "eta": 105      // seconds remaining
  },
  "resources": {
    "memoryMB": 487,
    "cpuPercent": 72,
    "diskIOps": 1250
  },
  "status": "Processing source files..."
}
```

## Validation Criteria

| Check | Threshold | Action on Failure |
|-------|-----------|-------------------|
| Document count | ±5% of expected | Investigate discrepancy |
| Sample queries | 95% return results | Rollback |
| Embedding dims | Must match exactly | Fatal error |
| Corruption check | 0 corrupted entries | Rollback |
| Performance test | <2x slower | Warning only |

## Definition of Done

- [ ] All trigger conditions detected accurately
- [ ] Full re-indexing completes successfully
- [ ] Blue-green deployment works with zero downtime
- [ ] Progress reporting at 1Hz frequency
- [ ] Validation ensures index quality
- [ ] Rollback mechanism tested
- [ ] Performance targets met
- [ ] Unit tests >90% coverage
- [ ] Integration tests with large repos
- [ ] Load tests verify scalability