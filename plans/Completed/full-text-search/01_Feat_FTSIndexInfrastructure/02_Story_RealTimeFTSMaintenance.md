# Story: Real-Time FTS Index Maintenance via Watch Mode

## Summary

As a developer actively coding with CIDX watch mode, I want the FTS index to update automatically when files change, so that my text searches always reflect the current codebase.

## Acceptance Criteria

1. **Watch Mode Default Behavior:**
   - `cidx watch` monitors semantic index only (no breaking change)
   - Existing watch functionality unaffected

2. **FTS Watch Integration:**
   - `cidx watch --fts` monitors BOTH semantic and FTS indexes
   - File changes trigger updates to both indexes in parallel
   - Changes reflected in search within 100ms

3. **Incremental Updates:**
   - Only modified files re-indexed in Tantivy
   - Atomic updates prevent search disruption
   - Proper deletion handling for removed files

4. **Minimal Blocking:**
   - Commit operations complete within 5-50ms
   - Search queries not blocked during updates
   - Write operations use lock-free algorithms where possible

5. **Background Optimization:**
   - Automatic segment merging in background
   - Target 3-5 optimal segments from 10-20 raw segments
   - Merging doesn't impact search performance

6. **Missing Index Handling:**
   - Graceful warning if --fts used but index doesn't exist
   - Option to build FTS index on-the-fly
   - Continue with semantic-only if FTS unavailable

## Technical Implementation Details

### Watch Mode Integration
```python
class FTSWatchHandler:
    def __init__(self, tantivy_index_path: Path):
        self.index = Index.open(str(tantivy_index_path))
        self.writer = self.index.writer(heap_size=1_000_000_000)

    def on_file_modified(self, file_path: Path, content: str):
        """Handle file modification with incremental update"""
        # Delete old version
        self.writer.delete_term("path", str(file_path))

        # Add updated version
        doc = self._create_document(file_path, content)
        self.writer.add_document(doc)

        # Commit with minimal blocking
        self.writer.commit()  # 5-50ms target

    def on_file_deleted(self, file_path: Path):
        """Handle file deletion"""
        self.writer.delete_term("path", str(file_path))
        self.writer.commit()
```

### Adaptive Commit Strategy
```python
class AdaptiveCommitStrategy:
    def __init__(self):
        self.pending_changes = []
        self.last_commit = time.time()

    def should_commit(self) -> bool:
        # Per-file commits in watch mode (5-50ms window)
        if len(self.pending_changes) >= 1:
            return True
        # Time-based commit for low activity
        if time.time() - self.last_commit > 0.05:  # 50ms
            return len(self.pending_changes) > 0
        return False
```

### Background Segment Merging
```python
class BackgroundMerger:
    def __init__(self, index: Index):
        self.index = index
        self.merge_thread = None

    def start_background_merging(self):
        """Run segment merging in background thread"""
        def merge_worker():
            while True:
                segment_count = self.index.segment_count()
                if segment_count > 10:
                    # Merge down to 3-5 segments
                    self.index.merge_segments()
                time.sleep(60)  # Check every minute

        self.merge_thread = Thread(target=merge_worker, daemon=True)
        self.merge_thread.start()
```

### CLI Integration
```python
@click.option('--fts', is_flag=True, help='Monitor and update FTS index alongside semantic')
def watch(fts: bool, ...):
    handlers = [SemanticWatchHandler()]

    if fts:
        if not fts_index_exists():
            if prompt_build_fts():
                build_fts_index()
            else:
                logger.warning("Continuing with semantic-only watch")
        else:
            handlers.append(FTSWatchHandler())

    start_watch_mode(handlers)
```

## Test Scenarios

1. **Basic Watch Test:**
   - Start `cidx watch --fts` with existing indexes
   - Modify a file
   - Verify both indexes updated
   - Search for modified content

2. **Performance Test:**
   - Modify 10 files rapidly
   - Measure update latency (<100ms requirement)
   - Verify all changes searchable

3. **Deletion Test:**
   - Delete files while watch mode active
   - Verify removed from FTS index
   - Confirm search doesn't return deleted files

4. **Missing Index Test:**
   - Run `cidx watch --fts` without FTS index
   - Verify graceful warning
   - Verify semantic watch continues

5. **Segment Merging Test:**
   - Create many file changes (20+ segments)
   - Verify background merging activates
   - Confirm search performance maintained

6. **Concurrent Access Test:**
   - Run searches while watch updates active
   - Verify no search failures
   - Verify consistent results

## Dependencies

- Existing GitAwareWatchHandler
- SmartIndexer for change detection
- Tantivy writer with heap configuration
- Background thread management

## Effort Estimate

- **Development:** 2-3 days
- **Testing:** 1.5 days
- **Documentation:** 0.5 days
- **Total:** ~4 days

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Lock contention during updates | High | Use lock-free algorithms, atomic commits |
| Memory pressure from writer | Medium | Fixed 1GB heap, monitor usage |
| Segment explosion | Medium | Aggressive background merging |
| Search disruption during commit | High | Minimal commit window (5-50ms) |

## Conversation References

- **Watch Integration:** "cidx watch monitors semantic only (default), cidx watch --fts monitors BOTH"
- **Incremental Updates:** "file changes trigger incremental Tantivy updates"
- **Minimal Blocking:** "minimal blocking (5-50ms commits)"
- **Background Merging:** "background segment merging"
- **Graceful Handling:** "graceful handling of missing FTS index"