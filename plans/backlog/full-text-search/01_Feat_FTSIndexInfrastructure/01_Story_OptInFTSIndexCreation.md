# Story: Opt-In FTS Index Creation

## Summary

As a developer using CIDX, I want to build a full-text search index alongside my semantic index using an opt-in flag, so that I can perform fast exact text searches without re-scanning files.

## Acceptance Criteria

1. **Default Behavior Preserved:**
   - `cidx index` continues to build semantic index only (no breaking change)
   - Existing workflows remain unaffected

2. **FTS Opt-In Activation:**
   - `cidx index --fts` builds BOTH semantic and FTS indexes
   - --fts flag properly integrated via Click decorators
   - Clear documentation of flag in --help output

3. **Storage Organization:**
   - FTS index stored in `.code-indexer/tantivy_index/` directory
   - Parallel structure to existing `.code-indexer/index/` semantic storage
   - Proper directory creation with appropriate permissions

4. **Progress Reporting:**
   - Unified progress bar shows both indexing operations
   - Clear indication of which index is being built
   - Accurate file count and processing speed for both

5. **Tantivy Integration:**
   - Tantivy schema properly configured with required fields
   - Segments written correctly to disk
   - Atomic writes to prevent corruption

6. **Metadata Tracking:**
   - Config/metadata indicates FTS index availability
   - Version information stored for future migrations
   - Index creation timestamp recorded

7. **Error Handling:**
   - Graceful failure if Tantivy not installed
   - Clear error messages for permission issues
   - Rollback capability if indexing fails partway

## Technical Implementation Details

### Tantivy Schema
```python
from tantivy import SchemaBuilder, Document, Index

schema_builder = SchemaBuilder()
schema_builder.add_text_field("path", stored=True)
schema_builder.add_text_field("content", tokenizer_name="code")
schema_builder.add_text_field("content_raw", stored=True)
schema_builder.add_text_field("identifiers", tokenizer_name="simple")
schema_builder.add_u64_field("line_start", indexed=True)
schema_builder.add_u64_field("line_end", indexed=True)
schema_builder.add_facet_field("language")
schema = schema_builder.build()
```

### CLI Integration
```python
@click.option('--fts', is_flag=True, help='Build full-text search index alongside semantic index')
def index(fts: bool, ...):
    if fts:
        # Trigger parallel FTS indexing
        run_parallel_indexing(semantic=True, fts=True)
    else:
        # Default semantic-only
        run_semantic_indexing()
```

### Parallel Processing Hook
```python
class FTSIndexer:
    def process_file(self, file_path: Path, content: str, metadata: dict):
        """Process single file for FTS indexing"""
        doc = Document()
        doc.add_text("path", str(file_path))
        doc.add_text("content", content)
        doc.add_text("content_raw", content)
        # Extract identifiers using tree-sitter
        doc.add_text("identifiers", extract_identifiers(content))
        doc.add_u64("line_start", metadata['line_start'])
        doc.add_u64("line_end", metadata['line_end'])
        doc.add_facet("language", f"/lang/{metadata['language']}")
        return doc
```

## Test Scenarios

1. **Default Behavior Test:**
   - Run `cidx index` without --fts flag
   - Verify only semantic index created
   - Verify no tantivy_index directory created

2. **FTS Index Creation Test:**
   - Run `cidx index --fts` on test repository
   - Verify both indexes created successfully
   - Verify correct directory structure
   - Verify Tantivy segments present

3. **Progress Reporting Test:**
   - Monitor progress output during --fts indexing
   - Verify both operations shown
   - Verify accurate counts and speeds

4. **Large Repository Test:**
   - Index repository with 10K+ files using --fts
   - Verify completion within expected time
   - Verify memory usage stays within 1GB limit

5. **Error Recovery Test:**
   - Simulate failure during FTS indexing
   - Verify graceful error handling
   - Verify semantic index unaffected

## Dependencies

- Tantivy Python bindings (v0.25.0)
- Existing FileChunkingManager
- HighThroughputProcessor for parallelization
- RichLiveProgressManager for progress display

## Effort Estimate

- **Development:** 3-4 days
- **Testing:** 2 days
- **Documentation:** 0.5 days
- **Total:** ~5.5 days

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Tantivy installation issues | High | Provide clear installation docs, optional dependency |
| Memory pressure with dual indexing | Medium | Fixed heap size, monitor usage |
| Storage overhead concerns | Medium | Document overhead, compression options |

## Conversation References

- **Opt-in Requirement:** "cidx index builds semantic only (default), cidx index --fts builds both"
- **Storage Location:** "FTS stored in .code-indexer/tantivy_index/"
- **Progress Reporting:** "progress reporting shows both"
- **Metadata Tracking:** "metadata tracks FTS availability"
- **Tantivy Segments:** "uses Tantivy segments"